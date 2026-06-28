"""Async OpenAI Chat-Completions adapter — implements ``core.LlmClient``.

Param-defensive across model families (strips an unsupported ``temperature``; adapts the
max-tokens param name) and retries transient failures with bounded backoff. Holds a
pre-constructed ``AsyncOpenAI`` instance (built by ``llm.factory``); it does not import the
``openai`` package itself, so this module stays import-light.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sealai_v2.core.contracts import LlmResult, ModelConfig, TokenUsage


def _parse_usage(resp: Any) -> TokenUsage | None:
    """Read the provider's token usage defensively (OpenAI + OpenAI-compatible Mistral both expose
    ``resp.usage.{prompt,completion,total}_tokens``). Absent/partial → best-effort/None, never raises."""
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    return TokenUsage(
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
    )


class OpenAiLlmClient:
    def __init__(
        self,
        async_client: Any,
        *,
        timeout_s: float = 180.0,  # i5-ok: Transport-Timeout
        max_retries: int = 3,
    ) -> None:
        self._client = async_client
        self._timeout_s = timeout_s
        self._max_retries = max(1, max_retries)

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
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

        last_exc: Exception | None = None
        attempts = 0  # counts only REAL (transient) failures — param adaptations don't consume budget
        while attempts < self._max_retries:
            try:
                resp = await self._client.chat.completions.create(
                    timeout=self._timeout_s, **kwargs
                )
                choice = resp.choices[0]
                return LlmResult(
                    text=choice.message.content or "",
                    model=getattr(resp, "model", model_config.model),
                    finish_reason=getattr(choice, "finish_reason", None),
                    usage=_parse_usage(resp),
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
        raise last_exc
