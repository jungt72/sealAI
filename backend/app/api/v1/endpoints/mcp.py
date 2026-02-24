from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.mcp.knowledge_tool import (
    MCP_TRANSPORT_PREFERENCE,
    execute_tool_call,
    get_permitted_tool_specs,
)
from app.schemas.mcp import JsonRpcRequest, JsonRpcResponse
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user

router = APIRouter()


def _jsonrpc_error(
    *,
    request_id: str | int | None,
    code: int,
    message: str,
) -> JsonRpcResponse:
    return JsonRpcResponse(id=request_id, error={"code": code, "message": message})


@router.post("/", response_model=JsonRpcResponse)
async def handle_mcp_request(
    request: JsonRpcRequest,
    user: RequestUser = Depends(get_current_request_user),
) -> JsonRpcResponse:
    visible_tools = get_permitted_tool_specs(list(user.scopes or []))
    visible_tool_names = {tool.get("name") for tool in visible_tools}

    if request.method == "tools/list":
        return JsonRpcResponse(
            id=request.id,
            result={
                "tools": visible_tools,
                # MCP transport policy: Streamable HTTP (JSON-RPC 2.0) first, SSE fallback.
                "transport": dict(MCP_TRANSPORT_PREFERENCE),
            },
        )

    if request.method != "tools/call":
        return _jsonrpc_error(
            request_id=request.id,
            code=-32601,
            message=f"Method not supported: {request.method}",
        )

    params = request.params or {}
    tool_name = str(params.get("name") or "").strip()
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}

    if not tool_name:
        return _jsonrpc_error(request_id=request.id, code=-32602, message="Missing tool name")
    if tool_name not in visible_tool_names:
        return _jsonrpc_error(
            request_id=request.id,
            code=-32601,
            message=f"Method not found or tool not available: {tool_name}",
        )

    try:
        result: Dict[str, Any] = execute_tool_call(
            tool_name=tool_name,
            arguments=arguments,
            tenant_id=canonical_user_id(user),
        )
    except ValueError as exc:
        return _jsonrpc_error(request_id=request.id, code=-32602, message=str(exc))
    except KeyError:
        return _jsonrpc_error(
            request_id=request.id,
            code=-32601,
            message=f"Method not found or tool not available: {tool_name}",
        )
    except Exception:
        return _jsonrpc_error(
            request_id=request.id,
            code=-32603,
            message="Internal MCP tool execution error",
        )

    return JsonRpcResponse(id=request.id, result=result)
