from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace

import pytest


REQUIRED_ENV = {
    "postgres_user": "test",
    "postgres_password": "test",
    "postgres_host": "localhost",
    "postgres_port": "5432",
    "postgres_db": "testdb",
    "database_url": "postgresql+asyncpg://test:test@localhost:5432/testdb",
    "POSTGRES_SYNC_URL": "postgresql://test:test@localhost:5432/testdb",
    "openai_api_key": "sk-test",
    "qdrant_url": "http://localhost:6333",
    "redis_url": "redis://localhost:6379/0",
    "nextauth_url": "http://localhost:3000",
    "nextauth_secret": "test-secret",
    "keycloak_issuer": "http://localhost/realms/test",
    "keycloak_jwks_url": "http://localhost/.well-known/jwks.json",
    "keycloak_client_id": "test-client",
    "keycloak_client_secret": "test-secret",
    "keycloak_expected_azp": "test-client",
}

STARTUP_FLAG_ENV = {
    "APP_ENV",
    "FASTAPI_DOCS_ENABLED",
    "DEV_CLEAR_LANGGRAPH_CHECKPOINTS_ON_STARTUP",
    "QDRANT_BOOTSTRAP_ON_STARTUP",
    "AUDIT_LOG_BOOTSTRAP_ON_STARTUP",
    "JOB_WORKER_ENABLED",
    "WARMUP_ON_START",
}


def _install_required_env(
    monkeypatch: pytest.MonkeyPatch, *, app_env: str = "production", **flags: str
) -> None:
    for key in STARTUP_FLAG_ENV:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_ENV", app_env)
    for key, value in flags.items():
        monkeypatch.setenv(key, value)


def _install_multipart_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    multipart_stub = types.ModuleType("multipart")
    multipart_module = types.ModuleType("multipart.multipart")

    def _parse_options_header(_value):
        return {}

    multipart_module.parse_options_header = _parse_options_header
    multipart_stub.__version__ = "0.0.13"
    monkeypatch.setitem(sys.modules, "multipart", multipart_stub)
    monkeypatch.setitem(sys.modules, "multipart.multipart", multipart_module)

    python_multipart = types.ModuleType("python_multipart")
    python_multipart.__version__ = "0.0.13"
    monkeypatch.setitem(sys.modules, "python_multipart", python_multipart)


def _reload_config(monkeypatch: pytest.MonkeyPatch):
    loaded = sys.modules.get("app.core.config")
    if loaded is not None and not hasattr(loaded, "get_settings"):
        monkeypatch.delitem(sys.modules, "app.core.config", raising=False)
    config_module = importlib.import_module("app.core.config")
    config_module.get_settings.cache_clear()
    return importlib.reload(config_module)


def _reload_main(monkeypatch: pytest.MonkeyPatch):
    _install_multipart_stub(monkeypatch)
    config_module = _reload_config(monkeypatch)
    main_module = importlib.import_module("app.main")
    return importlib.reload(main_module), config_module


def test_settings_define_backend_referenced_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_required_env(monkeypatch)
    config_module = _reload_config(monkeypatch)
    settings = config_module.get_settings()

    referenced = {
        "database_url",
        "debug_sql",
        "postgres_dsn",
        "POSTGRES_SYNC_URL",
        "openai_api_key",
        "qdrant_url",
        "qdrant_api_key",
        "qdrant_collection",
        "qdrant_collection_ltm",
        "QDRANT_COLLECTION_NAME",
        "redis_url",
        "REDIS_URL",
        "ltm_enable",
        "chat_history_ttl_days",
        "chat_max_conversations_per_user",
        "nextauth_url",
        "keycloak_issuer",
        "keycloak_jwks_url",
        "keycloak_client_id",
        "keycloak_expected_azp",
        "backend_keycloak_issuer",
        "langchain_tracing_v2",
        "langchain_api_key",
        "langchain_endpoint",
        "langchain_project",
        "prometheus_enabled",
        "rate_limit_upload",
        "rate_limit_window_s",
        "gotenberg_url",
        "app_name",
        "app_version",
        "app_env",
        "frontend_origin",
        "enable_cors",
        "warmup_on_start",
        "job_worker_enabled",
        "job_worker_poll_sec",
        "dev_clear_langgraph_checkpoints_on_startup",
        "qdrant_bootstrap_on_startup",
        "audit_log_bootstrap_on_startup",
        "fastapi_docs_enabled",
    }

    missing = [name for name in sorted(referenced) if not hasattr(settings, name)]
    assert missing == []


def test_production_defaults_do_not_enable_startup_mutations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_required_env(monkeypatch, app_env="production")
    config_module = _reload_config(monkeypatch)
    settings = config_module.get_settings()

    assert settings.dev_clear_langgraph_checkpoints_on_startup is False
    assert settings.qdrant_bootstrap_on_startup is False
    assert settings.audit_log_bootstrap_on_startup is False
    assert settings.job_worker_enabled is False
    assert settings.fastapi_docs_enabled is False


def test_fastapi_docs_openapi_and_redoc_are_setting_gated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_required_env(
        monkeypatch, app_env="production", FASTAPI_DOCS_ENABLED="false"
    )
    main_module, _config_module = _reload_main(monkeypatch)

    app = main_module.create_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


@pytest.mark.asyncio
async def test_lifespan_skips_prod_mutating_bootstraps_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_required_env(monkeypatch, app_env="production")
    main_module, _config_module = _reload_main(monkeypatch)
    calls: list[str] = []

    monkeypatch.setattr(
        main_module, "ensure_upload_directory", lambda: calls.append("upload_dir")
    )
    monkeypatch.setattr(
        main_module, "bootstrap_rag_collection", lambda: calls.append("qdrant")
    )

    async def _audit() -> None:
        calls.append("audit")

    async def _worker() -> None:
        calls.append("worker")

    monkeypatch.setattr(main_module, "_bootstrap_audit_log", _audit)
    monkeypatch.setattr(main_module, "start_job_worker", _worker)

    app = SimpleNamespace(state=SimpleNamespace())
    async with main_module.lifespan(app):
        assert app.state.warmed_up is True

    assert calls == ["upload_dir"]


@pytest.mark.asyncio
async def test_langgraph_checkpoint_clear_requires_dev_or_test_even_when_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_required_env(
        monkeypatch,
        app_env="production",
        DEV_CLEAR_LANGGRAPH_CHECKPOINTS_ON_STARTUP="true",
    )
    main_module, _config_module = _reload_main(monkeypatch)

    await main_module._clear_langgraph_checkpoints_for_dev_run()


@pytest.mark.asyncio
async def test_worker_start_requires_explicit_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_required_env(monkeypatch, app_env="test", JOB_WORKER_ENABLED="true")
    main_module, _config_module = _reload_main(monkeypatch)
    calls: list[str] = []

    monkeypatch.setattr(main_module, "ensure_upload_directory", lambda: None)

    async def _worker() -> None:
        calls.append("worker")

    monkeypatch.setattr(main_module, "start_job_worker", _worker)

    app = SimpleNamespace(state=SimpleNamespace())
    async with main_module.lifespan(app):
        await main_module.asyncio.sleep(0)

    assert calls == ["worker"]
