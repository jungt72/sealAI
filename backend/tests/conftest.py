import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUB_PATH = ROOT.parent / "langchain_core_stub"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if STUB_PATH.exists() and str(STUB_PATH) not in sys.path:
    sys.path.insert(0, str(STUB_PATH))

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

            def observe(self, *_args, **_kwargs):
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
    prometheus_stub.generate_latest = lambda *_a, **_kw: b""
    sys.modules["prometheus_client"] = prometheus_stub
