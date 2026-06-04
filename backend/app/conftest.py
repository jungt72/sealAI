from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "prometheus_client" not in sys.modules:

    class _MetricValue:
        def __init__(self) -> None:
            self._current = 0.0

        def get(self) -> float:
            return self._current

    def _make_prom_metric(*_args, **_kwargs):
        class _Stub:
            def __init__(self) -> None:
                self._value = _MetricValue()
                self._children = {}

            def inc(self, amount=1, *args, **kwargs):
                try:
                    self._value._current += float(amount)
                except Exception:
                    self._value._current += 1.0
                return None

            def observe(self, *args, **kwargs):
                return None

            def set(self, value=0, *args, **kwargs):
                try:
                    self._value._current = float(value)
                except Exception:
                    self._value._current = 0.0
                return None

            def labels(self, *args, **kwargs):
                key = (args, tuple(sorted(kwargs.items())))
                child = self._children.get(key)
                if child is None:
                    child = _Stub()
                    self._children[key] = child
                return child

        return _Stub()

    prometheus_stub = types.ModuleType("prometheus_client")
    prometheus_stub.Counter = _make_prom_metric
    prometheus_stub.Histogram = _make_prom_metric
    prometheus_stub.Gauge = _make_prom_metric
    prometheus_stub.REGISTRY = object()
    prometheus_stub.CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    prometheus_stub.generate_latest = (
        lambda *_args, **_kwargs: b"sealai_http_requests_total 1.0\n"
    )
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
