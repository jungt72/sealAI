from __future__ import annotations
import os

target_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_knowledge.py'

if not os.path.exists(target_path):
    print(f"Target file not found: {target_path}")
    exit(1)

with open(target_path, 'r') as f:
    content = f.read()

# The specific block we found in the file:
old_block = """    # Augmentierter Prompt
    prompt = f\"\"\"Kontext aus Wissensdatenbank:
{rag_text}

Frage: {user_text or 'Beantworte eine allgemeine Frage zur Dichtungstechnik klar und praxisnah.'}

Beantworte basierend auf dem Kontext.\"\"\"
    
    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=(
            "Du bist ein allgemeiner Berater f??r Dichtungstechnik. "
            "Nutze die Wissensdatenbank. "
            "Antworte klar, strukturiert und m??glichst praxisnah (Beispiele aus Pumpen, Zylindern, Getrieben etc.). "
            "Bleib kompakt und vermeide unn??tige Wiederholungen."
        ),"""

new_block = """    # Manual Template Rendering via Jinja2
    template_path = "/app/app/prompts/knowledge_generic_qa.j2"
    try:
        with open(template_path, "r") as f:
            from jinja2 import Template
            tmpl = Template(f.read())
        
        prompt = tmpl.render(
            context=rag_text,
            question=user_text or 'Beantworte eine allgemeine Frage zur Dichtungstechnik klar und praxisnah.'
        )
    except Exception as e:
        print(f"Template rendering failed: {e}")
        prompt = f\"\"\"Kontext aus Wissensdatenbank:
{rag_text}

Frage: {user_text or 'Beantworte eine allgemeine Frage zur Dichtungstechnik klar und praxisnah.'}

Beantworte basierend auf dem Kontext.\"\"\"

    reply_text = run_llm(
        model=model_name,
        prompt=prompt,
        system=(
            "Du bist ein allgemeiner Berater f??r Dichtungstechnik. "
            "Nutze die Wissensdatenbank. "
            "Antworte klar, strukturiert und m??glichst praxisnah (Beispiele aus Pumpen, Zylindern, Getrieben etc.). "
            "Bleib kompakt und vermeide unn??tige Wiederholungen."
        ),"""

if old_block in content:
    content = content.replace(old_block, new_block)
    print("Replaced f-string prompt with Jinja2 rendering.")
else:
    print("Could not find exact block match. Checking content...")
    # Debug info
    start_marker = "# Augmentierter Prompt"
    idx = content.find(start_marker)
    if idx != -1:
        print("Found start marker. Dumping next 500 chars:")
        print(content[idx:idx+500])
    else:
        print("Start marker not found.")
        
with open(target_path, 'w') as f:
    f.write(content)
