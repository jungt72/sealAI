"""Frontdoor node: intent discovery and parameter extraction."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import (
    Intent,
    IntentGoal,
    SealAIState,
    TechnicalParameters,
    WorkingMemory,
)
from app.langgraph_v2.utils.jinja_renderer import render_template
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance
from app.langgraph_v2.utils.state_debug import log_state_debug

logger = structlog.get_logger("langgraph_v2.nodes_frontdoor")

SMALLTALK_PATTERNS = [
    r"^(hallo|hi|hey)$",
    r"^(servus|moin)$",
    r"^(gruss dich|grues dich|gruezi|gruss gott|grussgott)$",
    r"^(guten (morgen|tag|abend))$",
    r"^(danke|dankeschoen|danke dir|thx)$",
]

# Internal note for the downstream final-answer templates (should not be a user-facing greeting).
FRIENDLY_SMALLTALK_REPLY = (
    "Smalltalk/Begrüßung erkannt. Bitte direkt nach Kontext fragen (Medium, Temperatur, Druck, Bewegung, Geometrie)."
)

FRONTDOOR_PROMPT_TEMPLATE = "frontdoor_discovery_prompt.jinja2"

GOAL_DESCRIPTIONS = {
    "smalltalk": "Grüße, Off-Topic oder Unsicherheiten (Fallback: Immer wählen, wenn Zweifel bestehen).",
    "design_recommendation": "Material-/Produktauswahl oder Design-Optimierung für spezifische Bedingungen.",
    "explanation_or_comparison": "Erklärungen, Vergleiche oder Normen-Checks (z. B. FDA-Konformität).",
    "troubleshooting_leakage": "Fehlerdiagnosen und Optimierungen bei Leckagen in Pumpen oder Systemen.",
    "out_of_scope": "Alles außerhalb der Dichtungstechnik – leite sanft zurück.",
}

PARAMETER_LABELS: Dict[str, str] = {
    "pressure_bar": "Druck (bar)",
    "temperature_C": "Temperatur (°C)",
    "temperature_max": "Max Temperatur (°C)",
    "temperature_min": "Min Temperatur (°C)",
    "shaft_diameter": "Welle Ø (mm)",
    "housing_diameter": "Gehäuse Ø (mm)",
    "speed_rpm": "Drehzahl (RPM)",
    "medium": "Medium",
}

# ---------------------------------------------------------------------------
# Guardrails: prevent DIN/ISO numbers being misinterpreted as speed_rpm
# ---------------------------------------------------------------------------

_NORM_RE = re.compile(r"\b(?:din|iso|en|vdi|astm|sae)\s*[-:]?\s*(\d{2,6})\b", re.IGNORECASE)
_RPM_MARKER_RE = re.compile(
    r"\b(?:rpm|u\s*/\s*min|u/min|1\s*/\s*min|1/min|umdrehungen|u\.?\s*\/\s*min)\b",
    re.IGNORECASE,
)


def _infer_norm_number(text: str) -> Optional[int]:
    if not text:
        return None
    m = _NORM_RE.search(text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def _has_rpm_marker(text: str) -> bool:
    if not text:
        return False
    return bool(_RPM_MARKER_RE.search(text))


def _strip_false_speed_rpm_from_norm_query(user_text: str, extracted_params: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Guardrail: avoid mapping norm numbers (e.g., 'DIN 3761') to speed_rpm.

    If a norm is mentioned and there are NO rpm markers in user text, then remove speed_rpm
    when it equals the norm number (high precision heuristic).
    """
    if not extracted_params:
        return extracted_params, False

    norm_no = _infer_norm_number(user_text or "")
    if norm_no is None:
        return extracted_params, False

    # User explicitly talks about rpm -> keep speed_rpm.
    if _has_rpm_marker(user_text or ""):
        return extracted_params, False

    raw = extracted_params.get("speed_rpm")
    try:
        speed_val = int(float(raw)) if raw is not None else None
    except (TypeError, ValueError):
        speed_val = None

    if speed_val is not None and speed_val == norm_no:
        cleaned = dict(extracted_params)
        cleaned.pop("speed_rpm", None)
        return cleaned, True

    return extracted_params, False


