# MIGRATION: Phase-2 - Exit Response

from ..state import SealAIState

async def exit_response(state: SealAIState) -> dict:
    # Baue JSON-Struktur
    answer = "Final answer"  # From state
    response = {
        "answer": answer,
        "evidence_ids": [ref.id for ref in state["context_refs"]],
        "parameters": state["slots"],
        "risks": [],
        "next_steps": [],
        "ui_hints": {},
        "meta": state["meta"]
    }
    return {"messages": state["messages"] + [{"role": "assistant", "content": str(response)}]}