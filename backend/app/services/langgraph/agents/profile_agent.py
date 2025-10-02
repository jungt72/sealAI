# backend/app/services/langgraph/agents/profile_agent.py
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from app.services.langgraph.llm_factory import get_llm
from app.services.langgraph.prompting import render_template, build_system_prompt_from_parts

def _last_user_text(messages: List[Any]) -> str:
    for m in reversed(messages or []):
        c = getattr(m, "content", None)
        if isinstance(c, str) and c.strip():
            return c.strip()
    return ""

class ProfileAgent:
    name = "profile_agent"

    def __init__(self) -> None:
        self.llm = get_llm()

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        msgs = list(state.get("messages") or [])
        # Remove any existing SystemMessage from history
        msgs = [m for m in msgs if not isinstance(m, SystemMessage)]
        query = _last_user_text(msgs)
        base_prompt = render_template("profile_agent.jinja2", query=query)
        summary = state.get("summary") or None
        retrieved = state.get("retrieved_docs") or []
        rag_texts = [d.get("text") for d in retrieved if isinstance(d, dict) and d.get("text")]
        system_text = build_system_prompt_from_parts(
            base_prompt, summary=summary, rag_docs=rag_texts, max_tokens=int(__import__("os").getenv("PROMPT_MAX_TOKENS", "3000")), model=__import__("os").getenv("OPENAI_MODEL", "gpt-4o"),
        )
        response = self.llm.invoke([SystemMessage(content=system_text)] + msgs)
        ai = response if isinstance(response, AIMessage) else AIMessage(content=getattr(response, "content", "") or "")
        return {"messages": [ai]}

def get_profile_agent() -> ProfileAgent:
    return ProfileAgent()
