from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
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
from app.services.auth.dependencies import RequestUser, get_current_request_user

router = APIRouter()
logger = logging.getLogger(__name__)
SSE_DEBUG = os.getenv("SEALAI_SSE_DEBUG") == "1"
PARAM_SYNC_DEBUG = os.getenv("SEALAI_PARAM_SYNC_DEBUG") == "1"
DEDUP_TTL_SEC = int(os.getenv("LANGGRAPH_V2_DEDUP_TTL_SEC", "900"))


def _lg_trace_enabled() -> bool:
    return os.getenv("SEALAI_LG_TRACE") == "1"

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional dependency
    Redis = None

CONFIRM_GO_AS_NODE = "confirm_recommendation_node"
PARAMETERS_PATCH_AS_NODE = "supervisor_policy_node"


class LangGraphV2Request(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: str = Field(default="", description="User prompt")
    chat_id: str = Field(default="default", description="Conversation/thread id")
    client_msg_id: Optional[str] = Field(default=None, description="Client message id for tracing")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional client metadata")


def _format_sse(event: str, payload: Dict[str, Any], *, event_id: str | None = None) -> bytes:
    prefix = f"id: {event_id}\n" if event_id else ""
    return (
        prefix + f"event: {event}\n" + f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    ).encode("utf-8")


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


async def _build_graph_config(
    *, thread_id: str, user_id: str, username: str | None = None
) -> tuple[Any, Dict[str, Any]]:
    graph = await get_sealai_graph_v2()
    config = build_v2_config(thread_id=thread_id, user_id=user_id)
    configurable = config.setdefault("configurable", {})
    configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
    if username:
        metadata = config.setdefault("metadata", {})
        metadata["username"] = username
    return graph, config


async def _run_graph_to_state(req: LangGraphV2Request, *, user_id: str, username: str | None = None) -> SealAIState:
    graph, config = await _build_graph_config(thread_id=req.chat_id, user_id=user_id, username=username)
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
    text_attr = getattr(token, "text", None)
    if isinstance(text_attr, str) and text_attr:
        return text_attr
    content_attr = getattr(token, "content", None)
    if isinstance(content_attr, str) and content_attr:
        return content_attr
    text = _flatten_message_content(token)
    return text if text else None


def _is_message_chunk(token: BaseMessage) -> bool:
    if isinstance(token, AIMessageChunk):
        return True
    return token.__class__.__name__.endswith("Chunk")


def _parse_last_event_id(last_event_id: str | None, *, base_id: str) -> int:
    if not last_event_id:
        return 1
    if ":" in last_event_id:
        prefix, _, seq_raw = last_event_id.rpartition(":")
        if prefix != base_id:
            return 1
        try:
            return int(seq_raw) + 1
        except (TypeError, ValueError):
            return 1
    if last_event_id.isdigit():
        return int(last_event_id) + 1
    return 1


def _get_dict_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _extract_trace_node(*, meta: Any = None, data: Any = None, state: Any = None) -> str | None:
    for source in (meta, data):
        node_value = _get_dict_value(source, "node") or _get_dict_value(source, "name")
        if isinstance(node_value, str) and node_value:
            return node_value
        metadata = _get_dict_value(source, "metadata")
        node_value = _get_dict_value(metadata, "node") or _get_dict_value(metadata, "name")
        if isinstance(node_value, str) and node_value:
            return node_value
    if isinstance(state, SealAIState):
        return state.last_node
    if isinstance(state, dict):
        node_value = state.get("last_node") or state.get("node") or state.get("name")
        return node_value if isinstance(node_value, str) else None
    return None


def _extract_trace_phase(*, data: Any = None, state: Any = None) -> str | None:
    phase_value = _get_dict_value(data, "phase")
    if isinstance(phase_value, str) and phase_value:
        return phase_value
    if isinstance(state, SealAIState):
        return state.phase
    if isinstance(state, dict):
        phase_value = state.get("phase")
        return phase_value if isinstance(phase_value, str) else None
    return None


def _extract_trace_action(*, data: Any = None, state: Any = None) -> str | None:
    for key in ("supervisor_action", "supervisor_decision", "action"):
        action_value = _get_dict_value(data, key)
        if isinstance(action_value, str) and action_value:
            return action_value
    working_memory = _get_dict_value(data, "working_memory")
    action_value = _get_dict_value(working_memory, "supervisor_decision")
    if isinstance(action_value, str) and action_value:
        return action_value
    if isinstance(state, SealAIState):
        action_value = getattr(state.working_memory, "supervisor_decision", None)
        return action_value if isinstance(action_value, str) else None
    if isinstance(state, dict):
        working_memory = state.get("working_memory")
        action_value = _get_dict_value(working_memory, "supervisor_decision")
        return action_value if isinstance(action_value, str) else None
    return None


def _build_trace_payload(
    *,
    mode: str,
    data: Any,
    meta: Any,
    state: Any,
) -> Dict[str, str]:
    node_name = _extract_trace_node(meta=meta, data=data, state=state)
    phase = _extract_trace_phase(data=data, state=state)
    action = _extract_trace_action(data=data, state=state)
    payload = {
        "node": node_name,
        "type": mode,
        "phase": phase,
        "action": action,
    }
    return {key: value for key, value in payload.items() if value}


_DEDUP_REDIS: Redis | None = None


async def _get_dedup_redis() -> Redis | None:
    global _DEDUP_REDIS
    if _DEDUP_REDIS is not None:
        return _DEDUP_REDIS
    if Redis is None:
        return None
    conn_string = os.getenv("LANGGRAPH_V2_REDIS_URL") or os.getenv("REDIS_URL")
    if not conn_string:
        return None
    _DEDUP_REDIS = Redis.from_url(conn_string, decode_responses=True)
    return _DEDUP_REDIS


async def _claim_client_msg_id(*, user_id: str, chat_id: str, client_msg_id: str) -> bool:
    if not client_msg_id:
        return True
    client = await _get_dedup_redis()
    if client is None:
        return True
    key = f"langgraph_v2:dedup:{user_id}:{chat_id}:{client_msg_id}"
    try:
        claimed = await client.set(key, "1", nx=True, ex=DEDUP_TTL_SEC)
        return bool(claimed)
    except Exception:
        logger.exception("langgraph_v2_dedup_failed", extra={"chat_id": chat_id, "user": user_id})
        return True


async def _event_stream_v2(
    req: LangGraphV2Request,
    *,
    user_id: str,
    request_id: str | None = None,
    last_event_id: str | None = None,
) -> AsyncIterator[bytes]:
    stream_task: asyncio.Task[None] | None = None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    try:
        base_id = req.client_msg_id or request_id or str(uuid.uuid4())
        seq = _parse_last_event_id(last_event_id, base_id=base_id)
        graph, config = await _build_graph_config(thread_id=req.chat_id, user_id=user_id)
        trace_enabled = _lg_trace_enabled()
        metadata = config.get("metadata") if isinstance(config, dict) else {}
        run_id = metadata.get("run_id") if isinstance(metadata, dict) else None
        initial_state = SealAIState(
            user_id=user_id,
            thread_id=req.chat_id,
            messages=[HumanMessage(content=req.input)],
        )

        emitted_any_token = False
        token_count = 0
        done_sent = False
        latest_state: SealAIState | Dict[str, Any] = initial_state
        last_trace_signature: tuple[Any, Any, Any, Any] | None = None

        async def _emit_trace(mode: str, *, data: Any = None, meta: Any = None, state: Any = None) -> None:
            nonlocal seq, last_trace_signature
            if not trace_enabled:
                return
            payload = _build_trace_payload(mode=mode, data=data, meta=meta, state=state)
            if not payload:
                return
            signature = (
                payload.get("node"),
                payload.get("type"),
                payload.get("phase"),
                payload.get("action"),
            )
            if signature == last_trace_signature:
                return
            last_trace_signature = signature
            payload["ts"] = datetime.utcnow().isoformat() + "Z"
            logger.info(
                "langgraph_v2_trace",
                extra={
                    "thread_id": req.chat_id,
                    "chat_id": req.chat_id,
                    "user_id": user_id,
                    "run_id": run_id,
                    "request_id": request_id,
                    "node": payload.get("node"),
                    "event_type": payload.get("type"),
                    "phase": payload.get("phase"),
                    "supervisor_action": payload.get("action"),
                },
            )
            event_id = f"{base_id}:{seq}"
            seq += 1
            await queue.put(_format_sse("trace", payload, event_id=event_id))

        async def _producer() -> None:
            nonlocal emitted_any_token, latest_state, token_count, done_sent, seq
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
                                event_id = f"{base_id}:{seq}"
                                seq += 1
                                await queue.put(
                                    _format_sse(
                                        "token",
                                        {"type": "token", "text": text},
                                        event_id=event_id,
                                    )
                                )
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
                                await _emit_trace("messages", data=None, meta=meta, state=latest_state)
                            continue

                        if mode == "values":
                            if isinstance(data, SealAIState):
                                latest_state = data
                            elif isinstance(data, dict):
                                latest_state = data
                            await _emit_trace("values", data=data, meta=None, state=latest_state)
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
                    event_id = f"{base_id}:{seq}"
                    seq += 1
                    await queue.put(
                        _format_sse("confirm_checkpoint", payload, event_id=event_id)
                    )
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
                        event_id = f"{base_id}:{seq}"
                        seq += 1
                        await queue.put(
                            _format_sse(
                                "token",
                                {"type": "token", "text": chunk},
                                event_id=event_id,
                            )
                        )
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
                event_id = f"{base_id}:{seq}"
                seq += 1
                await queue.put(_format_sse("done", done_payload, event_id=event_id))
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
                logger.exception(
                    "langgraph_v2_sse_stream_error",
                    extra={
                        "request_id": request_id,
                        "chat_id": req.chat_id,
                        "client_msg_id": req.client_msg_id,
                        "thread_id": req.chat_id,
                        "user_id": user_id,
                        "supervisor_mode": os.getenv("LANGGRAPH_V2_SUPERVISOR_MODE"),
                    },
                )
                message = (
                    "dependency_unavailable"
                    if is_dependency_unavailable_error(exc)
                    else "internal_error"
                )
                event_id = f"{base_id}:{seq}"
                seq += 1
                await queue.put(
                    _format_sse(
                        "error",
                        {"type": "error", "message": message, "request_id": request_id},
                        event_id=event_id,
                    )
                )
                event_id = f"{base_id}:{seq}"
                seq += 1
                await queue.put(
                    _format_sse(
                        "done",
                        {
                            "type": "done",
                            "chat_id": req.chat_id,
                            "request_id": request_id,
                            "client_msg_id": req.client_msg_id,
                        },
                        event_id=event_id,
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
        event_id = f"{req.client_msg_id or request_id or 'stream'}:1"
        yield _format_sse(
            "done",
            {
                "type": "done",
                "chat_id": req.chat_id,
                "request_id": request_id,
                "client_msg_id": req.client_msg_id,
            },
            event_id=event_id,
        )
        return
    except Exception as exc:  # pragma: no cover
        logger.exception(
            "langgraph_v2_sse_outer_error",
            extra={
                "request_id": request_id,
                "chat_id": req.chat_id,
                "client_msg_id": req.client_msg_id,
                "thread_id": req.chat_id,
                "user_id": user_id,
                "supervisor_mode": os.getenv("LANGGRAPH_V2_SUPERVISOR_MODE"),
            },
        )
        message = "dependency_unavailable" if is_dependency_unavailable_error(exc) else "internal_error"
        event_id = f"{req.client_msg_id or request_id or 'stream'}:1"
        yield _format_sse(
            "error",
            {"type": "error", "message": message, "request_id": request_id},
            event_id=event_id,
        )
        event_id = f"{req.client_msg_id or request_id or 'stream'}:2"
        yield _format_sse(
            "done",
            {
                "type": "done",
                "chat_id": req.chat_id,
                "request_id": request_id,
                "client_msg_id": req.client_msg_id,
            },
            event_id=event_id,
        )
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()


@router.post("/chat/v2")
async def langgraph_chat_v2_endpoint(
    request: LangGraphV2Request,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> StreamingResponse:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    last_event_id = raw_request.headers.get("Last-Event-ID")
    if request.client_msg_id:
        claimed = await _claim_client_msg_id(
            user_id=user.user_id,
            chat_id=request.chat_id,
            client_msg_id=request.client_msg_id,
        )
        if not claimed:
            raise HTTPException(
                status_code=409,
                detail=error_detail(
                    "duplicate_client_msg_id",
                    request_id=request_id,
                    client_msg_id=request.client_msg_id,
                ),
            )
    logger.info(
        "langgraph_v2_chat_request",
        extra={
            "request_id": request_id,
            "chat_id": request.chat_id,
            "user": user.user_id,
            "username": user.username,
            "client_msg_id": request.client_msg_id,
            "last_event_id": last_event_id,
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
        _event_stream_v2(
            request,
            user_id=user.user_id,
            request_id=request_id,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers=headers,
    )


@router.post("/confirm/go")
async def confirm_go(
    body: ConfirmGoRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    try:
        if not (body.chat_id or "").strip():
            raise HTTPException(status_code=400, detail=error_detail("missing_chat_id", request_id=request_id))
        graph, config = await _build_graph_config(
            thread_id=body.chat_id,
            user_id=user.user_id,
            username=user.username,
        )
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
            extra={"request_id": request_id, "chat_id": body.chat_id, "user": user.user_id},
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc


@router.post("/parameters/patch")
async def patch_parameters(
    body: ParametersPatchRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
) -> Dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    chat_id = (body.chat_id or "").strip()
    try:
        if PARAM_SYNC_DEBUG:
            logger.info(
                "langgraph_v2_parameters_patch_payload",
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "parameters": body.parameters,
                },
            )
        if not chat_id:
            raise HTTPException(status_code=400, detail=error_detail("missing_chat_id", request_id=request_id))
        patch = sanitize_v2_parameter_patch(body.parameters)
        if not patch:
            raise HTTPException(status_code=400, detail=error_detail("missing_parameters", request_id=request_id))

        graph, config = await _build_graph_config(
            thread_id=chat_id,
            user_id=user.user_id,
            username=user.username,
        )
        assert_node_exists(graph, PARAMETERS_PATCH_AS_NODE, request_id=request_id)
        snapshot = await graph.aget_state(config)
        state_values = snapshot.values if isinstance(snapshot.values, dict) else {}
        existing_params = state_values.get("parameters") if isinstance(state_values, dict) else {}
        merged = merge_parameters(existing_params, patch)

        if PARAM_SYNC_DEBUG:
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            logger.info(
                "langgraph_v2_parameters_patch_debug",
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "user": user.user_id,
                    "patch_keys": sorted(patch.keys()),
                    "merged_keys": sorted(merged.keys()) if isinstance(merged, dict) else [],
                    "checkpoint_thread_id": configurable.get("thread_id"),
                    "checkpoint_ns": configurable.get("checkpoint_ns"),
                },
            )

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
        if PARAM_SYNC_DEBUG:
            logger.warning(
                "langgraph_v2_parameters_patch_invalid_update",
                exc_info=exc,
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "patch_keys": sorted(patch.keys()) if isinstance(patch, dict) else [],
                },
            )
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
                "user": user.user_id,
                "patch_keys": sorted(patch.keys()),
            },
        )
        raise HTTPException(
            status_code=500,
            detail=error_detail("internal_error", request_id=request_id),
        ) from exc


__all__ = ["LangGraphV2Request"]