def _looks_like_norm_query(text: Optional[str]) -> bool:
    """
    True if the user text likely references a standard/norm (DIN/ISO/EN/VDI/ASTM etc.)
    """
    if not text:
        return False
    return bool(_NORM_RE.search(text))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _requests_parameter_summary(text: Optional[str]) -> bool:
    if not text:
        return False

    cleaned = re.sub(r"[^\wäöüÄÖÜß\s]", " ", text).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return "parameter" in cleaned and any(
        marker in cleaned for marker in ("welche", "kennst", "hast du", "was weißt", "erinnerst")
    )


def _format_parameter_summary(parameters: TechnicalParameters) -> str:
    params_dict = parameters.as_dict()
    if not params_dict:
        return (
            "Ich habe aktuell noch keine technischen Parameter gespeichert. "
            "Teile mir bitte Druck, Temperatur oder andere Bedingungen mit."
        )

    parts: List[str] = []
    for key, value in sorted(params_dict.items()):
        label = PARAMETER_LABELS.get(key, key.replace("_", " ").capitalize())
        parts.append(f"{label}: {value}")

    joined = ", ".join(parts)
    return f"Ich habe bisher folgende Parameter von dir: {joined}. Sag Bescheid, wenn du etwas anpassen möchtest."


def _build_frontdoor_system_prompt() -> str:
    goal_list = getattr(IntentGoal, "__args__", ())
    goal_descriptions = {
        goal: GOAL_DESCRIPTIONS.get(goal, "")
        for goal in goal_list
        if goal in GOAL_DESCRIPTIONS
    }
    return render_template(
        FRONTDOOR_PROMPT_TEMPLATE,
        goal_descriptions=goal_descriptions,
    )


def _looks_like_smalltalk(text: Optional[str]) -> bool:
    if not text:
        return False

    normalized = re.sub(r"[!?.]+$", "", text).strip().lower()
    normalized = normalized.translate(str.maketrans({"ß": "ss", "ü": "u", "ä": "a", "ö": "o"}))
    normalized = re.sub(r"\s+", " ", normalized)
    if "wissensdatenbank" in normalized or "rag" in normalized:
        return False
    if ("quelle" in normalized or "quellen" in normalized) and ("auszug" in normalized or "auszuge" in normalized):
        return False
    return any(re.match(pat, normalized) for pat in SMALLTALK_PATTERNS)


def _get_working_memory(state: SealAIState, updates: Dict[str, Any]) -> WorkingMemory:
    wm = state.working_memory or WorkingMemory()
    return wm.model_copy(update=updates)


def detect_sources_request(text: Optional[str]) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"[^\wäöüÄÖÜß\s]", " ", text).lower()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return False

    # Handle explicit opt-outs like "ohne Quellen" / "keine Quellen".
    # Negation wins over any positive keyword match.
    negation_patterns = [
        r"\bohne\s+(?:irgend\w+\s+)?(?:quellen?|quelle|wissensdatenbank|datenbank|normen?)\b",
        r"\bkeine\s+(?:quellen?|quelle|wissensdatenbank|datenbank|normen?)\b",
        r"\bnicht\s+(?:mit|unter)\s+(?:quellen?|quelle|wissensdatenbank|datenbank|normen?)\b",
        r"\bohne\s+(?:din|en|iso|astm|vdi)\b",
        r"\bkeine\s+(?:din|en|iso|astm|vdi)\b",
    ]
    if any(re.search(pat, cleaned) for pat in negation_patterns):
        return False

    patterns = [
        r"\bmit quellen\b",
        r"\bquelle\b",
        r"\bquellen\b",
        r"\bbeleg\b",
        r"\bbelege\b",
        r"\bwissensdatenbank\b",
        r"\bwissens database\b",
        r"\bnorm\b",
        r"\bnormen\b",
        r"\brichtlinie\b",
        r"\bstandard\b",
        r"\bstandards\b",
        r"\bsource\b",
        r"\bsources\b",
        r"\b(din|iso|astm|vdi)\b",
        r"\b(?:din|iso|en|vdi)\s?\d{2,}\b",
    ]
    return any(re.search(pat, cleaned) for pat in patterns)


