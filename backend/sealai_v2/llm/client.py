"""Async OpenAI Chat-Completions adapter — implements ``core.LlmClient``.

Param-defensive across model families (strips an unsupported ``temperature``; adapts the
max-tokens param name) and retries transient failures with bounded backoff. Holds a
pre-constructed ``AsyncOpenAI`` instance (built by ``llm.factory``); it does not import the
``openai`` package itself, so this module stays import-light.

Phase 1 (LangGraph-suitability audit, telemetry): extracts ``cached_tokens`` when the provider
exposes it and emits a safe ``LlmCallTelemetry`` event per call via an optional, injected
``TelemetrySink`` — fully inert (zero behavior/latency-relevant change) when no sink is wired, which
is the default for every existing call site.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

from sealai_v2.core.contracts import (
    LlmResult,
    LlmStreamEvent,
    ModelConfig,
    TokenUsage,
)
from sealai_v2.llm.telemetry import LlmCallTelemetry, TelemetrySink


def _parse_usage(resp: Any) -> TokenUsage | None:
    """Read the provider's token usage defensively (OpenAI + OpenAI-compatible Mistral both expose
    ``resp.usage.{prompt,completion,total}_tokens``). Absent/partial → best-effort/None, never raises.

    ``cached_tokens`` (Phase 1): both OpenAI and Mistral expose prompt-cache hits at
    ``usage.prompt_tokens_details.cached_tokens``. Missing (older response shape, a provider that
    doesn't support caching, or an offline fake) → 0, never raises — the caller's ``cache_ratio``
    then safely reads as 0.0."""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    details = getattr(usage, "prompt_tokens_details", None)
    cached = (
        int(getattr(details, "cached_tokens", 0) or 0) if details is not None else 0
    )
    return TokenUsage(
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        cached_tokens=cached,
    )


class OpenAiLlmClient:
    def __init__(
        self,
        async_client: Any,
        *,
        timeout_s: float = 180.0,  # i5-ok: Transport-Timeout
        max_retries: int = 3,
        provider: str = "unknown",
        telemetry_sink: TelemetrySink | None = None,
    ) -> None:
        self._client = async_client
        self._timeout_s = timeout_s
        self._max_retries = max(1, max_retries)
        self._provider = provider
        self._telemetry_sink = telemetry_sink

    def _emit_telemetry(
        self,
        *,
        model_config: ModelConfig,
        usage: TokenUsage | None,
        latency_ms: float,
        status: str,
        error_type: str | None,
    ) -> None:
        """Build + emit a safe ``LlmCallTelemetry`` event. Never raises into the caller — a
        telemetry bug (or a misbehaving sink) must never break a real LLM call or mask a real
        exception. No-op when no sink is wired (the default for every existing call site)."""
        if self._telemetry_sink is None:
            return
        try:
            u = usage or TokenUsage()
            self._telemetry_sink.record(
                LlmCallTelemetry(
                    provider=self._provider,
                    model=model_config.model,
                    stage=model_config.stage,
                    prompt_cache_key=model_config.cache_key,
                    prompt_hash=None,
                    prompt_tokens=u.prompt_tokens,
                    cached_tokens=u.cached_tokens,
                    completion_tokens=u.completion_tokens,
                    total_tokens=u.total_tokens,
                    cache_ratio=u.cache_ratio,
                    latency_ms=latency_ms,
                    status=status,
                    error_type=error_type,
                )
            )
        except Exception:  # noqa: BLE001 — telemetry must never break or mask a real call/error
            pass

    def _build_request_kwargs(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> dict[str, Any]:
        """The shared Chat-Completions request kwargs for BOTH ``generate`` and ``generate_stream``
        -- identical model / system+user / temperature / max-tokens / prompt-cache construction, so
        the two paths can never drift. The streaming path layers ``stream``/``stream_options`` on
        top of this (see ``generate_stream``)."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict[str, Any] = {"model": model_config.model, "messages": messages}
        if model_config.temperature is not None:
            kwargs["temperature"] = model_config.temperature
        if model_config.max_output_tokens is not None:
            kwargs["max_completion_tokens"] = model_config.max_output_tokens
        if model_config.cache_key is not None:
            # Mistral/OpenAI prompt caching: opt-in via a stable key; the doctrine prefix then
            # bills at 10% on cache hits. extra_body passes through regardless of SDK version.
            kwargs["extra_body"] = {"prompt_cache_key": model_config.cache_key}
        return kwargs

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        kwargs = self._build_request_kwargs(
            system=system, user=user, model_config=model_config
        )

        started = time.monotonic()
        last_exc: Exception | None = None
        attempts = 0  # counts only REAL (transient) failures — param adaptations don't consume budget
        while attempts < self._max_retries:
            try:
                resp = await self._client.chat.completions.create(
                    timeout=self._timeout_s, **kwargs
                )
                choice = resp.choices[0]
                usage = _parse_usage(resp)
                self._emit_telemetry(
                    model_config=model_config,
                    usage=usage,
                    latency_ms=(time.monotonic() - started)
                    * 1000.0,  # i5-ok: sec->ms unit conversion, not an engineering value
                    status="ok",
                    error_type=None,
                )
                return LlmResult(
                    text=choice.message.content or "",
                    model=getattr(resp, "model", model_config.model),
                    finish_reason=getattr(choice, "finish_reason", None),
                    usage=usage,
                )
            except Exception as exc:  # noqa: BLE001 — param-defensive + transient retry, then re-raise
                msg = str(exc).lower()
                # ONE-TIME param adaptations (model-family drift): strip/rename + retry WITHOUT consuming
                # the transient-retry budget. Each branch is guarded by "param in kwargs", so it fires at
                # most once (the next identical error falls through) — bounded, no infinite loop, and the
                # old `assert last_exc is not None` can no longer trip when params eat all attempts.
                if "temperature" in msg and "temperature" in kwargs:
                    kwargs.pop("temperature", None)
                    continue
                if "prompt_cache_key" in msg and "extra_body" in kwargs:
                    kwargs.pop("extra_body", None)
                    continue
                if (
                    "max_completion_tokens" in msg or "max_tokens" in msg
                ) and "max_completion_tokens" in kwargs:
                    kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
                    continue
                last_exc = exc
                attempts += 1
                if attempts < self._max_retries:
                    backoff = min(2.0 ** (attempts - 1), 8.0)  # i5-ok: Retry-Backoff
                    await asyncio.sleep(backoff)
        assert (
            last_exc is not None
        )  # loop only exits here after a real failure incremented attempts
        self._emit_telemetry(
            model_config=model_config,
            usage=None,
            latency_ms=(time.monotonic() - started)
            * 1000.0,  # i5-ok: sec->ms unit conversion, not an engineering value
            status="error",
            error_type=type(last_exc).__name__,
        )
        raise last_exc

    async def generate_stream(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> AsyncIterator[LlmStreamEvent]:
        """Stream the SAME Chat-Completions call as ``generate`` token-by-token (Phase 3A). Yields an
        ``LlmStreamEvent(delta=...)`` per content fragment as it arrives, then EXACTLY ONE terminal
        ``LlmStreamEvent(result=...)`` carrying the fully accumulated text + finish_reason + usage
        (parsed from the final ``stream_options={"include_usage": True}`` chunk -- confirmed present
        for OpenAI + OpenAI-compatible Mistral).

        Failure model: a mid-stream exception PROPAGATES unchanged -- no synthetic/partial terminal
        event is ever synthesized (a failed stream is a failed call, identical to a failed
        ``generate``). The param-defensive unwind (strip an unsupported ``temperature`` /
        ``prompt_cache_key`` / rename ``max_completion_tokens``) is applied ONLY on the FIRST attempt,
        BEFORE any delta has been yielded: once a token has crossed the wire the request cannot be
        transparently retried from scratch without duplicating already-sent tokens, so any failure
        after the first yielded delta simply propagates. Transient-retry backoff is deliberately NOT
        applied here for the same reason (a partial stream is not safely resumable)."""
        base_kwargs = self._build_request_kwargs(
            system=system, user=user, model_config=model_config
        )
        base_kwargs["stream"] = True
        base_kwargs["stream_options"] = {"include_usage": True}
        started = time.monotonic()
        kwargs = dict(base_kwargs)
        yielded_any = False
        while True:
            buffer: list[str] = []
            model_name = model_config.model
            finish_reason: str | None = None
            usage: TokenUsage | None = None
            try:
                stream = await self._client.chat.completions.create(
                    timeout=self._timeout_s, **kwargs
                )
                async for chunk in stream:
                    model_name = getattr(chunk, "model", None) or model_name
                    choices = getattr(chunk, "choices", None) or []
                    if choices:
                        choice0 = choices[0]
                        fr = getattr(choice0, "finish_reason", None)
                        if fr is not None:
                            finish_reason = fr
                        delta = getattr(
                            getattr(choice0, "delta", None), "content", None
                        )
                        if delta:
                            buffer.append(delta)
                            yielded_any = True
                            yield LlmStreamEvent(delta=delta)
                    # The final chunk (include_usage) carries usage, typically with empty choices.
                    if getattr(chunk, "usage", None) is not None:
                        usage = _parse_usage(chunk)
                break
            except Exception as exc:  # noqa: BLE001 — param-defensive ONCE, else propagate
                if not yielded_any:
                    msg = str(exc).lower()
                    # ONE-TIME param adaptations (model-family drift), mirroring generate(); each is
                    # guarded by "param in kwargs" so it fires at most once. Only reachable before the
                    # first delta -- see the docstring for why a post-first-token failure can't retry.
                    if "temperature" in msg and "temperature" in kwargs:
                        kwargs.pop("temperature", None)
                        continue
                    if "prompt_cache_key" in msg and "extra_body" in kwargs:
                        kwargs.pop("extra_body", None)
                        continue
                    if (
                        "max_completion_tokens" in msg or "max_tokens" in msg
                    ) and "max_completion_tokens" in kwargs:
                        kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
                        continue
                self._emit_telemetry(
                    model_config=model_config,
                    usage=None,
                    latency_ms=(time.monotonic() - started)
                    * 1000.0,  # i5-ok: sec->ms unit conversion, not an engineering value
                    status="error",
                    error_type=type(exc).__name__,
                )
                raise
        final = LlmResult(
            text="".join(buffer),
            model=model_name,
            finish_reason=finish_reason,
            usage=usage,
        )
        self._emit_telemetry(
            model_config=model_config,
            usage=usage,
            latency_ms=(time.monotonic() - started)
            * 1000.0,  # i5-ok: sec->ms unit conversion, not an engineering value
            status="ok",
            error_type=None,
        )
        yield LlmStreamEvent(result=final)
