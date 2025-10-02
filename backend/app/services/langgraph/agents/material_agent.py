import os
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from app.services.langgraph.prompting import render_template, build_system_prompt_from_parts

PROMPT_NAME = "material_agent.jinja2"


def get_prompt(context: dict | None = None) -> str:
    try:
        return render_template(PROMPT_NAME, context=context or {})
    except Exception:
        return ""


class MaterialAgent:
    name = "material_agent"

    def __init__(self, context: dict | None = None):
        self.system_prompt = get_prompt(context)
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0")),
            streaming=True,
            output_version="responses/v1",
            use_responses_api=True,
        )

    def invoke(self, state: dict[str, Any]):
        # Prevent duplicate system messages: strip leading system messages from state
        msgs = list(state.get("messages") or [])
        msgs = [m for m in msgs if not isinstance(m, SystemMessage)]

        # If state contains retrieved docs or a summary, optionally merge them
        retrieved = state.get("retrieved_docs") or []
        rag_texts = [d.get("text") for d in retrieved if isinstance(d, dict) and d.get("text")]
        summary = state.get("summary") or None
        system_text = build_system_prompt_from_parts(
            f"{self.system_prompt}", summary=summary, rag_docs=rag_texts, max_tokens=int(os.getenv("PROMPT_MAX_TOKENS", "3000")), model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        )

        messages = [SystemMessage(content=system_text)] + msgs
        return {"messages": self.llm.invoke(messages)}


def get_material_agent(context: dict | None = None) -> MaterialAgent:
    return MaterialAgent(context)
