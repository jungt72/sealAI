"""
Improved Challenger Feedback Node with Revision Logic.
Critically reviews answers and provides improved versions.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage

from app.langgraph.nodes.members import create_domain_agent
from app.langgraph.state import SealAIState

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _challenger_graph():
    """Cached challenger agent graph."""
    return create_domain_agent("challenger")


def _extract_last_ai(messages: List[BaseMessage]) -> Optional[str]:
    """Extract the last AI message content from message list."""
    for msg in reversed(messages):
        try:
            if getattr(msg, "type", "") == "ai":
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    return content
                if isinstance(content, dict) and "content" in content:
                    return str(content["content"])
                return str(content) if content else None
        except AttributeError as e:
            logger.warning(f"AttributeError extracting AI message: {e}")
            continue
        except Exception as e:
            logger.error(f"Unexpected error extracting AI message: {e}", exc_info=True)
            continue
    return None


def _invoke_challenger(user_query: str, candidate_answer: str, critique_context: str = "") -> str:
    """
    Invoke the Challenger agent to critique and improve an answer.
    
    Args:
        user_query: Original user question
        candidate_answer: Current answer to be critiqued
        critique_context: Additional context from previous reviews
    
    Returns:
        Challenger's response (critique + improved answer)
    """
    prompt = f"""Prüfe die folgende Antwort kritisch und liefere eine verbesserte Version.

**Ursprüngliche Frage:**
{user_query}

**Aktuelle Antwort:**
{candidate_answer}
"""
    
    if critique_context:
        prompt += f"\n**Bisherige Kritikpunkte:**\n{critique_context}\n"
    
    prompt += """
**Deine Aufgabe:**
1. Identifiziere Schwächen, Fehler oder Bias in der Antwort
2. Liefere eine verbesserte, faktenbasierte Antwort
3. Falls die Antwort bereits gut ist, gib "OK" mit kurzer Begründung zurück

**Format (JSON bevorzugt):**
```json
{
  "status": "needs_improvement" oder "ok",
  "critique": "Detaillierte Kritikpunkte",
  "improved_answer": "Verbesserte Antwort (falls nötig)"
}
```
"""
    
    messages = [HumanMessage(content=prompt)]
    result = _challenger_graph().invoke({"messages": messages})
    response_messages: List[BaseMessage] = result.get("messages", [])
    return _extract_last_ai(response_messages) or ""


def _parse_challenger_response(raw_text: str) -> Dict[str, Any]:
    """
    Parse Challenger's response.
    Tries JSON first, falls back to text parsing.
    
    Returns:
        Dict with keys: status, critique, improved_answer
    """
    # Try JSON parsing
    try:
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(1))
        else:
            data = json.loads(raw_text)
        
        return {
            "status": str(data.get("status", "needs_improvement")).lower(),
            "critique": str(data.get("critique", "")).strip(),
            "improved_answer": str(data.get("improved_answer", "")).strip() or None,
        }
    except (json.JSONDecodeError, AttributeError):
        pass
    
    # Fallback: text parsing
    status = "ok" if re.search(r'\b(OK|APPROVED|PASS)\b', raw_text, re.I) else "needs_improvement"
    
    # Try to extract improved answer from text
    improved_match = re.search(
        r'(?:verbesserte?\s+antwort|improved\s+answer|revision)[:\s]+(.+)',
        raw_text,
        re.I | re.DOTALL
    )
    improved_answer = improved_match.group(1).strip() if improved_match else None
    
    return {
        "status": status,
        "critique": raw_text.strip(),
        "improved_answer": improved_answer,
    }


def challenger_feedback(state: SealAIState) -> Dict[str, Any]:
    """
    Challenger Feedback Node - Critiques and improves answers.
    
    Reads candidate_answer from slots, invokes Challenger agent,
    and updates the answer if an improvement is provided.
    
    Returns:
        State updates with improved answer and critique history
    """
    slots = dict(state.get("slots") or {})
    user_query = str(slots.get("user_query", "")).strip()
    candidate_answer = str(slots.get("candidate_answer", "")).strip()
    
    if not user_query or not candidate_answer:
        logger.warning("Challenger: Missing user_query or candidate_answer - skipping")
        return {}
    
    # Get previous critique context
    checklist = slots.get("checklist_result") or {}
    previous_critique = checklist.get("critique", "")
    
    logger.info("🔍 Challenger: Reviewing answer for improvements...")
    
    # Invoke Challenger
    raw_response = _invoke_challenger(user_query, candidate_answer, previous_critique)
    parsed = _parse_challenger_response(raw_response)
    
    logger.info(f"Challenger status: {parsed['status']}")
    logger.debug(f"Challenger critique: {parsed['critique'][:200]}...")
    
    # Update slots with challenger feedback
    slots["challenger_feedback"] = {
        "status": parsed["status"],
        "critique": parsed["critique"],
        "raw_response": raw_response,
    }
    
    # If improved answer provided, update candidate_answer
    if parsed["improved_answer"]:
        logger.info("✨ Challenger provided improved answer - updating candidate")
        slots["candidate_answer"] = parsed["improved_answer"]
        slots["revision_history"] = slots.get("revision_history", []) + [
            {
                "original": candidate_answer,
                "improved": parsed["improved_answer"],
                "critique": parsed["critique"],
            }
        ]
    else:
        logger.info("Challenger approved answer or no improvement provided")
    
    return {"slots": slots}


__all__ = ["challenger_feedback"]
