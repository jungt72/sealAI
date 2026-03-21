from __future__ import annotations

from unittest.mock import patch

from app._legacy_v2.state import SealAIState, WorkingMemory

import pytest
from langchain_core.messages import HumanMessage

from app._legacy_v2.nodes import conversational_rag as rag_mod


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
    state = SealAIState(
        conversation={
            "messages": [HumanMessage(content="Was ist geeignet?")],
            "thread_id": "thread-1",
            "user_id": "user-1",
        },
        reasoning={
            "working_memory": WorkingMemory(panel_material={"rag_context": "Fakt A"}),
            "context": "",
            "flags": {},
        },
        system={"run_id": "run-1"},
    )
    fake_llm = _FakeLLM(["Hallo", " Welt"])
    config = {"configurable": {"thread_id": "thread-1"}, "callbacks": ["cb"]}

    with patch.object(rag_mod, "_RAG_LLM", fake_llm):
        patch_result = await rag_mod.conversational_rag_node(state, config=config)

    assert patch_result["system"]["final_text"] == "Hallo Welt"
    assert patch_result["system"]["final_answer"] == "Hallo Welt"
    # governed output fields must be set — primary SoT
    assert patch_result["system"]["governed_output_text"] == "Hallo Welt"
    assert patch_result["system"]["governed_output_ready"] is True
    assert patch_result["system"]["governed_output_status"] == "conversational_rag"
    assert fake_llm.calls and fake_llm.calls[0]["config"] == config
    system_prompt = str(fake_llm.calls[0]["messages"][0].content)
    assert "ABSOLUTE Priorität" in system_prompt
    assert "kryogen-tauglich" in system_prompt


@pytest.mark.asyncio
async def test_conversational_rag_low_quality_short_circuits_without_llm():
    state = SealAIState(
        conversation={
            "messages": [HumanMessage(content="Was ist geeignet?")],
            "thread_id": "thread-1",
            "user_id": "user-1",
        },
        reasoning={
            "working_memory": WorkingMemory(panel_material={"rag_context": "Fakt A"}),
            "context": "",
            "flags": {"rag_low_quality_results": True},
        },
        system={"run_id": "run-1"},
    )
    fake_llm = _FakeLLM(["unused"])

    with patch.object(rag_mod, "_RAG_LLM", fake_llm):
        patch_result = await rag_mod.conversational_rag_node(state, config={"callbacks": ["cb"]})

    assert "allgemeine Informationen zu PTFE-Dichtungen" in patch_result["system"]["final_text"]
    assert patch_result["system"]["final_answer"] == patch_result["system"]["final_text"]
    # governed output mirrors final_text even on fallback path
    assert patch_result["system"]["governed_output_text"] == patch_result["system"]["final_text"]
    assert patch_result["system"]["governed_output_ready"] is True
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_conversational_rag_no_docs_fallback_sets_governed_output():
    """Ensure the no-docs (rag_limit_reached) fallback also sets governed output."""
    state = SealAIState(
        conversation={
            "messages": [HumanMessage(content="Noch ein Versuch")],
            "thread_id": "thread-1",
            "user_id": "user-1",
        },
        reasoning={
            "working_memory": WorkingMemory(panel_material={"rag_context": ""}),
            "context": "",
            "flags": {"rag_limit_reached": True},
            "rag_turn_count": 3,
        },
        system={"run_id": "run-1"},
    )
    fake_llm = _FakeLLM(["unused"])

    with patch.object(rag_mod, "_RAG_LLM", fake_llm):
        patch_result = await rag_mod.conversational_rag_node(state, config={})

    sys = patch_result["system"]
    # no-docs text is a legitimate terminal answer — must be governed
    assert sys["governed_output_text"] == sys["final_text"]
    assert sys["governed_output_ready"] is True
    assert sys["governed_output_status"] == "conversational_rag"
    assert fake_llm.calls == []


def test_speaking_nodes_constant_removed():
    """SPEAKING_NODES and CONVERSATIONAL_STREAM_NODES must not exist in the endpoint
    module — they were dead code that falsely listed node_draft_answer as a speaking node."""
    from app.api.v1.endpoints import langgraph_v2 as ep

    assert not hasattr(ep, "SPEAKING_NODES"), (
        "SPEAKING_NODES was dead code listing node_draft_answer — it must be removed"
    )
    assert not hasattr(ep, "CONVERSATIONAL_STREAM_NODES"), (
        "CONVERSATIONAL_STREAM_NODES was dead code listing node_draft_answer — it must be removed"
    )
