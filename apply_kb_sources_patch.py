import re
import os

def patch_file(path, replacements):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return
    with open(path, 'r') as f:
        content = f.read()
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"Applied patch to {path}")
        else:
            print(f"Pattern not found in {path}: {old[:50]}...")
    
    with open(path, 'w') as f:
        f.write(content)

# 1. Patch nodes_frontdoor.py
fd_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_frontdoor.py'
fd_repl = [
    (
        'intent.knowledge_type in ("material", "lifetime", "norms")):',
        'intent.knowledge_type in ("material", "lifetime", "norms") or intent.key == "generic_sealing_qa"):'
    )
]
patch_file(fd_path, fd_repl)

# 2. Patch nodes_knowledge.py
kn_path = '/home/thorsten/sealai/backend/app/langgraph_v2/nodes/nodes_knowledge.py'

# Update _process_knowledge_sources to handle merging/deduping if desired, 
# or ensure it correctly extracts from metrics/sources if that's the structure.
# But looking at the current code, it seems to match the requirement mostly, 
# except maybe the structure check.
# Let's refine it to be more robust.

old_helper = """def _process_knowledge_sources(retrieval_meta: Dict[str, Any] | None) -> Tuple[bool, str, List[Source]]:
    \"\"\"
    Extrahiert Quellen aus retrieval_meta und bestimmt needs_sources/sources_status.
    \"\"\"
    if not retrieval_meta or retrieval_meta.get("skipped"):
        return False, "missing", []
    
    raw_sources = retrieval_meta.get("sources", [])
    if not raw_sources:
        return False, "missing", []
    
    sources = []
    for s in raw_sources:
        sources.append(Source(
            source=s.get("source") or s.get("url"),
            metadata=s.get("metadata") or s
        ))
    
    return True, "ok", sources"""

new_helper = """def _process_knowledge_sources(retrieval_meta: Dict[str, Any] | None, existing_sources: List[Source] = None) -> Tuple[bool, str, List[Source]]:
    \"\"\"
    Extrahiert Quellen aus retrieval_meta und bestimmt needs_sources/sources_status.
    F??hrt Deduplizierung basierend auf der 'source' ID durch.
    \"\"\"
    sources = list(existing_sources or [])
    if not retrieval_meta or retrieval_meta.get("skipped"):
        return bool(sources), "ok" if sources else "missing", sources
    
    # RAG Orchestrator might return sources directly or under metrics
    raw_sources = retrieval_meta.get("sources") or retrieval_meta.get("metrics", {}).get("sources", [])
    
    if not raw_sources and not sources:
        return False, "missing", []
    
    known_ids = {s.source for s in sources if s.source}
    
    added_new = False
    for s in raw_sources:
        src_id = s.get("source") or s.get("url")
        if src_id and src_id not in known_ids:
            sources.append(Source(
                source=src_id,
                snippet=s.get("snippet") or s.get("text"),
                metadata=s.get("metadata") or s
            ))
            known_ids.add(src_id)
            added_new = True
    
    status = "ok" if sources else "missing"
    return bool(sources), status, sources"""

# Also need to update the call sites to pass state.sources
kn_repl = [
    (old_helper, new_helper),
    (
        "needs_src, src_status, sources = _process_knowledge_sources(retrieval_meta)",
        "needs_src, src_status, sources = _process_knowledge_sources(retrieval_meta, existing_sources=state.sources)"
    )
]
# Note: we need to use AllowMultiple for the call site replacement
with open(kn_path, 'r') as f:
    kn_content = f.read()
kn_content = kn_content.replace(old_helper, new_helper)
kn_content = kn_content.replace(
    "needs_src, src_status, sources = _process_knowledge_sources(retrieval_meta)",
    "needs_src, src_status, sources = _process_knowledge_sources(retrieval_meta, existing_sources=state.sources)"
)
with open(kn_path, 'w') as f:
    f.write(kn_content)
print(f"Patched {kn_path}")
