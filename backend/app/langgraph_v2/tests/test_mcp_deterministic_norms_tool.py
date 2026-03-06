from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from sqlalchemy.exc import SQLAlchemyError

from app.mcp import knowledge_tool


class _ResultRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)


def test_query_deterministic_norms_returns_matches(monkeypatch) -> None:
    norm_row = SimpleNamespace(
        _mapping={
            "norm_code": "DIN 3770",
            "material": "FKM",
            "medium": "H2",
            "pressure_min_bar": 10.0,
            "pressure_max_bar": 350.0,
            "temperature_min_c": -20.0,
            "temperature_max_c": 120.0,
            "payload_json": {"extrusion_gap_mm_max": 0.15},
            "source_ref": "DIN3770:2024",
            "revision": "2024-01",
            "version": 2,
            "effective_date": None,
            "valid_until": None,
            "tenant_id": "tenant-1",
        }
    )
    limit_row = SimpleNamespace(
        _mapping={
            "material": "FKM",
            "medium": "H2",
            "limit_kind": "pressure",
            "min_value": 0.0,
            "max_value": 350.0,
            "unit": "bar",
            "conditions_json": {"aed_required": True},
            "source_ref": "MAT-FKM-AED-01",
            "revision": "2024-03",
            "version": 1,
            "effective_date": None,
            "valid_until": None,
            "tenant_id": "tenant-1",
        }
    )

    class _FakeSession:
        def __init__(self, _engine):
            self._calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _stmt, _params=None):
            self._calls += 1
            if self._calls == 1:
                return _ResultRows([norm_row])
            return _ResultRows([limit_row])

    monkeypatch.setattr(knowledge_tool, "_get_sync_engine", lambda: object())
    monkeypatch.setattr(knowledge_tool, "Session", _FakeSession)

    payload = knowledge_tool.query_deterministic_norms(
        material="FKM",
        temp=80.0,
        pressure=120.0,
        tenant_id="tenant-1",
    )

    assert payload["tool"] == knowledge_tool.QUERY_DETERMINISTIC_NORMS_TOOL_NAME
    assert payload["status"] == "ok"
    assert len(payload["matches"]["din_norms"]) == 1
    assert len(payload["matches"]["material_limits"]) == 1
    assert payload["retrieval_meta"]["mode"] == "exact_range_sql"


def test_query_deterministic_norms_handles_sqlalchemy_error(monkeypatch) -> None:
    class _FailingSession:
        def __init__(self, _engine):
            pass

        def __enter__(self):
            raise SQLAlchemyError("db down")

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(knowledge_tool, "_get_sync_engine", lambda: object())
    monkeypatch.setattr(knowledge_tool, "Session", _FailingSession)

    payload = knowledge_tool.query_deterministic_norms(
        material="NBR",
        temp=60.0,
        pressure=20.0,
        tenant_id="tenant-1",
    )

    assert payload["status"] == "error"
    assert payload["matches"]["din_norms"] == []
    assert payload["matches"]["material_limits"] == []


def test_query_deterministic_norms_returns_no_match_message(monkeypatch) -> None:
    class _EmptySession:
        def __init__(self, _engine):
            self._calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _stmt, _params=None):
            self._calls += 1
            return _ResultRows([])

    monkeypatch.setattr(knowledge_tool, "_get_sync_engine", lambda: object())
    monkeypatch.setattr(knowledge_tool, "Session", _EmptySession)

    payload = knowledge_tool.query_deterministic_norms(
        material="PTFE",
        temp=25.0,
        pressure=5.0,
    )

    assert payload["status"] == "no_match"
    assert payload["context"] == "Ich finde keine spezifischen Normwerte in der Datenbank für dieses Material."
    assert (
        payload["retrieval_meta"]["database_message"]
        == "Ich finde keine spezifischen Normwerte in der Datenbank für dieses Material."
    )


def test_aquery_deterministic_norms_rejects_non_async_session_factory(monkeypatch) -> None:
    class _SyncLikeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setitem(
        sys.modules,
        "app.database",
        SimpleNamespace(AsyncSessionLocal=lambda: _SyncLikeSession()),
    )

    payload = asyncio.run(
        knowledge_tool.aquery_deterministic_norms(
            material="PTFE",
            temp=25.0,
            pressure=5.0,
        )
    )

    assert payload["status"] == "error"
    assert "AsyncSessionLocal must return an AsyncSession" in payload["retrieval_meta"]["error"]
