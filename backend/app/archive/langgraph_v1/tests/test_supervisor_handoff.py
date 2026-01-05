# backend/app/langgraph/tests/test_supervisor_handoff.py
from __future__ import annotations

import os

import pytest

from app.langgraph.compile import create_main_graph
from app.langgraph.state import MetaInfo, SealAIState


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Supervisor workflow requires OPENAI_API_KEY for the coordinating LLM.",
)
async def test_supervisor_handoffs_to_member_then_exit():
    graph = create_main_graph(require_async=True)
    state = SealAIState(
        meta=MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1"),
        slots={"user_query": "Heißwasser bei 120°C – brauche Materialempfehlung"},
    )
    cfg = {"configurable": {"thread_id": "t1", "user_id": "u1", "checkpoint_ns": "sealai:main"}}

    saw_member = False
    async for ev in graph.astream_events(state, config=cfg, stream_mode="values"):
        if ev.get("event") == "node_end":
            node = ev.get("name")
            if node in {"material_agent", "profil_agent", "validierung_agent"}:
                saw_member = True
        if ev.get("event") == "end":
            break

    assert saw_member, "Supervisor sollte an mindestens einen Member-Agent übergeben."
