from __future__ import annotations
import os

target_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_knowledge.py'

if not os.path.exists(target_path):
    print(f"Target file not found: {target_path}")
    exit(1)

with open(target_path, 'r') as f:
    content = f.read()

# 1. Add Import if missing
if "from jinja2 import Template" not in content:
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("from __future__"):
            lines.insert(i+1, "from jinja2 import Template")
            break
    content = "\n".join(lines)
    print("Added jinja2 import.")

# 2. Locate Start of Block
# We look for the comment "# Augmentierter Prompt" or similar unique line.
marker_start_text = "# Augmentierter Prompt"
start_idx = content.find(marker_start_text)

if start_idx == -1:
    print(f"Could not find start marker: '{marker_start_text}'")
    # Try alternative marker from recent dumps
    marker_start_text = "prompt = f\"\"\"Kontext"
    start_idx = content.find(marker_start_text)
    if start_idx == -1:
        print("Could not find alternative start marker either. Aborting.")
        exit(1)

print(f"Found start marker at index {start_idx}")

# 3. Locate End of Block (End of run_llm call)
# Find start of run_llm call after the marker
run_llm_start_text = "reply_text = run_llm("
# Actually, could be `reply_text = await run_llm(`?
# The dump showed `reply_text = run_llm(`. Wait, is it async?
# Step 2556 output: `reply_text = run_llm(`
# Step 2507 output: `reply_text = run_llm(`
# But `nodes_knowledge.py` is usually async. `run_llm` is sync implementation?
# `llm_factory.py` has `def run_llm(...) -> str`. It is sync.
# `generic_sealing_qa_node` is sync? `def generic_sealing_qa_node(...)`.
# OK, assuming sync call.

run_llm_idx = content.find(run_llm_start_text, start_idx)
if run_llm_idx == -1:
    # Try async just in case
    run_llm_start_text = "reply_text = await run_llm("
    run_llm_idx = content.find(run_llm_start_text, start_idx)
    if run_llm_idx == -1:
        print("Could not find run_llm call after marker.")
        exit(1)

print(f"Found run_llm call at index {run_llm_idx}")

# Find matching closing paren for run_llm
open_cnt = 0
close_pos = -1
for i in range(run_llm_idx, len(content)):
    char = content[i]
    if char == '(':
        open_cnt += 1
    elif char == ')':
        open_cnt -= 1
        if open_cnt == 0:
            close_pos = i
            break

if close_pos == -1:
    print("Could not find closing parenthesis for run_llm.")
    exit(1)

print(f"Found end of block at index {close_pos}")

# 4. Construct Replacement
# We preserve indentation of the start marker.
# Assuming standard 4-space indentation.

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
        sys_msg = "Du bist SealAI, ein Assistent f??r Dichtungstechnik."
    except Exception as e:
        print(f"Template rendering failed: {e}")
        prompt = f\"\"\"Kontext: {rag_text}\\n\\nFrage: {user_text}\\n\"\"\"
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
        },"""

# Add closing paren and newline, matching the `close_pos` replacement logic.
# We are replacing `content[start_idx : close_pos+1]`.
# The original code ended with `    )` (indented close paren).
# Our `new_block` ends with `,`. We need to add the closing paren.
new_block += "\n    )"

# 5. Apply Patch
content = content[:start_idx] + new_block + content[close_pos+1:]

with open(target_path, 'w') as f:
    f.write(content)

print("Successfully patched nodes_knowledge.py")
