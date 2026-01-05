# backend/app/langgraph/nodes/confirm_gate.py
from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple

from app.langgraph.prompts.prompt_loader import render_prompt

LOW_THRESHOLD = 0.50
MID_THRESHOLD = 0.85

def _estimate_coverage(state: Dict[str, Any]) -> float:
    """
    Heuristische Coverage-Berechnung.
    Verwendet – in dieser Reihenfolge – vorhandene Felder:
      1) state["coverage"] falls vorhanden (float 0..1)
      2) Verhältnis known/required Parameter
      3) Fallback: grobe Heuristik über Nachrichtenlänge
    """
    cov = state.get("coverage")
    if isinstance(cov, (int, float)) and 0.0 <= float(cov) <= 1.0:
        return float(cov)

    required: Optional[List[str]] = state.get("required_parameters")
    known: Optional[Dict[str, Any]] = state.get("known_parameters")
    if isinstance(required, list) and isinstance(known, dict) and required:
        have = sum(1 for k in required if k in known and known.get(k) not in (None, ""))
        return max(0.0, min(1.0, have / len(required)))

    # Fallback über letzte User-Message-Länge
    msgs: List[Dict[str, Any]] = state.get("messages", [])
    last_user = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
    if last_user:
        length = len(str(last_user.get("content", "")))
        # 0..1 grob überlogarithmisch normalisieren
        return max(0.0, min(1.0, (min(length, 400) / 400.0)))

    return 0.0


def _missing_parameter_context(state: Dict[str, Any]) -> Tuple[List[str], bool]:
    required: Optional[List[str]] = state.get("required_parameters")
    known: Optional[Dict[str, Any]] = state.get("known_parameters")
    if isinstance(required, list) and isinstance(known, dict):
        missing = [p for p in required if not known.get(p)]
        has_more = len(missing) > 6
        labels = [p.replace("_", " ") for p in missing[:6]]
        return labels, has_more
    return [], False


def confirm_gate(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Confirm-Gate gemäß Leitfaden:
      - coverage < 0.50  → weiter fragen (fehlende Angaben)
      - 0.50..0.84       → Zusammenfassung & Bestätigung einholen
      - ≥ 0.85           → automatisch fortfahren
    Der Node appends eine Assistant-Nachricht bei den ersten beiden Fällen.
    """
    coverage = _estimate_coverage(state)
    msgs: List[Dict[str, Any]] = list(state.get("messages", []))

    if coverage < LOW_THRESHOLD:
        missing_labels, has_more = _missing_parameter_context(state)
        text = render_prompt(
            "confirm_gate.de.j2",
            mode="missing",
            missing_parameters=missing_labels,
            has_more_missing=has_more,
        )
        msgs.append({
            "role": "assistant",
            "content": text.strip()
        })
        return {**state, "messages": msgs, "next_action": "ask_more", "coverage": coverage}

    if coverage < MID_THRESHOLD:
        summary = str(state.get("summary") or "").strip()
        text = render_prompt(
            "confirm_gate.de.j2",
            mode="confirm",
            summary=summary,
            missing_parameters=[],
            has_more_missing=False,
        )
        msgs.append({
            "role": "assistant",
            "content": text.strip()
        })
        return {**state, "messages": msgs, "next_action": "confirm", "coverage": coverage}

    # Automatisch fortfahren (keine Nachricht hinzufügen)
    return {**state, "next_action": "proceed", "coverage": coverage}
