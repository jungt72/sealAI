from __future__ import annotations

from app.langgraph.graph_chat import compile_chat_graph


def test_chat_graph_smoke():
    graph = compile_chat_graph()
    result = graph.invoke(
        {
            "messages": [{"role": "user", "content": "Ich brauche ein Material für 200°C."}],
            "parameter_bag": {
                "items": [
                    {"name": "temperatur", "value": 200, "unit": "°C", "source": "user"},
                    {"name": "druck", "value": 2.5, "unit": "bar", "source": "user"},
                ]
            },
            "thread_id": "test-thread",
            "user_id": "tester",
        }
    )

    assert "final" in result
    final = result["final"]
    assert "synthesis" in final
    assert "safety" in final
    assert final["safety"]["result"] in {"pass", "block_with_reason"}
