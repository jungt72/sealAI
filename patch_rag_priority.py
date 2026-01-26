from __future__ import annotations
import os

target_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_supervisor.py'

if not os.path.exists(target_path):
    print(f"Target file not found: {target_path}")
    exit(1)

with open(target_path, 'r') as f:
    content = f.read()

# We want to move the needs_sources check to the top of the technical goal decision block.
# The search string is the start of the decision block.

old_block = """    if goal in ("smalltalk", "out_of_scope"):
        reason = "non_technical_goal"
        action = ACTION_FINALIZE
    elif goal == "troubleshooting_leakage":
        reason = "troubleshooting_flow"
        action = ACTION_RUN_TROUBLESHOOTING
    elif goal == "design_recommendation" and is_knowledge:"""

# We insert `needs_sources` check before designs/troubleshooting etc? 
# The user said: "whenever the orchestrator signals that sources are required... route to ACTION_RUN_PANEL_NORMS_RAG ... BEFORE requesting calculation parameters ... even when goal='design_recommendation'".

# So we should put it right after non-technical goals.

new_block = """    if goal in ("smalltalk", "out_of_scope"):
        reason = "non_technical_goal"
        action = ACTION_FINALIZE
    elif needs_sources:
        # [PATCH] Orchestrator signaled research is needed. Prioritize this!
        reason = "rag_sources_required"
        action = ACTION_RUN_PANEL_NORMS_RAG
    elif goal == "troubleshooting_leakage":
        reason = "troubleshooting_flow"
        action = ACTION_RUN_TROUBLESHOOTING
    elif goal == "design_recommendation" and is_knowledge:"""

if old_block in content:
    new_content = content.replace(old_block, new_block)
    # We also need to REMOVE the old occurrences of needs_sources checks later in the file?
    # Actually, if we leave them, they won't be reached if needs_sources is True (because of the top-level block).
    # But for cleanliness, we should probably check if there are other blocks that SET action to RUN_PANEL_NORMS_RAG based on needs_sources.
    
    # In the original code (viewed in sed), there were checks in `explanation_or_comparison` and at the end.
    # If we catch it early, those won't be reached.
    
    with open(target_path, 'w') as f:
        f.write(new_content)
    print("Successfully patched nodes_supervisor.py")
else:
    print("Could not find target block in nodes_supervisor.py")
    # Debug: show what we find around there
    try:
        idx = content.find('if goal in ("smalltalk", "out_of_scope"):')
        if idx != -1:
            print("Found partial match. Content around it:")
            print(content[idx:idx+300])
    except:
        pass
    exit(1)
