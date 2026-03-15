import asyncio
import importlib
import json
import os

_ENV_DEFAULTS = {
    "POSTGRES_USER": "sealai",
    "POSTGRES_PASSWORD": "secret",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "sealai",
    "DATABASE_URL": "postgresql+asyncpg://sealai:secret@localhost:5432/sealai",
    "POSTGRES_SYNC_URL": "postgresql://sealai:secret@localhost:5432/sealai",
    "OPENAI_API_KEY": "test-key",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_COLLECTION": "sealai",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEXTAUTH_URL": "http://localhost:3000",
    "NEXTAUTH_SECRET": "dummy-secret",
    "KEYCLOAK_ISSUER": "http://localhost:8080/realms/test",
    "KEYCLOAK_JWKS_URL": "http://localhost:8080/realms/test/protocol/openid-connect/certs",
    "KEYCLOAK_CLIENT_ID": "sealai-backend",
    "KEYCLOAK_CLIENT_SECRET": "client-secret",
    "KEYCLOAK_EXPECTED_AZP": "sealai-frontend",
}


def _ensure_env():
    for key, value in _ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def _build_app_without_required_env(monkeypatch):
    for key in _ENV_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    config_mod = importlib.import_module("app.core.config")
    monkeypatch.setitem(config_mod.Settings.model_config, "env_file", None)
    config_mod.get_settings.cache_clear()
    main_mod = importlib.import_module("app.main")
    return main_mod.create_app()


def _call_json_route(app, path: str):
    for route in app.router.routes:
        if getattr(route, "path", None) == path:
            response = asyncio.run(route.endpoint())
            return json.loads(response.body.decode("utf-8")), response.status_code
    raise AssertionError(f"Route not found: {path}")


def test_fastapi_app_imports():
    _ensure_env()
    app_mod = importlib.import_module("app.main")
    assert hasattr(app_mod, "app")


def test_api_router_imports():
    _ensure_env()
    api_mod = importlib.import_module("app.api.v1.api")
    assert hasattr(api_mod, "api_router")


def test_health_route_exists():
    _ensure_env()
    app_mod = importlib.import_module("app.main"); app = getattr(app_mod, "app")
    paths = {r.path for r in app.router.routes}
    assert any(route in paths for route in ("/health", "/healthz", "/api/health"))


def test_readyz_reports_not_ready_when_required_config_missing(monkeypatch):
    app = _build_app_without_required_env(monkeypatch)
    payload, status_code = _call_json_route(app, "/readyz")

    assert status_code == 503
    assert payload["ready"] is False
    assert payload["config"]["config_ready"] is False
    assert payload["config"]["reason"] == "required_settings_missing"
    assert "database_url" in payload["config"]["missing_settings"]


def test_health_reports_degraded_when_required_config_missing(monkeypatch):
    app = _build_app_without_required_env(monkeypatch)
    payload, status_code = _call_json_route(app, "/health")

    assert status_code == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["config"]["config_ready"] is False
    assert payload["checks"]["config"]["reason"] == "required_settings_missing"
    assert "database_url" in payload["checks"]["config"]["missing_settings"]
