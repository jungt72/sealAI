from __future__ import annotations

import sys
import types

import pytest


def _install_fake_httpx(monkeypatch: pytest.MonkeyPatch, outcomes):
    class TimeoutException(Exception):
        pass

    class TransportError(Exception):
        pass

    class _Client:
        def __init__(self, timeout=None):
            self._timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, _url, json=None):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    fake = types.SimpleNamespace(
        Client=_Client,
        TimeoutException=TimeoutException,
        TransportError=TransportError,
    )
    monkeypatch.setitem(sys.modules, "httpx", fake)
    return fake


class _FakeResponse:
    def __init__(self, status_code: int, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_qdrant_retry_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.rag import rag_orchestrator as ro

    outcomes = [
        _FakeResponse(503, {}),
        _FakeResponse(
            200,
            {
                "result": [
                    {"payload": {"text": "A"}, "score": 0.9},
                ]
            },
        ),
    ]
    _install_fake_httpx(monkeypatch, outcomes)
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

    outcomes = [
        _FakeResponse(503, {}),
        _FakeResponse(503, {}),
        _FakeResponse(503, {}),
    ]
    _install_fake_httpx(monkeypatch, outcomes)
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
