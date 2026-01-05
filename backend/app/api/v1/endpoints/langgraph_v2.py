from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
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
from app.langgraph_v2.state import SealAIState, TechnicalParameters
from app.langgraph_v2.contracts import assert_node_exists, error_detail, is_dependency_unavailable_error
from app.langgraph_v2.utils.confirm_checkpoint import build_confirm_checkpoint_payload
from app.langgraph_v2.utils.confirm_go import ConfirmGoRequest
from app.langgraph_v2.utils.parameter_patch import (
    ParametersPatchRequest,
    apply_parameter_patch_lww,
    sanitize_v2_parameter_patch,
)
from app.services.auth.dependencies import RequestUser, canonical_user_id, get_current_request_user
from app.services.chat.conversations import upsert_conversation
from app.services.sse_broadcast import sse_broadcast

router = APIRouter()
logger = logging.getLogger(__name__)
SSE_DEBUG = os.getenv("SEALAI_SSE_DEBUG") == "1"
PARAM_SYNC_DEBUG = os.getenv("SEALAI_PARAM_SYNC_DEBUG") == "1"
DEDUP_TTL_SEC = int(os.getenv("LANGGRAPH_V2_DEDUP_TTL_SEC", "900"))
SSE_RETRY_MS = int(os.getenv("SEALAI_SSE_RETRY_MS", "3000"))
SSE_QUEUE_MAXSIZE = int(os.getenv("SEALAI_SSE_QUEUE_MAXSIZE", "200"))
SSE_SLOW_NOTICE_SEC = float(os.getenv("SEALAI_SSE_SLOW_NOTICE_SEC", "5"))
REQUIRE_PARAM_SNAPSHOT = os.getenv("SEALAI_REQUIRE_PARAM_SNAPSHOT") == "1"
WARN_STALE_PARAM_SNAPSHOT = os.getenv("SEALAI_WARN_STALE_PARAM_SNAPSHOT", "1") == "1"


def _lg_trace_enabled() -> bool:
    return os.getenv("SEALAI_LG_TRACE") == "1"


def _state_values_to_dict(values: Any) -> Dict[str, Any]:
    if values is None:
        return {}
    if isinstance(values, SealAIState):
        return values.model_dump(exclude_none=True)
    if isinstance(values, dict):
        return dict(values)
    try:
        return dict(values)
    except Exception:
        return {}


def _short_user_id(user_id: str | None) -> str:
    if not user_id:
        return ""
    return f"{user_id[:8]}..." if len(user_id) > 8 else user_id

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
    client_context: Dict[str, Any] = Field(default_factory=dict, description="Optional client context")


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


def _config_user_id(config: Dict[str, Any], fallback: str) -> str:
    metadata = config.get("metadata") if isinstance(config, dict) else {}
    if isinstance(metadata, dict):
        value = metadata.get("user_id")
        if isinstance(value, str) and value:
            return value
    return fallback


def _has_checkpoint_state(snapshot: Any) -> bool:
    values = _state_values_to_dict(getattr(snapshot, "values", None))
    return bool(values)


async def _build_graph_config(
    *,
    thread_id: str,
    user_id: str,
    username: str | None = None,
    legacy_user_id: str | None = None,
    request_id: str | None = None,
    allow_legacy_fallback: bool = True,
) -> tuple[Any, Dict[str, Any]]:
    graph = await get_sealai_graph_v2()

    def _attach_config(base_config: Dict[str, Any], *, scoped_user_id: str) -> Dict[str, Any]:
        configurable = base_config.setdefault("configurable", {})
        configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
        if username:
            metadata = base_config.setdefault("metadata", {})
            metadata["username"] = username
            metadata["user_sub"] = scoped_user_id
        return base_config

    config = _attach_config(build_v2_config(thread_id=thread_id, user_id=user_id), scoped_user_id=user_id)
    if not allow_legacy_fallback or not legacy_user_id or legacy_user_id == user_id:
        return graph, config

    try:
        snapshot = await graph.aget_state(config)
        if _has_checkpoint_state(snapshot):
            return graph, config

        legacy_config = _attach_config(
            build_v2_config(thread_id=thread_id, user_id=legacy_user_id),
            scoped_user_id=legacy_user_id,
        )
        legacy_snapshot = await graph.aget_state(legacy_config)
        if _has_checkpoint_state(legacy_snapshot):
            if SSE_DEBUG or PARAM_SYNC_DEBUG or _lg_trace_enabled():
                logger.warning(
                    "langgraph_v2_legacy_thread_fallback",
                    extra={
                        "request_id": request_id,
                        "chat_id": thread_id,
                        "user_id": user_id,
                        "legacy_user_id": legacy_user_id,
                    },
                )
            return graph, legacy_config
    except Exception:
        logger.exception(
            "langgraph_v2_legacy_fallback_failed",
            extra={
                "request_id": request_id,
                "chat_id": thread_id,
                "user_id": user_id,
                "legacy_user_id": legacy_user_id,
            },
        )

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
    if getattr(state, "awaiting_user_confirmation", False):
        return True
    if state.confirm_checkpoint:
        return True
    if (state.phase or "") == "confirm":
        return True
    if (state.last_node or "") == "confirm_recommendation_node":
        return True
    return False


