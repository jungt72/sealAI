from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.messages.ai import AIMessageChunk
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
SSE_DEBUG = os.getenv("SEALAI_SSE_DEBUG") == "1"

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


def _flatten_message_content(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict):
                text_value = chunk.get("text") or chunk.get("content")
                if text_value is None:
                    continue
                parts.append(str(text_value))
            else:
                parts.append(str(chunk))
        return "".join(parts)
    if isinstance(content, dict):
        text_value = content.get("text") or content.get("content")
        return str(text_value) if text_value is not None else str(content)
    if content is None:
        return ""
    return str(content)


def _extract_stream_token_text(token: Any) -> str | None:
    if token is None:
        return None
    if isinstance(token, BaseMessage) and not _is_message_chunk(token):
        return None
    text = _flatten_message_content(token)
    return text if text else None


def _is_message_chunk(token: BaseMessage) -> bool:
    if isinstance(token, AIMessageChunk):
        return True
    return token.__class__.__name__.endswith("Chunk")


async def _event_stream_v2(
    req: LangGraphV2Request,
    *,
    user_id: str,
    request_id: str | None = None,
) -> AsyncIterator[bytes]:
    stream_task: asyncio.Task[None] | None = None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    try:
        graph, config = await _build_graph_config(thread_id=req.chat_id, user_id=user_id)
        initial_state = SealAIState(
            user_id=user_id,
            thread_id=req.chat_id,
            messages=[HumanMessage(content=req.input)],
        )

        emitted_any_token = False
        token_count = 0
        done_sent = False
        latest_state: SealAIState | Dict[str, Any] = initial_state

        async def _producer() -> None:
            nonlocal emitted_any_token, latest_state
            try:
                iterator = graph.astream(
                    initial_state,
                    config=config,
                    stream_mode=["messages", "values"],
                ).__aiter__()

                while True:
                    try:
                        item = await asyncio.wait_for(iterator.__anext__(), timeout=15.0)
                    except asyncio.TimeoutError:
                        await queue.put(b": keepalive\n\n")
                        continue
                    except StopAsyncIteration:
                        break

                    if (
                        isinstance(item, tuple)
                        and len(item) == 2
                        and isinstance(item[0], str)
                    ):
                        mode, data = item
                        if mode == "messages":
                            token: Any
                            meta: Any
                            if isinstance(data, tuple) and len(data) == 2:
                                token, meta = data
                            else:
                                token, meta = data, None

                            text = _extract_stream_token_text(token)
                            if text:
                                emitted_any_token = True
                                token_count += 1
                                await queue.put(_format_sse("token", {"type": "token", "text": text}))
                                if SSE_DEBUG:
                                    logger.info(
                                        "langgraph_v2_sse_event",
                                        extra={
                                            "event_type": "token",
                                            "data_len": len(text),
                                            "token_count": token_count,
                                            "done_sent": done_sent,
                                            "request_id": request_id,
                                            "chat_id": req.chat_id,
                                        },
                                    )
                            continue

                        if mode == "values":
                            if isinstance(data, SealAIState):
                                latest_state = data
                            elif isinstance(data, dict):
                                latest_state = data
                            continue

                    # Unexpected shape: treat as terminal state-like output.
                    if isinstance(item, SealAIState):
                        latest_state = item
                    elif isinstance(item, dict):
                        latest_state = item

                # Finalize from last known state
                result_state = (
                    latest_state
                    if isinstance(latest_state, SealAIState)
                    else SealAIState.model_validate(latest_state or {})
                )

                if _should_emit_confirm_checkpoint(result_state):
                    payload = build_confirm_checkpoint_payload(result_state)
                    await queue.put(_format_sse("confirm_checkpoint", payload))
                    if SSE_DEBUG:
                        logger.info(
                            "langgraph_v2_sse_event",
                            extra={
                                "event_type": "confirm_checkpoint",
                                "data_len": len(json.dumps(payload, ensure_ascii=False)),
                                "token_count": token_count,
                                "done_sent": done_sent,
                                "request_id": request_id,
                                "chat_id": req.chat_id,
                            },
                        )

                final_text = (result_state.final_text or "")
                if (not emitted_any_token) and final_text.strip():
                    for chunk in _chunk_text(final_text.strip()):
                        await queue.put(_format_sse("token", {"type": "token", "text": chunk}))
                        token_count += 1
                        if SSE_DEBUG:
                            logger.info(
                                "langgraph_v2_sse_event",
                                extra={
                                    "event_type": "token_fallback",
                                    "data_len": len(chunk),
                                    "token_count": token_count,
                                    "done_sent": done_sent,
                                    "request_id": request_id,
                                    "chat_id": req.chat_id,
                                },
                            )

                done_payload = {
                    "type": "done",
                    "chat_id": req.chat_id,
                    "request_id": request_id,
                    "client_msg_id": req.client_msg_id,
                    "phase": result_state.phase,
                    "last_node": result_state.last_node,
                }
                await queue.put(_format_sse("done", done_payload))
                done_sent = True
                if SSE_DEBUG:
                    logger.info(
                        "langgraph_v2_sse_event",
                        extra={
                            "event_type": "done",
                            "data_len": len(json.dumps(done_payload, ensure_ascii=False)),
                            "token_count": token_count,
                            "done_sent": done_sent,
                            "request_id": request_id,
                            "chat_id": req.chat_id,
                        },
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                message = (
                    "dependency_unavailable"
                    if is_dependency_unavailable_error(exc)
                    else "internal_error"
                )
                await queue.put(_format_sse("error", {"type": "error", "message": message}))
                await queue.put(
                    _format_sse(
                        "done",
                        {
                            "type": "done",
                            "chat_id": req.chat_id,
                            "request_id": request_id,
                            "client_msg_id": req.client_msg_id,
                        },
                    )
                )
            finally:
                await queue.put(None)

        stream_task = asyncio.create_task(_producer())

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
    except asyncio.CancelledError:
        yield _format_sse(
            "done",
            {
                "type": "done",
                "chat_id": req.chat_id,
                "request_id": request_id,
                "client_msg_id": req.client_msg_id,
            },
        )
        return
    except Exception as exc:  # pragma: no cover
        message = "dependency_unavailable" if is_dependency_unavailable_error(exc) else "internal_error"
        yield _format_sse("error", {"type": "error", "message": message})
        yield _format_sse(
            "done",
            {
                "type": "done",
                "chat_id": req.chat_id,
                "request_id": request_id,
                "client_msg_id": req.client_msg_id,
            },
        )
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()


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
        _event_stream_v2(request, user_id=username, request_id=request_id),
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
