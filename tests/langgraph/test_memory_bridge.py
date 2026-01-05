from __future__ import annotations

import asyncio
from langchain_core.messages import HumanMessage

from app.langgraph.nodes import memory_bridge
from app.langgraph.state import SealAIState


def test_memory_bridge_injects_long_term_context(monkeypatch):
    async def _fake_transcript(_user_id: str):
        return {"chat_id": "c-1", "summary": "Letzte Beratung zu PTFE-Hülsen.", "metadata": {}}

    async def _fake_refs(_user_id: str):
        return [
            {
                "storage": "qdrant",
                "id": "ltm-1",
                "summary": "Bevorzugt Lebensdauer > 10.000 h.",
                "score": 0.82,
            }
        ]

    monkeypatch.setattr(memory_bridge, "_load_last_transcript", _fake_transcript)
    monkeypatch.setattr(memory_bridge, "_load_ltm_refs", _fake_refs)

    state: SealAIState = {
        "messages": [HumanMessage(content="Wir planen eine neue Anlage.")],
        "meta": {"user_id": "user-123"},
    }

    result = asyncio.run(memory_bridge.memory_bridge_node(state))

    assert result["long_term_memory_refs"], "LTM-Referenzen fehlen"
    assert result["slots"]["memory_injections"], "Memory-Injections fehlen"
    assert any(
        getattr(msg, "id", None) == "msg-memory-bridge"
        for msg in result.get("messages", [])
    ), "SystemMessage mit Langzeit-Kontext fehlt"
