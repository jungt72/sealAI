"""Phase 2B (LangGraph-suitability audit) — safe route-decision telemetry.

Mirrors the ``llm.telemetry`` pattern from Phase 1: a frozen, safe-fields-only dataclass + a sink
Protocol + a default log-only sink. Never carries raw user text, tenant_id, case_id, exact medium
names, file names, or sensitive parameters — only the route label, a short machine reason string,
a confidence float, booleans, a signal count, and a latency in ms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RouteTelemetry:
    route_name: str
    route_reason: str
    route_confidence: float
    forced_full_pipeline: bool
    deterministic_signal_count: int
    route_latency_ms: float


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
            "signal_count=%d latency_ms=%.2f",
            event.route_name,
            event.route_reason,
            event.route_confidence,
            event.forced_full_pipeline,
            event.deterministic_signal_count,
            event.route_latency_ms,
        )
