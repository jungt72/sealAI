from app.langgraph.nodes import context_retrieval as module


def test_context_retrieval_requires_tenant(monkeypatch) -> None:
    called = {"count": 0}

    def fake_retrieve(*, query: str, tenant: str):
        called["count"] += 1
        return [{"text": "ok", "source": "kb"}]

    monkeypatch.setattr(module, "hybrid_retrieve", fake_retrieve)

    state = {"slots": {"user_query": "test"}}
    result = module.context_retrieval(state)

    assert called["count"] == 0
    assert result.get("slots", {}).get("rag_status") == "empty"


def test_context_retrieval_passes_tenant(monkeypatch) -> None:
    captured = {}

    def fake_retrieve(*, query: str, tenant: str):
        captured["query"] = query
        captured["tenant"] = tenant
        return [{"text": "ok", "source": "kb"}]

    monkeypatch.setattr(module, "hybrid_retrieve", fake_retrieve)

    state = {"slots": {"user_query": "test"}, "meta": {"user_id": "tenant-1"}}
    result = module.context_retrieval(state)

    assert captured == {"query": "test", "tenant": "tenant-1"}
    assert result.get("slots", {}).get("rag_status") == "success"
