from __future__ import annotations

import logging
import os
import asyncio
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import RunnableConfig

from app.langgraph.state import SealAIState

logger = logging.getLogger(__name__)

NANO_MODEL = os.getenv("INTENT_CLASSIFIER_MODEL", "gpt-5-nano")

async def nano_triage_node(state: SealAIState, *, config: RunnableConfig) -> Dict[str, Any]:
    """Fast triage: detects smalltalk/simple questions in <500ms."""
    user_query = str(state.get("slots", {}).get("user_query", "")).strip()
    
    if not user_query:
        return {}
    
    # Simple pattern matching first (even faster)
    simple_greetings = ["hallo", "hi", "guten tag", "guten morgen", "hey", "servus"]
    if any(greeting in user_query.lower() for greeting in simple_greetings) and len(user_query) < 20:
        return {"routing": {"nano_classification": "smalltalk"}}
    
    # Nano LLM for slightly more complex cases
    try:
        llm = ChatOpenAI(model=NANO_MODEL, temperature=0.0, max_tokens=10)
        prompt = [
            SystemMessage(content="Answer only YES or NO."),
            HumanMessage(content=f"Is this a simple greeting or smalltalk? '{user_query}'")
        ]
        ainvoke = getattr(llm, "ainvoke", None)
        if callable(ainvoke):
            response = await ainvoke(prompt, config=config)
        else:
            response = await asyncio.to_thread(llm.invoke, prompt)
        is_smalltalk = "yes" in str(response.content).lower()
        
        return {"routing": {"nano_classification": "smalltalk" if is_smalltalk else "needs_llm"}}
    except Exception:
        logger.exception("nano_triage failed, falling back to LLM triage")
        return {"routing": {"nano_classification": "needs_llm"}}


__all__ = ["nano_triage_node"]
