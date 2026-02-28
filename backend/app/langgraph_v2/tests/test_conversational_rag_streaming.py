from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes import conversational_rag as rag_mod


class _Chunk:
    def __init__(self, content):
        self.content = content


class _FakeLLM:
    def __init__(self, chunks):
        self._chunks = chunks
        self.calls = []

    def astream(self, messages, *, config=None):
        self.calls.append({"messages": messages, "config": config})

        async def _gen():
            for item in self._chunks:
                yield _Chunk(item)

        return _gen()


@pytest.mark.asyncio
async def test_conversational_rag_streams_chunks_and_forwards_config():
    state = SimpleNamespace(
        messages=[HumanMessage(content="Was ist geeignet?")],
        working_memory=SimpleNamespace(panel_material={"rag_context": "Fakt A"}),
        context="",
        flags={},
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
    )
    fake_llm = _FakeLLM(["Hallo", " Welt"])
    config = {"configurable": {"thread_id": "thread-1"}, "callbacks": ["cb"]}

    with patch.object(rag_mod, "_RAG_LLM", fake_llm):
        patch_result = await rag_mod.conversational_rag_node(state, config=config)

    assert patch_result["final_text"] == "Hallo Welt"
    assert patch_result["final_answer"] == "Hallo Welt"
    assert fake_llm.calls and fake_llm.calls[0]["config"] == config
    system_prompt = str(fake_llm.calls[0]["messages"][0].content)
    assert "ABSOLUTE Priorität" in system_prompt
    assert "kryogen-tauglich" in system_prompt


@pytest.mark.asyncio
async def test_conversational_rag_low_quality_short_circuits_without_llm():
    state = SimpleNamespace(
        messages=[HumanMessage(content="Was ist geeignet?")],
        working_memory=SimpleNamespace(panel_material={"rag_context": "Fakt A"}),
        context="",
        flags={"rag_low_quality_results": True},
        run_id="run-1",
        thread_id="thread-1",
        user_id="user-1",
    )
    fake_llm = _FakeLLM(["unused"])

    with patch.object(rag_mod, "_RAG_LLM", fake_llm):
        patch_result = await rag_mod.conversational_rag_node(state, config={"callbacks": ["cb"]})

    assert "allgemeine Informationen zu PTFE-Dichtungen" in patch_result["final_text"]
    assert patch_result["final_answer"] == patch_result["final_text"]
    assert fake_llm.calls == []
