"""Deterministic feasibility guardrail for high-risk technical requests."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional, Tuple

from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import Recommendation, SealAIState
from app.langgraph_v2.utils.messages import latest_user_text

_DELTA_P_RE = re.compile(
    r"(?:delta\s*p|d\s*p|Δp|druckdifferenz|druckabfall)\D{0,12}(-?\d+(?:[.,]\d+)?)\s*bar",
    re.IGNORECASE,
)
_TEMP_C_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*°?\s*c\b", re.IGNORECASE)
_TEMP_F_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*°?\s*f\b", re.IGNORECASE)
_RATE_RE = re.compile(
    r"(?:bar\s*/\s*s|bar\s+pro\s+sek|depressurization\s*rate|entspannungsrate|entlastungsrate)",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"(?:peak\s*duration|spitzendauer|max(?:imal)?dauer|sekunden|minuten|stunden|\bms\b|\bs\b|\bmin\b|\bh\b)",
    re.IGNORECASE,
)

_PV_LIMITS_BAR_MPS = {
    "default": 12.0,
    "ptfe": 20.0,
    "fkm": 10.0,
    "nbr": 8.0,
    "epdm": 7.0,
}


def _safe_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        text = raw.strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _append_risk_hint(state: SealAIState, hint: str) -> Recommendation:
    recommendation = state.recommendation or Recommendation()
    hints = list(recommendation.risk_hints or [])
    if hint not in hints:
        hints.append(hint)
    return recommendation.model_copy(update={"risk_hints": hints})


def _has_mixed_units(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    if not lowered:
        return None
    if ("psi" in lowered) and ("bar" in lowered):
        return "Du nennst Druck in psi und bar. Bitte auf eine Einheit vereinheitlichen."
    if ("°f" in lowered or re.search(r"\bf\b", lowered)) and ("°c" in lowered or re.search(r"\bc\b", lowered)):
        if re.search(r"\d+\s*°?\s*f", lowered) and re.search(r"\d+\s*°?\s*c", lowered):
            return "Du nennst Temperatur in °F und °C. Bitte auf eine Einheit vereinheitlichen."
    if ("inch" in lowered or "inches" in lowered or "zoll" in lowered or re.search(r'\b"\b', text)) and ("mm" in lowered):
        return "Du nennst Abmessungen in inch und mm. Bitte auf eine Einheit vereinheitlichen."
    return None


def _extract_delta_p_bar(text: str) -> Optional[float]:
    match = _DELTA_P_RE.search(text or "")
    if not match:
        return None
    return _safe_float(match.group(1))


def _extract_peak_temp_c(text: str, fallback_c: Optional[float]) -> Optional[float]:
    values_c = [_safe_float(m.group(1)) for m in _TEMP_C_RE.finditer(text or "")]
    c_values = [v for v in values_c if v is not None]
    values_f = [_safe_float(m.group(1)) for m in _TEMP_F_RE.finditer(text or "")]
    f_as_c = [((v - 32.0) * (5.0 / 9.0)) for v in values_f if v is not None]
    candidates = c_values + f_as_c + ([fallback_c] if fallback_c is not None else [])
    if not candidates:
        return None
    return max(candidates)


def _is_gas_context(text: str, medium: str) -> bool:
    haystack = f"{text or ''} {medium or ''}".lower()
    return any(
        marker in haystack
        for marker in ("gas", "erdgas", "prozessgas", "methan", "propan", "butan", "ammoniakgas")
    )


def _is_steam_context(text: str, medium: str) -> bool:
    haystack = f"{text or ''} {medium or ''}".lower()
    return "steam" in haystack or "dampf" in haystack


def _pv_limit_bar_mps(material: str) -> float:
    key = (material or "").strip().lower()
    for marker, limit in _PV_LIMITS_BAR_MPS.items():
        if marker != "default" and marker in key:
            return limit
    return _PV_LIMITS_BAR_MPS["default"]


def _compute_pv_ratio(state: SealAIState) -> Optional[Tuple[float, float, float]]:
    params = state.parameters
    pressure = _safe_float(getattr(params, "pressure_bar", None))
    rpm = _safe_float(getattr(params, "speed_rpm", None))
    diameter_mm = (
        _safe_float(getattr(params, "shaft_diameter", None))
        or _safe_float(getattr(params, "diameter", None))
        or _safe_float(getattr(params, "d_shaft_nominal", None))
        or _safe_float(getattr(params, "inner_diameter_mm", None))
    )
    if pressure is None or rpm is None or diameter_mm is None:
        return None
    diameter_m = diameter_mm / 1000.0
    v_mps = math.pi * diameter_m * rpm / 60.0
    pv = pressure * v_mps
    material = ""
    if state.recommendation and state.recommendation.material:
        material = state.recommendation.material
    else:
        material = str(getattr(params, "elastomer_material", "") or "")
    limit = _pv_limit_bar_mps(material)
    if limit <= 0:
        return None
    return (pv / limit), pv, limit


def _build_blocking_patch(
    state: SealAIState,
    *,
    reason: str,
    question: str,
    append_hint: str,
    critical: bool = False,
) -> Dict[str, Any]:
    recommendation = _append_risk_hint(state, append_hint)
    flags = dict(state.flags or {})
    if critical:
        flags["risk_level"] = "critical"
    request = AskMissingRequest(
        missing_fields=["human_review"],
        question=question,
        reason=reason,
    )
    return {
        "recommendation": recommendation,
        "ask_missing_request": request,
        "ask_missing_scope": "technical",
        "awaiting_user_input": True,
        "phase": PHASE.VALIDATION,
        "last_node": "feasibility_guardrail_node",
        "flags": flags,
    }


def feasibility_guardrail_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    text = latest_user_text(list(state.messages or [])) or ""
    medium = str(getattr(state.parameters, "medium", "") or "")
    lowered = text.lower()

    mixed_units = _has_mixed_units(text)
    if mixed_units:
        return _build_blocking_patch(
            state,
            reason="mixed_units",
            question=mixed_units,
            append_hint="Mixed units detected; clarification required before feasibility assessment.",
        )

    if re.search(r"\bapi\s*682\b", lowered):
        return _build_blocking_patch(
            state,
            reason="human_required_api_682",
            question="API 682 wurde erkannt. Bitte bestätige, ob ein Human-Review für die Auslegung durchgeführt werden soll.",
            append_hint="HUMAN_REQUIRED: API 682 context detected.",
            critical=True,
        )

    if re.search(r"\b(h2|hydrogen|wasserstoff)\b", lowered):
        return _build_blocking_patch(
            state,
            reason="human_required_hydrogen",
            question="Wasserstoff/H2 wurde erkannt. Bitte Human-Review freigeben, bevor ich weiterrechne.",
            append_hint="HUMAN_REQUIRED: Hydrogen service requires specialist validation.",
            critical=True,
        )

    if re.search(r"\b(h2s|sour gas|sauergas)\b", lowered):
        return _build_blocking_patch(
            state,
            reason="human_required_h2s",
            question="H2S/Sour-Gas wurde erkannt. Bitte Human-Review freigeben, bevor ich fortfahre.",
            append_hint="HUMAN_REQUIRED: H2S/sour gas service detected.",
            critical=True,
        )

    delta_p = _extract_delta_p_bar(text)
    if _is_gas_context(text, medium) and delta_p is not None and delta_p > 100.0 and not _RATE_RE.search(text):
        return _build_blocking_patch(
            state,
            reason="human_required_gas_high_delta_p_rate_unknown",
            question="Gas-Anwendung mit ΔP > 100 bar erkannt, aber Entspannungsrate fehlt. Bitte Rate (z. B. bar/s) angeben und Human-Review bestätigen.",
            append_hint="HUMAN_REQUIRED: Gas service with high ΔP and unknown depressurization rate.",
            critical=True,
        )

    peak_temp_c = _extract_peak_temp_c(text, _safe_float(getattr(state.parameters, "temperature_C", None)))
    if _is_steam_context(text, medium) and peak_temp_c is not None and peak_temp_c > 120.0 and not _DURATION_RE.search(text):
        return _build_blocking_patch(
            state,
            reason="human_required_steam_duration_unknown",
            question="Dampf >120°C erkannt, aber Spitzendauer fehlt. Bitte Dauer angeben und Human-Review bestätigen.",
            append_hint="HUMAN_REQUIRED: Steam service above 120C with unknown peak duration.",
            critical=True,
        )

    pv_eval = _compute_pv_ratio(state)
    if pv_eval is not None:
        ratio, pv, limit = pv_eval
        if ratio > 0.8:
            return _build_blocking_patch(
                state,
                reason="pv_margin_critical",
                question=(
                    f"PV-Niveau kritisch ({pv:.2f} bei Limit {limit:.2f}, >80%). "
                    "Bitte bestätige, dass ich trotz geringer Sicherheitsmarge fortfahren soll."
                ),
                append_hint=f"Critical PV margin: PV={pv:.2f}, limit={limit:.2f}, ratio={ratio:.2f}.",
                critical=True,
            )

    recommendation = state.recommendation or Recommendation()
    return {
        "recommendation": recommendation,
        "phase": PHASE.VALIDATION,
        "last_node": "feasibility_guardrail_node",
    }


def feasibility_guardrail_router(state: SealAIState) -> str:
    if getattr(state, "awaiting_user_input", False) or getattr(state, "ask_missing_request", None):
        return "ask_missing"
    return "supervisor"


async def feasibility_guardrail_router_async(state: SealAIState) -> str:
    return feasibility_guardrail_router(state)


__all__ = [
    "feasibility_guardrail_node",
    "feasibility_guardrail_router",
    "feasibility_guardrail_router_async",
]
