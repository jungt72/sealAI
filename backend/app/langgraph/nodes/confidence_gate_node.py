from __future__ import annotations

import json
from typing import Any, Dict

from app.langgraph.types import interrupt
from app.langgraph.state import SealAIState


def confidence_gate_node(state: SealAIState, *, config: Dict[str, Any]) -> Dict[str, Any]:
    messages = list(state.get("messages") or [])
    if not messages:
        return {}
    cfg = config.get("configurable") if isinstance(config, dict) else {}
    llm = cfg.get("confidence_gate_llm") if isinstance(cfg, dict) else None
    if llm is None:
        return {}
    response = llm.invoke(messages)
    raw = getattr(response, "content", None)
    payload = json.loads(raw) if isinstance(raw, str) else {}

    score = payload.get("confidence_score")
    try:
        score_val = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_val = None
    reason = str(payload.get("confidence_reason") or "").strip()
    fallback_reason = str(payload.get("fallback_reason") or "").strip()
    message = str(payload.get("message") or "").strip()

    slots = dict(state.get("slots") or {})
    meta = dict(state.get("meta") or {})
    if score_val is not None:
        meta["confidence_score"] = score_val
    if reason:
        meta["confidence_reason"] = reason
    if score_val is not None and score_val < 0.7:
        slots["confidence_gate"] = "review_required"

    updates: Dict[str, Any] = {
        "slots": slots,
        "meta": meta,
        "message_out": message,
        "msg_type": "msg-confidence-gate",
    }

    if fallback_reason:
        interrupt({"prompt": message, "reason": fallback_reason})

    return updates


__all__ = ["confidence_gate_node"]
