from __future__ import annotations
from typing import Any, Dict, List, Tuple

from app.langgraph.prompts.prompt_loader import render_prompt
from app.langgraph.state import SealAIState, new_assistant_message

REQUIRED_PARAMS: List[str] = [
    "Medium/Anwendung",
    "Temperatur/Maximaltemperatur",
    "Druck/Maximaldruck",
    "Dichtungsart/Profil",
]

def _first_answer_hint(user_query: str) -> List[str]:
    uq = user_query.lower()
    hints: List[str] = []
    if any(k in uq for k in ["heißwasser", "heisswasser", "wasserdampf", "°c", " c "]):
        hints += [
            "",
            "Erste grobe Richtung (ohne Gewähr, Parameter fehlen noch):",
            "• PTFE (gefüllt) oder EPDM sind typische Optionen für Heißwasser –",
            "  genaue Auswahl hängt von Druck, Temperaturgrenze, Medienreinheit und Profil ab.",
        ]
    return hints


def _select_candidate(slots: Dict[str, Any]) -> Tuple[str, str]:
    checklist = slots.get("checklist_result") or {}
    improved = str(checklist.get("improved_answer") or "").strip()
    if improved:
        return improved, "quality_review"
    challenger = str(slots.get("challenger_feedback") or "").strip()
    if challenger and not challenger.lower().startswith("ok"):
        return challenger, "challenger"
    specialist = str(slots.get("specialist_summary") or "").strip()
    if specialist:
        return specialist, "specialists"
    candidate = str(slots.get("candidate_answer") or "").strip()
    if candidate:
        return candidate, "direct"
    return "", ""


def resolver(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    candidate, source = _select_candidate(slots)
    confidence = float(state.get("confidence") or (state.get("routing") or {}).get("confidence") or 0.0)

    if candidate:
        slots["candidate_answer"] = candidate
        reasoning = (
            f"Quelle: {source}, Confidence {confidence:.2f}. "
            "Diese Empfehlung geht als bevorzugte Antwort in die Abschlusssynthese."
        )
        arbiter_text = (
            "🧑‍⚖️ **Arbiter-Entscheidung**\n\n"
            f"{reasoning}\n\n"
            f"{candidate}"
        )
        return {"slots": slots, "messages": [new_assistant_message(arbiter_text, msg_id="msg-arbiter")], "phase": "review"}

    # Fallback auf bisherigen Resolver-Prompt, falls keine Kandidaten vorhanden sind
    user_query = str(slots.get("user_query") or "").strip()
    text = render_prompt(
        "resolver.de.j2",
        required_params=REQUIRED_PARAMS,
        hints=_first_answer_hint(user_query),
    )
    return {"messages": [new_assistant_message(text, msg_id="msg-resolver")], "phase": "review"}
