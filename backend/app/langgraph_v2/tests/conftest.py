from __future__ import annotations

import asyncio
import inspect
import sys
import types
from types import SimpleNamespace

import pytest


# Keep imports stable in isolated unit tests without requiring full runtime env.
if "app.core.config" not in sys.modules:
    config_stub = types.ModuleType("app.core.config")
    config_stub.settings = SimpleNamespace(
        postgres_user="test",
        postgres_password="test",
        postgres_host="localhost",
        postgres_port="5432",
        postgres_db="testdb",
        database_url="postgresql+asyncpg://test:test@localhost:5432/testdb",
        debug_sql=False,
        qdrant_collection="test_collection",
        openai_temperature=0.0,
        backend_keycloak_issuer="https://auth.example.test/realms/sealai",
        keycloak_jwks_url="https://auth.example.test/realms/sealai/protocol/openid-connect/certs",
        keycloak_client_id="sealai-backend-api",
        keycloak_expected_azp="sealai-backend-api",
        nextauth_url="http://localhost:3000",
        nextauth_secret="test-secret",
        redis_url="redis://localhost:6379",
        openai_api_key="sk-test",
        qdrant_url="http://localhost:6333",
    )
    sys.modules["app.core.config"] = config_stub

if "prometheus_client" not in sys.modules:
    def _make_prom_metric(*_a, **_kw):
        class _Stub:
            def inc(self, *a, **kw): pass
            def observe(self, *a, **kw): pass
            def set(self, *a, **kw): pass
            def labels(self, *a, **kw): return self
        return _Stub()
    _prometheus_stub = types.ModuleType("prometheus_client")
    _prometheus_stub.Counter = _make_prom_metric
    _prometheus_stub.Histogram = _make_prom_metric
    _prometheus_stub.Gauge = _make_prom_metric
    sys.modules["prometheus_client"] = _prometheus_stub

if "app.services.rag.bm25_store" not in sys.modules:
    _bm25_stub = types.ModuleType("app.services.rag.bm25_store")
    _bm25_stub.bm25_repo = SimpleNamespace(
        search=lambda *a, **kw: [],
        index=lambda *a, **kw: None,
        delete=lambda *a, **kw: None,
    )
    sys.modules["app.services.rag.bm25_store"] = _bm25_stub


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: run test in local asyncio event loop")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if "asyncio" not in pyfuncitem.keywords:
        return None
    test_func = pyfuncitem.obj
    if not inspect.iscoroutinefunction(test_func):
        return None
    kwargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
    asyncio.run(test_func(**kwargs))
    return True
