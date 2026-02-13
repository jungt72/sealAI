"""Deterministic assumption-lock gate for high-impact inferred risks."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Tuple

from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.messages import latest_user_text

_CONFIRM_RE = re.compile(r"\bconfirm\b\s*#?\s*([\d,\s#]+)", re.IGNORECASE)
_CONFIRM_ALL_RE = re.compile(r"\b(confirm\s*all|best[aä]tige\s+alle|alle\s+ok)\b", re.IGNORECASE)
_GENERIC_OK_RE = re.compile(r"^\s*(ok|passt|ja)\s*[.!]?\s*$", re.IGNORECASE)


def _parse_risk_level(state: SealAIState) -> str:
    flags = dict(getattr(state, "flags", {}) or {})
    level = str(flags.get("risk_level") or "").strip().lower()
    return level if level in {"low", "medium", "high", "critical"} else "low"


def _has_unknown_or_conditional_rag(state: SealAIState) -> bool:
    rag_cov = dict(getattr(state, "guardrail_rag_coverage", {}) or {})
    for value in rag_cov.values():
        status = str((value or {}).get("status") or "").lower()
        if status in {"unknown", "conditional"}:
            return True
    return False


def _status_to_heat(value: Dict[str, Any]) -> str:
    status = str((value or {}).get("status") or "").lower()
    decision = str((value or {}).get("decision") or "").lower()
    coverage = str((value or {}).get("coverage") or "").lower()
    if decision in {"refuse", "human_required"} or status == "hard_block":
        return "critical"
    if bool((value or {}).get("pv_critical")):
        return "high"
    if decision == "ask_user":
        return "medium"
    if coverage in {"unknown", "conditional"}:
        return coverage
    return "low"


def _build_risk_heatmap(state: SealAIState) -> Dict[str, str]:
    coverage = dict(getattr(state, "guardrail_coverage", {}) or {})
    existing = dict(getattr(state, "risk_heatmap", {}) or {})
    rename = {
        "steam_cip_sip": "steam_peak",
        "gas_decompression": "extrusion",
        "pv_limit": "pv_limit",
        "h2s_sour": "h2s_sour",
        "api682": "api682",
        "hydrogen": "hydrogen",
        "mixed_units": "mixed_units",
    }
    out: Dict[str, str] = dict(existing)
    for key, dst in rename.items():
        if key in coverage:
            out[dst] = _status_to_heat(dict(coverage.get(key) or {}))
    if not out:
        out["overall"] = _parse_risk_level(state)
    if bool(getattr(state, "failure_mode_active", False)) and bool(getattr(state, "failure_evidence_missing", False)):
        out["failure_evidence"] = "critical"
    return out


def _build_assumption_list(state: SealAIState) -> List[Dict[str, Any]]:
    risk_level = _parse_risk_level(state)
    escalation = str(getattr(state, "guardrail_escalation_reason", "") or "").strip()
    rag_cov = dict(getattr(state, "guardrail_rag_coverage", {}) or {})
    cov = dict(getattr(state, "guardrail_coverage", {}) or {})

    gate = (
        risk_level in {"medium", "high", "critical"}
        or bool(escalation)
        or _has_unknown_or_conditional_rag(state)
    )
    if not gate:
        return []

    assumptions: List[Tuple[str, str, str, str, bool]] = []
    steam = dict(cov.get("steam_cip_sip") or {})
    if str(steam.get("coverage") or "").lower() in {"unknown", "conditional"}:
        src = "rag" if str((rag_cov.get("steam_cip_sip") or {}).get("status") or "").lower() == "confirmed" else "inferred"
        assumptions.append(("1", "Steam peaks assumed <135°C with bounded exposure duration.", "high", src, True))
    gas = dict(cov.get("gas_decompression") or {})
    if str(gas.get("coverage") or "").lower() in {"unknown", "conditional"}:
        src = "rag" if str((rag_cov.get("gas_decompression") or {}).get("status") or "").lower() == "confirmed" else "inferred"
        assumptions.append(("2", "No rapid depressurization event (<10 bar/min equivalent) is assumed.", "critical", src, True))
    h2s = dict(cov.get("h2s_sour") or {})
    h2s_decision = str(h2s.get("decision") or h2s.get("status") or "").lower()
    if h2s_decision in {"human_required", "refuse"}:
        assumptions.append(("3", "H2S partial pressure/service class is assumed within validated limits.", "critical", "inferred", True))
    pv = dict(cov.get("pv_limit") or {})
    if bool(pv.get("pv_critical")):
        src = "rag" if str((rag_cov.get("pv_limit") or {}).get("status") or "").lower() == "confirmed" else "inferred"
        assumptions.append(("4", "Clearance and PV transient behavior assumed within allowable envelope.", "high", src, True))
    mixed = dict(cov.get("mixed_units") or {})
    mixed_decision = str(mixed.get("decision") or mixed.get("status") or "").lower()
    if mixed_decision == "ask_user":
        assumptions.append(("5", "All process inputs are assumed normalized to SI units.", "high", "user", True))

    out: List[Dict[str, Any]] = []
    for ident, text, impact, source, requires_confirmation in assumptions:
        out.append(
            {
                "id": ident,
                "text": text,
                "impact": impact,
                "source": source,
                "requires_confirmation": requires_confirmation,
            }
        )
    return out


def _parse_confirmed_ids(text: str) -> set[str]:
    match = _CONFIRM_RE.search(text or "")
    if not match:
        return set()
    raw = match.group(1)
    numbers = re.findall(r"\d+", raw)
    return {n.strip() for n in numbers if n.strip()}


def _extract_inline_ids(text: str) -> set[str]:
    raw = str(text or "")
    ids: set[str] = set()
    for a, b in re.findall(r"(?:#?\s*)(\d+)\s*-\s*(\d+)", raw):
        lo = min(int(a), int(b))
        hi = max(int(a), int(b))
        for value in range(lo, hi + 1):
            ids.add(str(value))
    for value in re.findall(r"(?:#\s*\d+)|(?:\b\d+\b)", raw):
        num = re.sub(r"[^\d]", "", value)
        if num:
            ids.add(num)
    return ids


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _guardrail_coverage_summary(coverage: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    summary: Dict[str, Dict[str, Any]] = {}
    for key in sorted((coverage or {}).keys()):
        item = dict((coverage or {}).get(key) or {})
        summary[key] = {
            "status": str(item.get("status") or ""),
            "coverage": str(item.get("coverage") or ""),
            "reason": str(item.get("reason") or ""),
        }
    return summary


def _compute_assumption_lock_hash(
    *,
    assumptions: List[Dict[str, Any]],
    risk_heatmap: Dict[str, str],
    guardrail_coverage: Dict[str, Any],
) -> str:
    payload = {
        "assumptions": assumptions,
        "risk_heatmap": dict(sorted((risk_heatmap or {}).items())),
        "guardrail_coverage_summary": _guardrail_coverage_summary(guardrail_coverage),
    }
    canonical = _canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_confirmation(
    *,
    text: str,
    assumptions: List[Dict[str, Any]],
    prior_pending: List[str],
    prior_last_node: str,
) -> set[str]:
    assumption_ids = {str(item.get("id") or "") for item in assumptions if str(item.get("id") or "")}
    if not assumption_ids:
        return set()

    explicit = _parse_confirmed_ids(text) | (_extract_inline_ids(text) if re.search(r"\d", text or "") else set())
    explicit = {item for item in explicit if item in assumption_ids}
    if explicit:
        return explicit

    if _CONFIRM_ALL_RE.search(text or ""):
        return set(assumption_ids)

    generic_ok = bool(_GENERIC_OK_RE.match(text or ""))
    has_pending_context = bool(prior_pending) and str(prior_last_node or "") == "assumption_lock_node"
    if generic_ok and has_pending_context:
        return set(assumption_ids)
    return set()


def _pending_high_assumptions(assumptions: List[Dict[str, Any]], confirmed_ids: set[str]) -> List[str]:
    pending: List[str] = []
    for item in assumptions:
        impact = str(item.get("impact") or "").lower()
        requires = bool(item.get("requires_confirmation"))
        ident = str(item.get("id") or "")
        if requires and impact in {"high", "critical"} and ident and ident not in confirmed_ids:
            pending.append(ident)
    return pending


def assumption_lock_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    assumptions = _build_assumption_list(state)
    risk_heatmap = _build_risk_heatmap(state)
    user_text = latest_user_text(list(state.messages or [])) or ""
    prior_pending = list(getattr(state, "pending_assumptions", []) or [])
    prior_last_node = str(getattr(state, "last_node", "") or "")
    confirmed_ids = _parse_confirmation(
        text=user_text,
        assumptions=assumptions,
        prior_pending=prior_pending,
        prior_last_node=prior_last_node,
    )
    pending = _pending_high_assumptions(assumptions, confirmed_ids)
    current_hash = _compute_assumption_lock_hash(
        assumptions=assumptions,
        risk_heatmap=risk_heatmap,
        guardrail_coverage=dict(getattr(state, "guardrail_coverage", {}) or {}),
    )
    confirmed_hash = getattr(state, "assumption_lock_hash_confirmed", None)
    hash_mismatch = bool(confirmed_hash and confirmed_hash != current_hash)
    if hash_mismatch:
        confirmed_ids = set()
        pending = _pending_high_assumptions(assumptions, confirmed_ids)

    if bool(getattr(state, "failure_mode_active", False)) and bool(getattr(state, "failure_evidence_missing", False)):
        request = state.ask_missing_request
        if request is None:
            request = AskMissingRequest(
                missing_fields=["failure_photo_or_damage_evidence"],
                question="Bitte erst Ausfallfoto oder belastbare Schadensbeschreibung liefern.",
                reason="failure_evidence_required",
                questions=[
                    "Upload photo of failed seal + damage area.",
                    "Describe damage: cuts / blisters / flat set / nibbling / spiral twist.",
                    "How long until failure + cycles + depressurization events?",
                ],
            )
        return {
            "assumption_list": assumptions,
            "pending_assumptions": list(getattr(state, "pending_assumptions", []) or []),
            "assumptions_confirmed": False,
            "assumption_lock_hash": current_hash,
            "risk_heatmap": risk_heatmap,
            "rfq_ready": False,
            "ask_missing_request": request,
            "ask_missing_scope": "technical",
            "awaiting_user_input": True,
            "last_node": "assumption_lock_node",
            "phase": PHASE.VALIDATION,
        }

    if pending:
        numbered = [f"{item['id']}. {item['text']}" for item in assumptions if str(item.get("id") or "") in set(pending)]
        question = (
            "Bitte bestätige die kritischen Annahmen explizit mit `confirm #"
            + ",".join(pending)
            + "` oder korrigiere sie: "
            + " ".join(numbered)
        )
        request = AskMissingRequest(
            missing_fields=[f"assumption_{idx}" for idx in pending],
            question=question,
            reason="assumption_lock_required",
            questions=numbered[:3],
        )
        return {
            "assumption_list": assumptions,
            "pending_assumptions": pending,
            "assumptions_confirmed": False,
            "assumption_lock_hash": current_hash,
            "assumption_lock_hash_confirmed": None if hash_mismatch else getattr(state, "assumption_lock_hash_confirmed", None),
            "risk_heatmap": risk_heatmap,
            "rfq_ready": False,
            "ask_missing_request": request,
            "ask_missing_scope": "technical",
            "awaiting_user_input": True,
            "last_node": "assumption_lock_node",
            "phase": PHASE.VALIDATION,
        }

    return {
        "assumption_list": assumptions,
        "pending_assumptions": [],
        "assumptions_confirmed": True,
        "assumption_lock_hash": current_hash,
        "assumption_lock_hash_confirmed": current_hash,
        "risk_heatmap": risk_heatmap,
        "rfq_ready": (
            not (bool(getattr(state, "failure_mode_active", False)) and bool(getattr(state, "failure_evidence_missing", False)))
            and str(getattr(state, "guardrail_escalation_level", "none") or "none") == "none"
        ),
        "ask_missing_request": None,
        "ask_missing_scope": None,
        "awaiting_user_input": False,
        "last_node": "assumption_lock_node",
        "phase": PHASE.VALIDATION,
    }


def assumption_lock_router(state: SealAIState) -> str:
    if getattr(state, "awaiting_user_input", False) or getattr(state, "ask_missing_request", None):
        return "ask_missing"
    if getattr(state, "assumptions_confirmed", False) is not True:
        return "ask_missing"
    return "supervisor"


async def assumption_lock_router_async(state: SealAIState) -> str:
    return assumption_lock_router(state)


__all__ = ["assumption_lock_node", "assumption_lock_router", "assumption_lock_router_async"]
