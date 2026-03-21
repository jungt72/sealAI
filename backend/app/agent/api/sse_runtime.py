"""Agent Stack SSE Runtime — Phase 0A.4

Streaming node whitelist for the agent graph:
  ALLOWED (user-visible): fast_guidance_node, final_response_node
  BLOCKED (internal):     reasoning_node, evidence_tool_node, selection_node

Internal node tokens are dropped silently — they never reach the client.
Uses LangGraph's native astream_events (v2) and filters on node name.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional

logger = logging.getLogger(__name__)

# Phase 0A.4: only these nodes may emit text tokens to the client.
AGENT_SPEAKING_NODES: frozenset[str] = frozenset({
    "fast_guidance_node",
    "final_response_node",
})


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
) -> AsyncGenerator[str, None]:
    """SSE token stream for the agent graph.

    Phase 0A.4 contract:
    - text_chunk events are emitted ONLY for nodes in AGENT_SPEAKING_NODES.
    - Tokens from reasoning_node / evidence_tool_node / selection_node are
      silently discarded before they leave the backend process.
    - A state_update event is emitted once when the graph completes.
    - [DONE] sentinel closes the stream.
    """
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
                    yield f"data: {json.dumps({'type': 'text_chunk', 'text': text})}\n\n"

            # ── Graph completion ───────────────────────────────────────────
            elif event_kind == "on_chain_end" and raw_event.get("name") == "LangGraph":
                output = (raw_event.get("data") or {}).get("output")
                if isinstance(output, dict):
                    final_state = output

        # Emit final state so the client can sync sealing_state / run_meta
        if final_state is not None:
            payload: Dict[str, Any] = {
                "type": "state_update",
                "sealing_state": final_state.get("sealing_state"),
                "working_profile": final_state.get("working_profile"),
                "run_meta": final_state.get("run_meta"),
            }
            yield f"data: {json.dumps(payload, default=str)}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        logger.error("[agent_sse] stream error: %s", exc, exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"
