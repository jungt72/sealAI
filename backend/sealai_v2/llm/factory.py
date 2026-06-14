"""Build the concrete LLM client(s) + resolve model tiers (provider-agnostic seam).

``openai`` is imported lazily here only — keeping the SDK off the import/CI path. Mistral is
OpenAI-API-compatible, so it runs through the SAME ``OpenAiLlmClient`` adapter via a different
``base_url`` + key — a new provider is a config entry here, not a new client class.

Per-role routing: ``build_client_factory`` returns a ``client_for(provider)`` that builds (once,
cached per provider) the right client, so a mixed cell (L1=mistral, L3=openai) is a pure config
flip. Unknown provider / missing key → fail closed (raise), never a silent default.
"""

from __future__ import annotations

import os
from collections.abc import Callable

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


def _resolve_provider(settings: Settings, provider: str) -> tuple[str | None, str]:
    """Pure resolve step (no SDK construction → offline-testable): map a provider name to its
    ``(base_url, api_key)``. Fail closed on an unknown provider or a missing key — never a silent
    default. Key VALUES are returned for client construction only; never logged."""
    if provider == "openai":
        base_url = settings.openai_base_url
        key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        key_env = "OPENAI_API_KEY"
    elif provider == "mistral":
        base_url = settings.mistral_base_url
        key = settings.mistral_api_key or os.getenv("MISTRAL_API_KEY")
        key_env = "MISTRAL_API_KEY"
    else:
        raise RuntimeError(
            f"unsupported provider {provider!r} — known providers: 'openai', 'mistral'. "
            "Add a resolve entry + (if non-OpenAI-compatible) an adapter; never default silently."
        )
    if not key:
        raise RuntimeError(
            f"{key_env} not set — required for the live measurement with provider {provider!r} "
            "(offline tests use a fake client, no key needed)."
        )
    return base_url, key


def _async_openai_compatible(settings: Settings, provider: str):
    """Construct the lazily-imported AsyncOpenAI SDK client pointed at ``provider``'s endpoint.
    Resolve FIRST so an unknown provider / missing key fails closed WITHOUT importing the SDK."""
    base_url, key = _resolve_provider(settings, provider)
    from openai import AsyncOpenAI  # lazy — keep the SDK at the I/O edge

    return AsyncOpenAI(api_key=key, base_url=base_url)


def build_client_for(settings: Settings, provider: str) -> LlmClient:
    """One concrete client for one provider (OpenAI-compatible adapter; Mistral reuses it)."""
    return OpenAiLlmClient(
        _async_openai_compatible(settings, provider),
        timeout_s=settings.request_timeout_s,
        max_retries=settings.max_retries,
    )


def build_client_factory(settings: Settings) -> Callable[[str], LlmClient]:
    """Return ``client_for(provider)``: builds each provider's client at most once and caches it,
    so an all-``openai`` run shares ONE client across every role (byte-identical to the single-client
    path). A mixed cell gets one client per distinct provider. Unknown provider → raises on first use."""
    cache: dict[str, LlmClient] = {}

    def client_for(provider: str) -> LlmClient:
        if provider not in cache:
            cache[provider] = build_client_for(settings, provider)
        return cache[provider]

    return client_for


def build_llm_client(settings: Settings) -> LlmClient:
    """Back-compat single client for the global ``provider`` (deps/eval default path)."""
    return build_client_for(settings, settings.provider)


async def resolve_l1_model(settings: Settings, preferred: str | None = None) -> str:
    """Pick the L1 model. For the OpenAI provider: honor an explicit choice, else rank
    ``models.list()`` by ``_L1_PREFERENCE``, else the lexicographically-last ``gpt-*``. For any
    non-OpenAI provider, return the CONFIGURED ``l1_model`` verbatim — a candidate cell names its
    model explicitly, and ``models.list()`` against a foreign account must not gate it."""
    l1_provider = settings.l1_provider or settings.provider
    if l1_provider != "openai":
        return preferred or settings.l1_model
    client = _async_openai_compatible(settings, "openai")
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
