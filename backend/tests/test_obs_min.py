from __future__ import annotations

import logging

from app.common.obs import RoutingMetrics, RoutingTimer, emit_routing_event


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - simple collector
        self.records.append(record)


def test_routing_metrics_to_dict():
    metrics = RoutingMetrics(
        route="material",
        chosen_agents=["material", "normen"],
        missing_parameters=["temperatur"],
        confidence=0.8,
        coverage=0.7,
        hybrid_score=0.75,
        risk=0.3,
        rag_sources=["kb:42"],
        safety_flags=["missing_evidence"],
        latency_ms_p50=120.5,
        latency_ms_p95=200.1,
    )
    data = metrics.to_dict()
    assert data["route"] == "material"
    assert data["chosen_agents"] == ["material", "normen"]
    assert data["risk"] == 0.3


def test_routing_timer_percentiles():
    timer = RoutingTimer(sample_size=5)
    with timer:
        pass
    timer.stop()
    for _ in range(4):
        timer._samples.append(100 + _ * 10)
    assert timer.p50 is not None
    assert timer.p95 is not None


def test_emit_routing_event_logs_json(caplog):
    handler = _ListHandler()
    logger = logging.getLogger("app.routing.telemetry")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    metrics = RoutingMetrics(route="material", chosen_agents=["material"])
    emit_routing_event(metrics, extra={"thread_id": "abc"})

    logger.removeHandler(handler)
    assert handler.records
    record = handler.records[0]
    assert "routing_event" in record.getMessage()
