"""Phase 2B/2D (LangGraph-suitability audit) — safe route-decision telemetry.

Mirrors the ``llm.telemetry`` pattern from Phase 1: a frozen, safe-fields-only dataclass + a sink
Protocol + a default log-only sink. Never carries raw user text, tenant_id, case_id, exact medium
names, file names, or sensitive parameters — only the route label, a short machine reason string,
a confidence float, booleans, a signal count, and a latency in ms.

Phase 2D adds two OPTIONAL fields (``prompt_family``, ``l3_bypassed``), both defaulted so every
existing Phase 2B/2C call site stays byte-identical without passing them. Per-call LLM telemetry
(model, prompt_hash via the cache key, cached_tokens, latency) for the smalltalk generator's actual
LLM call is already covered by the EXISTING Phase-1 ``llm.telemetry.LlmCallTelemetry`` / sink —
this dataclass stays a route/pipeline-level record, not a duplicate of the LLM-call-level one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


def configure_route_logging(logger_name: str = "sealai_v2.pipeline.routing") -> None:
    """Make INFO route decisions visible in container logs (idempotent, no PII)."""

    import logging
    import sys

    logger = logging.getLogger(logger_name)
    for handler in logger.handlers:
        if (
            isinstance(handler, logging.StreamHandler)
            and getattr(handler, "stream", None) is sys.stdout
        ):
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


@dataclass(frozen=True)
class RouteTelemetry:
    route_name: str
    route_reason: str
    route_confidence: float
    forced_full_pipeline: bool
    deterministic_signal_count: int
    route_latency_ms: float
    # Phase 2D: which prompt family actually answered the turn (a fixed label, e.g.
    # "smalltalk_navigation" or "PromptAssembler" for the unchanged full L1 path), and whether
    # the LLM-based L3 verifier was skipped for this turn. Both safe: labels/booleans only.
    prompt_family: str | None = None
    l3_bypassed: bool = False


@runtime_checkable
class RouteTelemetrySink(Protocol):
    def record(self, event: RouteTelemetry) -> None: ...


class LoggingRouteTelemetrySink:
    """Default sink: one structured log line per routing decision via the standard ``logging``
    module — no new dependency, no behavior change, safe to leave on by default (same reasoning as
    ``llm.telemetry.LoggingTelemetrySink``)."""

    def __init__(self, logger_name: str = "sealai_v2.pipeline.routing") -> None:
        import logging

        self._logger = logging.getLogger(logger_name)

    def record(self, event: RouteTelemetry) -> None:
        self._logger.info(
            "route_decision route=%s reason=%s confidence=%.2f forced_full_pipeline=%s "
            "signal_count=%d latency_ms=%.2f prompt_family=%s l3_bypassed=%s",
            event.route_name,
            event.route_reason,
            event.route_confidence,
            event.forced_full_pipeline,
            event.deterministic_signal_count,
            event.route_latency_ms,
            event.prompt_family,
            event.l3_bypassed,
        )
