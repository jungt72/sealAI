from __future__ import annotations

import json
from typing import Any, Dict

from app.langgraph.state import SealAIState
from app.langgraph.types import interrupt


async def review_and_rwdr_node(state: SealAIState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        return {}
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    llm = cfg.get("review_llm") if isinstance(cfg, dict) else None
    if llm is None:
        return {}
    response = await llm.ainvoke(messages, config=config)
    raw = getattr(response, "content", None)
    payload = json.loads(raw) if isinstance(raw, str) else {}

    validated = str(payload.get("validated_requirements") or "").strip()
    issues = str(payload.get("identified_issues") or "").strip()
    recommendations = str(payload.get("recommendations") or "").strip()
    fallback_reason = str(payload.get("fallback_reason") or "").strip()
    message = str(payload.get("message") or "").strip()

    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})
    if validated:
        slots["requirements_validated"] = validated
    if issues:
        meta["review_issues"] = issues
    if recommendations:
        meta["review_recommendations"] = recommendations

    updates: Dict[str, Any] = {
        "slots": slots,
        "meta": meta,
        "message_out": message,
        "msg_type": "msg-review",
    }

    if fallback_reason:
        interrupt({"prompt": message, "reason": fallback_reason})

    return updates


__all__ = ["review_and_rwdr_node"]
