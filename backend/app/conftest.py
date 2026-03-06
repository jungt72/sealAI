from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


if "prometheus_client" not in sys.modules:
    def _make_prom_metric(*_args, **_kwargs):
        class _Stub:
            def inc(self, *args, **kwargs):
                return None

            def observe(self, *args, **kwargs):
                return None

            def set(self, *args, **kwargs):
                return None

            def labels(self, *args, **kwargs):
                return self

        return _Stub()

    prometheus_stub = types.ModuleType("prometheus_client")
    prometheus_stub.Counter = _make_prom_metric
    prometheus_stub.Histogram = _make_prom_metric
    prometheus_stub.Gauge = _make_prom_metric
    sys.modules["prometheus_client"] = prometheus_stub

if "app.services.rag.bm25_store" not in sys.modules:
    bm25_stub = types.ModuleType("app.services.rag.bm25_store")
    bm25_stub.bm25_repo = SimpleNamespace(
        search=lambda *args, **kwargs: [],
        index=lambda *args, **kwargs: None,
        delete=lambda *args, **kwargs: None,
    )
    sys.modules["app.services.rag.bm25_store"] = bm25_stub


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
