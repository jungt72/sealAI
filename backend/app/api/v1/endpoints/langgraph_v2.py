from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER
from langgraph.errors import InvalidUpdateError

from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.contracts import assert_node_exists, error_detail, is_dependency_unavailable_error
from app.langgraph_v2.utils.confirm_checkpoint import build_confirm_checkpoint_payload
from app.langgraph_v2.utils.confirm_go import ConfirmGoRequest
from app.langgraph_v2.utils.parameter_patch import (
    ParametersPatchRequest,
    merge_parameters,
    sanitize_v2_parameter_patch,
)
from app.services.auth.dependencies import get_current_request_user

router = APIRouter()
logger = logging.getLogger(__name__)

CONFIRM_GO_AS_NODE = "confirm_recommendation_node"
PARAMETERS_PATCH_AS_NODE = "supervisor_logic_node"


class LangGraphV2Request(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: str = Field(default="", description="User prompt")
    chat_id: str = Field(default="default", description="Conversation/thread id")
    client_msg_id: Optional[str] = Field(default=None, description="Client message id for tracing")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional client metadata")


def _format_sse(event: str, payload: Dict[str, Any]) -> bytes:
    return (f"event: {event}\n" + f"data: {json.dumps(payload, ensure_ascii=False)}\n\n").encode(
        "utf-8"
    )


def _chunk_text(text: str, *, max_len: int = 700) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


async def _build_graph_config(*, thread_id: str, user_id: str) -> tuple[Any, Dict[str, Any]]:
    graph = await get_sealai_graph_v2()
    config = build_v2_config(thread_id=thread_id, user_id=user_id)
    configurable = config.setdefault("configurable", {})
    configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
    return graph, config


async def _run_graph_to_state(req: LangGraphV2Request, *, user_id: str) -> SealAIState:
    graph, config = await _build_graph_config(thread_id=req.chat_id, user_id=user_id)
    initial_state = SealAIState(
        user_id=user_id,
        thread_id=req.chat_id,
        messages=[HumanMessage(content=req.input)],
    )
    result = await graph.ainvoke(initial_state, config=config)
    if isinstance(result, SealAIState):
        return result
    if isinstance(result, dict):
        return SealAIState(**result)
    raise TypeError(f"Unexpected graph result type: {type(result).__name__}")


def _should_emit_confirm_checkpoint(state: SealAIState) -> bool:
    if (state.phase or "") == "confirm":
        return True
    if (state.last_node or "") == "confirm_recommendation_node":
        return True
    return False


async def _event_stream_v2(req: LangGraphV2Request, *, user_id: str) -> AsyncIterator[bytes]:
    task: asyncio.Task[SealAIState] | None = None
    try:
        task = asyncio.create_task(_run_graph_to_state(req, user_id=user_id))
        while True:
            done, _pending = await asyncio.wait({task}, timeout=15.0)
            if done:
                break
            yield b": keepalive\n\n"

        result_state = task.result()

        if _should_emit_confirm_checkpoint(result_state):
            yield _format_sse("confirm_checkpoint", build_confirm_checkpoint_payload(result_state))

        final_text = (result_state.final_text or "").strip()
        if final_text:
            for chunk in _chunk_text(final_text):
                yield _format_sse("token", {"type": "token", "text": chunk})

        yield _format_sse("done", {"type": "done"})
    except asyncio.CancelledError:
        yield _format_sse("done", {"type": "done"})
        return
    except Exception as exc:  # pragma: no cover
        yield _format_sse("error", {"type": "error", "message": str(exc)})
        yield _format_sse("done", {"type": "done"})
    finally:
        if task and not task.done():
            task.cancel()


@router.post("/chat/v2")
async def langgraph_chat_v2_endpoint(
    request: LangGraphV2Request,
    raw_request: Request,
    username: str = Depends(get_current_request_user),
) -> StreamingResponse:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    logger.info(
        "langgraph_v2_chat_request",
        extra={
            "request_id": request_id,
            "chat_id": request.chat_id,
            "user": username,
            "client_msg_id": request.client_msg_id,
        },
    )
    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    if request_id:
        headers["X-Request-Id"] = request_id
    return StreamingResponse(
        _event_stream_v2(request, user_id=username),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/confirm/go")
async def confirm_go(
    body: ConfirmGoRequest,
    raw_request: Request,
    username: str = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    try:
        if not (body.chat_id or "").strip():
            raise HTTPException(status_code=400, detail=error_detail("missing_chat_id", request_id=request_id))
        graph, config = await _build_graph_config(thread_id=body.chat_id, user_id=username)
        assert_node_exists(
            graph,
            CONFIRM_GO_AS_NODE,
            request_id=request_id,
            status_code=500,
            code="server_misconfigured",
        )
        await graph.aupdate_state(
            config,
            {"recommendation_go": bool(body.go)},
            as_node=CONFIRM_GO_AS_NODE,
        )
        return {"ok": True, "chat_id": body.chat_id, "recommendation_go": bool(body.go)}
    except HTTPException:
        raise
    except InvalidUpdateError as exc:
        raise HTTPException(
            status_code=400,
            detail=error_detail("invalid_as_node", request_id=request_id, message=str(exc)),
        ) from exc
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "langgraph_v2_confirm_go_error",
            extra={"request_id": request_id, "chat_id": body.chat_id, "user": username},
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc


@router.post("/parameters/patch")
async def patch_parameters(
    body: ParametersPatchRequest,
    raw_request: Request,
    username: str = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    chat_id = (body.chat_id or "").strip()
    try:
        if not chat_id:
            raise HTTPException(status_code=400, detail=error_detail("missing_chat_id", request_id=request_id))
        patch = sanitize_v2_parameter_patch(body.parameters)
        if not patch:
            raise HTTPException(status_code=400, detail=error_detail("missing_parameters", request_id=request_id))

        graph, config = await _build_graph_config(thread_id=chat_id, user_id=username)
        assert_node_exists(graph, PARAMETERS_PATCH_AS_NODE, request_id=request_id)
        snapshot = await graph.aget_state(config)
        state_values = snapshot.values if isinstance(snapshot.values, dict) else {}
        existing_params = state_values.get("parameters") if isinstance(state_values, dict) else {}
        merged = merge_parameters(existing_params, patch)

        await graph.aupdate_state(
            config,
            {"parameters": merged},
            # LangGraph requires `as_node` to be an existing node in the compiled graph.
            # Parameter patches are UI-driven and should not advance the graph; we attach
            # the update to a stable, always-present node.
            as_node=PARAMETERS_PATCH_AS_NODE,
        )
        return {"ok": True, "chat_id": body.chat_id, "updated": patch}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=error_detail("invalid_parameters", request_id=request_id, message=str(exc)),
        ) from exc
    except InvalidUpdateError as exc:
        raise HTTPException(
            status_code=400,
            detail=error_detail("invalid_as_node", request_id=request_id, message=str(exc)),
        ) from exc
    except Exception as exc:
        if is_dependency_unavailable_error(exc):
            raise HTTPException(
                status_code=503,
                detail=error_detail("dependency_unavailable", request_id=request_id),
            ) from exc
        logger.exception(
            "langgraph_v2_parameters_patch_error",
            extra={
                "request_id": request_id,
                "chat_id": chat_id,
                "user": username,
                "patch_keys": sorted(patch.keys()),
            },
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc


__all__ = ["LangGraphV2Request"]
