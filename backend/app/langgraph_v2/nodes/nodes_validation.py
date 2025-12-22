# backend/app/langgraph_v2/nodes/nodes_validation.py
"""Validation, RAG and synthesis nodes for LangGraph v2."""

from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import HumanMessage, BaseMessage

from app.langgraph_v2.constants import MODEL_PRO
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text


def answer_synthesizer_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Bereitet den finalen Prompt vor (Template + Kontext) und markiert den Abschluss.

    Der eigentliche LLM-Aufruf erfolgt im SSE-Endpoint, damit die Token dort
    direkt gestreamt werden können.
    """
    messages = state.get("messages") or []
    user_text = latest_user_text(messages)

    application_category = state.get("application_category")
    motion_type = state.get("motion_type")
    seal_family = state.get("seal_family")
    parameters = state.get("parameters") or {}
    calc_raw = state.get("calc_results") or {}
    recommendation_raw = state.get("recommendation") or {}
    if hasattr(calc_raw, "model_dump"):
        calc_results = calc_raw.model_dump()
    else:
        calc_results = calc_raw
    if hasattr(recommendation_raw, "model_dump"):
        recommendation = recommendation_raw.model_dump()
    else:
        recommendation = recommendation_raw
    working_memory = state.get("working_memory") or {}

    knowledge_material = working_memory.get("knowledge_material")
    knowledge_lifetime = working_memory.get("knowledge_lifetime")
    knowledge_generic = working_memory.get("knowledge_generic")

    context: Dict[str, object] = {
        "user_input": user_text,
        "application_category": application_category,
        "motion_type": motion_type,
        "seal_family": seal_family,
        "parameters": parameters,
        "calc_results": calc_results,
        "recommendation": recommendation,
        "knowledge_material": knowledge_material,
        "knowledge_lifetime": knowledge_lifetime,
        "knowledge_generic": knowledge_generic,
    }

    prompt = render_template("final_answer_v2.j2", context)

    model_name = get_model_tier("pro") or MODEL_PRO

    prompt_metadata = {
        "model": model_name,
        "system": (
            "Du bist ein technischer Berater für Dichtungstechnik. "
            "Erkläre klar, strukturiert und weise darauf hin, dass dies eine initiale Empfehlung ist."
        ),
        "temperature": 0.4,
        "max_tokens": 800,
    }

    return {
        "messages": list(messages),
        "phase": PHASE.FINAL,
        "last_node": "answer_synthesizer_node",
        "final_prompt": prompt,
        "final_prompt_metadata": prompt_metadata,
    }


__all__ = ["answer_synthesizer_node"]
