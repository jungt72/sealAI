from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Dict, Mapping


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(exclude_none=True)
        if isinstance(dumped, dict):
            return dict(dumped)
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        dumped = as_dict()
        if isinstance(dumped, dict):
            return dict(dumped)
    try:
        return dict(value)
    except Exception:
        return {}


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    return value


def rfq_gate_failed(values: Mapping[str, Any] | Dict[str, Any]) -> bool:
    state = dict(values or {})
    rfq_ready = bool(state.get("rfq_ready", False))
    escalation_level = str(state.get("guardrail_escalation_level", "none") or "none").strip().lower()
    failure_evidence_missing = bool(state.get("failure_evidence_missing", False))
    assumption_hash = state.get("assumption_lock_hash")
    confirmed_hash = state.get("assumption_lock_hash_confirmed")
    return (
        (not rfq_ready)
        or escalation_level != "none"
        or failure_evidence_missing
        or not assumption_hash
        or assumption_hash != confirmed_hash
    )


def _normalize_assumptions(values: Dict[str, Any]) -> Dict[str, Any]:
    assumptions_raw = list(values.get("assumption_list") or [])
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(assumptions_raw, start=1):
        row = _as_dict(item)
        ident = str(row.get("id") or f"A{index}").strip()
        text = str(row.get("text") or "").strip()
        impact = str(row.get("impact") or "medium").strip().lower()
        if impact not in {"low", "medium", "high", "critical"}:
            impact = "medium"
        source = str(row.get("source") or "inferred").strip().lower()
        if source not in {"user", "inferred", "rag"}:
            source = "unknown"
        normalized.append(
            {
                "id": ident,
                "text": text,
                "impact": impact,
                "source": source,
                "requires_confirmation": bool(row.get("requires_confirmation", True)),
            }
        )
    pending_ids = [str(item) for item in list(values.get("pending_assumptions") or []) if str(item).strip()]
    pending_lookup = set(pending_ids)
    if bool(values.get("assumptions_confirmed", False)) and not pending_ids:
        confirmed_ids = [str(item.get("id")) for item in normalized if str(item.get("id"))]
    else:
        confirmed_ids = [str(item.get("id")) for item in normalized if str(item.get("id")) and str(item.get("id")) not in pending_lookup]
    return {
        "list": normalized,
        "confirmed_ids": confirmed_ids,
        "pending_ids": pending_ids,
    }


def _risk_level(values: Dict[str, Any], heatmap: Dict[str, str]) -> str:
    flags = _as_dict(values.get("flags"))
    flagged = str(flags.get("risk_level") or "").strip().lower()
    if flagged in {"low", "medium", "high", "critical"}:
        return flagged
    order = {"low": 1, "medium": 2, "high": 3, "critical": 4, "unknown": 3}
    level = "low"
    score = order[level]
    for candidate in heatmap.values():
        cand = str(candidate or "").strip().lower()
        cand_score = order.get(cand)
        if cand_score and cand_score > score:
            level = "high" if cand == "unknown" else cand
            score = cand_score
    return level


def _pv_check(values: Dict[str, Any], guardrail_coverage: Dict[str, Any]) -> Dict[str, Any]:
    params = _as_dict(values.get("parameters"))
    pressure = params.get("pressure_bar")
    if pressure is None:
        pressure = params.get("pressure")
    rpm = params.get("speed_rpm")
    diameter_mm = (
        params.get("shaft_diameter")
        or params.get("diameter")
        or params.get("d_shaft_nominal")
        or params.get("inner_diameter_mm")
    )
    pv_cov = _as_dict((guardrail_coverage or {}).get("pv_limit"))
    try:
        pressure_f = float(pressure) if pressure is not None else None
        rpm_f = float(rpm) if rpm is not None else None
        diameter_mm_f = float(diameter_mm) if diameter_mm is not None else None
    except (TypeError, ValueError):
        pressure_f = None
        rpm_f = None
        diameter_mm_f = None
    if pressure_f is None or rpm_f is None or diameter_mm_f is None:
        return {
            "available": False,
            "pressure_bar": pressure,
            "speed_rpm": rpm,
            "diameter_mm": diameter_mm,
            "notes": ["PV check not computable from current parameters."],
        }
    v_mps = math.pi * (diameter_mm_f / 1000.0) * rpm_f / 60.0
    pv = pressure_f * v_mps
    limit = pv_cov.get("limit")
    ratio = pv_cov.get("ratio")
    near_limit = False
    try:
        if isinstance(ratio, (int, float)):
            near_limit = float(ratio) >= 0.85
        elif isinstance(limit, (int, float)) and float(limit) > 0:
            near_limit = (pv / float(limit)) >= 0.85
    except (TypeError, ValueError, ZeroDivisionError):
        near_limit = False
    return {
        "available": True,
        "pressure_bar": pressure_f,
        "speed_rpm": rpm_f,
        "diameter_mm": diameter_mm_f,
        "surface_speed_mps": v_mps,
        "pv": pv,
        "limits": {
            "pv_limit_bar_mps": limit,
            "ratio": ratio,
            "status": pv_cov.get("status"),
        },
        "near_limit": near_limit,
        "notes": [str(pv_cov.get("reason"))] if pv_cov.get("reason") else [],
    }


