"""Error/special handling nodes for LangGraph v2 (smalltalk, out-of-scope)."""
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.langgraph_v2.phase import PHASE
from app.langgraph_v2.state import SealAIState, WorkingMemory
from app.langgraph_v2.utils.jinja import render_template
from app.langgraph_v2.utils.llm_factory import LazyChatOpenAI, get_model_tier, run_llm
from app.langgraph_v2.utils.messages import latest_user_text


_SMALLTALK_LLM: Any | None = None


def _extract_langgraph_config(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Any | None:
    config = kwargs.get("config")
    if config is not None:
        return config
    if args:
        candidate = args[0]
        if isinstance(candidate, dict):
            return candidate
    return None


def _chunk_to_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
                if text is not None:
                    parts.append(str(text))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content or "")


def _get_smalltalk_llm(model_name: str) -> Any:
    global _SMALLTALK_LLM
    if _SMALLTALK_LLM is None:
        _SMALLTALK_LLM = LazyChatOpenAI(
            model=model_name,
            temperature=0,
            cache=False,
            max_tokens=160,
            streaming=True,
        )
    return _SMALLTALK_LLM


async def smalltalk_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    user_text = latest_user_text(state.conversation.messages)
    model_name = get_model_tier("nano")
    llm = _get_smalltalk_llm(model_name)
    config = _extract_langgraph_config(_args, _kwargs)
    messages = [
        SystemMessage(content=render_template("smalltalk_system.j2")),
        HumanMessage(content=user_text or "Freundliche kurze Begrüßung oder Rückfrage."),
    ]
    chunks: List[str] = []
    async for chunk in llm.astream(messages, config=config):
        text = _chunk_to_text(chunk)
        if text:
            chunks.append(text)
    reply_text = "".join(chunks).strip() or "Hallo! Wie kann ich dir bei Dichtungstechnik helfen?"

    wm = state.reasoning.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": reply_text, "response_kind": "smalltalk"})
    updated_messages = list(state.conversation.messages or [])
    updated_messages.append(AIMessage(content=[{"type": "text", "text": reply_text}]))

    return {
               "conversation": {
                   "messages": updated_messages,
               },
               "reasoning": {
                   "phase": PHASE.SMALLTALK,
                   "last_node": "smalltalk_node",
                   "working_memory": wm,
               },
               "system": {
                   "final_text": reply_text,
                   "final_answer": reply_text,
               },
           }


def out_of_scope_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    user_text = latest_user_text(state.conversation.messages)
    model_name = get_model_tier("mini")
    reply_text = run_llm(
        model=model_name,
        prompt=user_text or "Keine fachliche Frage.",
        system=render_template("out_of_scope_system.j2"),
        temperature=0,
        max_tokens=160,
        metadata={
            "run_id": state.system.run_id,
            "thread_id": state.conversation.thread_id,
            "user_id": state.conversation.user_id,
            "node": "out_of_scope_node",
        },  # PATCH/FIX: Observability – LLM metadata
    )

    wm = state.reasoning.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": reply_text, "response_kind": "out_of_scope"})

    return {
               "conversation": {
                   "messages": list(state.conversation.messages or []),
               },
               "reasoning": {
                   "phase": PHASE.ERROR,
                   "last_node": "out_of_scope_node",
                   "working_memory": wm,
               },
               "system": {
                   "error": reply_text,
               },
           }


_CRITICAL_FIELDS = ["medium", "pressure_bar", "temperature_c", "dynamic_type"]


def _missing_critical(state: SealAIState) -> list[str]:
    return [f for f in _CRITICAL_FIELDS if not getattr(state.working_profile, f, None)]


def turn_limit_node(state: SealAIState, *_args, **_kwargs) -> Dict[str, object]:
    missing = _missing_critical(state)
    missing_str = ", ".join(missing) if missing else "–"
    reply_text = (
        f"Ich habe jetzt {state.reasoning.max_turns} Runden mit dir gesprochen und konnte "
        f"die Auslegung noch nicht abschließen. "
        f"Fehlende Kernparameter: {missing_str}. "
        f"Ich empfehle: direkt einen Hersteller-Ingenieur kontaktieren "
        f"oder die Parameter ergänzen und neu starten."
    )
    wm = state.reasoning.working_memory or WorkingMemory()
    wm = wm.model_copy(update={"response_text": reply_text, "response_kind": "turn_limit"})
    updated_messages = list(state.conversation.messages or [])
    updated_messages.append(AIMessage(content=[{"type": "text", "text": reply_text}]))
    return {
               "conversation": {
                   "messages": updated_messages,
               },
               "reasoning": {
                   "phase": PHASE.ERROR,
                   "last_node": "turn_limit_node",
                   "working_memory": wm,
               },
               "system": {
                   "final_text": reply_text,
                   "final_answer": reply_text,
               },
           }


__all__ = ["smalltalk_node", "out_of_scope_node", "turn_limit_node"]
