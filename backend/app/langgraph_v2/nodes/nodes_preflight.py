from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.langgraph_v2.constants import PHASE, PhaseLiteral
from app.langgraph_v2.contracts import (
    ApplicationType,
    AskMissingRequest,
    AskMissingScope,
    CalcResults,
    CoverageAnalysis,
    ParameterProfile,
    SealFamily,
)
from app.langgraph_v2.state import (
    SealAIState,
    TechnicalParameters,
    WorkingMemory,
)
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.output_sanitizer import extract_json_obj
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_lww  # Updated import
from app.langgraph_v2.utils.state_debug import log_state_debug

logger = logging.getLogger(__name__)

# --- Konstanten / Daten (Mock) ---
APPLICATION_TO_SEAL_FAMILY = {
    "hydraulics": "piston_seal",
    "pneumatics": "rod_seal",
    "pump": "rotary_shaft_seal",
    "general": "o_ring",
}

SEAL_PARAMETER_PROFILES = {
    "o_ring": ParameterProfile(
        required=["pressure_bar", "temperature_C", "medium"],
        optional=["cross_section_diameter", "inner_diameter"],
    ),
    "rotary_shaft_seal": ParameterProfile(
        required=["pressure_bar", "temperature_C", "medium", "shaft_diameter", "speed_rpm"],
        optional=["housing_bore_diameter", "width"],
    ),
    # Fallback
    "default": ParameterProfile(
        required=["pressure_bar", "temperature_C"],
        optional=["medium"],
    ),
}

# --- Hilfsfunktionen für das LLM-Parsing (Preflight) ---

def _parse_user_params(text: str, expected_keys: List[str]) -> Dict[str, Any]:
    """
    Simples LLM- oder Regex-Extraction-Tool für fehlende Werte.
    Hier vereinfacht als Mock/Regex.
    """
    extracted = {}
    # Sehr simpler Regex für "key=value" oder "key: value"
    # Echte Implementierung würde LLM (Nano) nutzen.
    if not text:
        return {}

    # 1. Versuch: JSON extraction
    data, ok = extract_json_obj(text, default={})
    if ok and isinstance(data, dict):
        # Filtern auf expected
        for k, v in data.items():
            if k in expected_keys or not expected_keys:
                extracted[k] = v
        return extracted

    # 2. Versuch: Regex für Zahlenwerte
    # z. B. "10 bar", "80 grad"
    patterns = {
        "pressure_bar": r"(\d+(?:[.,]\d+)?)\s*(?:bar|psi)",
        "temperature_C": r"(\d+(?:[.,]\d+)?)\s*(?:°?C|grad|celsius)",
        "speed_rpm": r"(\d+(?:[.,]\d+)?)\s*(?:u/min|rpm)",
        "shaft_diameter": r"(\d+(?:[.,]\d+)?)\s*(?:mm|millimeter)",
    }
    for key, pat in patterns.items():
        if key in expected_keys:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                try:
                    val_str = match.group(1).replace(",", ".")
                    extracted[key] = float(val_str)
                except ValueError:
                    pass
    
    # 3. Versuch: Einfache String-Suche für Medium
    if "medium" in expected_keys:
        media = ["öl", "oil", "wasser", "water", "luft", "air", "hydraulik"]
        for m in media:
            if m in text.lower():
                extracted["medium"] = m
                break

    return extracted


# --- Nodes ---

def preflight_use_case_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Analysiert den Kontext auf Application Type (z. B. Hydraulik, Pneumatik).
    """
    user_text = latest_user_text(state.get("messages"))
    # Mocking simple detection
    app_type = "general"
    if "hydraulik" in (user_text or "").lower():
        app_type = "hydraulics"
    elif "pneumatik" in (user_text or "").lower():
        app_type = "pneumatics"
    elif "pumpe" in (user_text or "").lower():
        app_type = "pump"
    
    return {
        "application_type": app_type,
        "phase": PHASE.PREFLIGHT_USE_CASE,
        "last_node": "preflight_use_case_node",
    }


def seal_family_selector_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Wählt basierend auf Application Type die Seal Family.
    """
    app_type = str(state.get("application_type") or "general")
    family = APPLICATION_TO_SEAL_FAMILY.get(app_type, "o_ring")
    
    return {
        "seal_family": family,
        "phase": PHASE.PREFLIGHT_USE_CASE,
        "last_node": "seal_family_selector_node",
    }


