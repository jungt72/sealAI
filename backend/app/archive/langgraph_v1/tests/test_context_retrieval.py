from app.langgraph.nodes.context_retrieval import context_retrieval
from app.langgraph.state import MetaInfo, Routing, SealAIState


def test_context_retrieval_enriches_state(monkeypatch):
    def fake_retrieve(**kwargs):
        return [
            {"text": "Doc snippet", "source": "kb://1", "vector_score": 0.91},
            {"text": "Second snippet", "source": "kb://2", "vector_score": 0.42},
        ]

    monkeypatch.setattr("app.langgraph.nodes.context_retrieval.hybrid_retrieve", fake_retrieve)

    state = SealAIState(
        messages=[],
        slots={"user_query": "Wie funktioniert RAG?"},
        routing=Routing(),
        context_refs=[],
        meta=MetaInfo(thread_id="t", user_id="u", trace_id="z"),
    )

    result = context_retrieval(state)
    assert "messages" in result
    assert result["slots"]["rag_sources"] == ["kb://1", "kb://2"]
    assert len(result["context_refs"]) == 2
