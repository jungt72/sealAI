from __future__ import annotations

import json
from typing import Any, Dict

from app.langgraph.types import interrupt
from app.langgraph.state import SealAIState


def arbiter_node(state: SealAIState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        return {}
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    llm = cfg.get("arbiter_llm") if isinstance(cfg, dict) else None
    if llm is None:
        return {}
    response = llm.invoke(messages)
    raw = getattr(response, "content", None)
    payload = json.loads(raw) if isinstance(raw, str) else {}
    final_reco = str(payload.get("final_recommendation") or "").strip()
    reasoning = str(payload.get("reasoning") or "").strip()
    message = str(payload.get("message") or final_reco or "").strip()
    fallback_reason = str(payload.get("fallback_reason") or "").strip()

    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})
    if final_reco:
        slots["final_recommendation"] = final_reco
    if reasoning:
        meta["arbiter_reasoning"] = reasoning

    updates: Dict[str, Any] = {
        "slots": slots,
        "meta": meta,
        "message_out": message,
        "msg_type": "msg-arbiter",
    }

    if fallback_reason:
        interrupt({"prompt": message, "reason": fallback_reason})

    return updates


__all__ = ["arbiter_node"]
