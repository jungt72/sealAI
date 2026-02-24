import asyncio
import importlib
import os
from typing import Any, Dict

os.environ.setdefault("POSTGRES_USER", "sealai")
os.environ.setdefault("POSTGRES_PASSWORD", "secret")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "sealai")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("POSTGRES_DSN", "postgresql://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("postgres_dsn", "postgresql://sealai:secret@localhost:5432/sealai")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_COLLECTION", "sealai")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEXTAUTH_URL", "http://localhost:3000")
os.environ.setdefault("NEXTAUTH_SECRET", "dummy-secret")
os.environ.setdefault("KEYCLOAK_ISSUER", "http://localhost:8080/realms/test")
os.environ.setdefault("KEYCLOAK_JWKS_URL", "http://localhost:8080/realms/test/protocol/openid-connect/certs")
os.environ.setdefault("KEYCLOAK_CLIENT_ID", "sealai-backend")
os.environ.setdefault("KEYCLOAK_CLIENT_SECRET", "client-secret")
os.environ.setdefault("KEYCLOAK_EXPECTED_AZP", "sealai-frontend")

from app.schemas.mcp import JsonRpcRequest
from app.services.auth.dependencies import RequestUser


def _request_user(*, scopes: list[str]) -> RequestUser:
    return RequestUser(
        user_id="alice",
        username="alice",
        sub="alice",
        roles=[],
        scopes=scopes,
    )


def test_mcp_tools_list_hidden_without_scope() -> None:
    endpoint = importlib.import_module("app.api.v1.endpoints.mcp")
    request = JsonRpcRequest(jsonrpc="2.0", id="1", method="tools/list", params={})
    response = asyncio.run(endpoint.handle_mcp_request(request, user=_request_user(scopes=["openid"])))
    assert response.error is None
    assert response.result["tools"] == []


def test_mcp_tools_list_visible_with_knowledge_scope() -> None:
    endpoint = importlib.import_module("app.api.v1.endpoints.mcp")
    request = JsonRpcRequest(jsonrpc="2.0", id="1", method="tools/list", params={})
    response = asyncio.run(
        endpoint.handle_mcp_request(
            request,
            user=_request_user(scopes=["openid", "mcp:knowledge:read"]),
        )
    )
    assert response.error is None
    tools = response.result["tools"]
    assert any(tool.get("name") == "search_technical_docs" for tool in tools)
    assert any(tool.get("name") == "get_available_filters" for tool in tools)
    assert response.result["transport"]["primary"] == "streamable_http"
    assert response.result["transport"]["fallback"] == "sse"


def test_mcp_tools_list_hides_erp_tools_without_erp_scope() -> None:
    endpoint = importlib.import_module("app.api.v1.endpoints.mcp")
    request = JsonRpcRequest(jsonrpc="2.0", id="1", method="tools/list", params={})
    response = asyncio.run(
        endpoint.handle_mcp_request(
            request,
            user=_request_user(scopes=["openid", "mcp:knowledge:read"]),
        )
    )
    tool_names = {tool.get("name") for tool in response.result["tools"]}
    assert "pricing_tool" not in tool_names
    assert "stock_check_tool" not in tool_names
    assert "approve_discount" not in tool_names


def test_mcp_tools_list_exposes_erp_and_admin_tools_by_scope() -> None:
    endpoint = importlib.import_module("app.api.v1.endpoints.mcp")
    request = JsonRpcRequest(jsonrpc="2.0", id="1", method="tools/list", params={})
    response = asyncio.run(
        endpoint.handle_mcp_request(
            request,
            user=_request_user(scopes=["mcp:erp:read", "mcp:sales:admin"]),
        )
    )
    tool_names = {tool.get("name") for tool in response.result["tools"]}
    assert "pricing_tool" in tool_names
    assert "stock_check_tool" in tool_names
    assert "approve_discount" in tool_names


def test_mcp_tools_call_executes_when_scope_is_present(monkeypatch) -> None:
    endpoint = importlib.import_module("app.api.v1.endpoints.mcp")

    def _fake_execute_tool_call(*, tool_name: str, arguments: Dict[str, Any], tenant_id: str):
        assert tool_name == "search_technical_docs"
        assert tenant_id == "alice"
        return {
            "content": [{"type": "text", "text": "stub hit"}],
            "structuredContent": {"query": arguments.get("query"), "hits": [{"document_id": "NBR-90"}]},
        }

    monkeypatch.setattr(endpoint, "execute_tool_call", _fake_execute_tool_call)
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id="1",
        method="tools/call",
        params={
            "name": "search_technical_docs",
            "arguments": {"query": "NBR-90 data sheet"},
        },
    )
    response = asyncio.run(
        endpoint.handle_mcp_request(
            request,
            user=_request_user(scopes=["openid", "mcp:pim:read"]),
        )
    )
    assert response.error is None
    assert response.result["content"][0]["text"] == "stub hit"


def test_mcp_get_available_filters_call_executes_when_scope_is_present(monkeypatch) -> None:
    endpoint = importlib.import_module("app.api.v1.endpoints.mcp")

    def _fake_execute_tool_call(*, tool_name: str, arguments: Dict[str, Any], tenant_id: str):
        assert tool_name == "get_available_filters"
        assert tenant_id == "alice"
        return {
            "content": [{"type": "text", "text": "filters stub"}],
            "structuredContent": {"filters": ["material_code", "additional_metadata.density_kg_m3"]},
        }

    monkeypatch.setattr(endpoint, "execute_tool_call", _fake_execute_tool_call)
    request = JsonRpcRequest(
        jsonrpc="2.0",
        id="1",
        method="tools/call",
        params={
            "name": "get_available_filters",
            "arguments": {"max_points": 100},
        },
    )
    response = asyncio.run(
        endpoint.handle_mcp_request(
            request,
            user=_request_user(scopes=["openid", "mcp:pim:read"]),
        )
    )
    assert response.error is None
    assert "additional_metadata.density_kg_m3" in response.result["structuredContent"]["filters"]
