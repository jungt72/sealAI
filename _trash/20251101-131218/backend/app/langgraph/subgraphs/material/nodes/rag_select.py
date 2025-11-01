import asyncio
# MIGRATION: Phase-2 - RAG Select (nur Referenzen)

from ....state import SealAIState, ContextRef
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../../services/rag"))
from rag_orchestrator import hybrid_retrieve

async def rag_select(state: SealAIState) -> dict:
    # RAG-Query aus State, z.B. user_query
    query = state["slots"].get("user_query", "")
    if not query:
        return {}
    # Rufe RAG auf
    results = await asyncio.get_event_loop().run_in_executor(None, lambda: hybrid_retrieve(query=query, tenant=None, k=6))  # Dummy tenant
    # Extrahiere nur IDs/Meta, keine Volltexte
    refs = [
        ContextRef(
            kind="rag",
            id=result.get("id", f"doc_{i}"),  # Annahme id ist vorhanden
            meta={
                "score": result.get("vector_score", 0.0),
                "source": result.get("source", ""),
                "title": result.get("metadata", {}).get("title", "")
            }
        ) for i, result in enumerate(results)
    ]
    return {"context_refs": state["context_refs"] + refs}