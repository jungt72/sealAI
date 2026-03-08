"""Test-only helpers for LangGraph v2 SSE streaming tests.

These functions are NOT called from any production endpoint. They exist solely
to provide test fixtures for SSE streaming behaviour tests.

Both `_event_stream_v2` and `_run_graph_to_state` were removed from
`app.api.v1.endpoints.langgraph_v2` during the v13 refactor because the
production endpoint uses `event_multiplexer` directly. Tests that reference
them must import from this module.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict

from langchain_core.messages import HumanMessage

# Re-import everything from the production module that the moved functions need.
# These remain private helpers in langgraph_v2.py — we import them explicitly
# rather than doing `import *` so the dependency surface is visible.
from app.api.v1.endpoints.langgraph_v2 import (  # noqa: F401
    LangGraphV2Request,
    PARAMETERS_PATCH_AS_NODE,
    PARAM_SYNC_DEBUG,
    SSE_DEBUG,
    SSE_HEARTBEAT_SEC,
    SSE_QUEUE_MAXSIZE,
    SSE_RETRY_MS,
    SSE_SLOW_NOTICE_SEC,
    WARN_STALE_PARAM_SNAPSHOT,
    _build_graph_config,
    _build_state_update_payload,
    _build_trace_payload,
    _config_user_id,
    _conversation_value,
    _extract_final_text_from_patch,
    _extract_param_snapshot,
    _extract_snapshot_checkpoint_id,
    _extract_state_update_source,
    _extract_stream_token_text,
    _extract_terminal_text_candidate,
    _format_sse,
    _get_graph_state_values_for_stream,
    _inject_live_calc_tile,
    _is_meaningful_live_calc_tile,
    _latest_ai_text,
    _lg_trace_enabled,
    _merge_state_like,
    _normalize_live_calc_tile,
    _parse_last_event_id,
    _reasoning_value,
    _resolve_final_text,
    _resolve_stream_node_name,
    _scope_thread_id_for_user,
    _should_emit_confirm_checkpoint,
    _snapshot_versions,
    _snapshot_waiting_on_human_review,
    _state_values_to_dict,
    _system_value,
    _working_profile_value,
    _event_belongs_to_current_run,
)
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.contracts import is_dependency_unavailable_error
from app.services.sse_broadcast import sse_broadcast

logger = logging.getLogger(__name__)


async def _run_graph_to_state(
    req: LangGraphV2Request,
    *,
    user_id: str,
    username: str | None = None,
    auth_scopes: list[str] | None = None,
    tenant_id: str | None = None,
) -> SealAIState:
    scoped_thread_id = _scope_thread_id_for_user(user_id=user_id, thread_id=req.chat_id)
    graph, config = await _build_graph_config(
        thread_id=scoped_thread_id,
        user_id=user_id,
        username=username,
        auth_scopes=auth_scopes,
    )
    initial_state = SealAIState(
        conversation={
            "user_id": user_id,
            "thread_id": scoped_thread_id,
            "messages": [HumanMessage(content=req.input)],
            "user_context": {"auth_scopes": list(auth_scopes or []), "tenant_id": tenant_id},
        },
        system={"tenant_id": tenant_id},
    )
    result = await graph.ainvoke(initial_state, config=config)
    if isinstance(result, SealAIState):
        return result
    if isinstance(result, dict):
        return SealAIState(**result)
    raise TypeError(f"Unexpected graph result type: {type(result).__name__}")


async def _event_stream_v2(
    req: LangGraphV2Request,
    *,
    user_id: str | None = None,
    username: str | None = None,
    auth_scopes: list[str] | None = None,
    tenant_id: str | None = None,
    legacy_user_id: str | None = None,
    request_id: str | None = None,
    last_event_id: str | None = None,
) -> AsyncIterator[bytes]:
    if user_id:
        req.chat_id = _scope_thread_id_for_user(user_id=user_id, thread_id=req.chat_id)
    stream_task: asyncio.Task[None] | None = None
    broadcast_task: asyncio.Task[None] | None = None
    broadcast_queue: asyncio.Queue[tuple[int, str, Dict[str, Any]]] | None = None
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=SSE_QUEUE_MAXSIZE)
    last_slow_notice = 0.0
    scoped_user_id = user_id or "anonymous"
    sticky_live_calc_tile: Dict[str, Any] | None = None
    initial_stream_values: Dict[str, Any] = {}
    try:
        resolved_user_id = user_id or "anonymous"
        scoped_user_id = resolved_user_id
        graph, config = await _build_graph_config(
            thread_id=req.chat_id,
            user_id=resolved_user_id,
            username=username,
            auth_scopes=auth_scopes,
            legacy_user_id=legacy_user_id,
            request_id=request_id,
        )
        scoped_user_id = _config_user_id(config, resolved_user_id)
        initial_stream_values = await _get_graph_state_values_for_stream(graph, config)
        sticky_live_calc_tile = _normalize_live_calc_tile(_working_profile_value(initial_stream_values, "live_calc_tile"))

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
            nonlocal sticky_live_calc_tile
            if event_name == "state_update":
                payload_data = payload.get("data")
                candidate_tile = None
                if isinstance(payload_data, dict):
                    candidate_tile = _normalize_live_calc_tile(payload_data.get("live_calc_tile"))
                if candidate_tile is None:
                    candidate_tile = _normalize_live_calc_tile(payload.get("live_calc_tile"))
                if candidate_tile is not None:
                    sticky_live_calc_tile = candidate_tile
                _inject_live_calc_tile(payload, live_calc_tile=sticky_live_calc_tile)
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
            nonlocal sticky_live_calc_tile
            if broadcast_queue is None:
                return
            try:
                while True:
                    item = await broadcast_queue.get()
                    if not item:
                        continue
                    seq, event_name, payload = item
                    if event_name == "state_update":
                        candidate_tile = None
                        payload_data = payload.get("data") if isinstance(payload, dict) else None
                        if isinstance(payload_data, dict):
                            candidate_tile = _normalize_live_calc_tile(payload_data.get("live_calc_tile"))
                        if candidate_tile is None and isinstance(payload, dict):
                            candidate_tile = _normalize_live_calc_tile(payload.get("live_calc_tile"))
                        if candidate_tile is not None:
                            sticky_live_calc_tile = candidate_tile
                        if isinstance(payload, dict):
                            _inject_live_calc_tile(payload, live_calc_tile=sticky_live_calc_tile)
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
                state_values = dict(initial_stream_values)
                if not state_values and hasattr(graph, "aget_state"):
                    server_snapshot = await graph.aget_state(config)
                    state_values = _state_values_to_dict(server_snapshot.values)
                server_versions = _reasoning_value(state_values, "parameter_versions") if isinstance(state_values, dict) else {}
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
            conversation={
                "user_id": scoped_user_id,
                "thread_id": req.chat_id,
                "messages": [HumanMessage(content=req.input)],
                "user_context": {"auth_scopes": list(auth_scopes or []), "tenant_id": tenant_id},
            },
            system={"tenant_id": tenant_id},
        )

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
                payload.get("prompt_hash"),
                payload.get("prompt_version"),
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
                    "prompt_hash": payload.get("prompt_hash"),
                    "prompt_version": payload.get("prompt_version"),
                },
            )
            await _emit_event("trace", payload)

        async def _producer() -> None:
            nonlocal latest_state, token_count, done_sent, sticky_live_calc_tile
            live_tile_stream_signature: str | None = None
            rfq_document_stream_signature: str | None = None
            streamed_text_parts: list[str] = []
            terminal_final_text: str = ""
            latest_patch_final_text: str = ""
            terminal_nodes = {
                "node_finalize",
                "node_safe_fallback",
                "final_answer_node",
                "response_node",
                "node_p4b_calc_render",
                "p4b_calc_render",
            }

            async def _emit_state_update_if_changed(
                *,
                update_source: SealAIState | Dict[str, Any] | None,
                node_hint: str | None = None,
            ) -> None:
                nonlocal live_tile_stream_signature, rfq_document_stream_signature, sticky_live_calc_tile
                if not isinstance(update_source, (SealAIState, dict)):
                    return

                source_values = _state_values_to_dict(update_source)
                payload = _build_state_update_payload(update_source)
                source_tile = _normalize_live_calc_tile(_working_profile_value(source_values, "live_calc_tile"))
                if source_tile is not None:
                    sticky_live_calc_tile = source_tile
                _inject_live_calc_tile(payload, live_calc_tile=sticky_live_calc_tile)
                payload_data = payload.get("data")
                if not isinstance(payload_data, dict):
                    return

                should_emit = False
                has_live_calc_tile = _is_meaningful_live_calc_tile(payload_data.get("live_calc_tile"))
                should_emit_live_tile = has_live_calc_tile
                if should_emit_live_tile:
                    tile = payload_data.get("live_calc_tile", {})
                    tile_signature = json.dumps(tile, sort_keys=True, default=str)
                    if tile_signature != live_tile_stream_signature:
                        live_tile_stream_signature = tile_signature
                        should_emit = True

                rfq_admissibility = payload_data.get("rfq_admissibility")
                has_rfq_document = bool(
                    isinstance(rfq_admissibility, dict)
                    and (
                        rfq_admissibility.get("governed_ready")
                        or rfq_admissibility.get("status")
                        or rfq_admissibility.get("reason")
                    )
                )
                should_emit_rfq = bool(has_rfq_document)
                if should_emit_rfq:
                    rfq_document = payload_data.get("rfq_document", {})
                    rfq_signature = json.dumps(rfq_document, sort_keys=True, default=str)
                    if rfq_signature != rfq_document_stream_signature:
                        rfq_document_stream_signature = rfq_signature
                        should_emit = True

                if should_emit:
                    await _emit_event("state_update", payload)

            stream_error_emitted = False
            producer_cancelled = False
            try:
                if hasattr(graph, "astream_events"):
                    event_count = 0
                    if SSE_DEBUG or _lg_trace_enabled():
                        logger.info(
                            "langgraph_v2_stream_mode",
                            extra={
                                "request_id": request_id,
                                "chat_id": req.chat_id,
                                "user_id": scoped_user_id,
                                "mode": "astream_events",
                            },
                        )
                    async for raw_event in graph.astream_events(initial_state, config=config):
                        event = raw_event if isinstance(raw_event, dict) else {}
                        if not isinstance(raw_event, dict):
                            continue
                        event_count += 1
                        event_name = str(raw_event.get("event") or "")
                        node_name = str(raw_event.get("name") or "")
                        data = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}
                        if event_name in {
                            "on_node_end",
                            "on_chain_end",
                            "on_graph_end",
                            "on_chain_stream",
                            "on_graph_stream",
                        }:
                            patch_final_text = _extract_final_text_from_patch(data)
                            if patch_final_text:
                                latest_patch_final_text = patch_final_text
                                terminal_final_text = patch_final_text
                        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                        if event_name == "on_node_start":
                            await _emit_event("node_start", {"node": node_name, "ts": ts})
                            await _emit_trace("node_start", data=data, meta=raw_event.get("metadata"), state=latest_state)
                        elif event_name == "on_chat_model_stream":
                            if not _event_belongs_to_current_run(raw_event, run_id):
                                continue
                            chunk = data.get("chunk") if isinstance(data, dict) else None
                            stream_node = _resolve_stream_node_name(
                                node_name=node_name,
                                meta=raw_event.get("metadata"),
                            )
                            text = _extract_stream_token_text(chunk, stream_node=stream_node, state=latest_state)
                            if isinstance(text, str) and text:
                                streamed_text_parts.append(text)
                                token_count += 1
                                await _emit_event("token", {"type": "token", "text": text})
                        elif event_name == "on_node_end":
                            await _emit_event("node_end", {"node": node_name, "ts": ts})
                            # Prometheus node counter — never raises
                            try:
                                from app.core.metrics import graph_node_runs_total
                                if node_name:
                                    graph_node_runs_total.labels(node=node_name).inc()
                            except Exception:
                                pass
                            output = data.get("output")
                            if isinstance(output, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, output)
                            update_source = _extract_state_update_source(data)
                            if isinstance(update_source, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, update_source)
                            else:
                                update_source = (
                                    output if isinstance(output, (SealAIState, dict)) else latest_state
                                )
                            if node_name in terminal_nodes:
                                terminal_candidate = _extract_terminal_text_candidate(update_source)
                                if not terminal_candidate and isinstance(output, (SealAIState, dict)):
                                    terminal_candidate = _extract_terminal_text_candidate(output)
                                if terminal_candidate:
                                    terminal_final_text = terminal_candidate
                            await _emit_state_update_if_changed(update_source=update_source, node_hint=node_name)
                            await _emit_trace(
                                "node_end",
                                data=(output if isinstance(output, (SealAIState, dict)) else data),
                                meta=raw_event.get("metadata"),
                                state=latest_state,
                            )
                        elif event_name in {"on_chain_end", "on_graph_end"}:
                            update_source = _extract_state_update_source(data)
                            if isinstance(update_source, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, update_source)
                                terminal_candidate = _extract_terminal_text_candidate(update_source)
                                if terminal_candidate:
                                    terminal_final_text = terminal_candidate
                            else:
                                update_source = latest_state
                            await _emit_state_update_if_changed(update_source=update_source, node_hint=node_name)

                            await _emit_trace(
                                event_name.replace("on_", ""),
                                data=(update_source if isinstance(update_source, (SealAIState, dict)) else data),
                                meta=raw_event.get("metadata"),
                                state=latest_state,
                            )
                        elif event_name == "on_error":
                            if not stream_error_emitted:
                                stream_error_emitted = True
                                await _emit_event(
                                    "error",
                                    {
                                        "type": "error",
                                        "message": "internal_error",
                                        "request_id": request_id,
                                    },
                                )
                    if SSE_DEBUG or _lg_trace_enabled():
                        logger.info(
                            "langgraph_v2_stream_mode_complete",
                            extra={
                                "request_id": request_id,
                                "chat_id": req.chat_id,
                                "user_id": scoped_user_id,
                                "mode": "astream_events",
                                "event_count": event_count,
                                "token_count": token_count,
                            },
                        )
                elif hasattr(graph, "astream"):
                    async for mode, data in graph.astream(initial_state, config=config, stream_mode=["messages", "values"]):
                        if mode == "messages":
                            token, meta = data if isinstance(data, tuple) and len(data) == 2 else (data, None)
                            stream_node = _resolve_stream_node_name(meta=meta)
                            text = _extract_stream_token_text(token, stream_node=stream_node, state=latest_state)
                            if isinstance(text, str) and text:
                                streamed_text_parts.append(text)
                                token_count += 1
                                await _emit_event("token", {"type": "token", "text": text})
                        elif mode == "values":
                            if isinstance(data, (SealAIState, dict)):
                                latest_state = _merge_state_like(latest_state, data)
                                terminal_candidate = _extract_terminal_text_candidate(data)
                                if terminal_candidate:
                                    terminal_final_text = terminal_candidate
                                    latest_patch_final_text = terminal_candidate
                                await _emit_trace("values", data=data, state=latest_state)
                                node_hint = None
                                if isinstance(data, SealAIState):
                                    node_hint = data.reasoning.last_node
                                elif isinstance(data, dict):
                                    last_node = _reasoning_value(data, "last_node")
                                    node_hint = last_node if isinstance(last_node, str) else None
                                await _emit_state_update_if_changed(update_source=data, node_hint=node_hint)

            except asyncio.CancelledError:
                producer_cancelled = True
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
                if not stream_error_emitted:
                    stream_error_emitted = True
                    message = "dependency_unavailable" if is_dependency_unavailable_error(exc) else "internal_error"
                    await _emit_event("error", {"type": "error", "message": message, "request_id": request_id})
            finally:
                try:
                    if not producer_cancelled:
                        result_state: SealAIState = latest_state if isinstance(latest_state, SealAIState) else initial_state
                        done_payload: Dict[str, Any] = {
                            "type": "done",
                            "chat_id": req.chat_id,
                            "request_id": request_id,
                            "client_msg_id": req.client_msg_id,
                        }
                        try:
                            snapshot = None
                            final_state = None
                            final_state_values: Dict[str, Any] = {}
                            final_state = await graph.aget_state(config)
                            snapshot = final_state
                            if hasattr(final_state, "values"):
                                final_state_values = _state_values_to_dict(final_state.values)
                                if final_state_values:
                                    latest_state = _merge_state_like(latest_state, final_state.values)

                            result_state = (
                                latest_state
                                if isinstance(latest_state, SealAIState)
                                else SealAIState.model_validate(latest_state or {})
                            )
                            state_values = _state_values_to_dict(result_state)
                            await _emit_state_update_if_changed(
                                update_source=result_state,
                                node_hint=result_state.reasoning.last_node,
                            )
                            interrupted = bool(snapshot is not None and _snapshot_waiting_on_human_review(snapshot))
                            if interrupted:
                                checkpoint_id = _extract_snapshot_checkpoint_id(
                                    snapshot,
                                    state_values,
                                    fallback=f"{req.chat_id}:{uuid.uuid4().hex}",
                                )
                                await _emit_event(
                                    "interrupt",
                                    {
                                        "thread_id": req.chat_id,
                                        "checkpoint_id": checkpoint_id,
                                        "reason": "Paused before human_review_node",
                                        "required_action": "approve_specification",
                                    },
                                )
                            if _should_emit_confirm_checkpoint(result_state):
                                checkpoint_payload = result_state.system.confirm_checkpoint or {
                                    "checkpoint_id": result_state.system.confirm_checkpoint_id,
                                    "action": str(result_state.system.pending_action or "human_review"),
                                    "risk": "med",
                                }
                                await _emit_event(
                                    "checkpoint_required",
                                    {
                                        "chat_id": req.chat_id,
                                        "checkpoint_id": checkpoint_payload.get("checkpoint_id"),
                                        "pending_action": checkpoint_payload.get("action"),
                                        "risk": checkpoint_payload.get("risk"),
                                    },
                                )
                            final_text = ""
                            if final_state_values:
                                state_final_text = _system_value(final_state_values, "final_text") or _system_value(final_state_values, "final_answer")
                                if isinstance(state_final_text, str) and state_final_text.strip():
                                    final_text = state_final_text.strip()
                                elif terminal_final_text or latest_patch_final_text:
                                    final_text = str(terminal_final_text or latest_patch_final_text).strip()
                                else:
                                    snapshot_message_text = _latest_ai_text(_conversation_value(final_state_values, "messages") or []).strip()
                                    if snapshot_message_text:
                                        final_text = snapshot_message_text
                            if not final_text:
                                if terminal_final_text:
                                    final_text = str(terminal_final_text).strip()
                                elif latest_patch_final_text:
                                    final_text = str(latest_patch_final_text).strip()
                                else:
                                    final_text = str(_resolve_final_text(result_state)).strip()
                            streamed_text = "".join(streamed_text_parts).strip()
                            should_emit_final_text = bool(final_text) and ((not streamed_text) or (streamed_text != final_text))
                            if final_text:
                                # Emit an authoritative terminal assistant payload from final state so clients
                                # can replace partial/stale content from token-only streaming paths.
                                await _emit_event(
                                    "message",
                                    {
                                        "type": "message",
                                        "text": final_text,
                                        "replace": True,
                                        "source": "final_state",
                                    },
                                )
                            if should_emit_final_text:
                                # Frontend appends only `type=token` + `text` payloads to the active assistant turn.
                                logger.info(f"Emitting final SSE text of length: {len(final_text)}")
                                await _emit_event("token", {"type": "token", "text": final_text})

                            done_payload.update(
                                {
                                    "phase": result_state.reasoning.phase,
                                    "last_node": result_state.reasoning.last_node,
                                    "awaiting_confirmation": bool(result_state.system.awaiting_user_confirmation),
                                    "checkpoint_id": result_state.system.confirm_checkpoint_id,
                                }
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception(
                                "langgraph_v2_sse_finalize_error",
                                extra={
                                    "request_id": request_id,
                                    "chat_id": req.chat_id,
                                    "client_msg_id": req.client_msg_id,
                                    "thread_id": req.chat_id,
                                    "user_id": scoped_user_id,
                                },
                            )
                        finally:
                            if not done_sent:
                                try:
                                    await _emit_event("done", done_payload)
                                    done_sent = True
                                except Exception:
                                    logger.exception(
                                        "langgraph_v2_sse_done_emit_failed",
                                        extra={
                                            "request_id": request_id,
                                            "chat_id": req.chat_id,
                                            "client_msg_id": req.client_msg_id,
                                            "thread_id": req.chat_id,
                                            "user_id": scoped_user_id,
                                        },
                                    )

                            # Audit log — fire-and-forget, never blocks
                            try:
                                from app.services.audit.audit_logger import get_global_audit_logger
                                _al = get_global_audit_logger()
                                if _al is not None:
                                    _al.append(
                                        session_id=req.chat_id,
                                        tenant_id=tenant_id,
                                        state=_state_values_to_dict(result_state),
                                    )
                            except Exception:
                                pass
                finally:
                    await queue.put(None)

        stream_task = asyncio.create_task(_producer())

        while True:
            if SSE_HEARTBEAT_SEC > 0:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SEC)
                except asyncio.TimeoutError:
                    # Keep proxy/browser SSE connections warm during long-running graph steps.
                    yield ": keep-alive\n\n"
                    continue
            else:
                item = await queue.get()
            if item is None:
                break
            yield item.decode("utf-8") if isinstance(item, bytes) else item
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
        yield _format_sse("done", done_payload, event_id=str(seq)).decode("utf-8")
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
        yield _format_sse("error", error_payload, event_id=str(error_seq)).decode("utf-8")
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
        yield _format_sse("done", done_payload, event_id=str(done_seq)).decode("utf-8")
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
