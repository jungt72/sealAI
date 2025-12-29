from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import structlog

from app.langgraph_v2.state import (
    Intent,
    IntentGoal,
    SealAIState,
    TechnicalParameters,
    WorkingMemory,
)
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.sealai_graph_v2 import log_state_debug
from app.langgraph_v2.utils.json_sanitizer import extract_json_obj
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_with_provenance
from app.langgraph_v2.utils.jinja import render_template

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
    normalized = normalized.translate(
        str.maketrans({"ß": "ss", "ü": "u", "ä": "a", "ö": "o"})
    )
    normalized = re.sub(r"\s+", " ", normalized)
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
        r"\bwissensdatenbank\b",
        r"\bwissens database\b",
        r"\bnorm\b",
        r"\bnormen\b",
        r"\b(din|en|iso|astm|vdi)\b",
    ]
    return any(re.search(pat, cleaned) for pat in patterns)


def frontdoor_discovery_node(state: SealAIState, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """
    Frontdoor-Node: erkennt Smalltalk, ruft ansonsten ein Nano-LLM auf,
    das eine strukturierte Intent-Payload + Frontdoor-Reply liefert.

    Wichtige Eigenschaften:
    - Smalltalk-Heuristik ohne LLM-Call (fast path)
    - Robuste JSON-Parsing-Logik (intent kann String oder Dict sein)
    """
    log_state_debug("frontdoor_discovery_node", state)
    user_text = latest_user_text(state.get("messages")) or ""
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

    # 2) LLM-basierter Frontdoor-Intent
    extracted_params = extract_parameters_from_text(user_text)
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
        # 2b) Fallback: defensiver Default-Intent
        logger.warning("frontdoor_llm_failed", error=str(exc), user_text=user_text)
        intent = Intent(goal="design_recommendation", confidence=0.6, high_impact_gaps=[])
        if extracted_params:
            merged_params, merged_provenance = apply_parameter_patch_with_provenance(
                parameters.as_dict(),
                extracted_params,
                state.parameter_provenance,
                source="user",
            )
            parameters = TechnicalParameters.model_validate(merged_params)
        wm_updates["frontdoor_reply"] = (
            "Danke für deine Nachricht. Ich sammele gleich mehr Kontext und melde mich mit einem technischen Vorschlag."
        )
        wm = _get_working_memory(state, wm_updates)
        return {
            "intent": intent,
            "working_memory": wm,
            "phase": PHASE.FRONTDOOR,
            "last_node": "frontdoor_discovery_node",
            "parameters": parameters,
            "parameter_provenance": merged_provenance if extracted_params else state.parameter_provenance,
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
        # z. B. "design_recommendation"
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

    intent_payload: Dict[str, Any] = {
        "goal": goal,
        "confidence": confidence,
        "high_impact_gaps": high_impact_gaps,
        "domain": raw_intent.get("domain") or "sealing_technology",
    }
    # optionale Felder durchreichen, falls vorhanden
    for key in ("key", "knowledge_type", "routing_hint", "complexity", "needs_sources", "need_sources"):
        if raw_intent.get(key) is not None:
            intent_payload[key] = raw_intent.get(key)

    intent_payload["seeded_parameters"] = raw_intent.get("seeded_parameters") or {}
    intent = Intent(**intent_payload)

    wm_updates["frontdoor_reply"] = frontdoor_reply
    wm = _get_working_memory(state, wm_updates)

    # [PATCH] Extract parameters
    if extracted_params:
        merged_params, merged_provenance = apply_parameter_patch_with_provenance(
            parameters.as_dict(),
            extracted_params,
            state.parameter_provenance,
            source="user",
        )
        parameters = TechnicalParameters.model_validate(merged_params)
    # [PATCH] End

    logger.info(
        "frontdoor_intent",
        goal=goal,
        confidence=confidence,
        gaps=high_impact_gaps,
        user_text=user_text,
        run_id=state.run_id,
        thread_id=state.thread_id,
    )

    wants_sources = detect_sources_request(user_text) or bool(
        raw_intent.get("needs_sources") or raw_intent.get("need_sources")
    )
    requires_rag = bool(goal == "explanation_or_comparison" and wants_sources)
    # Never enable optional RAG for smalltalk/out_of_scope.
    if goal in ("smalltalk", "out_of_scope"):
        requires_rag = False

    return {
        "intent": intent,
        "working_memory": wm,
        "phase": PHASE.FRONTDOOR,
        "last_node": "frontdoor_discovery_node",
        "parameters": parameters,
        "parameter_provenance": merged_provenance if extracted_params else state.parameter_provenance,
        "requires_rag": requires_rag,
    }


__all__ = ["frontdoor_discovery_node", "detect_sources_request"]
