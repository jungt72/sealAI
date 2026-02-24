from __future__ import annotations

import sys
import types

import pytest


class _FakePoint:
    def __init__(self, payload=None, score: float = 0.0) -> None:
        self.payload = payload or {}
        self.score = score


class _FakeQueryResponse:
    def __init__(self, points=None) -> None:
        self.points = points or []


def _install_fake_qdrant_modules(monkeypatch: pytest.MonkeyPatch):
    class UnexpectedResponse(Exception):
        def __init__(self, status_code: int) -> None:
            super().__init__(f"HTTP {status_code}")
            self.status_code = status_code

    class _FakeModels:
        class Filter:
            def __init__(self, **_kwargs):
                pass

        class Prefetch:
            def __init__(self, **_kwargs):
                pass

        class SparseVector:
            def __init__(self, **_kwargs):
                pass

        class Fusion:
            RRF = "rrf"

        class FusionQuery:
            def __init__(self, **_kwargs):
                pass

    qdrant_mod = types.ModuleType("qdrant_client")
    qdrant_mod.models = _FakeModels
    monkeypatch.setitem(sys.modules, "qdrant_client", qdrant_mod)

    http_mod = types.ModuleType("qdrant_client.http")
    exceptions_mod = types.ModuleType("qdrant_client.http.exceptions")
    exceptions_mod.UnexpectedResponse = UnexpectedResponse
    monkeypatch.setitem(sys.modules, "qdrant_client.http", http_mod)
    monkeypatch.setitem(sys.modules, "qdrant_client.http.exceptions", exceptions_mod)
    return UnexpectedResponse


def test_qdrant_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    unexpected_response = _install_fake_qdrant_modules(monkeypatch)

    outcomes = [
        unexpected_response(503),  # first attempt fails with retriable HTTP error
        _FakeQueryResponse(points=[_FakePoint(payload={"text": "A"}, score=0.9)]),
    ]
    def _query_points(**_kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(ro, "_make_qdrant_client", lambda: types.SimpleNamespace(query_points=_query_points))
    monkeypatch.setattr(ro, "_build_qdrant_filter", lambda _filters=None: None)
    monkeypatch.setattr(ro, "_embed_sparse_query", lambda _q: None)
    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0]])
    monkeypatch.setattr(ro, "_fallback_external_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ro.time, "sleep", lambda _value: None)
    monkeypatch.setattr(ro.random, "random", lambda: 0.0)

    _hits, meta = ro.hybrid_retrieve(
        query="test",
        tenant="tenant-1",
        k=1,
        use_rerank=False,
        return_metrics=True,
    )

    qdrant_meta = meta.get("qdrant") or {}
    assert qdrant_meta.get("attempts") == 2
    assert qdrant_meta.get("error") is None
    assert isinstance(qdrant_meta.get("elapsed_ms"), int)


def test_qdrant_retry_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    unexpected_response = _install_fake_qdrant_modules(monkeypatch)
    outcomes = [unexpected_response(503), unexpected_response(503), unexpected_response(503)]
    monkeypatch.setattr(ro, "_make_qdrant_client", lambda: types.SimpleNamespace(query_points=lambda **_kwargs: (_ for _ in ()).throw(outcomes.pop(0))))
    monkeypatch.setattr(ro, "_build_qdrant_filter", lambda _filters=None: None)
    monkeypatch.setattr(ro, "_embed_sparse_query", lambda _q: None)
    monkeypatch.setattr(ro, "_embed", lambda _texts: [[0.0]])
    monkeypatch.setattr(ro, "_fallback_external_search", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ro.time, "sleep", lambda _value: None)
    monkeypatch.setattr(ro.random, "random", lambda: 0.0)

    hits, meta = ro.hybrid_retrieve(
        query="test",
        tenant="tenant-1",
        k=1,
        use_rerank=False,
        return_metrics=True,
    )

    assert hits == []
    qdrant_meta = meta.get("qdrant") or {}
    assert qdrant_meta.get("attempts") == 3
    error = qdrant_meta.get("error") or {}
    assert error.get("kind") == "http_error"
    assert error.get("status") == 503
