"""
Arbiter Node for Multi-Agent Consensus.
Implements voting, LLM-based judgment, and ensemble strategies
as described in the LangGraph performance guide.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.langgraph.state import SealAIState

logger = logging.getLogger(__name__)
DEFAULT_ARBITER_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")


def _extract_agent_responses(state: SealAIState) -> List[Dict[str, str]]:
    """
    Extract responses from multiple agents for arbitration.
    
    Returns:
        List of dicts with 'agent' and 'response' keys
    """
    messages = state.get("messages", [])
    responses: List[Dict[str, str]] = []
    
    for msg in reversed(messages):
        try:
            if getattr(msg, "type", "") == "ai":
                agent_name = getattr(msg, "name", "unknown")
                content = getattr(msg, "content", "")
                
                if isinstance(content, str) and content.strip():
                    responses.append({
                        "agent": agent_name,
                        "response": content.strip()
                    })
                    
                # Collect last 3 agent responses for comparison
                if len(responses) >= 3:
                    break
                    
        except (AttributeError, TypeError) as e:
            logger.warning(f"Error extracting agent response: {e}")
            continue
    
    return list(reversed(responses))  # Return in chronological order


def arbiter_voting(responses: List[str]) -> str:
    """
    Simple majority voting arbiter.
    
    Args:
        responses: List of response strings from different agents
        
    Returns:
        Most common response
    """
    if not responses:
        return ""
    
    # Normalize responses for comparison
    normalized = [r.strip().lower() for r in responses]
    
    # Count occurrences
    counter = Counter(normalized)
    most_common = counter.most_common(1)[0][0]
    
    # Return original (non-normalized) version
    for orig, norm in zip(responses, normalized):
        if norm == most_common:
            return orig
    
    return responses[0]  # Fallback


def arbiter_llm_judge(
    user_query: str,
    responses: List[Dict[str, str]],
    *,
    model: str = DEFAULT_ARBITER_MODEL,
) -> Dict[str, Any]:
    """
    LLM-based arbiter that judges which response is best.
    
    Args:
        user_query: Original user question
        responses: List of agent responses with agent names
        model: LLM model to use for judgment
        
    Returns:
        Dict with 'best_response', 'reasoning', and 'confidence'
    """
    if not responses:
        return {
            "best_response": "",
            "reasoning": "No responses to judge",
            "confidence": 0.0
        }
    
    if len(responses) == 1:
        return {
            "best_response": responses[0]["response"],
            "reasoning": "Only one response available",
            "confidence": 1.0
        }
    
    try:
        judge = ChatOpenAI(model=model, temperature=0)
        
        responses_text = "\n\n".join([
            f"**Agent {i+1} ({r['agent']}):**\n{r['response']}"
            for i, r in enumerate(responses)
        ])
        
        prompt = f"""Du bist ein neutraler Schiedsrichter. Bewerte die folgenden Antworten und wähle die beste aus.

**Ursprüngliche Frage:**
{user_query}

**Antworten zur Bewertung:**
{responses_text}

**Aufgabe:**
1. Bewerte jede Antwort nach Korrektheit, Vollständigkeit und Klarheit
2. Wähle die beste Antwort aus
3. Begründe deine Entscheidung kurz

**Format (JSON):**
```json
{{
  "best_agent_number": 1,
  "reasoning": "Kurze Begründung",
  "confidence": 0.9
}}
```"""
        
        response = judge.invoke(prompt)
        content = response.content
        
        # Parse JSON response
        try:
            # Extract JSON from markdown if present
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                data = json.loads(content)
            
            best_idx = int(data.get("best_agent_number", 1)) - 1
            if 0 <= best_idx < len(responses):
                return {
                    "best_response": responses[best_idx]["response"],
                    "reasoning": data.get("reasoning", ""),
                    "confidence": float(data.get("confidence", 0.8))
                }
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse judge response: {e}")
        
        # Fallback: return first response
        return {
            "best_response": responses[0]["response"],
            "reasoning": "Judge parsing failed, using first response",
            "confidence": 0.5
        }
        
    except Exception as e:
        logger.error(f"Error in LLM judge: {e}", exc_info=True)
        return {
            "best_response": responses[0]["response"] if responses else "",
            "reasoning": f"Judge error: {type(e).__name__}",
            "confidence": 0.3
        }


def arbiter_confidence_weighted(responses: List[Dict[str, Any]]) -> str:
    """
    Choose response with highest confidence score.
    
    Args:
        responses: List of dicts with 'response' and 'confidence' keys
        
    Returns:
        Response with highest confidence
    """
    if not responses:
        return ""
    
    # Find response with max confidence
    best = max(responses, key=lambda r: float(r.get("confidence", 0.0)))
    return best.get("response", "")


def arbiter_node(
    state: SealAIState,
    *,
    strategy: Literal["voting", "llm_judge", "confidence"] = "llm_judge"
) -> Dict[str, Any]:
    """
    Arbiter Node - Resolves conflicts between multiple agent responses.
    
    Implements three strategies:
    - voting: Simple majority vote
    - llm_judge: LLM-based judgment of best response
    - confidence: Choose response with highest confidence score
    
    Args:
        state: Current state
        strategy: Arbitration strategy to use
        
    Returns:
        State updates with arbitrated response
    """
    agent_responses = _extract_agent_responses(state)
    
    if len(agent_responses) < 2:
        logger.info("Arbiter: Less than 2 responses, no arbitration needed")
        return {}
    
    logger.info(f"Arbiter: Resolving {len(agent_responses)} responses using {strategy} strategy")
    
    slots = dict(state.get("slots") or {})
    user_query = slots.get("user_query", "")
    
    try:
        if strategy == "voting":
            best_response = arbiter_voting([r["response"] for r in agent_responses])
            reasoning = "Majority vote"
            confidence = 0.7
            
        elif strategy == "llm_judge":
            result = arbiter_llm_judge(user_query, agent_responses)
            best_response = result["best_response"]
            reasoning = result["reasoning"]
            confidence = result["confidence"]
            
        elif strategy == "confidence":
            # Need confidence scores in responses
            best_response = arbiter_confidence_weighted(agent_responses)
            reasoning = "Highest confidence score"
            confidence = 0.8
            
        else:
            logger.warning(f"Unknown arbiter strategy: {strategy}, using first response")
            best_response = agent_responses[0]["response"]
            reasoning = "Fallback to first response"
            confidence = 0.5
        
        # Update slots with arbitrated result
        slots["candidate_answer"] = best_response
        slots["arbiter_result"] = {
            "strategy": strategy,
            "reasoning": reasoning,
            "confidence": confidence,
            "num_responses": len(agent_responses),
        }
        
        logger.info(f"Arbiter selected response with confidence {confidence:.2f}")
        
        return {"slots": slots}
        
    except Exception as e:
        logger.error(f"Error in arbiter node: {e}", exc_info=True)
        # Fallback: use first response
        if agent_responses:
            slots["candidate_answer"] = agent_responses[0]["response"]
        return {"slots": slots}


__all__ = [
    "arbiter_node",
    "arbiter_voting",
    "arbiter_llm_judge",
    "arbiter_confidence_weighted",
]
