from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _jsonrpc_error(*, request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


async def _get_strict_tenant_user(
    authorization: str | None = Header(default=None),
) -> Any:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ungültig",
        )
    from app.services.auth.dependencies import get_current_request_user_strict_tenant

    return await get_current_request_user_strict_tenant(authorization=authorization)


@router.post("")
async def mcp_jsonrpc(
    payload: Dict[str, Any],
    user: Any = Depends(_get_strict_tenant_user),
) -> JSONResponse:
    request_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(payload, dict):
        return JSONResponse(_jsonrpc_error(request_id=request_id, code=-32600, message="Invalid Request"))
    if payload.get("jsonrpc") != "2.0":
        return JSONResponse(_jsonrpc_error(request_id=request_id, code=-32600, message="Invalid Request"))
    method = payload.get("method")
    if not isinstance(method, str) or not method:
        return JSONResponse(_jsonrpc_error(request_id=request_id, code=-32600, message="Invalid Request"))

    if method == "initialize":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "serverInfo": {"name": "sealai-mcp-stub", "version": "0.1.0"},
                    "capabilities": {"tools": {"listChanged": False}},
                    "tenant_id": user.tenant_id,
                },
            }
        )

    if method == "tools/list":
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [],
                    "tenant_id": user.tenant_id,
                },
            }
        )

    return JSONResponse(_jsonrpc_error(request_id=request_id, code=-32601, message="Method not found"))
