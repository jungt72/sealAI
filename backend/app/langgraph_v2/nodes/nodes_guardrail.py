from __future__ import annotations
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.prompts.registry import PromptRegistry
from app.prompts.contexts import EmpathicConcernContext
"""Deterministic feasibility guardrail for high-risk technical requests."""


import math
import re
from typing import Any, Dict, List, Optional, Tuple

from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import Recommendation, SealAIState
from app.langgraph_v2.utils.messages import latest_user_text
from app.services.rag.rag_orchestrator import hybrid_retrieve

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
_H2S_PARTIAL_PRESSURE_RE = re.compile(
    r"(?:partial(?:druck| pressure)|pp(?:\s*[:=])?\s*h2s|h2s\D{0,12}partial)\D{0,12}\d+(?:[.,]\d+)?\s*(?:bar|mbar|kpa|pa|psi|ppm)?",
    re.IGNORECASE,
)
_RAG_CONDITIONAL_TEXT_RE = re.compile(
    r"(?:depends|abh[aä]ngig|unter\s+vorbehalt|typisch|typical|guideline|indikativ|conditional)",
    re.IGNORECASE,
)
_REGULATED_REFUSE_RE = re.compile(r"\b(nuclear|medical|aircraft|aviation|space|raumfahrt)\b", re.IGNORECASE)
_SIGNOFF_REFUSE_RE = re.compile(
    r"(?:\b(certif(?:y|ication)?|compliance|conform(?:ity)?|sign[\s-]?off|freigabe|zulassung)\b)",
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


def _append_guardrail_question(questions: List[str], question: str, *, max_questions: int = 3) -> List[str]:
    deduped = list(questions or [])
    if question and question not in deduped and len(deduped) < max_questions:
        deduped.append(question)
    return deduped[:max_questions]


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


def _has_h2s_partial_pressure(text: str) -> bool:
    return bool(_H2S_PARTIAL_PRESSURE_RE.search(text or ""))


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
    def _decision(data: Dict[str, Any]) -> str:
        return str(data.get("decision") or data.get("status") or "").lower()

    api682 = coverage.get("api682") or {}
    if _decision(api682) == "human_required":
        hints.append("HUMAN_REQUIRED: API 682 context detected.")

    hydrogen = coverage.get("hydrogen") or {}
    if _decision(hydrogen) == "human_required":
        hints.append("HUMAN_REQUIRED: Hydrogen service requires specialist validation.")

    h2s = coverage.get("h2s_sour") or {}
    if _decision(h2s) == "human_required":
        hints.append("HUMAN_REQUIRED: H2S/sour gas service detected.")

    gas = coverage.get("gas_decompression") or {}
    if _decision(gas) == "human_required":
        hints.append("HUMAN_REQUIRED: Gas service with high ΔP and unknown depressurization data.")

    steam = coverage.get("steam_cip_sip") or {}
    if _decision(steam) == "human_required":
        hints.append("HUMAN_REQUIRED: Steam service above 120C with missing peak-duration or chemistry context.")

    mixed = coverage.get("mixed_units") or {}
    if _decision(mixed) == "ask_user":
        hints.append("Mixed units detected; clarification required before feasibility assessment.")

    pv_limit = coverage.get("pv_limit") or {}
    if bool(pv_limit.get("pv_critical")) or str(pv_limit.get("status") or "").lower() == "critical":
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
        has_partial_pressure = _has_h2s_partial_pressure(text)
        coverage["h2s_sour"] = {
            "status": "human_required",
            "coverage": "conditional" if has_partial_pressure else "unknown",
            "reason": (
                "H2S/sour gas service detected; partial pressure provided."
                if has_partial_pressure
                else "H2S/sour gas service detected but partial pressure is missing."
            ),
            "h2s_partial_pressure_known": has_partial_pressure,
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
    hydrogen_decision = str(hydrogen.get("decision") or hydrogen.get("status") or "").lower()
    h2s_decision = str(h2s.get("decision") or h2s.get("status") or "").lower()
    if (
        hydrogen_decision in {"human_required", "ask_user"}
        or h2s_decision in {"human_required", "ask_user"}
    ):
        questions.append("Bitte bestätige H2/H2S-Anteil inkl. Konzentration bzw. Partialdruck und den Service-Typ.")

    api682 = coverage.get("api682") or {}
    api682_decision = str(api682.get("decision") or api682.get("status") or "").lower()
    if api682_decision in {"human_required", "ask_user"}:
        questions.append("Bitte bestätige API-682 Kategorie, Arrangement und Flush-Plan.")

    deduped: List[str] = []
    for item in questions:
        if item not in deduped:
            deduped.append(item)
    return deduped[:3]


def _select_guardrail_escalation(coverage: Dict[str, Dict[str, Any]]) -> Optional[str]:
    for key, data in coverage.items():
        matrix_status = str((data or {}).get("status") or "").lower()
        decision = str((data or {}).get("decision") or "").lower()
        if decision in {"refuse", "human_required", "ask_user"}:
            return f"{key}:{decision}"
        if matrix_status == "hard_block":
            return f"{key}:human_required"
    return None


def _derive_escalation_level(
    *,
    escalation_reason: Optional[str],
    text: str,
) -> str:
    lowered = str(text or "")
    if _SIGNOFF_REFUSE_RE.search(lowered):
        return "refuse"
    _, _, reason_status = str(escalation_reason or "").partition(":")
    status = reason_status.lower().strip()
    if status == "refuse":
        return "refuse"
    if status == "human_required":
        if _REGULATED_REFUSE_RE.search(lowered):
            return "refuse"
        return "human_required"
    if status == "ask_user":
        return "ask_user"
    return "none"


def _is_hard_escalation(reason: Optional[str]) -> bool:
    if not reason:
        return False
    key, _, status = reason.partition(":")
    return key in {"api682", "hydrogen", "h2s_sour"} and status in {"refuse", "human_required"}


def _rag_probe_query_for_category(*, category: str, text: str, medium: str) -> str:
    queries = {
        "steam_cip_sip": f"{text} steam CIP SIP peak duration temperature limit material compatibility",
        "gas_decompression": f"{text} gas decompression blowdown time delta p compatibility limits",
        "mixed_units": f"{text} unit conversion SI units pressure temperature dimensions",
        "pv_limit": f"{text} pv limit pressure velocity material threshold",
        "h2s_sour": f"{text} h2s sour gas partial pressure limits NACE compatibility",
        "hydrogen": f"{text} hydrogen service sealing restrictions compatibility",
        "api682": f"{text} API 682 arrangement flush plan seal support",
    }
    query = queries.get(category) or f"{text} {medium} sealing technical limits"
    return query.strip()


def _probe_rag_coverage(
    *,
    category: str,
    tenant_id: Optional[str],
    query_terms: str,
    can_read_private: bool,
    k: int = 3,
) -> Dict[str, Any]:
    if not tenant_id:
        return {
            "status": "unknown",
            "reason": "Missing tenant_id; tenant-scoped KB probe not possible.",
            "hits": 0,
            "top_sources": [],
        }
    metadata_filters: Dict[str, Any] = {}
    if not can_read_private:
        metadata_filters["metadata.visibility"] = "public"
    try:
        out = hybrid_retrieve(
            query=query_terms,
            tenant=tenant_id,
            k=k,
            metadata_filters=metadata_filters,
            use_rerank=False,
            return_metrics=True,
        )
        hits, metrics = out  # type: ignore[misc]
    except Exception as exc:
        return {
            "status": "unknown",
            "reason": f"KB probe failed closed: {type(exc).__name__}",
            "hits": 0,
            "top_sources": [],
        }

    hit_list = list(hits or [])
    if not hit_list:
        return {
            "status": "unknown",
            "reason": "No tenant-scoped KB hits for this risk category.",
            "hits": 0,
            "top_sources": [],
        }

    top_sources = list(((metrics or {}).get("sources") or []))[:k]
    top_score = float((hit_list[0].get("fused_score") or hit_list[0].get("vector_score") or 0.0))
    shared_or_non_tenant = any(
        str((hit.get("metadata") or {}).get("tenant_id") or "").strip() not in {"", tenant_id}
        for hit in hit_list[:k]
    )
    top_text = " ".join(str(hit.get("text") or "") for hit in hit_list[:2])
    if shared_or_non_tenant:
        return {
            "status": "conditional",
            "reason": "Hits include non-tenant/shared sources; cannot fully confirm tenant-specific coverage.",
            "hits": len(hit_list),
            "top_sources": top_sources,
        }
    if top_score < 0.2:
        return {
            "status": "conditional",
            "reason": "KB hits found, but confidence is low.",
            "hits": len(hit_list),
            "top_sources": top_sources,
        }
    if _RAG_CONDITIONAL_TEXT_RE.search(top_text):
        return {
            "status": "conditional",
            "reason": "KB snippets indicate conditional limits or assumptions.",
            "hits": len(hit_list),
            "top_sources": top_sources,
        }
    return {
        "status": "confirmed",
        "reason": "Tenant KB contains relevant technical references.",
        "hits": len(hit_list),
        "top_sources": top_sources,
    }


def _apply_rag_coverage_cross_check(
    state: SealAIState,
    *,
    text: str,
    medium: str,
    guardrail_coverage: Dict[str, Dict[str, Any]],
    escalation_reason: Optional[str],
    guardrail_questions: List[str],
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any], Optional[str], List[str], Recommendation]:
    rag_coverage: Dict[str, Any] = {}
    updated_coverage = dict(guardrail_coverage or {})
    updated_questions = list(guardrail_questions or [])[:3]
    updated_escalation = escalation_reason
    recommendation = _build_recommendation_with_hints(state, updated_coverage)
    can_read_private = bool(getattr(state, "can_read_private", False) or getattr(state, "is_privileged", False))
    hard_escalation = _is_hard_escalation(updated_escalation)

    for category in ("api682", "hydrogen", "h2s_sour", "steam_cip_sip", "gas_decompression", "pv_limit", "mixed_units"):
        coverage = updated_coverage.get(category) or {}
        status = str(coverage.get("status") or "").lower()
        cov = str(coverage.get("coverage") or "").lower()
        should_probe = False
        if category == "pv_limit":
            should_probe = status == "critical"
        elif category == "mixed_units":
            should_probe = status == "ask_user"
        else:
            should_probe = status in {"critical", "human_required"} and cov in {"unknown", "conditional"}
        if not should_probe:
            continue

        query_terms = _rag_probe_query_for_category(category=category, text=text, medium=medium)
        rag_result = _probe_rag_coverage(
            category=category,
            tenant_id=state.tenant_id,
            query_terms=query_terms,
            can_read_private=can_read_private,
            k=3,
        )
        rag_coverage[category] = rag_result
        rag_status = str(rag_result.get("status") or "unknown").lower()

        if category == "steam_cip_sip":
            if rag_status == "confirmed":
                updated_coverage[category] = {
                    **coverage,
                    "status": "ask_user",
                    "coverage": "conditional",
                    "reason": "Steam >120C with unknown peak duration; KB coverage exists but user values are required.",
                }
                updated_questions = _append_guardrail_question(
                    updated_questions,
                    "Bitte nenne Spitzendauer sowie CIP/SIP-Profil (Zyklen, Chemie, Peak-Temperatur).",
                )
                if not hard_escalation and (
                    updated_escalation is None or updated_escalation.startswith("steam_cip_sip:")
                ):
                    updated_escalation = "steam_cip_sip:ask_user"
            else:
                if updated_escalation is None or updated_escalation.startswith("steam_cip_sip:"):
                    updated_escalation = "steam_cip_sip:human_required"

        elif category == "gas_decompression":
            if rag_status == "confirmed":
                updated_coverage[category] = {
                    **coverage,
                    "status": "ask_user",
                    "coverage": "conditional",
                    "reason": "Gas ΔP >100 bar with missing depressurization time; KB coverage exists but key inputs are missing.",
                }
                updated_questions = _append_guardrail_question(
                    updated_questions,
                    "Bitte nenne Blowdown-/Entspannungszeit und Gaszusammensetzung (inkl. kritischer Komponenten).",
                )
                if not hard_escalation and (
                    updated_escalation is None or updated_escalation.startswith("gas_decompression:")
                ):
                    updated_escalation = "gas_decompression:ask_user"
            else:
                if updated_escalation is None or updated_escalation.startswith("gas_decompression:"):
                    updated_escalation = "gas_decompression:human_required"

        elif category == "mixed_units":
            updated_questions = _append_guardrail_question(
                updated_questions,
                "Bitte bestätige alle Eingaben in SI-Einheiten (bar, °C, mm, m/s).",
            )
            if not hard_escalation and (
                updated_escalation is None or updated_escalation.startswith("mixed_units:")
            ):
                updated_escalation = "mixed_units:ask_user"

        elif category == "pv_limit":
            if rag_status != "confirmed":
                hints = list(recommendation.risk_hints or [])
                warning = "WARNING: PV is near critical threshold and tenant KB coverage could not be confirmed."
                if warning not in hints:
                    hints.append(warning)
                recommendation = recommendation.model_copy(update={"risk_hints": hints})

        elif category == "h2s_sour":
            has_partial = bool((updated_coverage.get("h2s_sour") or {}).get("h2s_partial_pressure_known"))
            if (not has_partial) or rag_status != "confirmed":
                updated_escalation = "h2s_sour:human_required"

        elif category == "api682":
            updated_escalation = "api682:human_required"

        elif category == "hydrogen":
            updated_escalation = "hydrogen:human_required"

    return updated_coverage, rag_coverage, updated_escalation, updated_questions[:3], recommendation


def _apply_coverage_matrix_gate(
    coverage: Dict[str, Dict[str, Any]],
    *,
    rag_coverage: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, raw in (coverage or {}).items():
        item = dict(raw or {})
        old_status = str(item.get("status") or "").lower()
        cov = str(item.get("coverage") or "").lower()
        rag_status = str((rag_coverage.get(key) or {}).get("status") or "").lower()

        matrix_status = "not_covered" if cov in {"not_applicable", ""} else (
            "confirmed" if cov == "confirmed" else "conditional" if cov == "conditional" else "unknown"
        )
        decision: Optional[str] = None

        if key in {"api682", "hydrogen", "h2s_sour"} and matrix_status != "not_covered":
            matrix_status = "hard_block"
            decision = "human_required"
        elif key in {"steam_cip_sip", "gas_decompression"} and old_status in {"human_required", "ask_user"} and cov in {"unknown", "conditional"}:
            if rag_status == "confirmed":
                matrix_status = "conditional"
                decision = "ask_user"
            else:
                matrix_status = "hard_block"
                decision = "human_required"
        elif key == "mixed_units" and old_status == "ask_user":
            matrix_status = "conditional"
            decision = "ask_user"
        elif key == "pv_limit" and old_status == "critical":
            matrix_status = "conditional"
            decision = None
            item["pv_critical"] = True
        elif old_status in {"human_required", "refuse"}:
            matrix_status = "hard_block"
            decision = "human_required"
        elif old_status == "ask_user":
            matrix_status = "conditional"
            decision = "ask_user"

        item["status"] = matrix_status
        if decision is not None:
            item["decision"] = decision
        normalized[key] = item
    return normalized


def _build_guardrail_escalation_patch(
    state: SealAIState,
    *,
    guardrail_coverage: Dict[str, Dict[str, Any]],
    guardrail_rag_coverage: Dict[str, Any],
    escalation_reason: str,
    escalation_level: str,
    guardrail_questions: List[str],
) -> Dict[str, Any]:
    recommendation = _build_recommendation_with_hints(state, guardrail_coverage)
    flags = dict(state.flags or {})
    
    # 1. Identify Critical Issues (Logic preserved)
    critical_key_list = ("api682", "hydrogen", "h2s_sour", "steam_cip_sip", "gas_decompression", "pv_limit")
    if any(
        str((guardrail_coverage.get(key) or {}).get("decision") or "").lower() in {"critical", "human_required", "refuse"}
        or bool((guardrail_coverage.get(key) or {}).get("pv_critical"))
        for key in critical_key_list
    ):
        flags["risk_level"] = "critical"

    # 2. PLATINUM REFACTOR: Empathic Concern (Safety/Guardrail_v1)
    registry = PromptRegistry()
    critical_issues = []
    
    for key in critical_key_list:
       item = guardrail_coverage.get(key) or {}
       decision = str(item.get("decision") or "").lower()
       if decision in {"critical", "human_required", "refuse"} or item.get("pv_critical"):
           critical_issues.append({"type": key, "description": f"Decision: {decision}"})

    app_type = getattr(state.parameters, "application_type", None) or "General"

    ctx = EmpathicConcernContext(
        trace_id=state.run_id or "unknown",
        session_id=state.thread_id or "unknown",
        language="de",
        critical_issues=critical_issues,
        urgency_level=escalation_level,
        application_type=str(app_type)
    )
    
    prompt_content, fingerprint, version = registry.render("safety/empathic_concern_v1", ctx.to_dict())
    
    primary_question = run_llm(
        model=get_model_tier("nano"),
        prompt=prompt_content,
        system="Du bist ein Sicherheitsingenieur. Antworte empathisch und klar.",
        temperature=0.4,
        metadata={
             "prompt_id_used": "safety/empathic_concern",
             "prompt_fingerprint": fingerprint,
             "prompt_version": version
        }
    )
    
    # 3. Fallback for guardrail_questions list (for struct legacy)
    if not guardrail_questions:
         guardrail_questions = ["Compliance Check required."]

    request = AskMissingRequest(
        missing_fields=["human_review", "guardrail"],
        question=primary_question,
        reason=escalation_reason,
        questions=guardrail_questions,
    )
    return {
        "recommendation": recommendation,
        "guardrail_coverage": guardrail_coverage,
        "guardrail_rag_coverage": guardrail_rag_coverage,
        "guardrail_escalation_reason": escalation_reason,
        "guardrail_escalation_level": escalation_level,
        "guardrail_questions": guardrail_questions,
        "ask_missing_request": request,
        "ask_missing_scope": "technical",

        "prompt_id_used": "safety/empathic_concern",

        "prompt_fingerprint": fingerprint,

        "prompt_version_used": version,
        "awaiting_user_input": True,
        "phase": PHASE.VALIDATION,
        "last_node": "feasibility_guardrail_node",
        "flags": flags,
        "rfq_ready": False,
        "conversation_track": "design",
    }


def feasibility_guardrail_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    text = latest_user_text(list(state.messages or [])) or ""
    medium = str(getattr(state.parameters, "medium", "") or "")
    guardrail_coverage = _build_guardrail_coverage(state, text=text, medium=medium)
    escalation_reason = _select_guardrail_escalation(guardrail_coverage)
    guardrail_questions = _build_guardrail_questions(guardrail_coverage, text=text, medium=medium)
    (
        guardrail_coverage,
        guardrail_rag_coverage,
        escalation_reason,
        guardrail_questions,
        recommendation,
    ) = _apply_rag_coverage_cross_check(
        state,
        text=text,
        medium=medium,
        guardrail_coverage=guardrail_coverage,
        escalation_reason=escalation_reason,
        guardrail_questions=guardrail_questions,
    )
    guardrail_coverage = _apply_coverage_matrix_gate(guardrail_coverage, rag_coverage=guardrail_rag_coverage)
    escalation_reason = _select_guardrail_escalation(guardrail_coverage)
    escalation_level = _derive_escalation_level(escalation_reason=escalation_reason, text=text)
    if escalation_level == "refuse" and not escalation_reason:
        escalation_reason = "compliance_signoff:refuse"
    if escalation_reason:
        return _build_guardrail_escalation_patch(
            state,
            guardrail_coverage=guardrail_coverage,
            guardrail_rag_coverage=guardrail_rag_coverage,
            escalation_reason=escalation_reason,
            escalation_level=escalation_level,
            guardrail_questions=guardrail_questions,
        )

    flags = dict(state.flags or {})
    pv = guardrail_coverage.get("pv_limit") or {}
    if bool(pv.get("pv_critical")):
        flags["risk_level"] = "critical"
    return {
        "recommendation": recommendation,
        "guardrail_coverage": guardrail_coverage,
        "guardrail_rag_coverage": guardrail_rag_coverage,
        "guardrail_escalation_reason": None,
        "guardrail_escalation_level": "none",
        "guardrail_questions": [],
        "awaiting_user_input": False,
        "ask_missing_request": None,
        "ask_missing_scope": None,
        "phase": PHASE.VALIDATION,
        "last_node": "feasibility_guardrail_node",
        "flags": flags,
        "conversation_track": "design",
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
