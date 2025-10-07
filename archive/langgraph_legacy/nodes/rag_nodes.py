from __future__ import annotations
from typing import Dict, Any, List
from datetime import date
from app.services.langgraph.tools.telemetry import telemetry, PARTNER_COVERAGE, NO_MATCH_RATE

def rag_retrieve(state: Dict[str, Any]) -> Dict[str, Any]:
    cands = state.get("candidates") or []
    state["sources"] = state.get("sources") or []
    state.setdefault("telemetry", {})["candidates_total"] = len(cands)
    return state

def _is_partner(c: Dict[str, Any]) -> bool:
    tier = (c.get("paid_tier") or "none").lower()
    active = bool(c.get("active", False))
    valid_until = (c.get("contract_valid_until") or "")
    try:
        y, m, d = map(int, valid_until.split("-"))
        ok_date = date(y, m, d) >= date.today()
    except Exception:
        ok_date = False
    return tier != "none" and active and ok_date

def partner_only_filter(state: Dict[str, Any]) -> Dict[str, Any]:
    cands: List[Dict[str, Any]] = state.get("candidates") or []
    partners = [c for c in cands if _is_partner(c)]
    state["candidates"] = partners
    total = state.get("telemetry", {}).get("candidates_total", 0)
    coverage = (len(partners) / total) if total else 0.0
    telemetry.set_gauge(PARTNER_COVERAGE, coverage)
    if not partners:
        state.setdefault("ui_events", []).append({"ui_action": "no_partner_available", "payload": {}})
        telemetry.incr(NO_MATCH_RATE, 1)
    return state

def rules_filter(state: Dict[str, Any]) -> Dict[str, Any]:
    return state
