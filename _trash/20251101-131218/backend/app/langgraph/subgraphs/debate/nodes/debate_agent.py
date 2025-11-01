# Debate Agent

from langgraph.types import Send
from ....state import SealAIState
from ....utils.llm import create_llm_for_domain, call_llm

async def debate_agent(state: SealAIState) -> Send:
    # Simple debate: Re-evaluate confidence
    prompt = "Debate the routing decision and update confidence."
    llm = create_llm_for_domain("material")
    response = await call_llm(llm, prompt)
    # Assume updates confidence
    updated_routing = state.get("routing", {}).copy()
    updated_routing["confidence"] = 0.9  # Dummy
    updated_state = state.copy()
    updated_state["routing"] = updated_routing
    return Send("resolver", updated_state)
