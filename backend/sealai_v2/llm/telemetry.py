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

from prometheus_client import Counter, Histogram

from sealai_v2.obs.log_redaction import (
    opaque_reference,
    safe_code_or_placeholder,
)
from sealai_v2.obs.telemetry_sampling import (
    resolve_telemetry_sample_rate,
    should_sample,
)

_LLM_CALLS = Counter(
    "sealai_v2_llm_calls_total",
    "LLM calls observed by the V2 runtime.",
    ("provider", "model", "stage", "status"),
)
_LLM_TOKENS = Counter(
    "sealai_v2_llm_tokens_total",
    "LLM tokens observed by the V2 runtime.",
    ("provider", "model", "stage", "token_type"),
)
_LLM_LATENCY = Histogram(
    "sealai_v2_llm_call_duration_seconds",
    "LLM call wall time in seconds.",
    ("provider", "model", "stage", "status"),
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 180),
)
_LLM_FAILURES = Counter(
    "sealai_v2_llm_failures_total",
    "Bounded LLM failure categories observed by the V2 runtime.",
    ("provider", "model", "stage", "category"),
)

# Publish zero-valued sentinels so an idle but correctly instrumented process
# does not look the same as a process where the required metric families were
# never registered. Real observations always use their bounded real labels.
_LLM_CALLS.labels("none", "none", "none", "ok").inc(0)
_LLM_FAILURES.labels("none", "none", "none", "provider").inc(0)


def _metric_label(value: str | None) -> str:
    safe = safe_code_or_placeholder(value, placeholder="none").value
    return safe[:96]


def _failure_category(error_type: str | None) -> str:
    """Collapse provider exception class names into a fixed metric-label allowlist."""
    normalized = (error_type or "").replace("_", "").lower()
    if "timeout" in normalized or "timedout" in normalized:
        return "timeout"
    if "ratelimit" in normalized or "toomanyrequests" in normalized:
        return "rate_limit"
    if "authentication" in normalized or "permission" in normalized:
        return "auth"
    if "connection" in normalized or "transport" in normalized:
        return "transport"
    return "provider"


def _record_metrics(event: "LlmCallTelemetry") -> None:
    provider = _metric_label(event.provider)
    model = _metric_label(event.model)
    stage = _metric_label(event.stage)
    status = _metric_label(event.status)
    _LLM_CALLS.labels(provider, model, stage, status).inc()
    for token_type, count in (
        ("prompt", event.prompt_tokens),
        ("cached", event.cached_tokens),
        ("completion", event.completion_tokens),
    ):
        _LLM_TOKENS.labels(provider, model, stage, token_type).inc(max(0, count))
    _LLM_LATENCY.labels(provider, model, stage, status).observe(
        max(0.0, event.latency_ms / 1000.0)
    )
    if event.status != "ok":
        _LLM_FAILURES.labels(
            provider,
            model,
            stage,
            _failure_category(event.error_type),
        ).inc()


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

    def __init__(
        self,
        logger_name: str = "sealai_v2.llm.telemetry",
        *,
        sample_rate: float | None = None,
    ) -> None:
        import logging

        self._logger = logging.getLogger(logger_name)
        self._sample_rate = (
            resolve_telemetry_sample_rate()
            if sample_rate is None
            else resolve_telemetry_sample_rate(str(sample_rate))
        )

    def record(self, event: LlmCallTelemetry) -> None:
        try:
            _record_metrics(event)
        except Exception:  # noqa: BLE001 - metrics must never affect an LLM call
            pass
        if event.status != "error" and not should_sample(self._sample_rate):
            return
        self._logger.info(
            "llm_call provider=%s model=%s stage=%s cache_key=%s prompt_tokens=%d "
            "cached_tokens=%d completion_tokens=%d total_tokens=%d cache_ratio=%.3f "
            "latency_ms=%.1f status=%s error_type=%s",
            safe_code_or_placeholder(event.provider),
            safe_code_or_placeholder(event.model),
            safe_code_or_placeholder(event.stage, placeholder="none"),
            (
                opaque_reference("prompt_cache", event.prompt_cache_key)
                if event.prompt_cache_key
                else safe_code_or_placeholder(None, placeholder="none")
            ),
            event.prompt_tokens,
            event.cached_tokens,
            event.completion_tokens,
            event.total_tokens,
            event.cache_ratio,
            event.latency_ms,
            safe_code_or_placeholder(event.status),
            safe_code_or_placeholder(event.error_type, placeholder="none"),
        )
