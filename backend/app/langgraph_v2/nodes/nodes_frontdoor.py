from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, Optional, Tuple

from app.core.config import settings
from app.langgraph_v2.constants import PHASE, PhaseLiteral
from app.langgraph_v2.contracts import Intent, IntentGoal
from app.langgraph_v2.state import (
    SealAIState,
    TechnicalParameters,
    WorkingMemory,
)
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.utils.output_sanitizer import extract_json_obj
from app.langgraph_v2.utils.parameter_extraction import extract_parameters_from_text
from app.langgraph_v2.utils.parameter_patch import apply_parameter_patch_lww
from app.langgraph_v2.utils.state_debug import log_state_debug

logger = logging.getLogger(__name__)

FRIENDLY_SMALLTALK_REPLY = (
    "Hallo! Ich bin dein SealAI-Assistent. Ich helfe dir gerne bei der Auswahl der richtigen Dichtung "
    "oder beantworte deine Fragen zu unseren Produkten. Wie kann ich dir heute behilflich sein?"
)


def _get_working_memory(state: SealAIState, updates: Dict[str, Any]) -> WorkingMemory:
    wm = state.working_memory or WorkingMemory()
    return wm.model_copy(update=updates)


def _requests_parameter_summary(text: str) -> bool:
    cleaned = text.lower()
    patterns = [
        r"welche (daten|parameter|werte) (hast du|sind bekannt|liegen vor)",
        r"fass (meine|die) (daten|parameter) zusammen",
        r"was weißt du (über meine|bisher)",
        r"meine (eingaben|parameter|daten)",
    ]
    return any(re.search(pat, cleaned) for pat in patterns)


def _format_parameter_summary(params: TechnicalParameters) -> str:
    lines = ["Hier ist eine Zusammenfassung der bisher erfassten technischen Parameter:"]
    found = False
    
    # Simple mapping for better readability
    labels = {
        "pressure_bar": "Druck",
        "temperature_C": "Temperatur",
        "shaft_diameter": "Wellendurchmesser",
        "speed_rpm": "Drehzahl",
        "medium": "Medium",
    }
    
    for key, label in labels.items():
        val = getattr(params, key, None)
        if val is not None:
            unit = " bar" if "pressure" in key else " °C" if "temp" in key else " mm" if "diameter" in key else " RPM" if "speed" in key else ""
            lines.append(f"- **{label}**: {val}{unit}")
            found = True
            
    if not found:
        return "Bisher wurden noch keine spezifischen technischen Parameter erfasst. Wie kann ich dir helfen?"
        
    return "\n".join(lines)


def _looks_like_smalltalk(text: str) -> bool:
    """Heuristik für Smalltalk / Begrüßung."""
    cleaned = text.lower().strip()
    if len(cleaned) < 2:
        return True
    
    # Sehr kurze Phrasen
    if len(cleaned.split()) <= 2:
        smalltalk_words = {
            "hallo",
            "hi",
            "hey",
            "moin",
            "servus",
            "abend",
            "morgen",
            "tag",
            "ciao",
            "tschüss",
            "danke",
            "grüß dich",
            "gruess dich",
            "gruss dich",
        }
        if cleaned.rstrip("!?.") in smalltalk_words:
            return True

    # Phrasen
    phrases = [
        r"^wie geht[ s']+",
        r"^wer bist du",
        r"^was kannst du",
        r"^hallo.*wie geht",
        r"^schönen tag",
    ]
    return any(re.search(pat, cleaned) for pat in phrases)


def detect_sources_request(text: str) -> bool:
    """
    Erkennt, ob der User explizit nach Quellen, Normen oder Belegen fragt.
    """
    cleaned = text.lower()
    
    negation_patterns = [
        r"\bohne\s+(?:quellen|belege|studien|nachweise)\b",
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
    merged_provenance = state.parameter_provenance
    merged_versions = state.parameter_versions
    merged_updated_at = state.parameter_updated_at

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
        logger.warning(
            "frontdoor_llm_failed",
            extra={"error": str(exc), "user_text": user_text},
        )
        intent = Intent(goal="design_recommendation", confidence=0.6, high_impact_gaps=[])
        if extracted_params:
            (
                merged_params,
                merged_provenance,
                merged_versions,
                merged_updated_at,
                applied_fields,
                rejected_fields,
            ) = apply_parameter_patch_lww(
                parameters.as_dict(),
                extracted_params,
                state.parameter_provenance,
                source="user",
                parameter_versions=state.parameter_versions,
                parameter_updated_at=state.parameter_updated_at,
                base_versions=state.parameter_versions,
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
            "parameter_provenance": merged_provenance,
            "parameter_versions": merged_versions,
            "parameter_updated_at": merged_updated_at,
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
        (
            merged_params,
            merged_provenance,
            merged_versions,
            merged_updated_at,
            applied_fields,
            rejected_fields,
        ) = apply_parameter_patch_lww(
            parameters.as_dict(),
            extracted_params,
            state.parameter_provenance,
            source="user",
            parameter_versions=state.parameter_versions,
            parameter_updated_at=state.parameter_updated_at,
            base_versions=state.parameter_versions,
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
        "parameter_provenance": merged_provenance,
        "parameter_versions": merged_versions,
        "parameter_updated_at": merged_updated_at,
        "requires_rag": requires_rag,
    }

def _build_frontdoor_system_prompt() -> str:
    """Helper: builds system prompt for frontdoor LLM."""
    return (
        "Du bist der 'Frontdoor'-Agent für SealAI. Deine Aufgabe ist es, den Intent des Nutzers "
        "zu erfassen und eine hilfreiche erste Antwort zu geben.\n"
        "Antworte IMMER im JSON-Format:\n"
        "{\n"
        "  \"intent\": {\n"
        "    \"goal\": \"design_recommendation\" | \"explanation_or_comparison\" | \"troubleshooting\" | \"smalltalk\" | \"out_of_scope\",\n"
        "    \"confidence\": float,\n"
        "    \"high_impact_gaps\": string[]\n"
        "  },\n"
        "  \"frontdoor_reply\": \"Deine freundliche Antwort an den Nutzer\"\n"
        "}"
    )


__all__ = ["frontdoor_discovery_node", "detect_sources_request"]