def _build_state_update_payload(state: SealAIState | Dict[str, Any]) -> Dict[str, Any]:
    values = _state_values_to_dict(state)
    parameters = values.get("parameters") if isinstance(values, dict) else {}
    if isinstance(parameters, TechnicalParameters):
        parameters = parameters.model_dump(exclude_none=True)
    payload = {
        "type": "state_update",
        "phase": values.get("phase"),
        "last_node": values.get("last_node"),
        "awaiting_user_input": values.get("awaiting_user_input"),
        "awaiting_user_confirmation": values.get("awaiting_user_confirmation"),
        "recommendation_ready": values.get("recommendation_ready"),
        "recommendation_go": values.get("recommendation_go"),
        "coverage_score": values.get("coverage_score"),
        "coverage_gaps": values.get("coverage_gaps"),
        "missing_params": values.get("missing_params"),
        "parameters": parameters if isinstance(parameters, dict) else {},
        "pending_action": values.get("pending_action"),
        "confirm_checkpoint_id": values.get("confirm_checkpoint_id"),
    }
    return {key: value for key, value in payload.items() if value is not None}


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


def _parse_last_event_id(last_event_id: str | None, *, chat_id: str) -> int | None:
    return sse_broadcast.parse_last_event_id(chat_id, last_event_id)


def _get_dict_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _extract_param_snapshot(req: LangGraphV2Request) -> Dict[str, Any] | None:
    if not isinstance(req.client_context, dict):
        return None
    snapshot = req.client_context.get("param_snapshot")
    return snapshot if isinstance(snapshot, dict) else None


def _snapshot_stats(snapshot: Dict[str, Any] | None) -> tuple[int, float | None]:
    if not snapshot:
        return 0, None
    versions = snapshot.get("versions") if isinstance(snapshot, dict) else None
    updated_at = snapshot.get("updated_at") if isinstance(snapshot, dict) else None
    version_count = len(versions) if isinstance(versions, dict) else 0
    updated_values = []
    if isinstance(updated_at, dict):
        for value in updated_at.values():
            if isinstance(value, (int, float)):
                updated_values.append(float(value))
    return version_count, (max(updated_values) if updated_values else None)


