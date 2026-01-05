# MIGRATION: Phase-2 - Confirm Gate (Interrupt)

# from langgraph.types import interrupt  # Disabled for streaming compatibility

async def confirm_gate(state):
    # Interrupt mit reason
    # interrupt({"reason": "confirm_discovery", "current_state": state})  # Disabled
    return {}