def _derive_knowledge_type_from_intent(raw_intent: Dict[str, Any]) -> Optional[str]:
    if raw_intent.get("knowledge_type") is not None:
        return raw_intent.get("knowledge_type")
    key = str(raw_intent.get("key") or "")
    mapping = {
        "knowledge_material": "material",
        "knowledge_lifetime": "lifetime",
        "knowledge_norms": "norms",
        "generic_sealing_qa": None,
    }
    return mapping.get(key)


def _compute_requires_rag(goal: str, wants_sources: bool) -> bool:
    return bool(wants_sources and goal not in ("smalltalk", "out_of_scope"))


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


def frontdoor_discovery_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """
    Frontdoor-Node: erkennt Smalltalk, ruft ansonsten ein Nano-LLM auf,
    das eine strukturierte Intent-Payload + Frontdoor-Reply liefert.

    Wichtige Eigenschaften:
    - Smalltalk-Heuristik ohne LLM-Call (fast path)
    - Robuste JSON-Parsing-Logik (intent kann String oder Dict sein)
    """
    log_state_debug("frontdoor_discovery_node", state)
    messages = list(getattr(state, "messages", None) or [])
    user_text = latest_user_text(messages) or ""
    wm_updates: Dict[str, Any] = {}
    parameters = state.parameters or TechnicalParameters()

    if _requests_parameter_summary(user_text):
        reply = _format_parameter_summary(parameters)
        intent = Intent(goal="design_recommendation", confidence=0.65, high_impact_gaps=[])
        wm_updates["frontdoor_reply"] = reply
        wm = _get_working_memory(state, wm_updates)
        logger.info(
            "frontdoor_parameter_summary",
            user_text=user_text,
            run_id=state.run_id,
            thread_id=state.thread_id,
        )
        return {
            "intent": intent,
            "working_memory": wm,
            "phase": PHASE.FRONTDOOR,
            "last_node": "frontdoor_discovery_node",
            "parameters": parameters,
        }

    # 1) Hard-fast-path für sehr klaren Smalltalk (ohne LLM)
    if _looks_like_smalltalk(user_text):
        intent = Intent(goal="smalltalk", confidence=1.0, high_impact_gaps=[])
        wm_updates["frontdoor_reply"] = FRIENDLY_SMALLTALK_REPLY
        wm = _get_working_memory(state, wm_updates)
        return {
            "intent": intent,
            "working_memory": wm,
            "phase": PHASE.FRONTDOOR,
            "last_node": "frontdoor_discovery_node",
            "parameters": parameters,
        }

    # Early routing hint: Norm query + sources request => Knowledge Norms
    wants_sources_early = detect_sources_request(user_text)
    looks_like_norms = _looks_like_norm_query(user_text)

    # 2) Parameter extraction (regex-based)
    extracted_params = extract_parameters_from_text(user_text)

    # Guardrail: avoid mapping norm numbers (e.g. DIN 3761) to speed_rpm when no rpm markers are present.
    extracted_params, stripped = _strip_false_speed_rpm_from_norm_query(user_text, extracted_params)
    if stripped:
        logger.info(
            "frontdoor_strip_false_speed_rpm",
            user_text=(user_text or "")[:160],
            run_id=state.run_id,
            thread_id=state.thread_id,
            reason="norm_number_mapped_to_speed_rpm",
        )

    system = _build_frontdoor_system_prompt()
    prompt = user_text.strip() or ""

    try:
        response_text = run_llm(
            model=get_model_tier("nano"),
            prompt=prompt,
            system=system,
            temperature=0.2,
            max_tokens=360,
            metadata={
                "node": "frontdoor_discovery_node",
                "run_id": state.run_id,
                "thread_id": state.thread_id,
                "user_id": state.user_id,
            },
        )
    except Exception as exc:
        # Fallback: defensiver Default-Intent
        logger.warning("frontdoor_llm_failed", error=str(exc), user_text=user_text)
        intent = Intent(goal="design_recommendation", confidence=0.6, high_impact_gaps=[])
        parameter_provenance = state.parameter_provenance
        if extracted_params:
            merged_params, parameter_provenance = apply_parameter_patch_with_provenance(
                parameters.as_dict(),
                extracted_params,
                state.parameter_provenance,
                source="user",
            )
            parameters = TechnicalParameters.model_validate(merged_params)

        # Normen + Quellen: auch im Fallback sauber routen.
        if wants_sources_early and looks_like_norms:
            intent = Intent(
                goal="explanation_or_comparison",
                confidence=0.7,
                high_impact_gaps=[],
                key="knowledge_norms",
                knowledge_type="norms",
                domain="sealing_technology",
            )

        if wants_sources_early and getattr(intent, "goal", None) not in ("smalltalk", "out_of_scope"):
            if getattr(intent, "goal", None) != "explanation_or_comparison":
                intent = intent.model_copy(update={"goal": "explanation_or_comparison"})

        wm_updates["frontdoor_reply"] = (
            "Danke für deine Nachricht. Ich sammle gleich mehr Kontext und melde mich mit einem technischen Vorschlag."
        )
        wm = _get_working_memory(state, wm_updates)
        return {
            "intent": intent,
            "working_memory": wm,
            "phase": PHASE.FRONTDOOR,
            "last_node": "frontdoor_discovery_node",
            "parameters": parameters,
            "parameter_provenance": parameter_provenance,
            "requires_rag": True if (wants_sources_early and getattr(intent, "goal", None) not in ("smalltalk", "out_of_scope")) else False,
            "needs_sources": True if (wants_sources_early and getattr(intent, "goal", None) not in ("smalltalk", "out_of_scope")) else False,
            "knowledge_type": "norms" if (wants_sources_early and looks_like_norms) else None,
        }

    # 3) Robust JSON-Parsing
    data, _ = extract_json_obj(response_text, default={})
    if not isinstance(data, dict):
        logger.warning(
            "frontdoor_json_not_dict",
            raw=response_text,
            parsed_type=type(data).__name__,
            user_text=user_text,
        )
        data = {}

    frontdoor_reply = data.get("frontdoor_reply") or (
        "Ich habe deine Anfrage aufgenommen und schaue nach den passenden Informationen."
    )

    raw_intent = data.get("intent") or {}

    # Intent kann String oder Dict sein → normalisieren
    if isinstance(raw_intent, str):
        raw_intent = {"goal": raw_intent}
    elif not isinstance(raw_intent, dict):
        logger.warning(
            "frontdoor_intent_not_dict",
            intent_type=type(raw_intent).__name__,
            raw_intent=raw_intent,
            user_text=user_text,
        )
        raw_intent = {}

    # Goal robust auslesen + auf erlaubte Werte clampen
    goal = str(raw_intent.get("goal") or "design_recommendation")
    if goal not in getattr(IntentGoal, "__args__", ()):
        logger.warning(
            "frontdoor_unknown_goal",
            goal=goal,
            raw_intent=raw_intent,
            user_text=user_text,
        )
        goal = "design_recommendation"

    # Confidence robust normalisieren
    try:
        confidence = float(raw_intent.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # high_impact_gaps kann Liste, String oder etwas anderes sein
    raw_gaps = raw_intent.get("high_impact_gaps") or []
    if isinstance(raw_gaps, str):
        high_impact_gaps: List[str] = [raw_gaps]
    elif isinstance(raw_gaps, list):
        high_impact_gaps = [str(item) for item in raw_gaps]
    else:
        high_impact_gaps = [str(raw_gaps)]
    high_impact_gaps = [item.strip() for item in high_impact_gaps if item and str(item).strip()]

    derived_knowledge_type = _derive_knowledge_type_from_intent(raw_intent)
    intent_payload: Dict[str, Any] = {
        "goal": goal,
        "confidence": confidence,
        "high_impact_gaps": high_impact_gaps,
        "domain": raw_intent.get("domain") or "sealing_technology",
    }
    if derived_knowledge_type is not None:
        intent_payload["knowledge_type"] = derived_knowledge_type

    # optionale Felder durchreichen, falls vorhanden
    for key in ("key", "knowledge_type", "routing_hint", "complexity", "needs_sources", "need_sources"):
        if raw_intent.get(key) is not None:
            intent_payload[key] = raw_intent.get(key)

    intent_payload["seeded_parameters"] = raw_intent.get("seeded_parameters") or {}
    intent = Intent(**intent_payload)

    wm_updates["frontdoor_reply"] = frontdoor_reply
    wm = _get_working_memory(state, wm_updates)

    # Apply extracted parameters
    parameter_provenance = state.parameter_provenance
    if extracted_params:
        merged_params, parameter_provenance = apply_parameter_patch_with_provenance(
            parameters.as_dict(),
            extracted_params,
            state.parameter_provenance,
            source="user",
        )
        parameters = TechnicalParameters.model_validate(merged_params)

    logger.info(
        "frontdoor_intent",
        goal=goal,
        confidence=confidence,
        gaps=high_impact_gaps,
        user_text=user_text,
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    wants_sources = wants_sources_early or bool(raw_intent.get("needs_sources") or raw_intent.get("need_sources"))
    requires_rag = _compute_requires_rag(goal, wants_sources)

    if wants_sources and goal not in ("smalltalk", "out_of_scope"):
        if goal != "explanation_or_comparison":
            intent = intent.model_copy(update={"goal": "explanation_or_comparison"})
            goal = "explanation_or_comparison"
        requires_rag = True

    # HARD OVERRIDE (minimal, deterministic):
    # Norm query + sources => Knowledge Norms (prevents design gating)
    if wants_sources and looks_like_norms:
        intent = intent.model_copy(
            update={
                "goal": "explanation_or_comparison",
                "key": "knowledge_norms",
                "knowledge_type": "norms",
                "confidence": max(float(getattr(intent, "confidence", 0.0) or 0.0), 0.7),
            }
        )
        derived_knowledge_type = "norms"
        requires_rag = True
        wants_sources = True

    # Knowledge intents: allow RAG pathing (supervisor decides when/how).
    if (
        str(intent.key or "").startswith("knowledge_")
        or intent.knowledge_type in ("material", "lifetime", "norms")
        or intent.key == "generic_sealing_qa"
    ):
        requires_rag = True

    # Never enable optional RAG for smalltalk/out_of_scope.
    if str(getattr(intent, "goal", "") or "") in ("smalltalk", "out_of_scope"):
        requires_rag = False
        wants_sources = False

    return {
        "intent": intent,
        "working_memory": wm,
        "phase": PHASE.FRONTDOOR,
        "last_node": "frontdoor_discovery_node",
        "parameters": parameters,
        "parameter_provenance": parameter_provenance,
        "requires_rag": requires_rag,
        "needs_sources": wants_sources,
        "knowledge_type": derived_knowledge_type if derived_knowledge_type is not None else getattr(intent, "knowledge_type", None),
    }


__all__ = [
    "frontdoor_discovery_node",
    "detect_sources_request",
    "_compute_requires_rag",
    "_derive_knowledge_type_from_intent",
]
