# backend/app/langgraph/nodes/exit_response.py
from __future__ import annotations
from typing import Any, Dict
import json

from app.langgraph.prompts.prompt_loader import render_prompt
from app.langgraph.state import SealAIState, new_assistant_message

_FALLBACK = render_prompt("exit_fallback.de.j2").strip()


def _select_final_answer(slots: Dict[str, Any]) -> tuple[str, str]:
    # Check for final_answer first (set by nodes like smalltalk_agent, general_answer)
    final = str(slots.get("final_answer") or "").strip()
    if final:
        return final, "direct_final_answer"
    
    candidate = str(slots.get("candidate_answer") or "").strip()
    checklist = slots.get("checklist_result")
    if isinstance(checklist, dict):
        improved = str(checklist.get("improved_answer") or "").strip()
        approved = bool(checklist.get("approved"))
        if improved:
            return improved, "checklist_improved"
        if approved and candidate:
            return candidate, "candidate_approved"
        if not approved and candidate:
            return candidate, "candidate_needs_attention"
    if candidate:
        return candidate, "candidate_fallback"
    return _FALLBACK, "system_fallback"


def _is_sealing_domain(state: SealAIState) -> bool:
    intent = state.get("intent") if isinstance(state, dict) else None
    if not isinstance(intent, dict):
        return False
    domain = str(intent.get("domain") or "").lower()
    return "seal" in domain or "dichtung" in domain


def _structured_payload_from_state(slots: Dict[str, Any], state: SealAIState, answer_text: str) -> Dict[str, Any] | None:
    structured = slots.get("structured_answer")
    if isinstance(structured, dict) and structured.get("type") == "structured_answer":
        return structured

    if not _is_sealing_domain(state):
        return None

    confidence = state.get("confidence") if isinstance(state, dict) else None
    try:
        confidence_score = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence_score = None

    context_state = {}
    if isinstance(slots.get("context_state"), dict):
        context_state = slots["context_state"]

    return {
        "type": "structured_answer",
        "result": answer_text,
        "justification": str(slots.get("discovery_summary") or slots.get("rapport_summary") or "").strip() or None,
        "confidence_score": confidence_score,
        "sources": slots.get("sources") or [],
        "action_buttons": [
            {"label": "Nutabmessungen berechnen", "prompt": "Berechne Nutabmessungen basierend auf meinem Anwendungsfall."},
            {"label": "Materialcheck", "prompt": f"Prüfe Materialauswahl für {context_state.get('medium', 'das Medium')} bei {context_state.get('temperature', 'aktueller Temperatur')}."},
        ],
        "details_markdown": slots.get("final_answer_markdown") or slots.get("candidate_answer_markdown") or None,
    }


def exit_response(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    final_text, source = _select_final_answer(slots)
    slots["final_answer"] = final_text
    slots["final_answer_source"] = source
    structured = _structured_payload_from_state(slots, state, final_text)
    if structured:
        slots["structured_answer"] = structured
        message_text = json.dumps(structured, ensure_ascii=False)
    else:
        message_text = final_text

    message = new_assistant_message(message_text, msg_id="msg-exit-final")
    return {"slots": slots, "messages": [message]}
