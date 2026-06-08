"""Build the concrete LLM client + resolve model tiers (provider-agnostic seam).

``openai`` is imported lazily here only — keeping the SDK off the import/CI path. M1 ships the
OpenAI provider; swapping providers is a config change plus another adapter, not a rewrite.
"""

from __future__ import annotations

import os

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import LlmClient
from sealai_v2.llm.client import OpenAiLlmClient

# Strongest-first preference for resolving L1 when the configured id is not on the account.
_L1_PREFERENCE: tuple[str, ...] = (
    "gpt-5.1",
    "gpt-5",
    "gpt-5-pro",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4o",
    "gpt-4.1-mini",
    "gpt-4o-mini",
)


def _resolve_key(settings: Settings) -> str:
    key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not set — required for the live measurement "
            "(offline tests use a fake client, no key needed)."
        )
    return key


def _async_openai(settings: Settings):
    from openai import AsyncOpenAI  # lazy — keep the SDK at the I/O edge

    return AsyncOpenAI(
        api_key=_resolve_key(settings), base_url=settings.openai_base_url
    )


def build_llm_client(settings: Settings) -> LlmClient:
    if settings.provider != "openai":
        raise RuntimeError(
            f"unsupported provider {settings.provider!r} — M1 ships OpenAI; "
            "the adapter is provider-agnostic by design."
        )
    return OpenAiLlmClient(
        _async_openai(settings),
        timeout_s=settings.request_timeout_s,
        max_retries=settings.max_retries,
    )


async def resolve_l1_model(settings: Settings, preferred: str | None = None) -> str:
    """Pick the strongest available GPT for L1: honor an explicit choice, else rank
    ``models.list()`` by ``_L1_PREFERENCE``, else the lexicographically-last ``gpt-*``."""
    client = _async_openai(settings)
    available = {m.id for m in (await client.models.list()).data}
    choice = preferred or settings.l1_model
    if choice in available:
        return choice
    for cand in _L1_PREFERENCE:
        if cand in available:
            return cand
    gpts = sorted(m for m in available if m.startswith("gpt-"))
    if gpts:
        return gpts[-1]
    raise RuntimeError("no GPT chat model available on this OpenAI account")
