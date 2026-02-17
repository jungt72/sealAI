from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from qdrant_client import models

sys.path.append(str(Path(__file__).resolve().parents[4]))

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
os.environ.setdefault("nextauth_url", "http://localhost")
os.environ.setdefault("nextauth_secret", "test")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from app.services.memory import memory_core


def _is_empty(payload: dict[str, Any], key: str) -> bool:
    return key not in payload or payload.get(key) in (None, "", [], {})


def _matches_condition(payload: dict[str, Any], condition: Any) -> bool:
    if isinstance(condition, models.FieldCondition):
        if condition.match is None:
            return False
        expected = getattr(condition.match, "value", None)
        return payload.get(condition.key) == expected
    if isinstance(condition, models.IsEmptyCondition):
        return _is_empty(payload, condition.is_empty.key)
    if isinstance(condition, models.IsNullCondition):
        return condition.is_null.key in payload and payload.get(condition.is_null.key) is None
    if isinstance(condition, models.Filter):
        return _matches_filter(payload, condition)
    return False


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _matches_filter(payload: dict[str, Any], flt: models.Filter) -> bool:
    must = _as_list(flt.must)
    should = _as_list(flt.should)
    must_not = _as_list(flt.must_not)
    if must and not all(_matches_condition(payload, c) for c in must):
        return False
    if should and not any(_matches_condition(payload, c) for c in should):
        return False
    if must_not and any(_matches_condition(payload, c) for c in must_not):
        return False
    return True


class _FakeQdrantClient:
    def __init__(self, points: list[SimpleNamespace]) -> None:
        self._points = points

    def scroll(self, *, scroll_filter, limit, offset=None, **_kwargs):
        matched = [point for point in self._points if _matches_filter(point.payload or {}, scroll_filter)]
        start = int(offset or 0)
        chunk = matched[start : start + limit]
        next_page = start + len(chunk)
        if next_page >= len(matched):
            next_page = None
        return chunk, next_page


def _mkpoint(pid: str, payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(id=pid, payload=payload)


def test_ltm_export_is_tenant_scoped_for_same_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LTM_ALLOW_LEGACY_WITHOUT_TENANT", raising=False)
    monkeypatch.setattr(memory_core.settings, "ltm_enable", True)

    points = [
        _mkpoint("a1", {"tenant_id": "tenant-a", "user": "shared-user", "text": "A"}),
        _mkpoint("b1", {"tenant_id": "tenant-b", "user": "shared-user", "text": "B"}),
    ]
    fake = _FakeQdrantClient(points)
    monkeypatch.setattr(memory_core, "_get_qdrant_client", lambda: fake)
    monkeypatch.setattr(memory_core, "ensure_ltm_collection", lambda _client: None)

    exported = memory_core.ltm_export_all(tenant_id="tenant-a", user="shared-user", limit=100)
    ids = {item["id"] for item in exported}
    assert ids == {"a1"}


def test_ltm_export_excludes_legacy_records_without_tenant_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LTM_ALLOW_LEGACY_WITHOUT_TENANT", raising=False)
    monkeypatch.setattr(memory_core.settings, "ltm_enable", True)

    points = [
        _mkpoint("a1", {"tenant_id": "tenant-a", "user": "shared-user", "text": "A"}),
        _mkpoint("legacy1", {"user": "shared-user", "text": "legacy"}),
    ]
    fake = _FakeQdrantClient(points)
    monkeypatch.setattr(memory_core, "_get_qdrant_client", lambda: fake)
    monkeypatch.setattr(memory_core, "ensure_ltm_collection", lambda _client: None)

    exported = memory_core.ltm_export_all(tenant_id="tenant-a", user="shared-user", limit=100)
    ids = {item["id"] for item in exported}
    assert "a1" in ids
    assert "legacy1" not in ids
