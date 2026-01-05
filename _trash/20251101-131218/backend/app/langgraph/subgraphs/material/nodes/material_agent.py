# MIGRATION: Phase-2 - Material Agent

from ....state import SealAIState
from ....utils.jinja_renderer import render_template
from ....utils.llm import create_llm_for_domain, call_llm
import os

async def material_agent(state: SealAIState) -> dict:
    # Render Prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "../../../prompts/material_agent.md")
    context = {
        "user_query": state["slots"].get("user_query", ""),
        "messages_window": state["messages"][-5:],  # Letzte 5
        "slots": state["slots"],
        "context_refs": state["context_refs"]
    }
    prompt = render_template(prompt_path, context)
    
    # LLM Call
    llm = create_llm_for_domain("material")
    hypotheses = await call_llm(llm, prompt)
    
    return {"messages": state["messages"] + [{"role": "assistant", "content": hypotheses}]}