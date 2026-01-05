"""Error/special handling nodes for LangGraph v2 (smalltalk, out-of-scope)."""
from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import HumanMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.llm_factory import get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text


def smalltalk_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    user_text = latest_user_text(state.get("messages"))
    model_name = get_model_tier("nano")
    reply_text = run_llm(
        model=model_name,
        prompt=user_text or "Freundliche Begrüßung.",
        system=(
            "Du bist ein freundlicher, aber fokussierter Assistent von SealAI. "
            "SealAI ist auf Dichtungstechnik spezialisiert. "
            "Bleib kurz und locker, keine langen Monologe."
        ),
        temperature=0.5,
        max_tokens=120,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "smalltalk_node",
        },  # PATCH/FIX: Observability – LLM metadata
    )

    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": reply_text, "response_kind": "smalltalk"})

    return {
        "messages": list(state.get("messages") or []),
        "phase": PHASE.SMALLTALK,
        "last_node": "smalltalk_node",
        "working_memory": wm,
    }


def out_of_scope_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    user_text = latest_user_text(state.get("messages"))
    model_name = get_model_tier("mini")
    reply_text = run_llm(
        model=model_name,
        prompt=user_text or "Keine fachliche Frage.",
        system=(
            "Du bist SealAI, spezialisiert auf Dichtungstechnik. "
            "Wenn die Frage nicht dazu passt, erkläre höflich den Fokus "
            "und biete Unterstützung für dichtungsbezogene Themen an."
        ),
        temperature=0.3,
        max_tokens=160,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "out_of_scope_node",
        },  # PATCH/FIX: Observability – LLM metadata
    )

    wm = state.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": reply_text, "response_kind": "out_of_scope"})

    return {
        "messages": list(state.get("messages") or []),
        "phase": PHASE.ERROR,
        "last_node": "out_of_scope_node",
        "working_memory": wm,
        "error": reply_text,
    }


__all__ = ["smalltalk_node", "out_of_scope_node"]
