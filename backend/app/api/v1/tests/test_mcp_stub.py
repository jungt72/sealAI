from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.api.v1.endpoints import mcp


def _auth_user() -> Any:
    return SimpleNamespace(
        user_id="user-1",
        tenant_id="tenant-1",
        username="tester",
        sub="sub-1",
        roles=[],
    )


@pytest.mark.anyio
async def test_mcp_requires_auth() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await mcp._get_strict_tenant_user(authorization=None)
    assert exc_info.value.status_code in {401, 403}


@pytest.mark.anyio
async def test_mcp_initialize_ok_with_strict_tenant_user() -> None:
    response = await mcp.mcp_jsonrpc(
        payload={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        user=_auth_user(),
    )
    assert response.status_code == 200
    body = response.body
    import json
    body = json.loads(body.decode("utf-8"))
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["result"]["serverInfo"]["name"] == "sealai-mcp-stub"
    assert body["result"]["tenant_id"] == "tenant-1"


@pytest.mark.anyio
async def test_mcp_tools_list_stub_is_tenant_scoped() -> None:
    response = await mcp.mcp_jsonrpc(
        payload={"jsonrpc": "2.0", "id": "abc", "method": "tools/list"},
        user=_auth_user(),
    )
    assert response.status_code == 200
    import json
    body = json.loads(response.body.decode("utf-8"))
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "abc"
    assert body["result"]["tools"] == []
    assert body["result"]["tenant_id"] == "tenant-1"


@pytest.mark.anyio
async def test_mcp_invalid_jsonrpc_request_returns_error_object() -> None:
    response = await mcp.mcp_jsonrpc(
        payload={"jsonrpc": "1.0", "id": 9, "method": "initialize"},
        user=_auth_user(),
    )
    assert response.status_code == 200
    import json
    body = json.loads(response.body.decode("utf-8"))
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 9
    assert body["error"]["code"] == -32600


@pytest.mark.anyio
async def test_mcp_unknown_method_returns_jsonrpc_method_not_found() -> None:
    response = await mcp.mcp_jsonrpc(
        payload={"jsonrpc": "2.0", "id": 3, "method": "tools/call"},
        user=_auth_user(),
    )
    assert response.status_code == 200
    import json
    body = json.loads(response.body.decode("utf-8"))
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 3
    assert body["error"]["code"] == -32601


def test_mcp_route_uses_strict_tenant_dependency_wrapper() -> None:
    for route in mcp.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.endpoint is not mcp.mcp_jsonrpc:
            continue
        calls = {dep.call for dep in route.dependant.dependencies}
        assert mcp._get_strict_tenant_user in calls
