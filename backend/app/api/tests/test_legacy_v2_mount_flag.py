from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[3]))

os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "test-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub
if "multipart" not in sys.modules:
    multipart_stub = types.ModuleType("multipart")
    multipart_module = types.ModuleType("multipart.multipart")

    def _parse_options_header(_value):
        return {}

    multipart_module.parse_options_header = _parse_options_header
    multipart_stub.__version__ = "0.0.13"
    sys.modules["multipart"] = multipart_stub
    sys.modules["multipart.multipart"] = multipart_module
if "python_multipart" not in sys.modules:
    python_multipart = types.ModuleType("python_multipart")
    python_multipart.__version__ = "0.0.13"
    sys.modules["python_multipart"] = python_multipart


def _reload_v1_api(*, enabled: bool):
    os.environ["ENABLE_LEGACY_V2_ENDPOINT"] = "true" if enabled else "false"

    config_module = importlib.import_module("app.core.config")
    config_module.get_settings.cache_clear()
    importlib.reload(config_module)

    api_module = importlib.import_module("app.api.v1.api")
    return importlib.reload(api_module)


def _route_paths(router) -> set[str]:
    return {getattr(route, "path", "") for route in router.routes}


def test_legacy_v2_router_not_mounted_by_default():
    api_module = _reload_v1_api(enabled=False)
    paths = _route_paths(api_module.api_router)

    assert "/langgraph/health" in paths
    assert "/langgraph/chat/v2" not in paths
    assert "/langgraph/threads/{thread_id}/runs/resume" not in paths


def test_legacy_v2_router_mounted_when_flag_enabled():
    api_module = _reload_v1_api(enabled=True)
    paths = _route_paths(api_module.api_router)

    assert "/langgraph/health" in paths
    assert "/langgraph/chat/v2" in paths
