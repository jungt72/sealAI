from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage

from app.langgraph.nodes.members import create_domain_agent
from app.langgraph.prompts.prompt_loader import load_jinja_chat_prompt
from app.langgraph.state import Routing, SealAIState

MIN_CONFIDENCE = float(os.getenv("QUALITY_GATE_MIN_CONFIDENCE", "0.78"))


@dataclass
class _ReviewPayload:
    approved: bool
    confidence: float
    critique: str
    improved_answer: Optional[str]
    raw: str


@lru_cache(maxsize=1)
def _reviewer_graph():
    return create_domain_agent("reviewer")


def _extract_last_ai(messages: List[BaseMessage]) -> Optional[str]:
    for msg in reversed(messages):
        if getattr(msg, "type", "") == "ai":
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, dict) and "content" in content:
                return str(content["content"])
            return str(content)
    return None


def _invoke_reviewer(messages: List[BaseMessage]) -> str:
    result = _reviewer_graph().invoke({"messages": messages})
    response_messages: List[BaseMessage] = result.get("messages", [])  # type: ignore[index]
    return _extract_last_ai(response_messages) or ""


def _parse_payload(raw_text: str) -> _ReviewPayload:
    try:
        data = json.loads(raw_text)
    except Exception:
        match = re.search(r"confidence[:=]\s*(\d+(?:\.\d+)?)", raw_text, re.I)
        confidence = float(match.group(1)) / (100 if match and float(match.group(1)) > 1 else 1) if match else 0.5
        approved = bool(re.search(r"\bpass\b|\bapproved\b", raw_text, re.I))
        return _ReviewPayload(approved=approved, confidence=confidence, critique=raw_text.strip(), improved_answer=None, raw=raw_text)

    approved = bool(data.get("approved") or data.get("pass"))
    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)):
        confidence = float(confidence)
        if confidence > 1:
            confidence /= 100.0
    else:
        confidence = 0.0
    critique = str(data.get("critique") or data.get("notes") or "").strip()
    improved = data.get("improved_answer") or data.get("revision")
    improved_answer = str(improved).strip() if isinstance(improved, str) and str(improved).strip() else None
    return _ReviewPayload(
        approved=approved,
        confidence=float(confidence or 0.0),
        critique=critique or "Keine Anmerkungen.",
        improved_answer=improved_answer,
        raw=raw_text,
    )


def _style_hints(slots: Dict[str, Any]) -> List[str]:
    contract = slots.get("style_contract")
    if not isinstance(contract, dict) or not contract:
        return []
    clauses: List[str] = []
    if contract.get("no_intro"):
        clauses.append("Keine Einleitung erlauben.")
    if contract.get("no_outro"):
        clauses.append("Kein Nachsatz oder Fazit.")
    if contract.get("single_sentence"):
        clauses.append("Antwort muss exakt ein Satz sein.")
    if contract.get("numbers_with_commas"):
        clauses.append("Zahlenfolge mit Kommas trennen.")
    start = contract.get("literal_numbers_start")
    end = contract.get("literal_numbers_end")
    if isinstance(start, int) and isinstance(end, int):
        clauses.append(f"Zahlenbereich {start}–{end} vollständig abbilden.")
    if contract.get("enforce_plain_answer"):
        clauses.append("Keine Erklärungen oder Meta-Kommentare.")
    if contract.get("additional_notes"):
        clauses.append(str(contract.get("additional_notes")))
    return clauses


_QUALITY_GATE_PROMPT = load_jinja_chat_prompt("quality_gate.de.j2")


def run_quality_review(state: SealAIState) -> Dict[str, Any]:
    slots = dict(state.get("slots") or {})
    user_query = str(slots.get("user_query") or "").strip()
    candidate_answer = str(slots.get("candidate_answer") or "").strip()
    if not user_query or not candidate_answer:
        return {}

    style_hints = _style_hints(slots)
    prompt_messages = _QUALITY_GATE_PROMPT.format_messages(
        user_query=user_query,
        candidate_answer=candidate_answer,
        style_hints=style_hints,
    )
    raw = _invoke_reviewer(prompt_messages)
    payload = _parse_payload(raw)

    routing: Routing = dict(state.get("routing") or {})
    routing["confidence"] = payload.confidence

    slots["checklist_result"] = {
        "approved": payload.approved,
        "confidence": payload.confidence,
        "critique": payload.critique,
        "improved_answer": payload.improved_answer or "",
        "raw": payload.raw,
    }

    return {"slots": slots, "routing": routing}
