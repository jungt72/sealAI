from __future__ import annotations

import importlib

import pytest


def _supported_models() -> set[str]:
    try:
        from fastembed import TextEmbedding  # type: ignore
    except Exception as exc:
        pytest.skip(f"fastembed not available: {type(exc).__name__}: {exc}")
    items = TextEmbedding.list_supported_models()
    out: set[str] = set()
    for item in items or []:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict):
            name = item.get("model") or item.get("model_name") or item.get("name")
            if name:
                out.add(str(name))
        else:
            name = getattr(item, "model", None) or getattr(item, "model_name", None) or getattr(item, "name", None)
            if name:
                out.add(str(name))
    return out


def test_resolve_embedding_model_falls_back_if_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    supported = _supported_models()
    fallback = "jinaai/jina-embeddings-v2-base-de"
    if fallback not in supported:
        pytest.skip(f"expected fallback {fallback!r} not in supported fastembed models")

    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "intfloat/multilingual-e5-base")
    monkeypatch.delenv("RAG_EMBEDDING_DIM", raising=False)
    monkeypatch.delenv("EMB_MODEL_NAME", raising=False)
    monkeypatch.delenv("EMBEDDINGS_MODEL", raising=False)

    from app.services.rag import rag_orchestrator as ro

    importlib.reload(ro)
    model, dim = ro.resolve_embedding_model()
    assert model == fallback
    assert isinstance(dim, int) and dim > 0


def test_resolve_embedding_model_honors_canonical_env(monkeypatch: pytest.MonkeyPatch) -> None:
    model_name = "jinaai/jina-embeddings-v2-base-de"
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", model_name)
    monkeypatch.setenv("RAG_EMBEDDING_DIM", "768")

    from app.services.rag import rag_orchestrator as ro

    importlib.reload(ro)
    model, dim = ro.resolve_embedding_model()
    assert model == model_name
    assert dim == 768

