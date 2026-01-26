from __future__ import annotations
import os

target_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_knowledge.py'

if not os.path.exists(target_path):
    print(f"Target file not found: {target_path}")
    exit(1)

with open(target_path, 'r') as f:
    content = f.read()

# 1. Add Import
# Find a safe place for import. After "from __future__ ..."
import_marker = "from __future__ import annotations"
new_import = "\nfrom jinja2 import Template\n"

if "from jinja2 import Template" not in content:
    content = content.replace(import_marker, import_marker + new_import)
    print("Added jinja2 import")

# 2. Fix generic_sealing_qa_node logic
# We look for the run_llm call inside generic_sealing_qa_node
# The existing call:
#     reply_text = await run_llm(
#         model=tier,
#         prompt_template="knowledge_generic_qa.j2",
#         rag_context=rag_text,
#         # ...
#     )

# We want to replace it with:
#     template_path = "/app/app/prompts/knowledge_generic_qa.j2"
#     with open(template_path, "r") as f:
#         tmpl = Template(f.read())
#     
#     prompt_text = tmpl.render(
#         context=rag_text,
#         question=latest_user_text(state.messages)
#     )
#
#     reply_text = await run_llm(
#         model=tier,
#         prompt=prompt_text,
#         # ...
#     )

import re

# ... (previous code) ...

# 2. Fix generic_sealing_qa_node logic using Regex
# We want to match the run_llm call specifically inside generic_sealing_qa_node if possible, 
# or just the specific call that uses "knowledge_generic_qa.j2".

# Pattern to find:
# reply_text = await run_llm(
#    ...
#    prompt_template="knowledge_generic_qa.j2",
#    ...
# )

# Regex explanation:
# reply_text\s*=\s*await\s+run_llm\s*\(  -> match start of call
# .*?                                   -> match anything (non-greedy)
# prompt_template\s*=\s*"knowledge_generic_qa\.j2", -> match our target line
# .*?                                   -> match rest until end
# \)                                    -> match closing paren? 
# Matching standard python calls with regex is hard due to nesting. 
# BUT we know the structure is roughly indentation based.

# Let's try to match the specific unique ARGUMENT usage and replace the whole call manually constructed.

regex_pattern = r'(reply_text\s*=\s*await\s+run_llm\s*\(\s*[^)]*?prompt_template\s*=\s*"knowledge_generic_qa\.j2"[^)]*?\))'

# We need to capture the indentation to preserve it or just assume standard 4 spaces.
# The matching block will be replaced.

replacement_code = """    # Manual Template Rendering:
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

# We apply regex sub
new_content, count = re.subn(regex_pattern, replacement_code, content, flags=re.DOTALL)

if count > 0:
    print(f"Replaced {count} occurrence(s) using regex.")
    content = new_content
else:
    print("Regex failed to find target block.")
    # Debug: print snippet
    start_search = content.find('prompt_template="knowledge_generic_qa.j2"')
    if start_search != -1:
         print("DEBUG Snippet around target:")
         print(content[start_search-100:start_search+100])

with open(target_path, 'w') as f:
    f.write(content)
