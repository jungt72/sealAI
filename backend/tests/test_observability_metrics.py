"""Tests for Prometheus observability metrics (Sprint 9).

Verifies:
- Each instrument is defined and labelled correctly
- Counter.inc() and Histogram.observe() don't raise
- /metrics endpoint returns 200 with correct Content-Type
- qgate_checks_total increments are correctly labelled
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY


# ---------------------------------------------------------------------------
# Instrument existence
# ---------------------------------------------------------------------------


class TestMetricsModuleExists:
    def test_imports_without_error(self):
        import app.core.metrics  # noqa: F401

    def test_all_instruments_exported(self):
        from app.core.metrics import (
            graph_node_runs_total,
            http_request_duration_seconds,
            http_requests_total,
            mcp_tool_calls_total,
            qgate_checks_total,
        )
        assert http_requests_total is not None
        assert http_request_duration_seconds is not None
        assert graph_node_runs_total is not None
        assert qgate_checks_total is not None
        assert mcp_tool_calls_total is not None


# ---------------------------------------------------------------------------
# Counter increments
# ---------------------------------------------------------------------------


class TestCounterIncrements:
    def test_http_requests_total_increments(self):
        from app.core.metrics import http_requests_total
        before = _counter_value(http_requests_total, method="GET", path="/test", status="200")
        http_requests_total.labels(method="GET", path="/test", status="200").inc()
        after = _counter_value(http_requests_total, method="GET", path="/test", status="200")
        assert after == before + 1

    def test_graph_node_runs_total_increments(self):
        from app.core.metrics import graph_node_runs_total
        before = _counter_value(graph_node_runs_total, node="final_answer_node")
        graph_node_runs_total.labels(node="final_answer_node").inc()
        after = _counter_value(graph_node_runs_total, node="final_answer_node")
        assert after == before + 1

    def test_qgate_checks_total_increments(self):
        from app.core.metrics import qgate_checks_total
        before = _counter_value(
            qgate_checks_total, check_name="thermal_margin", severity="WARNING", passed="True"
        )
        qgate_checks_total.labels(
            check_name="thermal_margin", severity="WARNING", passed="True"
        ).inc()
        after = _counter_value(
            qgate_checks_total, check_name="thermal_margin", severity="WARNING", passed="True"
        )
        assert after == before + 1

    def test_mcp_tool_calls_total_increments(self):
        from app.core.metrics import mcp_tool_calls_total
        before = _counter_value(mcp_tool_calls_total, tool="mcp_calc_gasket", status="ok")
        mcp_tool_calls_total.labels(tool="mcp_calc_gasket", status="ok").inc()
        after = _counter_value(mcp_tool_calls_total, tool="mcp_calc_gasket", status="ok")
        assert after == before + 1


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


class TestHistogramObserve:
    def test_http_request_duration_observe_does_not_raise(self):
        from app.core.metrics import http_request_duration_seconds
        # Should not raise for any valid float
        http_request_duration_seconds.labels(method="POST", path="/api/v1/test").observe(0.42)
        http_request_duration_seconds.labels(method="POST", path="/api/v1/test").observe(0.001)


# ---------------------------------------------------------------------------
# /metrics endpoint (FastAPI TestClient)
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_200(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("httpx / TestClient not available")

        # Build minimal app without full lifespan to avoid DB/Redis connections
        from fastapi import FastAPI
        from fastapi.responses import Response
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        app = FastAPI()

        @app.get("/metrics")
        async def metrics():
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_endpoint_contains_sealai_metric(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("httpx / TestClient not available")

        from fastapi import FastAPI
        from fastapi.responses import Response
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        from app.core.metrics import http_requests_total

        # Ensure at least one label combination exists
        http_requests_total.labels(method="GET", path="/healthz", status="200").inc()

        app = FastAPI()

        @app.get("/metrics")
        async def metrics():
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

        client = TestClient(app)
        response = client.get("/metrics")
        assert b"sealai_http_requests_total" in response.content


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------


class TestPrometheusPathNormalization:
    def test_normalize_uuid_segment(self):
        from fastapi import FastAPI
        from app.main import _PrometheusMiddleware

        middleware = _PrometheusMiddleware(FastAPI())
        path = "/api/v1/items/123e4567-e89b-12d3-a456-426614174000/detail"
        assert middleware._normalize_path(path) == "/api/v1/items/{id}/detail"

    def test_normalize_32_hex_segment_without_partial_replacement(self):
        from fastapi import FastAPI
        from app.main import _PrometheusMiddleware

        middleware = _PrometheusMiddleware(FastAPI())
        path = "/api/v1/rag/documents/0c26f6b46bac4644917fb24cca23ca3d/health-check"
        assert middleware._normalize_path(path) == "/api/v1/rag/documents/{id}/health-check"

    def test_normalize_numeric_segment_only(self):
        from fastapi import FastAPI
        from app.main import _PrometheusMiddleware

        middleware = _PrometheusMiddleware(FastAPI())
        path = "/api/v1/orders/12345/lines"
        assert middleware._normalize_path(path) == "/api/v1/orders/{id}/lines"


# ---------------------------------------------------------------------------
# qgate_checks_total via quality gate result dicts
# ---------------------------------------------------------------------------


class TestQGateMetricHook:
    def test_qgate_counter_for_each_check(self):
        from app.core.metrics import qgate_checks_total

        checks = [
            {"check_id": "thermal_margin", "severity": "WARNING", "passed": True},
            {"check_id": "medium_compatibility", "severity": "CRITICAL", "passed": False},
            {"check_id": "critical_flag", "severity": "FLAG", "passed": True},
        ]

        for chk in checks:
            qgate_checks_total.labels(
                check_name=chk["check_id"],
                severity=chk["severity"],
                passed=str(chk["passed"]),
            ).inc()

        # Verify CRITICAL failed check is registered
        value = _counter_value(
            qgate_checks_total,
            check_name="medium_compatibility",
            severity="CRITICAL",
            passed="False",
        )
        assert value >= 1


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _counter_value(counter, **labels) -> float:
    """Read current value of a Counter for a specific label set."""
    try:
        return counter.labels(**labels)._value.get()
    except Exception:
        return 0.0
