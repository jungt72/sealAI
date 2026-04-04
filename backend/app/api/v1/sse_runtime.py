"""LangGraph v2 SSE Runtime.

This module provides the `event_multiplexer` and related SSE-specific helpers
to translate LangGraph firehose events into strict typed SSE events for the
frontend.

Separating this from the endpoint allows for cleaner orchestration of the
Two-Speed Architecture (Fast Brain vs Slow Brain).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, AsyncIterator, Dict

from fastapi import Request
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.messages.ai import AIMessageChunk

from app.api.v1.utils.state_access import (
    _state_values_to_dict,
    _pillar_dict,
    _conversation_value,
    _reasoning_value,
    _system_value,
    _working_profile_value,
    _rfq_admissibility_value,
    _engineering_profile_payload,
    _system_model_payload,
    _candidate_semantics_payload,
    _governance_metadata_payload,
    _flatten_message_content,
    _is_structured_payload_text,
    _resolve_governed_output_text,
    _resolve_final_text,
    _merge_state_like,
    _is_meaningful_live_calc_tile,
    _normalize_live_calc_tile,
    _inject_live_calc_tile,
)

logger = logging.getLogger(__name__)


def rfq_contract_is_ready(rfq_admissibility: Any) -> bool:
    """Local stub — legacy graph removed."""
    if not isinstance(rfq_admissibility, dict):
        return False
    return bool(rfq_admissibility.get("ready") or rfq_admissibility.get("rfq_ready"))


SSE_QUEUE_MAXSIZE = 200
SSE_HEARTBEAT_SEC = 10.0


def _format_sse(event: str, payload: Dict[str, Any], *, event_id: str | None = None) -> bytes:
    safe_event = str(event).replace("\r", "").replace("\n", "")
    safe_event_id = str(event_id).replace("\r", "").replace("\n", "") if event_id else None
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Guarantee a single data line per SSE event even if payload serialization ever changes.
    payload_json = payload_json.replace("\r", "\\r").replace("\n", "\\n")
    prefix = f"id: {safe_event_id}\n" if safe_event_id else ""
    return (prefix + f"event: {safe_event}\n" + f"data: {payload_json}\n\n").encode("utf-8")


def _format_sse_text(event: str, payload: Dict[str, Any], *, event_id: str | None = None) -> str:
    return _format_sse(event, payload, event_id=event_id).decode("utf-8")


def _eventsource_event(event: str, payload: Dict[str, Any], *, event_id: str | None = None) -> Dict[str, Any]:
    event_payload = {
        "event": event,
        "data": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }
    if event_id:
        event_payload["id"] = event_id
    return event_payload


def _build_state_update_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    values = _state_values_to_dict(state)
    working_profile = _engineering_profile_payload(values) if isinstance(values, dict) else {}
    prompt_meta = _system_value(values, "final_prompt_metadata") if isinstance(values, dict) else None
    live_calc_tile = _working_profile_value(values, "live_calc_tile") if isinstance(values, dict) else None
    calc_results = _working_profile_value(values, "calc_results") if isinstance(values, dict) else None
    has_live_calc_tile = _is_meaningful_live_calc_tile(live_calc_tile)
    if not has_live_calc_tile and live_calc_tile:
        has_live_calc_tile = True
    if isinstance(state, dict) and "live_calc_tile" not in state and "working_profile" not in state and not has_live_calc_tile:
        has_live_calc_tile = False

    rfq_pdf_base64 = _system_value(values, "rfq_pdf_base64") if isinstance(values, dict) else None
    rfq_pdf_url = _system_value(values, "rfq_pdf_url") if isinstance(values, dict) else None
    rfq_html_report = _system_value(values, "rfq_html_report") if isinstance(values, dict) else None
    rfq_admissibility = _rfq_admissibility_value(values)
    sealing_requirement_spec = _system_model_payload(values, "sealing_requirement_spec")
    rfq_draft = _system_model_payload(values, "rfq_draft")
    candidate_semantics = _candidate_semantics_payload(values)
    governance_metadata = _governance_metadata_payload(values)

    if hasattr(working_profile, "model_dump"):
        working_profile = working_profile.model_dump(exclude_none=True)
    if hasattr(live_calc_tile, "model_dump"):
        live_calc_tile = live_calc_tile.model_dump(exclude_none=True)
    if hasattr(calc_results, "model_dump"):
        calc_results = calc_results.model_dump(exclude_none=True)

    data_working_profile = working_profile if isinstance(working_profile, dict) else {}
    if calc_results is not None:
        data_working_profile["calc_results"] = calc_results
    if has_live_calc_tile and isinstance(live_calc_tile, dict):
        data_working_profile["live_calc_tile"] = live_calc_tile

    rfq_document = {
        "ready": rfq_contract_is_ready(rfq_admissibility),
        "has_pdf_base64": bool(isinstance(rfq_pdf_base64, str) and rfq_pdf_base64.strip()),
        "has_pdf_url": bool(isinstance(rfq_pdf_url, str) and rfq_pdf_url.strip()),
        "has_html_report": bool(isinstance(rfq_html_report, str) and rfq_html_report.strip()),
    }

    governed_text = _resolve_governed_output_text(values)
    data = {
        "phase": _reasoning_value(values, "phase"),
        "last_node": _reasoning_value(values, "last_node"),
        "preview_text": _system_value(values, "preview_text"),
        "governed_output_text": _system_value(values, "governed_output_text"),
        "governed_output_status": _system_value(values, "governed_output_status"),
        "governed_output_ready": bool(_system_value(values, "governed_output_ready")),
        "governance_metadata": governance_metadata if governance_metadata else None,
        "final_text": governed_text or None,
        "final_answer": governed_text or None,
        "awaiting_user_input": _reasoning_value(values, "awaiting_user_input"),
        "streaming_complete": _reasoning_value(values, "streaming_complete"),
        "awaiting_user_confirmation": _system_value(values, "awaiting_user_confirmation"),
        "recommendation_ready": _reasoning_value(values, "recommendation_ready"),
        "recommendation_go": _reasoning_value(values, "recommendation_go"),
        "coverage_score": _reasoning_value(values, "coverage_score"),
        "coverage_gaps": _reasoning_value(values, "coverage_gaps"),
        "missing_params": _reasoning_value(values, "missing_params"),
        "working_profile": data_working_profile,
        "calc_results": calc_results,
        "compliance_results": _working_profile_value(values, "compliance_results"),
        "delta": {"working_profile": data_working_profile},
        "pending_action": _system_value(values, "pending_action"),
        "confirm_checkpoint_id": _system_value(values, "confirm_checkpoint_id"),
        "final_prompt_metadata": prompt_meta if isinstance(prompt_meta, dict) and prompt_meta else None,
        "rfq_admissibility": rfq_admissibility,
        "rfq_ready": rfq_contract_is_ready(rfq_admissibility),
        "rfq_confirmed": bool(_system_value(values, "rfq_confirmed")),
        "rfq_document": rfq_document,
    }
    if sealing_requirement_spec:
        data["sealing_requirement_spec"] = sealing_requirement_spec
    if rfq_draft:
        data["rfq_draft"] = rfq_draft
    if candidate_semantics:
        data["candidate_semantics"] = candidate_semantics
    if has_live_calc_tile and isinstance(live_calc_tile, dict):
        data["live_calc_tile"] = live_calc_tile

    data = {key: value for key, value in data.items() if value is not None}
    payload = {
        "type": "state_update",
        "data": data,
        "phase": data.get("phase"),
        "last_node": data.get("last_node"),
        "preview_text": data.get("preview_text"),
        "governed_output_text": data.get("governed_output_text"),
        "governed_output_status": data.get("governed_output_status"),
        "governed_output_ready": data.get("governed_output_ready"),
        "governance_metadata": data.get("governance_metadata"),
        "final_text": data.get("final_text"),
        "final_answer": data.get("final_answer"),
        "awaiting_user_input": data.get("awaiting_user_input"),
        "streaming_complete": data.get("streaming_complete"),
        "awaiting_user_confirmation": data.get("awaiting_user_confirmation"),
        "recommendation_ready": data.get("recommendation_ready"),
        "recommendation_go": data.get("recommendation_go"),
        "coverage_score": data.get("coverage_score"),
        "coverage_gaps": data.get("coverage_gaps"),
        "missing_params": data.get("missing_params"),
        "working_profile": data.get("working_profile"),
        "live_calc_tile": data.get("live_calc_tile"),
        "calc_results": data.get("calc_results"),
        "compliance_results": data.get("compliance_results"),
        "delta": data.get("delta"),
        "pending_action": data.get("pending_action"),
        "confirm_checkpoint_id": data.get("confirm_checkpoint_id"),
        "final_prompt_metadata": data.get("final_prompt_metadata"),
        "rfq_admissibility": data.get("rfq_admissibility"),
        "candidate_semantics": data.get("candidate_semantics"),
        "rfq_ready": data.get("rfq_ready"),
        "rfq_confirmed": data.get("rfq_confirmed"),
        "rfq_document": data.get("rfq_document"),
        "sealing_requirement_spec": data.get("sealing_requirement_spec"),
        "rfq_draft": data.get("rfq_draft"),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _normalize_stream_node_name(node_name: Any) -> str | None:
    if isinstance(node_name, str):
        candidate = node_name.strip()
        if candidate:
            return candidate
    return None


def _resolve_stream_node_name(*, node_name: Any = None, meta: Any = None) -> str | None:
    candidates: list[Any] = []
    if isinstance(meta, dict):
        candidates.extend([meta.get("langgraph_node"), meta.get("node"), meta.get("name")])
        nested_meta = meta.get("metadata")
        if isinstance(nested_meta, dict):
            candidates.extend([nested_meta.get("langgraph_node"), nested_meta.get("node"), nested_meta.get("name")])
    candidates.append(node_name)
    for candidate in candidates:
        resolved = _normalize_stream_node_name(candidate)
        if resolved:
            return resolved
    return None


def _extract_stream_nodes_from_tags(tags: Any) -> set[str]:
    nodes: set[str] = set()
    if not isinstance(tags, (list, tuple, set)):
        return nodes
    prefix = "langsmith:graph:node:"
    for tag in tags:
        if not isinstance(tag, str) or not tag.startswith(prefix):
            continue
        node_name = tag[len(prefix):].strip()
        if node_name:
            nodes.add(node_name)
    return nodes


def _event_belongs_to_current_run(raw_event: Any, expected_run_id: str | None) -> bool:
    if not expected_run_id or not isinstance(raw_event, dict):
        return True
    event_ids: set[str] = set()
    metadata = raw_event.get("metadata") if isinstance(raw_event.get("metadata"), dict) else {}
    for source in (raw_event, metadata):
        if not isinstance(source, dict):
            continue
        run_id = source.get("run_id")
        if isinstance(run_id, str) and run_id:
            event_ids.add(run_id)
        parent_run_id = source.get("parent_run_id")
        if isinstance(parent_run_id, str) and parent_run_id:
            event_ids.add(parent_run_id)
        parent_ids = source.get("parent_ids")
        if isinstance(parent_ids, (list, tuple, set)):
            for parent_id in parent_ids:
                if isinstance(parent_id, str) and parent_id:
                    event_ids.add(parent_id)
    if not event_ids:
        return True
    return expected_run_id in event_ids


def _looks_like_state_payload(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    expected_keys = {
        "conversation",
        "reasoning",
        "working_profile",
        "system",
        "phase",
        "last_node",
        "messages",
        "final_text",
        "final_answer",
        "working_profile",
        "rfq_admissibility",
        "rfq_ready",
        "rfq_document",
        "awaiting_user_input",
        "awaiting_user_confirmation",
    }
    return any(key in data for key in expected_keys)


def _extract_state_update_source(data: Any) -> Dict[str, Any] | None:
    if isinstance(data, dict):
        return data
    if not isinstance(data, dict):
        return None

    for key in ("output", "state", "final_state", "values", "result", "chunk", "patch", "update", "delta"):
        candidate = data.get(key)
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, dict):
            nested_values = candidate.get("values")
            if isinstance(nested_values, dict):
                return nested_values
            if _looks_like_state_payload(candidate):
                return candidate

    if _looks_like_state_payload(data):
        return data
    return None


_NODE_LABELS: Dict[str, str] = {
    "profile_loader_node": "Profile Loader",
    "safety_synonym_guard_node": "Safety Synonym Guard",
    "combinatorial_chemistry_guard_node": "Combinatorial Chemistry Guard",
    "frontdoor_discovery_node": "Intent Discovery",
    "node_router": "Router",
    "node_p1_context": "Parameter Extraction",
    "reasoning_core_node": "Reasoning Core",
    "human_review_node": "Human Review",
    "contract_first_output_node": "Contract Output",
    "final_answer_node": "Final Answer",
    "node_draft_answer": "Drafting Answer",
    "node_finalize": "Finalizing",
    "worm_evidence_node": "WORM Evidence",
}


def _human_node_label(node_name: str | None) -> str:
    normalized = str(node_name or "").strip()
    if not normalized:
        return "Unknown Node"
    return _NODE_LABELS.get(normalized, normalized.replace("_", " ").title())


def _extract_chunk_text_from_stream_event(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        text = chunk
    elif isinstance(chunk, (AIMessage, AIMessageChunk, BaseMessage)):
        text = _flatten_message_content(chunk)
    elif isinstance(chunk, dict):
        text = _flatten_message_content(chunk.get("content") or chunk.get("text") or chunk)
    else:
        text = _flatten_message_content(chunk)
    if not text:
        return ""
    structured_probe = text.strip()
    if structured_probe and _is_structured_payload_text(structured_probe):
        return ""
    return text


def _extract_working_profile_payload(state_like: Dict[str, Any] | None) -> Dict[str, Any] | None:
    values = _state_values_to_dict(state_like)
    raw_profile = _engineering_profile_payload(values)
    if isinstance(raw_profile, dict) and raw_profile:
        return dict(raw_profile)
    return None


def _extract_blocker_conflicts(state_like: Dict[str, Any] | None) -> list[Dict[str, Any]]:
    profile = _extract_working_profile_payload(state_like)
    if not isinstance(profile, dict):
        return []
    conflicts = profile.get("conflicts_detected")
    if not isinstance(conflicts, list):
        return []
    blockers: list[Dict[str, Any]] = []
    for conflict in conflicts:
        if isinstance(conflict, dict):
            severity = str(conflict.get("severity") or "").upper()
            if severity == "BLOCKER":
                blockers.append(dict(conflict))
            continue
        severity = str(getattr(conflict, "severity", "") or "").upper()
        if severity != "BLOCKER":
            continue
        if hasattr(conflict, "model_dump"):
            blockers.append(conflict.model_dump(exclude_none=True))
        else:
            blockers.append(
                {
                    "rule_id": str(getattr(conflict, "rule_id", "") or ""),
                    "severity": severity,
                    "title": str(getattr(conflict, "title", "") or ""),
                    "reason": str(getattr(conflict, "reason", "") or ""),
                }
            )
    return blockers


def _extract_terminal_text_candidate(state: Dict[str, Any] | None) -> str:
    if not isinstance(state, dict):
        return ""
    return _resolve_governed_output_text(state)


async def event_multiplexer(
    graph: Any,
    state_input: Dict[str, Any],
    config: Dict[str, Any],
    request: Request,
) -> AsyncIterator[str]:
    """Translate LangGraph firehose events into strict typed SSE events.

    Output format is always:
    `event: <type>\ndata: <json>\n\n`
    """
    metadata = config.get("metadata") if isinstance(config, dict) else {}
    expected_run_id = metadata.get("run_id") if isinstance(metadata, dict) else None
    thread_id = state_input.conversation.thread_id

    if not hasattr(graph, "astream_events"):
        yield _format_sse_text(
            "error",
            {"type": "error", "message": "astream_events_not_supported"},
        )
        yield _format_sse_text("turn_complete", {"type": "turn_complete"})
        if thread_id:
            from app.api.v1.endpoints.langgraph_v2 import _release_thread_lock
            await _release_thread_lock(thread_id)
        return

    queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=max(32, SSE_QUEUE_MAXSIZE // 2))
    latest_state: Dict[str, Any] | None = state_input
    turn_complete_sent = False

    async def _queue_emit(event_name: str, payload: Dict[str, Any]) -> None:
        frame = _format_sse_text(event_name, payload)
        if queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        queue.put_nowait(frame)

    async def _queue_done() -> None:
        final_text = _resolve_final_text(latest_state).strip() if isinstance(latest_state, dict) else ""
        payload = {
            "type": "done",
            "chat_id": thread_id,
        }
        if final_text:
            payload["final_text"] = final_text
            payload["final_answer"] = final_text
        await _queue_emit(
            "done",
            payload,
        )

    async def _producer() -> None:
        nonlocal latest_state, turn_complete_sent
        state_update_signature: str | None = None
        token_seen = False
        emitted_terminal_text: str | None = None

        async def _emit_terminal_token_if_available(source: Dict[str, Any] | None) -> None:
            nonlocal token_seen, emitted_terminal_text
            if token_seen or not isinstance(source, dict):
                return
            final_text = _extract_terminal_text_candidate(source).strip()
            if not final_text or final_text == emitted_terminal_text:
                return
            emitted_terminal_text = final_text
            token_seen = True
            await _queue_emit("token", {"type": "token", "text": final_text})

        async def _emit_state_update_if_available() -> None:
            nonlocal state_update_signature
            if not isinstance(latest_state, dict):
                return
            payload = _build_state_update_payload(latest_state)
            payload_data = payload.get("data")
            if not isinstance(payload_data, dict):
                return

            working_profile_payload = payload_data.get("working_profile")
            if not isinstance(working_profile_payload, dict):
                working_profile_payload = {}
                payload_data["working_profile"] = working_profile_payload

            # Ensure v10 nested structure is present for frontend consumers.
            wp_live_calc_tile = working_profile_payload.get("live_calc_tile")
            wp_calc_results = working_profile_payload.get("calc_results")
            if payload_data.get("live_calc_tile") is None and wp_live_calc_tile is not None:
                payload_data["live_calc_tile"] = wp_live_calc_tile
            if payload_data.get("calc_results") is None and wp_calc_results is not None:
                payload_data["calc_results"] = wp_calc_results

            if working_profile_payload.get("live_calc_tile") is None and payload_data.get("live_calc_tile") is not None:
                working_profile_payload["live_calc_tile"] = payload_data.get("live_calc_tile")
            if working_profile_payload.get("calc_results") is None and payload_data.get("calc_results") is not None:
                working_profile_payload["calc_results"] = payload_data.get("calc_results")

            if payload.get("live_calc_tile") is None and payload_data.get("live_calc_tile") is not None:
                payload["live_calc_tile"] = payload_data.get("live_calc_tile")
            if payload.get("calc_results") is None and payload_data.get("calc_results") is not None:
                payload["calc_results"] = payload_data.get("calc_results")
            if payload.get("working_profile") is None:
                payload["working_profile"] = working_profile_payload

            signature = json.dumps(
                {
                    "phase": payload_data.get("phase"),
                    "last_node": payload_data.get("last_node"),
                    "working_profile": payload_data.get("working_profile"),
                    "live_calc_tile": payload_data.get("live_calc_tile"),
                    "calc_results": payload_data.get("calc_results"),
                    "rfq_admissibility": payload_data.get("rfq_admissibility"),
                    "rfq_document": payload_data.get("rfq_document"),
                },
                sort_keys=True,
                default=str,
            )
            if signature == state_update_signature:
                return
            state_update_signature = signature
            await _queue_emit("state_update", payload)

        try:
            async for raw_event in graph.astream_events(state_input, config=config, version="v2"):
                if await request.is_disconnected():
                    raise asyncio.CancelledError()
                if not isinstance(raw_event, dict):
                    continue

                if not _event_belongs_to_current_run(raw_event, expected_run_id):
                    continue

                event_name = str(raw_event.get("event") or "")
                node_name = _resolve_stream_node_name(
                    node_name=raw_event.get("name"),
                    meta=raw_event.get("metadata"),
                )
                data = raw_event.get("data") if isinstance(raw_event.get("data"), dict) else {}

                if event_name in {"on_node_start", "on_chain_start"}:
                    await _queue_emit(
                        "node_status",
                        {
                            "type": "node_status",
                            "node": _human_node_label(node_name),
                            "status": "running",
                        },
                    )
                    continue

                if event_name == "on_chat_model_stream":
                    tags = raw_event.get("tags") or []
                    tagged_nodes = _extract_stream_nodes_from_tags(tags)
                    speaking_nodes = set(tagged_nodes)
                    if node_name:
                        speaking_nodes.add(str(node_name))
                    allowed_speaking_nodes = {
                        "response_node",
                        "contract_first_output_node",
                        "node_finalize",
                        "final_answer_node",
                    }
                    is_speaking = any(node in allowed_speaking_nodes for node in speaking_nodes)
                    if is_speaking:
                        chunk_text = _extract_chunk_text_from_stream_event(data.get("chunk"))
                        if chunk_text:
                            token_seen = True
                            await _queue_emit("text_chunk", {"type": "text_chunk", "text": chunk_text})
                            await _queue_emit("token", {"type": "token", "text": chunk_text})
                    continue

                update_source = _extract_state_update_source(data)
                if isinstance(update_source, dict):
                    latest_state = _merge_state_like(latest_state, update_source)

                if event_name in {"on_custom_event", "on_node_end", "on_chain_end"}:
                    await _emit_state_update_if_available()
                    await _emit_terminal_token_if_available(latest_state)

                    profile_payload = _extract_working_profile_payload(latest_state)
                    if profile_payload and (
                        event_name == "on_custom_event"
                        or str(node_name or "") in {"combinatorial_chemistry_guard_node", "reasoning_core_node"}
                    ):
                        await _queue_emit(
                            "profile_update",
                            {
                                "type": "profile_update",
                                "node": _human_node_label(node_name),
                                "working_profile": profile_payload,
                            },
                        )

                    blockers = _extract_blocker_conflicts(latest_state)
                    if blockers:
                        await _queue_emit(
                            "safety_alert",
                            {
                                "type": "safety_alert",
                                "severity": "BLOCKER",
                                "blockers": blockers,
                            },
                        )

                if event_name in {"on_node_end", "on_chain_end"}:
                    await _queue_emit(
                        "node_status",
                        {
                            "type": "node_status",
                            "node": _human_node_label(node_name),
                            "status": "completed",
                        },
                    )

                if event_name == "on_chat_model_end" or (
                    event_name == "on_chain_end" and str(node_name or "") == "reasoning_core_node"
                ):
                    await _queue_emit("turn_complete", {"type": "turn_complete"})
                    await _queue_done()
                    turn_complete_sent = True

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("langgraph_v2_event_multiplexer_error")
            await _queue_emit(
                "error",
                {
                    "type": "error",
                    "message": "internal_error",
                },
            )
            await _queue_emit("turn_complete", {"type": "turn_complete"})
            await _queue_done()
            turn_complete_sent = True
        finally:
            if not turn_complete_sent:
                await _queue_emit("turn_complete", {"type": "turn_complete"})
                await _queue_done()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    producer = asyncio.create_task(_producer())
    try:
        while True:
            if await request.is_disconnected():
                producer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
                return
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=max(0.25, SSE_HEARTBEAT_SEC))
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if frame is None:
                try:
                    from app.api.v1.utils.state_access import _state_values_to_dict
                    if hasattr(graph, "aget_state"):
                        snapshot = await graph.aget_state(config)
                        vals = _state_values_to_dict(snapshot.values if snapshot else {})
                        final = str(_resolve_governed_output_text(vals) or "")
                        if final:
                            logger.info("hitl_final_answer_flushed", extra={"length": len(final)})
                            yield _format_sse_text("token", {"type": "token", "text": final})
                except Exception as _flush_err:
                    logger.warning("hitl_flush_error", extra={"error": str(_flush_err)})
                break
            yield frame
    except asyncio.CancelledError:
        producer.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await producer
        return
    finally:
        if not producer.done():
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
        if thread_id:
            from app.api.v1.endpoints.langgraph_v2 import _release_thread_lock
            await _release_thread_lock(thread_id)
