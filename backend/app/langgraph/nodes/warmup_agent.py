from __future__ import annotations

import json
from typing import Any, Dict

from app.langgraph.state import SealAIState
from app.langgraph.types import interrupt


def warmup_agent_node(state: SealAIState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        return {}
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    llm = cfg.get("warmup_llm") if isinstance(cfg, dict) else None
    if llm is None:
        return {}
    response = llm.invoke(messages)
    raw = getattr(response, "content", None)
    payload = json.loads(raw) if isinstance(raw, str) else {}

    message = str(payload.get("message") or "").strip()
    slots_in = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    meta_in = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}

    slots = dict(state.get("slots") or {})
    slots.update(slots_in)
    meta = dict(state.get("meta") or {})
    meta["warmup"] = meta_in

    fallback_reason = str(meta_in.get("fallback_reason") or "").strip()
    if fallback_reason:
        interrupt({"prompt": message, "reason": fallback_reason})

    updates: Dict[str, Any] = {
        "slots": slots,
        "meta": meta,
        "message_out": message,
        "msg_type": "msg-warmup",
        "phase": "warmup",
    }

    if meta_in.get("warmup") is False:
        interrupt({"prompt": message, "reason": "warmup_failed"})

    return updates


__all__ = ["warmup_agent_node"]
