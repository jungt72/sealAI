"""Residual legacy SSE runtime seam — compat-only, non-productive for structured runtime.

This module exists for residual compatibility tests and helper seams around the
old agent graph. The authenticated productive structured runtime must use the
canonical governed graph stream in `app.agent.api.router`.

Agent Stack SSE Runtime — Phase 0A.4

Streaming node whitelist for the agent graph:
  ALLOWED (user-visible): fast_guidance_node, final_response_node
  BLOCKED (internal):     reasoning_node, evidence_tool_node, selection_node

Internal node tokens are dropped silently — they never reach the client.
Uses LangGraph's native astream_events (v2) and filters on node name.
"""
from __future__ import annotations

import json
import logging
import inspect
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Optional

from langchain_core.messages import AIMessage

from app.agent.runtime.selection import build_structured_api_exposure
from app.agent.api.models import build_public_response_core

logger = logging.getLogger(__name__)

# Phase 0A.4: only these nodes may emit text tokens to the client.
AGENT_SPEAKING_NODES: frozenset[str] = frozenset({
    "fast_guidance_node",
    "final_response_node",
})


def _emit_legacy_visible_text_chunk(text: str) -> str:
    """Legacy outward token seam for whitelisted graph-speaking nodes only."""
    return f"data: {json.dumps({'type': 'text_chunk', 'text': text})}\n\n"


def _node_name_from_event(raw_event: Dict[str, Any]) -> Optional[str]:
    """Extract the LangGraph node name from an astream_events v2 event."""
    metadata = raw_event.get("metadata") or {}
    for key in ("langgraph_node", "node", "name"):
        v = metadata.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    name = raw_event.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


async def agent_sse_generator(
    state: Dict[str, Any],
    *,
    graph: Any,
    on_complete: Optional[Callable[[Dict[str, Any]], Awaitable[None] | None]] = None,
) -> AsyncGenerator[str, None]:
    """SSE token stream for the agent graph.

    Phase 0A.4 contract:
    - text_chunk events are emitted ONLY for nodes in AGENT_SPEAKING_NODES.
    - Tokens from reasoning_node / evidence_tool_node / selection_node are
      silently discarded before they leave the backend process.
    - A state_update event is emitted once when the graph completes.
    - [DONE] sentinel closes the stream.
    """
    policy_path = str(state.get("policy_path") or "").strip().lower()
    if policy_path and policy_path not in {"fast", "greeting", "meta", "blocked"}:
        logger.warning(
            "[residual_legacy_compat_only] agent_sse_generator invoked for structured-like policy_path=%s",
            policy_path,
        )

    final_state: Optional[Dict[str, Any]] = None
    try:
        async for raw_event in graph.astream_events(state, version="v2"):
            if not isinstance(raw_event, dict):
                continue

            event_kind = str(raw_event.get("event") or "")

            # ── Token streaming ────────────────────────────────────────────
            if event_kind == "on_chat_model_stream":
                node_name = _node_name_from_event(raw_event)
                if node_name not in AGENT_SPEAKING_NODES:
                    # Blocked: internal node — drop silently (Phase 0A.4)
                    continue
                chunk = (raw_event.get("data") or {}).get("chunk")
                text = getattr(chunk, "content", None) if chunk is not None else None
                if text:
                    yield _emit_legacy_visible_text_chunk(text)

            # ── Graph completion ───────────────────────────────────────────
            elif event_kind == "on_chain_end" and raw_event.get("name") == "LangGraph":
                output = (raw_event.get("data") or {}).get("output")
                if isinstance(output, dict):
                    final_state = output

        if final_state is not None:
            if on_complete is not None:
                maybe_result = on_complete(final_state)
                if inspect.isawaitable(maybe_result):
                    await maybe_result

        # Emit final state so the client can sync sealing_state / run_meta.
        # Phase 0F: also include `reply` so meta/blocked responses (which emit
        # no streaming tokens) still reach the client via state_update.
        # Phase 0D+: suppress raw sealing_state from the canonical outward SSE
        # contract. Structured paths carry case_state-derived truth instead.
        if final_state is not None:
            messages = final_state.get("messages") or []
            ai_messages = [m for m in messages if isinstance(m, AIMessage)]
            reply_text = ai_messages[-1].content if ai_messages else None
            _policy_path = final_state.get("policy_path")
            _is_non_structured = _policy_path in {"fast", "greeting", "meta", "blocked"}
            payload: Dict[str, Any] = {
                "type": "state_update",
                "sealing_state": None,
                "case_state": None if _is_non_structured else final_state.get("case_state"),
                "working_profile": None if _is_non_structured else final_state.get("working_profile"),
                **build_public_response_core(
                    reply=reply_text,
                    structured_state=None if _is_non_structured else build_structured_api_exposure(
                        (((final_state.get("sealing_state") or {}).get("selection")) or {}),
                        case_state=final_state.get("case_state"),
                    ),
                    policy_path=_policy_path,
                    run_meta=final_state.get("run_meta"),
                    state_update=True,
                ),
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        logger.error("[agent_sse] stream error: %s", exc, exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"
