from __future__ import annotations

import importlib

import pytest


def _set_minimal_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("postgres_user", "test")
    monkeypatch.setenv("postgres_password", "test")
    monkeypatch.setenv("postgres_host", "localhost")
    monkeypatch.setenv("postgres_port", "5432")
    monkeypatch.setenv("postgres_db", "test")
    monkeypatch.setenv("database_url", "postgresql+psycopg://test:test@localhost:5432/test")
    monkeypatch.setenv("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("openai_api_key", "dummy")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    monkeypatch.setenv("qdrant_url", "http://localhost:6333")
    monkeypatch.setenv("qdrant_collection", "test")
    monkeypatch.setenv("redis_url", "redis://localhost:6379/0")
    monkeypatch.setenv("nextauth_url", "http://localhost:3000")
    monkeypatch.setenv("nextauth_secret", "dummy")
    monkeypatch.setenv("keycloak_issuer", "http://localhost:8080/realms/test")
    monkeypatch.setenv("keycloak_jwks_url", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
    monkeypatch.setenv("keycloak_client_id", "dummy")
    monkeypatch.setenv("keycloak_client_secret", "dummy")
    monkeypatch.setenv("keycloak_expected_azp", "dummy")


def test_resolve_embedding_model_uses_canonical_dense_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    model_name = "jinaai/jina-embeddings-v2-base-de"
    monkeypatch.setenv("RAG_DENSE_MODEL", model_name)
    monkeypatch.delenv("RAG_EMBEDDING_MODEL", raising=False)

    from app.services.rag import rag_orchestrator as ro

    importlib.reload(ro)
    ro._embedding_dim = 768
    model, dim = ro.resolve_embedding_model()
    assert model == model_name
    assert dim == 768


def test_resolve_embedding_config_probes_and_caches_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_minimal_settings_env(monkeypatch)
    monkeypatch.setenv("RAG_DENSE_MODEL", "BAAI/bge-base-en-v1.5")

    from app.services.rag import rag_orchestrator as ro

    importlib.reload(ro)
    calls = {"count": 0}

    def _fake_embed(_texts: list[str]) -> list[list[float]]:
        calls["count"] += 1
        return [[0.0, 0.0, 0.0, 0.0]]

    monkeypatch.setattr(ro, "_embed", _fake_embed)
    assert ro.resolve_embedding_config() == ("BAAI/bge-base-en-v1.5", 4)
    assert ro.resolve_embedding_config() == ("BAAI/bge-base-en-v1.5", 4)
    assert calls["count"] == 1