def parameter_profile_builder_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Lädt das Parameter-Profil für die gewählte Seal Family und ermittelt Missing Params.
    """
    family = str(state.get("seal_family") or "default")
    profile = SEAL_PARAMETER_PROFILES.get(family, SEAL_PARAMETER_PROFILES["default"])

    # Ist-Zustand prüfen
    params_obj = state.parameters or TechnicalParameters()
    parameters = params_obj.as_dict()
    
    missing = []
    for req in profile.required:
        val = parameters.get(req)
        if val in (None, ""):
            missing.append(req)

    # Serialisierbares Profil
    parameter_profile = ParameterProfile(
        required=profile.required,
        optional=profile.optional
    )

    return {
        "parameter_profile": parameter_profile,
        "missing_params": missing,
        "ask_missing_request": None,
        "coverage_analysis": None,
        "phase": PHASE.PREFLIGHT_PARAMETERS,
        "last_node": "parameter_profile_builder_node",
    }


def ingest_missing_user_input_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Parse user-supplied values for missing parameters (if we paused earlier).
    """
    params_obj = state.parameters or TechnicalParameters()
    parameters = params_obj.as_dict()
    missing = list(state.get("missing_params") or [])
    awaiting = bool(state.get("awaiting_user_input"))

    request_raw = state.get("ask_missing_request")
    if isinstance(request_raw, AskMissingRequest):
        request = request_raw
    elif isinstance(request_raw, dict):
        request = AskMissingRequest.model_validate(request_raw)
    else:
        request = None

    expected_keys = list(missing)
    if not expected_keys and request is not None:
        expected_keys = list(request.missing_fields)

    user_text = latest_user_text(state.get("messages"))
    parsed = _parse_user_params(user_text, expected_keys)
    
    # [PATCH] Use LWW
    (
        merged_params,
        merged_provenance,
        merged_versions,
        merged_updated_at,
        applied_fields,
        rejected_fields,
    ) = apply_parameter_patch_lww(
        parameters,
        parsed,
        state.parameter_provenance,
        source="user",
        parameter_versions=state.parameter_versions,
        parameter_updated_at=state.parameter_updated_at,
        base_versions=state.parameter_versions, # User input sees current state
    )
    # [PATCH] End

    for key in parsed:
        if key in missing and key in applied_fields:
            missing.remove(key)

    return {
        "parameters": TechnicalParameters.model_validate(merged_params),
        "parameter_provenance": merged_provenance,
        "parameter_versions": merged_versions,
        "parameter_updated_at": merged_updated_at,
        "missing_params": missing,
        "ask_missing_request": None,
        "awaiting_user_input": False if awaiting else state.get("awaiting_user_input", False),
        "ask_missing_scope": None,
        "phase": PHASE.PREFLIGHT_PARAMETERS,
        "last_node": "ingest_missing_user_input_node",
    }


