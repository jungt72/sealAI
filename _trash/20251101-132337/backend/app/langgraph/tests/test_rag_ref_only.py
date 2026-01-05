# MIGRATION: Phase-2 - RAG liefert nur Referenzen

from ..state import SealAIState, MetaInfo
from ..subgraphs.material.nodes.rag_select import rag_select

def test_rag_refs():
    meta = MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1")
    state = SealAIState(meta=meta, slots={"user_query": "material test"})
    initial_refs = len(state.context_refs)
    state_dict = rag_select(state)
    new_state = state.update(state_dict)
    # Assert only refs added, no full texts in messages
    assert len(new_state.context_refs) >= initial_refs
    for ref in new_state.context_refs:
        assert ref.kind == "rag"
        assert "id" in ref.dict()
        assert "text" not in str(ref.dict())  # No full text