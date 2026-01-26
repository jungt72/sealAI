"""Preflight nodes for LangGraph v2."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from langchain_core.messages import BaseMessage

from app.langgraph_v2.io import AskMissingRequest, CoverageAnalysis, ParameterProfile
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import AskMissingScope, CalcResults, SealAIState, TechnicalParameters, WorkingMemory
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance
import structlog

logger = structlog.get_logger("langgraph_v2.nodes_preflight")

# Mapping von (motion_type, application_category) zu möglichen Dichtungsfamilien.
APPLICATION_TO_SEAL_FAMILY: Dict[Tuple[str, str], List[str]] = {
    ("rotary", "getriebe"): ["radialwellendichtring"],
    ("rotary", "pumpe"): ["radialwellendichtring"],
    ("linear", "hydraulikzylinder"): ["kolbendichtring", "abstreifer"],
    ("linear", "presse"): ["kolbendichtring"],
    ("static", "allgemein"): ["statisch"],
}

# Parameterprofile je (motion_type, application_category, seal_family).
SEAL_PARAMETER_PROFILES: Dict[Tuple[str, str, str], Dict[str, List[str]]] = {
    (
        "rotary",
        "getriebe",
        "radialwellendichtring",
    ): {
        "required": ["shaft_diameter", "housing_diameter", "speed_rpm", "medium", "temperature_max", "pressure_bar"],
        "optional": ["temperature_min", "housing_surface_roughness", "shaft_material", "housing_material"],
    },
    (
        "linear",
        "hydraulikzylinder",
        "kolbendichtring",
    ): {
        "required": ["piston_diameter", "bore_diameter", "pressure_bar", "temperature_max", "medium"],
        "optional": ["stroke_length", "speed_linear", "temperature_min"],
    },
    (
        "linear",
        "hydraulikzylinder",
        "abstreifer",
    ): {
        "required": ["rod_diameter", "bore_diameter", "pressure_bar", "temperature_max", "medium"],
        "optional": ["stroke_length", "speed_linear", "temperature_min"],
    },
    (
        "static",
        "allgemein",
        "statisch",
    ): {
        "required": ["diameter", "pressure_bar", "temperature_max", "medium"],
        "optional": ["temperature_min"],
    },
}


def _coerce_number(value: str) -> Any:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except Exception:
        return value


def _parse_user_params(text: str, expected_keys: List[str]) -> Dict[str, Any]:
    """
    Parse user-provided parameter input.

    Accepts JSON objects or simple "key=value" / "key: value" pairs separated by
    commas/newlines/semicolons.
    """
    parsed: Dict[str, Any] = {}
    if not text:
        return parsed

    # 1) Try JSON object
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            for key, value in data.items():
                key_str = str(key).strip()
                if expected_keys and key_str not in expected_keys:
                    continue
                parsed[key_str] = value
            if parsed:
                return parsed
    except Exception:
        pass

    # 2) Parse simple key/value pairs
    separators = [",", ";", "\n"]
    for sep in separators:
        text = text.replace(sep, "\n")
    for line in text.split("\n"):
        if not line.strip():
            continue
        token = line.strip()
        if "=" in token:
            key, value = token.split("=", 1)
        elif ":" in token:
            key, value = token.split(":", 1)
        else:
            continue
        key = key.strip()
        if expected_keys and key not in expected_keys:
            continue
        parsed[key] = _coerce_number(value.strip())
    return parsed


def preflight_use_case_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Heuristische Vorbelegung von use_case_raw, application_category und motion_type.
    Modeltier: gpt-5-mini (Stub-Logic).
    """
    user_text = latest_user_text(state.get("messages")).lower()
    use_case_raw = user_text or state.get("use_case_raw") or "allgemein"

    application_category = "allgemein"
    motion_type = "static"

    if "getriebe" in user_text:
        application_category = "getriebe"
        motion_type = "rotary"
    elif "zylinder" in user_text:
        application_category = "hydraulikzylinder"
        motion_type = "linear"
    elif "pumpe" in user_text:
        application_category = "pumpe"
        motion_type = "rotary"

    return {
        "use_case_raw": use_case_raw,
        "application_category": application_category,
        "motion_type": motion_type,
        "phase": PHASE.PREFLIGHT_USE_CASE,
        "last_node": "preflight_use_case_node",
    }


def seal_family_selector_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    motion_type = (state.get("motion_type") or "static").strip().lower()
    application_category = (state.get("application_category") or "allgemein").strip().lower()
    options = APPLICATION_TO_SEAL_FAMILY.get((motion_type, application_category), [])

    seal_family = None
    if options:
        seal_family = options[0] if len(options) == 1 else options[0]
    else:
        seal_family = "statisch"

    return {
        "seal_family": seal_family,
        "phase": PHASE.PREFLIGHT_PARAMETERS,
        "last_node": "seal_family_selector_node",
    }


def parameter_profile_builder_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    motion_type = (state.get("motion_type") or "").strip().lower()
    application_category = (state.get("application_category") or "").strip().lower()
    seal_family = (state.get("seal_family") or "").strip().lower()
    params_obj = state.parameters or TechnicalParameters()
    parameters = params_obj.as_dict()

    key = (motion_type, application_category, seal_family)
    profile = SEAL_PARAMETER_PROFILES.get(key, {"required": [], "optional": []})
    parameter_profile = ParameterProfile(
        required=profile.get("required", []),
        optional=profile.get("optional", []),
    )

    missing = [param for param in parameter_profile.required if param not in parameters]

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
    merged_params, merged_provenance = apply_parameter_patch_with_provenance(
        parameters,
        parsed,
        state.parameter_provenance,
        source="user",
    )
    for key in parsed:
        if key in missing:
            missing.remove(key)

    return {
        "parameters": TechnicalParameters.model_validate(merged_params),
        "parameter_provenance": merged_provenance,
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
