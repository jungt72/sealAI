from __future__ import annotations
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER

from app.langgraph_v2.contracts import error_detail
from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.utils.threading import (
    reset_current_tenant_id,
    resolve_checkpoint_thread_id,
    set_current_tenant_id,
)
from app.services.auth.dependencies import (
    RequestUser,
    canonical_user_id,
    get_current_request_user_strict_tenant,
)
from app.services.rfq.report_builder import build_rfq_report, rfq_gate_failed

router = APIRouter()


def _state_values_to_dict(values: Any) -> Dict[str, Any]:
    if values is None:
        return {}
    if isinstance(values, dict):
        return dict(values)
    model_dump = getattr(values, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dumped
    try:
        return dict(values)
    except Exception:
        return {}


async def _load_rfq_state(
    *,
    chat_id: str,
    user: RequestUser,
) -> tuple[Dict[str, Any], str]:
    scoped_user_id = canonical_user_id(user)
    checkpoint_thread_id = resolve_checkpoint_thread_id(
        tenant_id=user.tenant_id,
        user_id=scoped_user_id,
        chat_id=chat_id,
    )
    graph = await get_sealai_graph_v2()
    tenant_token = set_current_tenant_id(user.tenant_id)
    try:
        config = build_v2_config(thread_id=chat_id, user_id=scoped_user_id, tenant_id=user.tenant_id)
    finally:
        reset_current_tenant_id(tenant_token)
    configurable = config.setdefault("configurable", {})
    configurable["thread_id"] = checkpoint_thread_id
    configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
    metadata = config.setdefault("metadata", {})
    metadata["thread_id"] = chat_id
    snapshot = await graph.aget_state(config)
    return _state_values_to_dict(getattr(snapshot, "values", None)), checkpoint_thread_id


@router.get("/download")
async def rfq_download(
    raw_request: Request,
    path: str = Query(..., description="Server-Pfad zur PDF"),
    chat_id: str | None = Query(default=None, description="Chat/Thread-ID"),
    user: RequestUser = Depends(get_current_request_user_strict_tenant),
):
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    effective_chat_id = (chat_id or "").strip()
    if not effective_chat_id:
        raise HTTPException(status_code=409, detail=error_detail("rfq_not_ready", request_id=request_id))

    values, _checkpoint_thread_id = await _load_rfq_state(chat_id=effective_chat_id, user=user)
    if rfq_gate_failed(values):
        raise HTTPException(status_code=409, detail=error_detail("rfq_not_ready", request_id=request_id))

    if not os.path.isfile(path):
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(path, filename=os.path.basename(path), media_type="application/pdf")


@router.get("/report")
async def rfq_report(
    raw_request: Request,
    chat_id: str = Query(..., description="Chat/Thread-ID"),
    user: RequestUser = Depends(get_current_request_user_strict_tenant),
):
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    effective_chat_id = (chat_id or "").strip()
    if not effective_chat_id:
        raise HTTPException(status_code=409, detail=error_detail("rfq_not_ready", request_id=request_id))

    values, checkpoint_thread_id = await _load_rfq_state(chat_id=effective_chat_id, user=user)
    if rfq_gate_failed(values):
        raise HTTPException(status_code=409, detail=error_detail("rfq_not_ready", request_id=request_id))

    try:
        report = build_rfq_report(
            state=values,
            chat_id=effective_chat_id,
            checkpoint_thread_id=checkpoint_thread_id,
            tenant_id=user.tenant_id,
            user_id=canonical_user_id(user),
        )
    except ValueError:
        raise HTTPException(status_code=409, detail=error_detail("rfq_not_ready", request_id=request_id))
    return JSONResponse(report)
