# backend/app/langgraph_v2/nodes/nodes_validation.py
"""Validation, RAG and synthesis nodes for LangGraph v2."""

from __future__ import annotations

from typing import Dict

from app.langgraph_v2.constants import MODEL_PRO
from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.llm_factory import get_model_tier
from app.langgraph_v2.utils.messages import latest_user_text
from app.langgraph_v2.nodes.nodes_flows import build_final_answer_context, render_final_answer_draft


def answer_synthesizer_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    """
    Bereitet den finalen Prompt vor (Template + Kontext) und markiert den Abschluss.

    Der eigentliche LLM-Aufruf erfolgt im SSE-Endpoint, damit die Token dort
    direkt gestreamt werden können.
    """
    messages = state.get("messages") or []
    user_text = latest_user_text(messages)

    context = build_final_answer_context(state)
    context["user_input"] = user_text
    prompt = render_final_answer_draft(context)

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
