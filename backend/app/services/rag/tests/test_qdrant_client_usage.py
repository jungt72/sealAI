from __future__ import annotations

from typing import Any


def test_qdrant_client_factory_used(monkeypatch) -> None:
    import app.services.rag.rag_orchestrator as ro

    called: dict[str, Any] = {}

    class FakeClient:
        def search(self, *args: Any, **kwargs: Any):
            called["search"] = True
            return []

    def fake_get_qdrant_client():
        called["factory"] = True
        return FakeClient()

    monkeypatch.setattr(ro, "get_qdrant_client", fake_get_qdrant_client)

    hits, meta = ro._qdrant_search_with_retry([0.1, 0.2], "test", top_k=1)

    assert called.get("factory") is True
    assert called.get("search") is True
    assert hits == []
    assert meta.get("attempts")
