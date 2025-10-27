# MIGRATION: Phase-2 - Synthesis (send zurück zu resolver)

from ....state import SealAIState
from langgraph.types import Send
from ....utils.jinja_renderer import render_template
from ....utils.llm import create_llm_for_domain, call_llm
import os
import json

async def synthesis(state: SealAIState) -> Send:
    # Render Synthesis-Prompt
    prompt_path = os.path.join(os.path.dirname(__file__), "../../../prompts/synthesis.md")
    context = {
        "user_query": state["slots"].get("user_query", ""),
        "slots": state["slots"],
        "context_refs": state["context_refs"],
        "tool_results_brief": []  # Placeholder
    }
    prompt = render_template(prompt_path, context)
    
    # LLM Call
    llm = create_llm_for_domain("material")
    response_text = await call_llm(llm, prompt)
    
    # Parse to structured answer (assume LLM returns JSON)
    try:
        answer = json.loads(response_text)
    except json.JSONDecodeError:
        answer = {
            "answer": response_text,
            "evidence_ids": [ref.id for ref in state["context_refs"]],
            "risks": ["Parsing error"],
            "confidence_dom": 0.5
        }
    
    updated_state = state.copy()
    updated_state["messages"] = state.get("messages", []) + [{"role": "assistant", "content": json.dumps(answer)}]
    # Send zurück zu resolver im Hauptgraph
    return Send("resolver", updated_state)
