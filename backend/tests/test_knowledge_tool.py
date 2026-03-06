from __future__ import annotations

from typing import Any, Dict

from app.mcp import knowledge_tool


def test_search_technical_docs_keeps_tenant_filter_when_empty(monkeypatch) -> None:
    calls: list[Dict[str, Any] | None] = []

    def _fake_hybrid_retrieve(
        *,
        query: str,
        tenant: str | None,
        k: int,
        metadata_filters: Dict[str, Any] | None,
        use_rerank: bool,
        qdrant_timeout_s: float,
        return_metrics: bool,
    ):
        calls.append(dict(metadata_filters or {}))
        if metadata_filters and metadata_filters.get("tenant_id") == "user-tenant":
            return [], {"k_returned": 0}
        return [], {"k_returned": 0}

    monkeypatch.setattr(knowledge_tool, "hybrid_retrieve", _fake_hybrid_retrieve)

    payload = knowledge_tool.search_technical_docs(
        query="Kyrolon 79X",
        tenant_id="user-tenant",
        metadata_filters={"additional_metadata.trade_name": "Kyrolon 79X"},
        k=5,
    )

    assert payload["hits"] == []
    assert payload["retrieval_meta"].get("tenant_filter_relaxed") is not True
    assert calls[0]["tenant_id"] == ["user-tenant", "sealai"]
    assert calls[0]["additional_metadata.trade_name"] == "Kyrolon 79X"
    assert len(calls) == 1


def test_execute_tool_call_forwards_metadata_filters(monkeypatch) -> None:
    captured: Dict[str, Any] = {}

    def _fake_search_technical_docs(
        query: str,
        material_code: str | None = None,
        *,
        tenant_id: str | None = None,
        k: int = 5,
        metadata_filters: Dict[str, Any] | None = None,
    ):
        captured["query"] = query
        captured["material_code"] = material_code
        captured["tenant_id"] = tenant_id
        captured["k"] = k
        captured["metadata_filters"] = metadata_filters
        return {
            "tool": "search_technical_docs",
            "query": query,
            "material_code": material_code,
            "metadata_filters": metadata_filters or {},
            "hits": [],
            "context": "No technical documents matched the query.",
            "retrieval_meta": {},
        }

    monkeypatch.setattr(knowledge_tool, "search_technical_docs", _fake_search_technical_docs)

    result = knowledge_tool.execute_tool_call(
        tool_name="search_technical_docs",
        arguments={
            "query": "Kyrolon 79X",
            "metadata_filters": {"additional_metadata.trade_name": "Kyrolon 79X"},
        },
        tenant_id="tenant-1",
    )

    assert result["structuredContent"]["query"] == "Kyrolon 79X"
    assert captured["tenant_id"] == "tenant-1"
    assert captured["metadata_filters"] == {"additional_metadata.trade_name": "Kyrolon 79X"}


def test_get_permitted_tools_scope_filtering() -> None:
    tools_no_scope = knowledge_tool.get_permitted_tools(["openid"])
    assert tools_no_scope == []

    tools_erp = knowledge_tool.get_permitted_tools(["mcp:erp:read"])
    names_erp = {tool.name for tool in tools_erp}
    assert "pricing_tool" in names_erp
    assert "stock_check_tool" in names_erp
    assert "approve_discount" not in names_erp

    tools_admin = knowledge_tool.get_permitted_tools(["mcp:sales:admin"])
    names_admin = {tool.name for tool in tools_admin}
    assert "approve_discount" in names_admin
