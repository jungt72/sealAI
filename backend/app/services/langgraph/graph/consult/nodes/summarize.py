from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage

from ....llm_factory import get_llm
from ..memory_utils import set_summary
from ....tools import long_term_memory as ltm


def _last_user_text(messages: List[Any]) -> str:
    for m in reversed(messages or []):
        role = (getattr(m, "type", "") or getattr(m, "role", "") or "").lower()
        content = getattr(m, "content", "")
        if isinstance(m, dict):
            role = (m.get("type") or m.get("role") or "").lower()
            content = m.get("content")
        if role in ("human", "user") and isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def summarize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Erzeugt eine knappe Zusammenfassung (Context handoff), injiziert sie in STM
    und persistiert sie im LTM (Qdrant) als conversation_summary.

    Inputs:
      - messages, retrieved_docs/docs, user_id, chat_id
    Outputs:
      - summary_text (optional)
    Nebenwirkungen:
      - Redis: chat:stm:{thread}:summary
      - Qdrant LTM: kind=conversation_summary
    """
    try:
        llm = get_llm(streaming=False)
    except Exception:
        llm = None

    msgs = state.get("messages") or []
    docs = state.get("retrieved_docs") or state.get("docs") or []
    user_id = state.get("user_id") or state.get("tenant") or None
    chat_id = state.get("chat_id") or None

    # Baue knappen Prompt
    question = _last_user_text(msgs)
    context_parts: List[str] = []
    if isinstance(docs, list) and docs:
        for d in docs[:4]:
            t = (d.get("text") or "").strip()
            if t:
                context_parts.append(t)
    ctx_text = "\n\n".join(context_parts)[:800]

    summary_text = ""
    if llm is not None:
        prompt = (
            "Fasse den Gesprächsverlauf und die wichtigsten Fakten extrem kurz zusammen. "
            "Max 3 Sätze, Deutsch. Wenn vorhanden, Parameter (z.B. Temperatur, Druck) erwähnen.\n\n"
        )
        try:
            content = prompt
            if question:
                content += f"Letzte Frage: {question}\n"
            if ctx_text:
                content += f"Kontext: {ctx_text}\n"
            resp = llm.invoke([HumanMessage(content=content)])
            summary_text = (getattr(resp, "content", "") or "").strip()
        except Exception:
            summary_text = ""

    # STM: Zusammenfassung injizieren, damit nachfolgende Turns sie sehen
    thread_id = str(chat_id or "")
    if thread_id and summary_text:
        try:
            set_summary(thread_id, summary_text)
        except Exception:
            pass

    # LTM: als conversation_summary speichern (falls möglich)
    if summary_text and (user_id or chat_id):
        try:
            ltm.upsert_memory(user=str(user_id or chat_id), chat_id=str(chat_id or user_id or ""), text=summary_text, kind="conversation_summary")
        except Exception:
            pass

    out = {**state, "phase": "summarize"}
    if summary_text:
        out["summary_text"] = summary_text
    return out


__all__ = ["summarize_node"]