def _snapshot_versions(snapshot: Dict[str, Any] | None) -> Dict[str, int]:
    if not snapshot:
        return {}
    raw = snapshot.get("versions") if isinstance(snapshot, dict) else None
    if not isinstance(raw, dict):
        return {}
    versions: Dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, (int, float)):
            versions[str(key)] = int(value)
    return versions


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
    legacy_user_id: str | None = None,
    request_id: str | None = None,
    last_event_id: str | None = None,
) -> AsyncIterator[bytes]:
    stream_task: asyncio.Task[None] | None = None
    broadcast_task: asyncio.Task[None] | None = None
    broadcast_queue: asyncio.Queue[tuple[int, str, Dict[str, Any]]] | None = None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=SSE_QUEUE_MAXSIZE)
    last_slow_notice = 0.0
    try:
        scoped_user_id = user_id
        graph, config = await _build_graph_config(
            thread_id=req.chat_id,
            user_id=user_id,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        scoped_user_id = _config_user_id(config, user_id)

        async def _enqueue_frame(frame: bytes, *, allow_slow_notice: bool = True) -> None:
            nonlocal last_slow_notice
            if queue.maxsize <= 0:
                queue.put_nowait(frame)
                return

            send_slow_notice = False
            if queue.full():
                now = time.time()
                if allow_slow_notice and now - last_slow_notice >= SSE_SLOW_NOTICE_SEC:
                    send_slow_notice = True
                    last_slow_notice = now

                while queue.qsize() > queue.maxsize - 1:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            if queue.qsize() <= queue.maxsize - 1:
                queue.put_nowait(frame)

            if send_slow_notice and queue.maxsize >= 2:
                while queue.qsize() > queue.maxsize - 1:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                if queue.qsize() <= queue.maxsize - 1:
                    slow_seq = await sse_broadcast.record_event(
                        user_id=scoped_user_id,
                        chat_id=req.chat_id,
                        event="slow_client",
                        data={"reason": "backpressure"},
                    )
                    slow_frame = _format_sse(
                        "slow_client",
                        {"reason": "backpressure"},
                        event_id=str(slow_seq),
                    )
                    queue.put_nowait(slow_frame)

        async def _emit_event(event_name: str, payload: Dict[str, Any]) -> None:
            seq = await sse_broadcast.record_event(
                user_id=scoped_user_id,
                chat_id=req.chat_id,
                event=event_name,
                data=payload,
            )
            frame = _format_sse(event_name, payload, event_id=str(seq))
            await _enqueue_frame(frame)

        broadcast_queue = await sse_broadcast.subscribe(user_id=scoped_user_id, chat_id=req.chat_id)

        async def _broadcast_forwarder() -> None:
            if broadcast_queue is None:
                return
            try:
                while True:
                    item = await broadcast_queue.get()
                    if not item:
                        continue
                    seq, event_name, payload = item
                    frame = _format_sse(event_name, payload, event_id=str(seq))
                    await _enqueue_frame(frame)
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception(
                    "langgraph_v2_sse_broadcast_error",
                    extra={"chat_id": req.chat_id, "user_id": scoped_user_id},
                )

        await _enqueue_frame(f"retry: {SSE_RETRY_MS}\n\n".encode("utf-8"), allow_slow_notice=False)

        last_seq = _parse_last_event_id(last_event_id, chat_id=req.chat_id)
        if last_seq is not None:
            replay, buffer_miss = await sse_broadcast.replay_after(
                user_id=scoped_user_id,
                chat_id=req.chat_id,
                last_seq=last_seq,
            )
            if buffer_miss:
                await _emit_event(
                    "resync_required",
                    {"reason": "buffer_miss"},
                )
            else:
                for item in replay:
                    frame = _format_sse(
                        item.get("event", ""),
                        item.get("data", {}),
                        event_id=str(item.get("seq", 0)),
                    )
                    await _enqueue_frame(frame)

        broadcast_task = asyncio.create_task(_broadcast_forwarder())
        snapshot = _extract_param_snapshot(req)
        snapshot_versions = _snapshot_versions(snapshot)
        if WARN_STALE_PARAM_SNAPSHOT and snapshot_versions:
            try:
                server_snapshot = await graph.aget_state(config)
                state_values = _state_values_to_dict(server_snapshot.values)
                server_versions = (
                    state_values.get("parameter_versions") if isinstance(state_values, dict) else {}
                )
                stale_count = 0
                if isinstance(server_versions, dict):
                    for key, snap_value in snapshot_versions.items():
                        server_value = server_versions.get(key)
                        if isinstance(server_value, (int, float)) and int(snap_value) < int(server_value):
                            stale_count += 1
                if stale_count:
                    logger.warning(
                        "stale_param_snapshot",
                        extra={
                            "request_id": request_id,
                            "chat_id": req.chat_id,
                            "user_id": scoped_user_id,
                            "stale_count": stale_count,
                            "snapshot_versions_count": len(snapshot_versions),
                        },
                    )
            except Exception:
                logger.exception(
                    "param_snapshot_compare_failed",
                    extra={
                        "request_id": request_id,
                        "chat_id": req.chat_id,
                        "user_id": scoped_user_id,
                    },
                )
        trace_enabled = _lg_trace_enabled()
        metadata = config.get("metadata") if isinstance(config, dict) else {}
        run_id = metadata.get("run_id") if isinstance(metadata, dict) else None
        prev_parameters: Dict[str, Any] = {}
        initial_state = SealAIState(
            user_id=scoped_user_id,
            thread_id=req.chat_id,
            messages=[HumanMessage(content=req.input)],
        )

        emitted_any_token = False
        token_count = 0
        done_sent = False
        latest_state: SealAIState | Dict[str, Any] = initial_state
        last_trace_signature: tuple[Any, Any, Any, Any] | None = None
        last_retrieval_signature: tuple[Any, Any] | None = None

        async def _emit_trace(mode: str, *, data: Any = None, meta: Any = None, state: Any = None) -> None:
            nonlocal last_trace_signature
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
            payload["ts"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            logger.info(
                "langgraph_v2_trace",
                    extra={
                        "thread_id": req.chat_id,
                        "chat_id": req.chat_id,
                        "user_id": scoped_user_id,
                        "run_id": run_id,
                        "request_id": request_id,
                        "node": payload.get("node"),
                    "event_type": payload.get("type"),
                    "phase": payload.get("phase"),
                    "supervisor_action": payload.get("action"),
                },
            )
            await _emit_event("trace", payload)

        async def _producer() -> None:
            nonlocal emitted_any_token, latest_state, token_count, done_sent, seq, prev_parameters
            nonlocal last_retrieval_signature
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
                        await _enqueue_frame(b": keepalive\n\n", allow_slow_notice=False)
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
                                await _emit_event(
                                    "token",
                                    {"type": "token", "text": text},
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
                            retrieval_meta: Dict[str, Any] | None = None
                            if isinstance(latest_state, SealAIState):
                                retrieval_meta = latest_state.retrieval_meta
                            elif isinstance(latest_state, dict):
                                raw_meta = latest_state.get("retrieval_meta")
                                if isinstance(raw_meta, dict):
                                    retrieval_meta = raw_meta
                            if isinstance(retrieval_meta, dict) and retrieval_meta:
                                safe_meta = {
                                    key: value
                                    for key, value in retrieval_meta.items()
                                    if key != "context"
                                }
                                event_name = (
                                    "retrieval.skipped"
                                    if retrieval_meta.get("skipped")
                                    else "retrieval.results"
                                )
                                signature = (
                                    event_name,
                                    json.dumps(safe_meta, ensure_ascii=False, sort_keys=True),
                                )
                                if signature != last_retrieval_signature:
                                    await _emit_event(event_name, safe_meta)
                                    last_retrieval_signature = signature
                            payload = _build_state_update_payload(latest_state)
                            if payload:
                                parameters = payload.get("parameters")
                                current_params = parameters if isinstance(parameters, dict) else {}
                                delta_keys = [
                                    key
                                    for key, value in current_params.items()
                                    if key not in prev_parameters or prev_parameters.get(key) != value
                                ]
                                removed_keys = [key for key in prev_parameters.keys() if key not in current_params]
                                if delta_keys or removed_keys:
                                    logger.info(
                                        "langgraph_v2_state_update_params",
                                        extra={
                                            "chat_id": req.chat_id,
                                            "user_id": scoped_user_id,
                                            "run_id": run_id,
                                            "request_id": request_id,
                                            "last_node": payload.get("last_node"),
                                            "phase": payload.get("phase"),
                                            "delta_keys": delta_keys,
                                            "removed_keys": removed_keys,
                                            "pressure_bar_before": prev_parameters.get("pressure_bar"),
                                            "pressure_bar_after": current_params.get("pressure_bar"),
                                        },
                                    )
                                prev_parameters = dict(current_params)
                                provenance: Dict[str, Any] = {}
                                if isinstance(latest_state, SealAIState):
                                    provenance = latest_state.parameter_provenance or {}
                                elif isinstance(latest_state, dict):
                                    prov_value = latest_state.get("parameter_provenance")
                                    if isinstance(prov_value, dict):
                                        provenance = prov_value
                                parameter_meta: Dict[str, Dict[str, Any]] = {}
                                if delta_keys and provenance:
                                    for key in delta_keys:
                                        if provenance.get(key) != "user":
                                            continue
                                        parameter_meta[key] = {
                                            "source": "user",
                                            "force_overwrite": True,
                                        }
                                if parameter_meta:
                                    payload["parameter_meta"] = parameter_meta
                                if PARAM_SYNC_DEBUG and delta_keys:
                                    logger.info(
                                        "langgraph_v2_state_update_meta",
                                        extra={
                                            "chat_id": req.chat_id,
                                            "last_node": payload.get("last_node"),
                                            "delta_keys": delta_keys,
                                            "provenance_by_key": {key: provenance.get(key) for key in delta_keys},
                                            "parameter_meta_attached": bool(parameter_meta),
                                        },
                                    )
                                await _emit_event("state_update", payload)
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
                    payload = (
                        result_state.confirm_checkpoint
                        if isinstance(result_state.confirm_checkpoint, dict) and result_state.confirm_checkpoint
                        else build_confirm_checkpoint_payload(
                            result_state,
                            action=result_state.pending_action or result_state.next_action or "FINALIZE",
                            checkpoint_id=result_state.confirm_checkpoint_id,
                        )
                    )
                    await _emit_event("checkpoint_required", payload)
                    if SSE_DEBUG:
                        logger.info(
                            "langgraph_v2_sse_event",
                            extra={
                                "event_type": "checkpoint_required",
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
                        await _emit_event(
                            "token",
                            {"type": "token", "text": chunk},
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
                    "awaiting_confirmation": bool(result_state.awaiting_user_confirmation),
                    "checkpoint_id": result_state.confirm_checkpoint_id,
                }
                await _emit_event("done", done_payload)
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
                        "user_id": scoped_user_id,
                        "supervisor_mode": os.getenv("LANGGRAPH_V2_SUPERVISOR_MODE"),
                    },
                )
                message = (
                    "dependency_unavailable"
                    if is_dependency_unavailable_error(exc)
                    else "internal_error"
                )
                await _emit_event(
                    "error",
                    {"type": "error", "message": message, "request_id": request_id},
                )
                await _emit_event(
                    "done",
                    {
                        "type": "done",
                        "chat_id": req.chat_id,
                        "request_id": request_id,
                        "client_msg_id": req.client_msg_id,
                    },
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
        done_payload = {
            "type": "done",
            "chat_id": req.chat_id,
            "request_id": request_id,
            "client_msg_id": req.client_msg_id,
        }
        seq = await sse_broadcast.record_event(
            user_id=scoped_user_id,
            chat_id=req.chat_id,
            event="done",
            data=done_payload,
        )
        yield _format_sse("done", done_payload, event_id=str(seq))
        return
    except Exception as exc:  # pragma: no cover
        logger.exception(
            "langgraph_v2_sse_outer_error",
            extra={
                "request_id": request_id,
                "chat_id": req.chat_id,
                "client_msg_id": req.client_msg_id,
                "thread_id": req.chat_id,
                "user_id": scoped_user_id,
                "supervisor_mode": os.getenv("LANGGRAPH_V2_SUPERVISOR_MODE"),
            },
        )
        message = "dependency_unavailable" if is_dependency_unavailable_error(exc) else "internal_error"
        error_payload = {"type": "error", "message": message, "request_id": request_id}
        error_seq = await sse_broadcast.record_event(
            user_id=scoped_user_id,
            chat_id=req.chat_id,
            event="error",
            data=error_payload,
        )
        yield _format_sse("error", error_payload, event_id=str(error_seq))
        done_payload = {
            "type": "done",
            "chat_id": req.chat_id,
            "request_id": request_id,
            "client_msg_id": req.client_msg_id,
        }
        done_seq = await sse_broadcast.record_event(
            user_id=scoped_user_id,
            chat_id=req.chat_id,
            event="done",
            data=done_payload,
        )
        yield _format_sse("done", done_payload, event_id=str(done_seq))
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
        if broadcast_task and not broadcast_task.done():
            broadcast_task.cancel()
        if broadcast_queue is not None:
            await sse_broadcast.unsubscribe(
                user_id=scoped_user_id,
                chat_id=req.chat_id,
                queue=broadcast_queue,
            )


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
    snapshot = _extract_param_snapshot(request)
    version_count, updated_max = _snapshot_stats(snapshot)
    if REQUIRE_PARAM_SNAPSHOT and not snapshot:
        raise HTTPException(
            status_code=400,
            detail=error_detail("missing_param_snapshot", request_id=request_id),
        )
    scoped_user_id = canonical_user_id(user)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None
    if request.client_msg_id:
        claimed = await _claim_client_msg_id(
            user_id=scoped_user_id,
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
    owner_id = user.sub
    if owner_id:
        try:
            upsert_conversation(
                owner_id=owner_id,
                conversation_id=request.chat_id,
                first_user_message=request.input,
                last_preview=request.input,
                updated_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist conversation metadata before streaming",
                exc_info=exc,
                extra={"user": owner_id, "chat_id": request.chat_id},
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
            "param_snapshot_present": bool(snapshot),
            "param_snapshot_versions_count": version_count,
            "param_snapshot_updated_at_max": updated_max,
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
            user_id=scoped_user_id,
            legacy_user_id=legacy_user_id,
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
    scoped_user_id = canonical_user_id(user)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None
    try:
        if not (body.chat_id or "").strip():
            raise HTTPException(status_code=400, detail=error_detail("missing_chat_id", request_id=request_id))
        if not body.decision:
            raise HTTPException(status_code=400, detail=error_detail("missing_decision", request_id=request_id))
        graph, config = await _build_graph_config(
            thread_id=body.chat_id,
            user_id=scoped_user_id,
            username=user.username,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        snapshot = await graph.aget_state(config)
        state_values = _state_values_to_dict(snapshot.values)
        confirm_payload = state_values.get("confirm_checkpoint") if isinstance(state_values, dict) else {}
        confirm_status = state_values.get("confirm_status") if isinstance(state_values, dict) else None
        required_sub = ""
        if isinstance(confirm_payload, dict):
            required_sub = str(confirm_payload.get("required_user_sub") or "")
        pending_action = state_values.get("pending_action") if isinstance(state_values, dict) else None
        if confirm_status == "resolved":
            raise HTTPException(
                status_code=409,
                detail=error_detail("checkpoint_already_resolved", request_id=request_id),
            )
        if not pending_action and not confirm_payload:
            raise HTTPException(
                status_code=409,
                detail=error_detail("no_pending_checkpoint", request_id=request_id),
            )
        if isinstance(confirm_payload, dict):
            conversation_id = str(confirm_payload.get("conversation_id") or "")
            if conversation_id != body.chat_id:
                raise HTTPException(
                    status_code=403,
                    detail=error_detail("checkpoint_conversation_mismatch", request_id=request_id),
                )
        if required_sub and required_sub != scoped_user_id:
            raise HTTPException(status_code=403, detail=error_detail("forbidden", request_id=request_id))
        checkpoint_id = state_values.get("confirm_checkpoint_id") if isinstance(state_values, dict) else None
        if body.checkpoint_id and checkpoint_id and body.checkpoint_id != checkpoint_id:
            raise HTTPException(status_code=409, detail=error_detail("checkpoint_mismatch", request_id=request_id))

        edits_payload = body.edits.model_dump(exclude_none=True) if body.edits else {}
        edit_parameters = {}
        if edits_payload.get("parameters"):
            edit_parameters = sanitize_v2_parameter_patch(edits_payload.get("parameters") or {})
        edits = {
            "parameters": edit_parameters,
            "instructions": (edits_payload.get("instructions") or "").strip() or None,
        }

        assert_node_exists(
            graph,
            "confirm_checkpoint_node",
            request_id=request_id,
            status_code=500,
            code="server_misconfigured",
        )
        await graph.aupdate_state(
            config,
            {
                "confirm_decision": body.decision,
                "confirm_edits": edits,
            },
            as_node="confirm_checkpoint_node",
        )

        result = await graph.ainvoke({}, config=config)
        state = result if isinstance(result, SealAIState) else SealAIState.model_validate(result or {})
        return {
            "ok": True,
            "chat_id": body.chat_id,
            "decision": body.decision,
            "final_text": state.final_text or "",
            "phase": state.phase,
            "last_node": state.last_node,
        }
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
    scoped_user_id = canonical_user_id(user)
    legacy_user_id = user.sub if user.sub and user.sub != scoped_user_id else None
    chat_id = (body.chat_id or "").strip()
    patch: Dict[str, Any] = {}
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
            user_id=scoped_user_id,
            username=user.username,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        assert_node_exists(graph, PARAMETERS_PATCH_AS_NODE, request_id=request_id)
        snapshot = await graph.aget_state(config)
        state_values = _state_values_to_dict(snapshot.values)
        existing_params = state_values.get("parameters") if isinstance(state_values, dict) else {}
        existing_provenance = {}
        existing_versions: Dict[str, int] = {}
        existing_updated_at: Dict[str, float] = {}
        if isinstance(state_values, dict):
            existing_provenance = state_values.get("parameter_provenance") or {}
            existing_versions = state_values.get("parameter_versions") or {}
            existing_updated_at = state_values.get("parameter_updated_at") or {}
        (
            merged,
            merged_provenance,
            merged_versions,
            merged_updated_at,
            applied_fields,
            rejected_fields,
        ) = apply_parameter_patch_lww(
            existing_params,
            patch,
            existing_provenance,
            source="user",
            parameter_versions=existing_versions,
            parameter_updated_at=existing_updated_at,
            base_versions=body.base_versions,
        )

        if PARAM_SYNC_DEBUG:
            patch_keys = sorted(patch.keys())
            types = {key: type(patch.get(key)).__name__ for key in patch_keys}
            before = {}
            after = {}
            if isinstance(existing_params, dict):
                before = {key: existing_params.get(key) for key in patch_keys}
            if isinstance(merged, dict):
                after = {key: merged.get(key) for key in patch_keys}
            configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
            logger.info(
                "langgraph_v2_parameters_patch_debug",
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "user": _short_user_id(user.user_id),
                    "patch_keys": patch_keys,
                    "patch_types": types,
                    "patch_before": before,
                    "patch_after": after,
                    "merged_keys": sorted(merged.keys()) if isinstance(merged, dict) else [],
                    "checkpoint_thread_id": configurable.get("thread_id"),
                    "checkpoint_ns": configurable.get("checkpoint_ns"),
                },
            )

        await graph.aupdate_state(
            config,
            {
                "parameters": merged,
                "parameter_provenance": merged_provenance,
                "parameter_versions": merged_versions,
                "parameter_updated_at": merged_updated_at,
            },
            # LangGraph requires `as_node` to be an existing node in the compiled graph.
            # Parameter patches are UI-driven and should not advance the graph; we attach
            # the update to a stable, always-present node.
            as_node=PARAMETERS_PATCH_AS_NODE,
        )
        response_fields = sorted(patch.keys())
        response_payload = {
            "ok": True,
            "chat_id": body.chat_id,
            "applied_fields": applied_fields,
            "rejected_fields": rejected_fields,
            "versions": {field: merged_versions.get(field, 0) for field in response_fields},
            "updated_at": {field: merged_updated_at.get(field) for field in response_fields},
        }
        ack_payload = {
            "chat_id": body.chat_id,
            "patch": patch,
            "applied_fields": applied_fields,
            "rejected_fields": rejected_fields,
            "versions": response_payload["versions"],
            "updated_at": response_payload["updated_at"],
            "source": "patch_endpoint",
            "request_id": request_id,
        }
        await sse_broadcast.broadcast(
            user_id=scoped_user_id,
            chat_id=chat_id,
            event="parameter_patch_ack",
            data=ack_payload,
        )
        return response_payload
    except HTTPException:
        raise
    except ValueError as exc:
        if PARAM_SYNC_DEBUG:
            logger.warning(
                "langgraph_v2_parameters_patch_invalid_payload",
                extra={
                    "request_id": request_id,
                    "chat_id": chat_id,
                    "user": _short_user_id(user.user_id),
                    "error": str(exc),
                    "patch_keys": sorted(patch.keys()) if isinstance(patch, dict) else [],
                },
            )
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
