from __future__ import annotations

import types
import sys

from app.services.rag import qdrant_bootstrap as qb


def _info(*, dim: int = 768, has_sparse: bool = False):
    vectors = {"dense": types.SimpleNamespace(size=dim)}
    sparse_vectors = {"sparse": object()} if has_sparse else {}
    return types.SimpleNamespace(
        config=types.SimpleNamespace(
            params=types.SimpleNamespace(vectors=vectors, sparse_vectors=sparse_vectors)
        )
    )


def _install_qdrant_stub(monkeypatch, client_cls):
    qdrant_mod = types.ModuleType("qdrant_client")
    qdrant_mod.QdrantClient = client_cls

    class _UnexpectedResponse(Exception):
        def __init__(self, status_code: int):
            self.status_code = status_code
            super().__init__(f"status={status_code}")

    exceptions_mod = types.ModuleType("qdrant_client.http.exceptions")
    exceptions_mod.UnexpectedResponse = _UnexpectedResponse

    models_mod = types.SimpleNamespace(
        Distance=types.SimpleNamespace(COSINE="cosine"),
        VectorParams=lambda **kwargs: types.SimpleNamespace(**kwargs),
        SparseVectorParams=lambda **kwargs: types.SimpleNamespace(**kwargs),
        HnswConfigDiff=lambda **kwargs: types.SimpleNamespace(**kwargs),
        OptimizersConfigDiff=lambda **kwargs: types.SimpleNamespace(**kwargs),
    )
    qdrant_mod.models = models_mod

    monkeypatch.setitem(sys.modules, "qdrant_client", qdrant_mod)
    monkeypatch.setitem(sys.modules, "qdrant_client.http", types.ModuleType("qdrant_client.http"))
    monkeypatch.setitem(sys.modules, "qdrant_client.http.exceptions", exceptions_mod)

    return _UnexpectedResponse


def test_bootstrap_create_collection_includes_sparse_config(monkeypatch) -> None:
    calls = {}

    class _Client:
        def __init__(self, **kwargs):
            calls["init"] = kwargs

        def get_collection(self, _name):
            raise _unexpected_response(404)

        def create_collection(self, **kwargs):
            calls["create"] = kwargs

    _unexpected_response = _install_qdrant_stub(monkeypatch, _Client)

    result = qb.bootstrap_rag_collection(expected=("model", 768))

    assert result == "created"
    create_kwargs = calls["create"]
    assert "sparse_vectors_config" in create_kwargs
    assert "sparse" in create_kwargs["sparse_vectors_config"]


def test_bootstrap_upgrades_missing_sparse_config(monkeypatch) -> None:
    calls = {"get_count": 0}

    class _Client:
        def __init__(self, **_kwargs):
            return None

        def get_collection(self, _name):
            calls["get_count"] += 1
            return _info(has_sparse=calls["get_count"] > 1)

        def update_collection(self, **kwargs):
            calls["update"] = kwargs

    _install_qdrant_stub(monkeypatch, _Client)

    result = qb.bootstrap_rag_collection(expected=("model", 768))

    assert result == "upgraded"
    update_kwargs = calls["update"]
    assert "sparse_vectors_config" in update_kwargs
    assert "sparse" in update_kwargs["sparse_vectors_config"]


def test_bootstrap_recreates_in_dev_when_sparse_upgrade_fails(monkeypatch) -> None:
    calls = {}
    monkeypatch.setenv("APP_ENV", "development")

    class _Client:
        def __init__(self, **_kwargs):
            return None

        def get_collection(self, _name):
            return _info(has_sparse=False)

        def update_collection(self, **_kwargs):
            raise RuntimeError("upgrade failed")

        def recreate_collection(self, **kwargs):
            calls["recreate"] = kwargs

    _install_qdrant_stub(monkeypatch, _Client)

    result = qb.bootstrap_rag_collection(expected=("model", 768))

    assert result == "recreated"
    recreate_kwargs = calls["recreate"]
    assert "sparse_vectors_config" in recreate_kwargs
    assert "sparse" in recreate_kwargs["sparse_vectors_config"]
