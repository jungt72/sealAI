"""Routing observability utilities."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("app.routing.telemetry")


@dataclass
class RoutingMetrics:
    """Container capturing routing KPIs for downstream logging/metrics."""

    route: Optional[str] = None
    chosen_agents: List[str] = field(default_factory=list)
    missing_parameters: List[str] = field(default_factory=list)
    confidence: Optional[float] = None
    coverage: Optional[float] = None
    hybrid_score: Optional[float] = None
    risk: Optional[float] = None
    rag_sources: List[str] = field(default_factory=list)
    safety_flags: List[str] = field(default_factory=list)
    latency_ms_p50: Optional[float] = None
    latency_ms_p95: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route,
            "chosen_agents": self.chosen_agents,
            "missing_parameters": self.missing_parameters,
            "confidence": self.confidence,
            "coverage": self.coverage,
            "hybrid_score": self.hybrid_score,
            "risk": self.risk,
            "rag_sources": self.rag_sources,
            "safety_flags": self.safety_flags,
            "latency_ms_p50": self.latency_ms_p50,
            "latency_ms_p95": self.latency_ms_p95,
        }


class RoutingTimer:
    """Context manager to measure routing latency percentiles."""

    def __init__(self, *, sample_size: int = 32) -> None:
        self.sample_size = max(1, sample_size)
        self._samples: List[float] = []
        self._start: Optional[float] = None

    def __enter__(self) -> "RoutingTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def stop(self) -> None:
        if self._start is None:
            return
        elapsed = (time.perf_counter() - self._start) * 1000.0
        self._samples.append(elapsed)
        if len(self._samples) > self.sample_size:
            self._samples.pop(0)
        self._start = None

    @property
    def p50(self) -> Optional[float]:
        return _percentile(self._samples, 50)

    @property
    def p95(self) -> Optional[float]:
        return _percentile(self._samples, 95)


def _percentile(samples: List[float], percentile: float) -> Optional[float]:
    if not samples:
        return None
    values = sorted(samples)
    rank = (percentile / 100.0) * (len(values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(values) - 1)
    if lower == upper:
        return round(values[lower], 3)
    weight = rank - lower
    return round(values[lower] * (1 - weight) + values[upper] * weight, 3)


def emit_routing_event(metrics: RoutingMetrics, *, extra: Optional[Dict[str, Any]] = None) -> None:
    """Serialize and emit routing telemetry as structured JSON log."""
    payload = metrics.to_dict()
    if extra:
        payload.update(extra)
    try:
        log.info("routing_event", extra={"json": json.dumps(payload, ensure_ascii=False)})
    except Exception:
        log.info("routing_event %s", payload)


__all__ = ["RoutingMetrics", "RoutingTimer", "emit_routing_event"]
