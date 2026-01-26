from __future__ import annotations
import os

target_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_knowledge.py'

if not os.path.exists(target_path):
    print(f"Target file not found: {target_path}")
    exit(1)

with open(target_path, 'r') as f:
    lines = f.readlines()

# 1. Add Import
import_marker = "from __future__ import annotations"
import_added = False
for i, line in enumerate(lines):
    if line.strip() == import_marker:
        if "from jinja2 import Template" not in "".join(lines):
            lines.insert(i+1, "from jinja2 import Template\n")
            print("Added jinja2 import")
            import_added = True
        break

# 2. Find the block
target_line_idx = -1
for i, line in enumerate(lines):
    if 'prompt_template="knowledge_generic_qa.j2"' in line:
        target_line_idx = i
        break

if target_line_idx == -1:
    print("Could not find target line with prompt_template='knowledge_generic_qa.j2'")
    exit(1)

# Backtrack to find start (reply_text = await run_llm)
start_idx = -1
for i in range(target_line_idx, -1, -1):
    if "reply_text = await run_llm(" in lines[i]:
        start_idx = i
        break

if start_idx == -1:
    print("Could not find start of run_llm call")
    exit(1)

# Find end (closing brace indentation matching start or close enough)
# We assume the closing paren is on a separate line indented similarly to arguments or start?
# In the file, start is indented 4 spaces. Closing paren is indented 4 spaces.
end_idx = -1
for i in range(target_line_idx, len(lines)):
    if lines[i].strip() == ")" and "nodes_knowledge.py" not in lines[i]: 
        # CAUTION: simple check. 
        # Let's check indentation.
        if lines[i].startswith("    )"): # 4 spaces
             end_idx = i
             break

if end_idx == -1:
    print("Could not find end of run_llm call")
    # Debug print
    print("Printing lines after target:")
    for j in range(target_line_idx, min(target_line_idx+20, len(lines))):
        print(f"{j}: {lines[j].rstrip()}")
    exit(1)

print(f"Found block from line {start_idx+1} to {end_idx+1}")

# Construct new block lines
new_block_lines = [
    '    # Manual Template Rendering:\n',
    '    template_path = "/app/app/prompts/knowledge_generic_qa.j2"\n',
    '    try:\n',
    '        with open(template_path, "r") as f:\n',
    '            tmpl = Template(f.read())\n',
    '        \n',
    '        prompt_text = tmpl.render(\n',
    '            context=rag_text,\n',
    '            question=latest_user_text(state.messages)\n',
    '        )\n',
    '    except Exception as e:\n',
    '        # Fallback if template missing\n',
    '        print(f"Template parsing error: {e}")\n',
    '        prompt_text = f"Context: {rag_text}\\n\\nQuestion: {latest_user_text(state.messages)}"\n',
    '\n',
    '    reply_text = await run_llm(\n',
    '        model=tier,\n',
    '        prompt=prompt_text,\n',
    '        system="Du bist ein hilfreicher Assistent.",\n',
    '        temperature=0.4,\n',
    '        max_tokens=400,\n',
    '        metadata={\n',
    '            "run_id": state.run_id,\n',
    '            "thread_id": state.thread_id,\n',
    '            "user_id": state.user_id,\n',
    '            "node": "generic_sealing_qa_node",\n',
    '        },\n',
    '    )\n'
]

# Replace
lines[start_idx:end_idx+1] = new_block_lines

with open(target_path, 'w') as f:
    f.writelines(lines)
print("Applied smart patch.")