def coverage_analysis_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Compute coverage over required parameters and request missing data when needed.
    """
    # PATCH/FIX: Observability – log entry for coverage analysis
    logger.info(
        "coverage_analysis_node_enter",
        run_id=state.run_id,
        thread_id=state.thread_id,
        phase=state.phase,
        missing=len(state.get("missing_params") or []),
    )
    raw_profile = state.get("parameter_profile")
    if isinstance(raw_profile, ParameterProfile):
        parameter_profile = raw_profile
    elif isinstance(raw_profile, dict):
        parameter_profile = ParameterProfile.model_validate(raw_profile)
    else:
        parameter_profile = ParameterProfile(required=[], optional=[])

    params_obj = state.parameters or TechnicalParameters()
    parameters = params_obj.as_dict()
    required = parameter_profile.required

    missing = [param for param in required if param not in parameters or parameters[param] in (None, "")]
    coverage_score = 1.0 if not required else max(0.0, min(1.0, (len(required) - len(missing)) / len(required)))

    coverage_analysis = CoverageAnalysis(
        coverage_score=coverage_score,
        missing_params=missing,
        high_impact_gaps=list(missing),
    )
    recommendation_ready = coverage_score >= 0.75 and not missing

    ask_missing_request: AskMissingRequest | None = None
    if missing:
        missing_text = ", ".join(missing)
        question = (
            "Mir fehlen noch folgende Angaben, um eine belastbare Dichtungsempfehlung zu geben: "
            f"{missing_text}. Bitte liefere die Werte (z. B. als JSON oder Schlüssel=wert-Liste)."
        )
        ask_missing_request = AskMissingRequest(
            missing_fields=missing,
            question=question,
            suggested_format='{ "pressure_bar": 10, "temperature_max": 80, "medium": "Hydraulikoel" }',
        )

    logger.info(
        "coverage_analysis_node_exit",
        run_id=state.run_id,
        thread_id=state.thread_id,
        coverage_score=coverage_score,
        missing=missing,
    )
    return {
        "coverage_analysis": coverage_analysis,
        "coverage_score": coverage_score,
        "coverage_gaps": missing,
        "recommendation_ready": recommendation_ready,
        "missing_params": missing,
        "ask_missing_request": ask_missing_request,
        "ask_missing_scope": "technical" if missing else None,
        "phase": PHASE.PREFLIGHT_PARAMETERS,
        "last_node": "coverage_analysis_node",
    }


def calc_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Stub-Berechnung: füllt einfache Kennzahlen aus.
    """
    calc_results = CalcResults(
        safety_factor=1.5,
        temperature_margin=20.0,
        pressure_margin=10.0,
        notes=["Stub-Berechnung (noch zu ersetzen)"],
    )
    return {
        "analysis_complete": True,
        "calc_results_ok": True,
        "calc_results": calc_results,
        "phase": PHASE.CALCULATION,
        "last_node": "calc_node",
    }


def ask_missing_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Prepare a structured ask-missing request and pause for user input.
    """
    raw_request = state.get("ask_missing_request")
    if isinstance(raw_request, AskMissingRequest):
        request = raw_request
    elif isinstance(raw_request, dict):
        request = AskMissingRequest.model_validate(raw_request)
    else:
        request = None

    missing = state.get("missing_params") or []
    scope: AskMissingScope | None = state.get("ask_missing_scope")

    if request is None:
        question = (
            "Ich benötige noch einige Angaben, um fortzufahren: "
            f"{', '.join(missing) if missing else 'Bitte ergänze die fehlenden Felder.'}"
        )
        request = AskMissingRequest(missing_fields=missing, question=question)

    friendly_message = request.question
    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": friendly_message, "response_kind": "ask_missing"})

    logger.info(
        "ask_missing_node_exit",
        run_id=state.run_id,
        thread_id=state.thread_id,
        scope=scope or "technical",
        missing=missing,
    )  # PATCH/FIX: Observability – ask-missing logging
    return {
        "ask_missing_request": request,
        "awaiting_user_input": True,
        "ask_missing_scope": scope or "technical",
        "messages": list(state.get("messages") or []),
        "phase": PHASE.PREFLIGHT_PARAMETERS if (scope or "technical") == "technical" else PHASE.ENTRY,
        "last_node": "ask_missing_node",
        "working_memory": wm,
    }


def analysis_gate_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Weiterleitung nach der Berechnung: Consulting-Phase oder Fehler.
    """
    ok = bool(state.get("calc_results_ok"))
    if not ok:
        error_text = state.get("error") or "Berechnung fehlgeschlagen."
        wm = state.working_memory or WorkingMemory()
        wm = wm.model_copy(update={"response_kind": "error", "response_text": error_text})  # PATCH/FIX: Calc-Error branch surfaced
        logger.error(
            "analysis_gate_node_error",
            run_id=state.run_id,
            thread_id=state.thread_id,
            error=error_text,
        )  # PATCH/FIX: Observability – error path
        return {
            "phase": PHASE.ERROR,
            "error": error_text,
            "last_node": "analysis_gate_node",
            "working_memory": wm,
        }
    logger.info(
        "analysis_gate_node_ok",
        run_id=state.run_id,
        thread_id=state.thread_id,
    )  # PATCH/FIX: Observability – ok path
    return {
        "phase": PHASE.CONSULTING,
        "last_node": "analysis_gate_node",
    }


__all__ = [
    "APPLICATION_TO_SEAL_FAMILY",
    "SEAL_PARAMETER_PROFILES",
    "preflight_use_case_node",
    "seal_family_selector_node",
    "parameter_profile_builder_node",
    "ingest_missing_user_input_node",
    "coverage_analysis_node",
    "ask_missing_node",
    "calc_node",
    "analysis_gate_node",
]
