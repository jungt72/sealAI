from app.langgraph_v2.utils import rag_tool


def test_format_hit_does_not_emit_intern_source_when_missing_metadata() -> None:
    rendered = rag_tool._format_hit({"metadata": {}, "text": "x", "vector_score": 0.1})
    assert "Quelle:" not in rendered
    assert "intern" not in rendered

