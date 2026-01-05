from __future__ import annotations

import json
from typing import Any, Dict

from app.langgraph.types import interrupt
from app.langgraph.state import SealAIState


def bedarfsanalyse_node(state: SealAIState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        return {}
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    llm = cfg.get("bedarfsanalyse_llm") if isinstance(cfg, dict) else None
    if llm is None:
        return {}
    response = llm.invoke(messages)
    raw = getattr(response, "content", None)
    payload = json.loads(raw) if isinstance(raw, str) else {}

    requirements = str(payload.get("requirements") or "").strip()
    context_hint = str(payload.get("context_hint") or "").strip()
    fallback_reason = str(payload.get("fallback_reason") or "").strip()
    message = str(payload.get("message") or requirements or "").strip()

    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})
    if requirements:
        slots["requirements"] = requirements
    if context_hint:
        meta["requirements"] = context_hint

    updates: Dict[str, Any] = {
        "slots": slots,
        "meta": meta,
        "message_out": message,
        "msg_type": "msg-bedarfsanalyse",
        "phase": "bedarfsanalyse",
    }

    if fallback_reason:
        interrupt({"prompt": message, "reason": fallback_reason})

    return updates


__all__ = ["bedarfsanalyse_node"]
