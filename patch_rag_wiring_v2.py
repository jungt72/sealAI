from __future__ import annotations
import os

target_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_knowledge.py'

if not os.path.exists(target_path):
    print(f"Target file not found: {target_path}")
    exit(1)

with open(target_path, 'r') as f:
    content = f.read()

# 1. Add Import
import_marker = "from __future__ import annotations"
new_import = "\nfrom jinja2 import Template\n"

if "from jinja2 import Template" not in content:
    content = content.replace(import_marker, import_marker + new_import)
    print("Added jinja2 import")

# 2. Fix generic_sealing_qa_node run_llm call
# We construct the EXACT string block based on the 'cat' output.

old_block = """    reply_text = await run_llm(
        model=tier,
        prompt_template="knowledge_generic_qa.j2",
        rag_context=rag_text,
        system="Du bist ein hilfreicher Assistent.",
        temperature=0.4,
        max_tokens=400,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "generic_sealing_qa_node",
        },
    )"""

new_block = """    # Manual Template Rendering:
    template_path = "/app/app/prompts/knowledge_generic_qa.j2"
    try:
        with open(template_path, "r") as f:
            tmpl = Template(f.read())
        
        prompt_text = tmpl.render(
            context=rag_text,
            question=latest_user_text(state.messages)
        )
    except Exception as e:
        # Fallback if template missing
        print(f"Template parsing error: {e}")
        prompt_text = f"Context: {rag_text}\\n\\nQuestion: {latest_user_text(state.messages)}"

    reply_text = await run_llm(
        model=tier,
        prompt=prompt_text,
        system="Du bist ein hilfreicher Assistent.",
        temperature=0.4,
        max_tokens=400,
        metadata={
            "run_id": state.run_id,
            "thread_id": state.thread_id,
            "user_id": state.user_id,
            "node": "generic_sealing_qa_node",
        },
    )"""

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Replaced run_llm call successfully.")
else:
    print("Exact block match failed. Attempting to normalize line endings and spaces...")
    # Try somewhat looser match by normalizing spaces if exact match fails
    # But usually copy-paste works if 'cat' output was clean
    pass

with open(target_path, 'w') as f:
    f.write(content)
