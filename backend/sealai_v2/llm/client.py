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

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
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
                # Strip/adapt unsupported params and retry immediately (model-family drift).
                if "temperature" in msg and "temperature" in kwargs:
                    kwargs.pop("temperature", None)
                    continue
                if (
                    "max_completion_tokens" in msg or "max_tokens" in msg
                ) and "max_completion_tokens" in kwargs:
                    kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
                    continue
                last_exc = exc
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(min(2.0**attempt, 8.0))  # i5-ok: Retry-Backoff
        assert last_exc is not None
        raise last_exc
