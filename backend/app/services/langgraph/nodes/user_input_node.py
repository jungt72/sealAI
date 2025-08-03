import re

async def user_input_node(state):
    messages = list(state.get("messages", []))
    current = state.get("current_input", "")
    new_state = {k: v for k, v in state.items() if k != "current_input"}

    if current:
        messages.append({"role": "user", "content": current})

        # Primitive Extraction: "Merke: Meine Lieblingsfarbe ist grün."
        match = re.search(r"(?i)merke.*lieblingsfarbe ist (\w+)", current)
        if match:
            new_state["favorite_color"] = match.group(1)
    new_state["messages"] = messages
    return new_state
