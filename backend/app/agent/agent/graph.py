# Re-export shim — canonical location: app.agent.graph.legacy_graph
# DO NOT add logic here. This file exists only for import compatibility.
from app.agent.graph.legacy_graph import (  # noqa: F401
    _GRAPH_MODEL_ID,
    _BLOCKED_REFUSAL,
    _RAG_ELIGIBLE_PATTERN,
    VISIBLE_REPLY_PROMPT_VERSION,
    VISIBLE_REPLY_PROMPT_HASH,
    route_by_policy,
    meta_response_node,
    blocked_node,
    greeting_node,
    fast_guidance_node,
    evidence_tool_node,
    reasoning_node,
    selection_node,
    final_response_node,
    app,
)
