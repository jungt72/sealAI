from __future__ import annotations
import os

target_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_knowledge.py'

if not os.path.exists(target_path):
    print(f"Target file not found: {target_path}")
    exit(1)

with open(target_path, 'r') as f:
    content = f.read()

# The confirmed block from the debug dump:
old_block_part = """    # Augmentierter Prompt mit RAG-Kontext
    prompt = f\"\"\"Kontext aus Wissensdatenbank:
{rag_text}

Frage des Nutzers: {user_text}

Beantworte die Frage basierend auf dem Kontext. Zitiere Quellen wenn m??glich.\"\"\""""

# The output from step 2529 showed this exactly.
# We need to be careful about what comes after.
# The dump showed:
#     reply_text = run_llm(
#         model=model_name,
#         prompt=prompt,
#         system=(
#             "Du bist ein Fachberater f??r Dichtungswerkstoffe. "
#             "Nutze die bereitgestellten Informationen aus der Wissensdatenbank. "
#             "Erkl??re Eigenschaften (Temperatur

# We can construct a precise search block now.

old_block = """    # Augmentierter Prompt mit RAG-Kontext
    prompt = f\"\"\"Kontext aus Wissensdatenbank:
{rag_text}

Frage des Nutzers: {user_text}

Beantworte die Frage basierend auf dem Kontext. Zitiere Quellen wenn m??glich.\"\"\"
    
    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=(
            "Du bist ein Fachberater f??r Dichtungswerkstoffe. "
            "Nutze die bereitgestellten Informationen aus der Wissensdatenbank. "
            "Erkl??re Eigenschaften (Temperatur"""

# Note: The system prompt continues. We can just replace the top part and keep the rest?
# No, we want to replace the whole prompt construction.
# AND we want to update the system prompt to match the template if desired, or keep it.
# The user's template `knowledge_generic_qa.j2` has its own system instruction: "Du bist ein technischer Assistent fuer Dichtungstechnik (SealAI)..."
# But `run_llm` takes a `system` arg.
# If we render the template into `prompt`, we might want to pass a minimal system prompt or the one from the template?
# Usually, Jinja templates for chat models include the system message, OR `run_llm` handles it.
# `run_llm` implementation takes `system` and `prompt`.
# The user template `knowledge_generic_qa.j2` starts with: "Du bist ein technischer Assistent..."
# This likely conceptually replaces the system prompt.
# BUT `run_llm` puts `system` into `SystemMessage`.
# If `prompt` (rendered from template) ALSO contains "Du bist...", we duplicate.
# However, the user-provided template looks like a single block of text.
# If `run_llm` forces a system message, we should probably set it to something compatible or generic.

# Let's replace the block up to `run_llm` call start, and then REWRITE the `run_llm` arguments entirely.

# Replacement logic:
new_block = """    # Manual Template Rendering via Jinja2
    template_path = "/app/app/prompts/knowledge_generic_qa.j2"
    try:
        with open(template_path, "r") as f:
            from jinja2 import Template
            tmpl = Template(f.read())
        
        prompt = tmpl.render(
            context=rag_text,
            question=user_text or 'Beantworte eine allgemeine Frage zur Dichtungstechnik.'
        )
        # Template includes system-like instructions.
        # We can pass a minimal system prompt or consistent one.
        sys_msg = "Du bist SealAI, ein Assistent f??r Dichtungstechnik."
    except Exception as e:
        print(f"Template rendering failed: {e}")
        prompt = f\"\"\"Kontext: {rag_text}\\n\\nFrage: {user_text}\\n\"\"\"
        sys_msg = "Du bist ein Fachberater f??r Dichtungswerkstoffe."

    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=sys_msg,
        # Rest of arguments will be in the old block part we didn't include?
        # Wait, if we replace partial block, we break syntax.
        # We must replace the VALID python structure.
"""

# To be safe, we will replace `old_block_part` (the prompt construction) AND the `run_llm` call.
# But since we don't know the full `run_llm` args (system prompt was truncated in dump), 
# we should try to match just the prompt construction and the START of run_llm,
# and then use regex to eat until the end of run_llm?
# No, regex is fragile.

# Let's use the dump info to be as precise as possible about the prompt construction.
# We will replace the PROMPT CONSTRUCTION lines.
# And we will replace the `run_llm` call.
# BUT we need to match the `run_llm` call to replace it.

# Let's try to match strict string on the PROMPT part, which we know 100%.
# And then assumes the next lines are `    reply_text = run_llm(`.

# Let's read the whole file content in the script and use `content.find(old_block_part)`.
# Then find the matching `)` for `run_llm`.

regex_logic = """
import re

# We know this block exists:
marker = '''    # Augmentierter Prompt mit RAG-Kontext
    prompt = f\"\"\"Kontext aus Wissensdatenbank:
{rag_text}

Frage des Nutzers: {user_text}

Beantworte die Frage basierend auf dem Kontext. Zitiere Quellen wenn m??glich.\"\"\"'''

idx = content.find(marker)
if idx != -1:
    # Found it. Now look forward to find the end of run_llm used immediately after.
    # It starts with `    reply_text = run_llm(`
    # We want to replace everything from `idx` up to the closing paranthesis of `run_llm`.
    
    # scan for next `reply_text = run_llm`
    run_llm_start = content.find("reply_text = run_llm", idx)
    if run_llm_start != -1:
        # scan for closing bracket. Simple counter approach.
        open_cnt = 0
        close_pos = -1
        for i in range(run_llm_start, len(content)):
            char = content[i]
            if char == '(':
                open_cnt += 1
            elif char == ')':
                open_cnt -= 1
                if open_cnt == 0:
                    close_pos = i
                    break
        
        if close_pos != -1:
            # We have the range [idx, close_pos+1]
            # Replace it!
            
            new_code = '''    # Manual Template Rendering via Jinja2
    template_path = "/app/app/prompts/knowledge_generic_qa.j2"
    try:
        with open(template_path, "r") as f:
            from jinja2 import Template
            tmpl = Template(f.read())
            
        prompt = tmpl.render(
            context=rag_text,
            question=user_text or 'Beantworte eine allgemeine Frage zur Dichtungstechnik.'
        )
        sys_msg = "Du bist SealAI, ein Assistent f??r Dichtungstechnik."
    except Exception as e:
        print(f"Template rendering failed: {e}")
        prompt = f"Kontext: {rag_text}\\n\\nFrage: {user_text}"
        sys_msg = "Du bist ein Fachberater f??r Dichtungswerkstoffe."

    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=sys_msg,
        temperature=0.4,
        max_tokens=400,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "generic_sealing_qa_node",
        },'''
            # Note: we need to match the original indentation of the closing brace?
            # The original code ended with `    )` indented.
            # My new_code ends with `        },`. We need to add `    )`
            new_code += "\\n    )"
            
            content = content[:idx] + new_code + content[close_pos+1:]
            print("Successfully patched via substring + paren counting.")
        else:
            print("Could not find closing parenthesis for run_llm.")
    else:
        print("Could not find run_llm call after prompt.")
else:
    print("Could not find prompt marker.")
"""

with open(target_path, 'w') as f:
    f.write(content)
    # Actually I need to RUN the logic I just wrote stringified.
    # So I will overwrite `content` in memory then write `content`.

exec(regex_logic)

with open(target_path, 'w') as f:
    f.write(content)
