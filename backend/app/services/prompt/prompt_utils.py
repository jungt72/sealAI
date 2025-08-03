def format_prompt(user_input: str, rag_context: list[str]) -> str:
    prompt = user_input
    if rag_context:
        prompt += "\n\nNützliche Passagen:\n" + "\n---\n".join(rag_context)
    return prompt
