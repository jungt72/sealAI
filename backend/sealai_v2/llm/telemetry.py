"""Safe per-call LLM telemetry (Phase 1 of the LangGraph-suitability audit).

Audit finding: prompt-cache effectiveness and per-call cost were unmeasurable — ``cached_tokens``
was never extracted, and no cost/cache-ratio telemetry existed on the live request path (only the
offline eval harness had a token meter, ``eval/metering.py``). This module defines the SAFE fields
that may be recorded for every LLM call and a sink protocol so ``llm.client`` can emit them without
depending on any concrete backend (log line, metrics registry, test spy, ...).

Hard rule (mirrors the LangSmith safe-tracing doctrine in ``obs.safe_trace``): this structure NEVER
carries raw prompt/message text, raw user/assistant content, tenant_id, case_id, file names, or
media names. Only counts, ratios, labels, and opaque hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class LlmCallTelemetry:
    """Safe observability record for one LLM call. Every field here is a count, a ratio, a short
    label, or an opaque hash — never raw content. See the module docstring for the excluded fields."""

    provider: str
    model: str
    stage: str | None
    prompt_cache_key: str | None
    prompt_hash: str | None
    prompt_tokens: int
    cached_tokens: int
    completion_tokens: int
    total_tokens: int
    cache_ratio: float
    latency_ms: float
    status: str  # "ok" | "error"
    error_type: str | None = None


@runtime_checkable
class TelemetrySink(Protocol):
    """Structural type for anything that can receive an ``LlmCallTelemetry`` event (a logger
    adapter, a metrics registry, a test spy, ...). Implementations must not raise — the call site
    (``llm.client.OpenAiLlmClient.generate``) invokes this inside a try/except regardless, so a
    telemetry bug can never break a real LLM call, but a well-behaved sink should be safe on its
    own too."""

    def record(self, event: LlmCallTelemetry) -> None: ...


class LoggingTelemetrySink:
    """Default sink: one structured log line per LLM call via the standard ``logging`` module — no
    new dependency, no external network call, and it can never change pipeline behavior (a logging
    failure is swallowed by the call site's own try/except in ``OpenAiLlmClient._emit_telemetry``).
    Makes cache/cost telemetry actually observable (grep the logs / ship to whatever log
    aggregation already exists) without requiring a metrics backend to be wired first."""

    def __init__(self, logger_name: str = "sealai_v2.llm.telemetry") -> None:
        import logging

        self._logger = logging.getLogger(logger_name)

    def record(self, event: LlmCallTelemetry) -> None:
        self._logger.info(
            "llm_call provider=%s model=%s stage=%s cache_key=%s prompt_tokens=%d "
            "cached_tokens=%d completion_tokens=%d total_tokens=%d cache_ratio=%.3f "
            "latency_ms=%.1f status=%s error_type=%s",
            event.provider,
            event.model,
            event.stage,
            event.prompt_cache_key,
            event.prompt_tokens,
            event.cached_tokens,
            event.completion_tokens,
            event.total_tokens,
            event.cache_ratio,
            event.latency_ms,
            event.status,
            event.error_type,
        )