def _unit_notes(guardrail_coverage: Dict[str, Any]) -> Dict[str, Any]:
    mixed = _as_dict((guardrail_coverage or {}).get("mixed_units"))
    status = str(mixed.get("status") or "").strip().lower()
    detected = status in {"conditional", "unknown", "hard_block"} or bool(mixed.get("decision"))
    notes: list[str] = []
    reason = mixed.get("reason")
    if reason:
        notes.append(str(reason))
    if detected and not notes:
        notes.append("Mixed units detected; confirm SI-normalized values before final release.")
    return {"detected_mixed_units": detected, "notes": notes}


def _attachment_sources(values: Dict[str, Any]) -> Dict[str, Any]:
    sources_raw = list(values.get("sources") or [])
    sources: list[dict[str, Any]] = []
    for item in sources_raw:
        row = _as_dict(item)
        sources.append(
            {
                "source": row.get("source"),
                "metadata": _as_dict(row.get("metadata")),
                "has_snippet": bool(row.get("snippet")),
            }
        )
    return {"sources": sources}


def build_rfq_report(
    *,
    state: Mapping[str, Any] | Dict[str, Any],
    chat_id: str,
    checkpoint_thread_id: str,
    tenant_id: str,
    user_id: str,
    now_ts: float | None = None,
) -> Dict[str, Any]:
    """
    Build a deterministic RFQ report from state.

    Liability invariant: fails closed unless RFQ gate is fully satisfied.
    """
    values = _as_dict(state)
    if rfq_gate_failed(values):
        raise ValueError("rfq_not_ready")

    generated_at = float(now_ts) if now_ts is not None else time.time()
    guardrail_coverage = _as_dict(values.get("guardrail_coverage"))
    guardrail_rag_coverage = _as_dict(values.get("guardrail_rag_coverage"))
    risk_heatmap = _canonicalize(_as_dict(values.get("risk_heatmap")))
    recommendation = _as_dict(values.get("recommendation"))
    assumptions = _normalize_assumptions(values)
    unit_norm = _unit_notes(guardrail_coverage)
    params = _as_dict(values.get("parameters"))

    executive_summary = {
        "status": "rfq_ready",
        "conversation_track": str(values.get("conversation_track") or "design"),
        "summary": (
            str(recommendation.get("summary") or "").strip()
            or str(values.get("final_text") or "").strip()
            or str(values.get("discovery_summary") or "").strip()
            or "RFQ report generated from confirmed assumptions and current state snapshot."
        ),
    }

    conditioned_recommendations = []
    if recommendation:
        conditioned_recommendations.append(
            {
                "seal_family": recommendation.get("seal_family"),
                "material": recommendation.get("material"),
                "profile": recommendation.get("profile"),
                "summary": recommendation.get("summary"),
                "conditions": "Derived under confirmed assumptions; verify prototype in application duty cycle.",
            }
        )

    report = {
        "meta": {
            "schema_version": "2.0",
            "generated_at": generated_at,
            "chat_id": chat_id,
            "checkpoint_thread_id": checkpoint_thread_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "assumption_lock_hash": values.get("assumption_lock_hash"),
            "assumption_lock_hash_confirmed": values.get("assumption_lock_hash_confirmed"),
            "rfq_ready": True,
        },
        "executive_summary": executive_summary,
        "inputs": {
            "parameters": _canonicalize(params),
            "hardware": _canonicalize(_as_dict(values.get("hardware"))),
            "environment": _canonicalize(_as_dict(values.get("environment"))),
            "units_notes": list(unit_norm.get("notes") or []),
        },
        "assumptions": assumptions,
        "risk": {
            "level": _risk_level(values, risk_heatmap),
            "heatmap": risk_heatmap,
            "guardrail_escalation_level": str(values.get("guardrail_escalation_level") or "none"),
        },
        "coverage": {
            "guardrail_coverage": _canonicalize(guardrail_coverage),
            "guardrail_rag_coverage": _canonicalize(guardrail_rag_coverage),
        },
        "calculated_checks": {
            "pv": _pv_check(values, guardrail_coverage),
            "unit_normalization": unit_norm,
        },
        "recommendation": {
            "status": "rfq_ready",
            "conditioned_recommendations": conditioned_recommendations,
            "risk_hints": list(recommendation.get("risk_hints") or []),
        },
        "attachments": _attachment_sources(values),
        "disclaimer": {
            "text": (
                "Engineering recommendations are contingent on confirmed assumptions and provided operating data. "
                "Final suitability must be validated by testing and responsible engineering sign-off."
            ),
            "assumptions_basis": (
                "User provided + confirmed assumptions; directional guidance; prototype testing required."
            ),
        },
    }

    canonical_report = _canonicalize(report)
    digest = hashlib.sha256(canonical_json(canonical_report).encode("utf-8")).hexdigest()
    canonical_report["meta"]["report_hash"] = digest
    canonical_report["meta"]["report_hash_algo"] = "sha256"
    return _canonicalize(canonical_report)


__all__ = ["build_rfq_report", "canonical_json", "rfq_gate_failed"]
