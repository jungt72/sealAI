# backend/app/services/langgraph/agents/profile_agent.py
from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from app.services.langgraph.llm_factory import get_llm
from app.services.langgraph.prompting import render_template

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
        msgs = state.get("messages") or []
        query = _last_user_text(msgs)
        system_prompt = render_template("profile_agent.jinja2", query=query)
        response = self.llm.invoke([SystemMessage(content=system_prompt)] + msgs)
        ai = response if isinstance(response, AIMessage) else AIMessage(content=getattr(response, "content", "") or "")
        return {"messages": [ai]}

def get_profile_agent() -> ProfileAgent:
    return ProfileAgent()
