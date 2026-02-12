"""Deterministic feasibility guardrail for high-risk technical requests."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

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
_GENERIC_MEDIA_RE = re.compile(r"\b(oil|oel|öl|water|wasser|steam|dampf)\b", re.IGNORECASE)
_CHEMICAL_HINT_RE = re.compile(
    r"(?:additiv|zusatz|naoh|koh|acid|säure|clean(?:er|ing)?|detergent|cip|sip|particle|abrasive|solid)",
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


def _build_recommendation_with_hints(state: SealAIState, coverage: Dict[str, Dict[str, Any]]) -> Recommendation:
    recommendation = state.recommendation or Recommendation()
    hints = list(recommendation.risk_hints or [])

    api682 = coverage.get("api682") or {}
    if str(api682.get("status") or "").lower() == "human_required":
        hints.append("HUMAN_REQUIRED: API 682 context detected.")

    hydrogen = coverage.get("hydrogen") or {}
    if str(hydrogen.get("status") or "").lower() == "human_required":
        hints.append("HUMAN_REQUIRED: Hydrogen service requires specialist validation.")

    h2s = coverage.get("h2s_sour") or {}
    if str(h2s.get("status") or "").lower() == "human_required":
        hints.append("HUMAN_REQUIRED: H2S/sour gas service detected.")

    gas = coverage.get("gas_decompression") or {}
    if str(gas.get("status") or "").lower() == "human_required":
        hints.append("HUMAN_REQUIRED: Gas service with high ΔP and unknown depressurization data.")

    steam = coverage.get("steam_cip_sip") or {}
    if str(steam.get("status") or "").lower() == "human_required":
        hints.append("HUMAN_REQUIRED: Steam service above 120C with missing peak-duration or chemistry context.")

    mixed = coverage.get("mixed_units") or {}
    if str(mixed.get("status") or "").lower() == "ask_user":
        hints.append("Mixed units detected; clarification required before feasibility assessment.")

    pv_limit = coverage.get("pv_limit") or {}
    if str(pv_limit.get("status") or "").lower() == "critical":
        pv = pv_limit.get("value")
        limit = pv_limit.get("limit")
        ratio = pv_limit.get("ratio")
        if isinstance(pv, (int, float)) and isinstance(limit, (int, float)) and isinstance(ratio, (int, float)):
            hints.append(f"Critical PV margin: PV={pv:.2f}, limit={limit:.2f}, ratio={ratio:.2f}.")
        else:
            hints.append("Critical PV margin detected.")

    deduped: List[str] = []
    for hint in hints:
        if hint and hint not in deduped:
            deduped.append(hint)
    return recommendation.model_copy(update={"risk_hints": deduped})


def _build_guardrail_coverage(state: SealAIState, *, text: str, medium: str) -> Dict[str, Dict[str, Any]]:
    lowered = (text or "").lower()
    coverage: Dict[str, Dict[str, Any]] = {
        "api682": {"status": "ok", "coverage": "not_applicable", "reason": "API 682 not referenced."},
        "hydrogen": {"status": "ok", "coverage": "not_applicable", "reason": "No hydrogen marker detected."},
        "h2s_sour": {"status": "ok", "coverage": "not_applicable", "reason": "No H2S/sour-gas marker detected."},
        "steam_cip_sip": {"status": "ok", "coverage": "not_applicable", "reason": "Steam context not detected."},
        "gas_decompression": {"status": "ok", "coverage": "not_applicable", "reason": "Gas decompression context not detected."},
        "pv_limit": {"status": "ok", "coverage": "not_applicable", "reason": "PV check not computable from current parameters."},
        "mixed_units": {"status": "ok", "coverage": "not_applicable", "reason": "No mixed units detected."},
    }

    mixed_units = _has_mixed_units(text)
    if mixed_units:
        coverage["mixed_units"] = {"status": "ask_user", "coverage": "unknown", "reason": mixed_units}

    if re.search(r"\bapi\s*682\b", lowered):
        coverage["api682"] = {
            "status": "human_required",
            "coverage": "confirmed",
            "reason": "API 682 mention requires specialist review.",
        }

    if re.search(r"\b(h2|hydrogen|wasserstoff)\b", lowered):
        coverage["hydrogen"] = {
            "status": "human_required",
            "coverage": "confirmed",
            "reason": "Hydrogen service detected.",
        }

    if re.search(r"\b(h2s|sour gas|sauergas)\b", lowered):
        coverage["h2s_sour"] = {
            "status": "human_required",
            "coverage": "confirmed",
            "reason": "H2S/sour gas service detected.",
        }

    is_gas = _is_gas_context(text, medium)
    delta_p = _extract_delta_p_bar(text)
    has_rate = bool(_RATE_RE.search(text or ""))
    has_duration = bool(_DURATION_RE.search(text or ""))
    if is_gas:
        if delta_p is None:
            coverage["gas_decompression"] = {
                "status": "ask_user",
                "coverage": "unknown",
                "reason": "Gas service detected but ΔP is missing.",
            }
        elif delta_p > 100.0 and not (has_rate or has_duration):
            coverage["gas_decompression"] = {
                "status": "human_required",
                "coverage": "unknown",
                "reason": "Gas service with ΔP > 100 bar lacks depressurization rate/time.",
                "delta_p_bar": delta_p,
            }
        else:
            coverage["gas_decompression"] = {
                "status": "ok",
                "coverage": "confirmed",
                "reason": "Gas decompression inputs are sufficient for deterministic screening.",
                "delta_p_bar": delta_p,
                "depressurization_rate_known": has_rate,
                "depressurization_time_known": has_duration,
            }

    is_steam = _is_steam_context(text, medium)
    peak_temp_c = _extract_peak_temp_c(text, _safe_float(getattr(state.parameters, "temperature_C", None)))
    medium_additives = str(getattr(state.parameters, "medium_additives", "") or "").strip()
    has_chemical_context = bool(medium_additives) or bool(_CHEMICAL_HINT_RE.search(text or ""))
    generic_media = bool(_GENERIC_MEDIA_RE.search(f"{text or ''} {medium or ''}"))
    if is_steam:
        if peak_temp_c is None:
            coverage["steam_cip_sip"] = {
                "status": "ask_user",
                "coverage": "unknown",
                "reason": "Steam context detected but peak temperature is missing.",
            }
        elif peak_temp_c > 120.0 and not has_duration:
            coverage["steam_cip_sip"] = {
                "status": "human_required",
                "coverage": "unknown",
                "reason": "Steam >120C detected but peak duration is missing.",
                "peak_temp_c": peak_temp_c,
            }
        elif peak_temp_c > 120.0 and not has_chemical_context:
            coverage["steam_cip_sip"] = {
                "status": "ask_user",
                "coverage": "unknown",
                "reason": "Steam >120C requires CIP/SIP chemistry details.",
                "peak_temp_c": peak_temp_c,
            }
        elif generic_media and not has_chemical_context:
            coverage["steam_cip_sip"] = {
                "status": "ask_user",
                "coverage": "conditional",
                "reason": "Only generic steam/media terms detected; additives/cleaning context is needed.",
                "peak_temp_c": peak_temp_c,
            }
        else:
            coverage["steam_cip_sip"] = {
                "status": "ok",
                "coverage": "confirmed",
                "reason": "Steam context has enough deterministic inputs for screening.",
                "peak_temp_c": peak_temp_c,
            }

    pv_eval = _compute_pv_ratio(state)
    if pv_eval is not None:
        ratio, pv, limit = pv_eval
        status = "critical" if ratio > 0.8 else "ok"
        coverage["pv_limit"] = {
            "status": status,
            "coverage": "confirmed",
            "reason": "PV ratio computed from pressure, speed, and diameter.",
            "value": pv,
            "limit": limit,
            "ratio": ratio,
        }

    return coverage


def _build_guardrail_questions(
    coverage: Dict[str, Dict[str, Any]],
    *,
    text: str,
    medium: str,
) -> List[str]:
    questions: List[str] = []

    gas = coverage.get("gas_decompression") or {}
    if str(gas.get("coverage") or "").lower() in {"unknown", "conditional"}:
        questions.append("Bitte nenne für die Gas-Entspannung ΔP sowie Entspannungszeit oder Blowdown-Rate (z. B. bar/s).")

    steam = coverage.get("steam_cip_sip") or {}
    if str(steam.get("coverage") or "").lower() in {"unknown", "conditional"}:
        questions.append("Bitte nenne Spitzentemperatur, Spitzendauer sowie CIP/SIP-Chemikalien oder Reinigungsmedien.")

    if _GENERIC_MEDIA_RE.search(f"{text or ''} {medium or ''}") and not _CHEMICAL_HINT_RE.search(text or ""):
        questions.append("Bei Medium wie Öl/Wasser: Welche Additive, Reinigungsstoffe und Partikel/Abrasivanteile sind vorhanden?")

    hydrogen = coverage.get("hydrogen") or {}
    h2s = coverage.get("h2s_sour") or {}
    if (
        str(hydrogen.get("status") or "").lower() in {"human_required", "ask_user"}
        or str(h2s.get("status") or "").lower() in {"human_required", "ask_user"}
    ):
        questions.append("Bitte bestätige H2/H2S-Anteil inkl. Konzentration bzw. Partialdruck und den Service-Typ.")

    api682 = coverage.get("api682") or {}
    if str(api682.get("status") or "").lower() in {"human_required", "ask_user"}:
        questions.append("Bitte bestätige API-682 Kategorie, Arrangement und Flush-Plan.")

    deduped: List[str] = []
    for item in questions:
        if item not in deduped:
            deduped.append(item)
    return deduped[:3]


def _select_guardrail_escalation(coverage: Dict[str, Dict[str, Any]]) -> Optional[str]:
    critical_keys = {"api682", "hydrogen", "h2s_sour", "steam_cip_sip", "gas_decompression"}
    for key, data in coverage.items():
        status = str((data or {}).get("status") or "").lower()
        cov = str((data or {}).get("coverage") or "").lower()
        if status in {"refuse", "human_required"}:
            return f"{key}:{status}"
        if key == "pv_limit" and status == "critical":
            return "pv_limit:critical"
        if key in critical_keys and cov in {"unknown", "conditional"}:
            return f"{key}:{cov}"
    return None


def _build_guardrail_escalation_patch(
    state: SealAIState,
    *,
    guardrail_coverage: Dict[str, Dict[str, Any]],
    escalation_reason: str,
    guardrail_questions: List[str],
) -> Dict[str, Any]:
    recommendation = _build_recommendation_with_hints(state, guardrail_coverage)
    flags = dict(state.flags or {})
    if any(
        str((guardrail_coverage.get(key) or {}).get("status") or "").lower() in {"critical", "human_required", "refuse"}
        for key in ("api682", "hydrogen", "h2s_sour", "steam_cip_sip", "gas_decompression", "pv_limit")
    ):
        flags["risk_level"] = "critical"
    primary_question = (
        "Zur sicheren Freigabe brauche ich noch folgende Angaben: " + " ".join(guardrail_questions)
        if guardrail_questions
        else "Für diesen Fall ist ein Human-Review bzw. eine sicherheitsrelevante Klärung erforderlich."
    )
    request = AskMissingRequest(
        missing_fields=["human_review", "guardrail"],
        question=primary_question,
        reason=escalation_reason,
        questions=guardrail_questions,
    )
    return {
        "recommendation": recommendation,
        "guardrail_coverage": guardrail_coverage,
        "guardrail_escalation_reason": escalation_reason,
        "guardrail_questions": guardrail_questions,
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
    guardrail_coverage = _build_guardrail_coverage(state, text=text, medium=medium)
    escalation_reason = _select_guardrail_escalation(guardrail_coverage)
    guardrail_questions = _build_guardrail_questions(guardrail_coverage, text=text, medium=medium)
    if escalation_reason:
        return _build_guardrail_escalation_patch(
            state,
            guardrail_coverage=guardrail_coverage,
            escalation_reason=escalation_reason,
            guardrail_questions=guardrail_questions,
        )

    recommendation = _build_recommendation_with_hints(state, guardrail_coverage)
    return {
        "recommendation": recommendation,
        "guardrail_coverage": guardrail_coverage,
        "guardrail_escalation_reason": None,
        "guardrail_questions": [],
        "awaiting_user_input": False,
        "ask_missing_request": None,
        "ask_missing_scope": None,
        "phase": PHASE.VALIDATION,
        "last_node": "feasibility_guardrail_node",
    }


def feasibility_guardrail_router(state: SealAIState) -> str:
    if getattr(state, "guardrail_escalation_reason", None):
        return "ask_missing"
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
