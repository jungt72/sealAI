from __future__ import annotations

import hashlib
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage


TEST_DIR = Path(__file__).resolve().parent
LANGGRAPH_V2_DIR = TEST_DIR.parent


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def answer_modules(monkeypatch: pytest.MonkeyPatch):
    sealai_state_mod = _load_module(
        "testmods_sealai_state",
        LANGGRAPH_V2_DIR / "state" / "sealai_state.py",
    )

    state_pkg = types.ModuleType("app.langgraph_v2.state")
    state_pkg.__path__ = []  # type: ignore[attr-defined]
    state_pkg.SealAIState = sealai_state_mod.SealAIState
    state_pkg.AnswerContract = sealai_state_mod.AnswerContract
    monkeypatch.setitem(sys.modules, "app.langgraph_v2.state", state_pkg)
    monkeypatch.setitem(sys.modules, "app.langgraph_v2.state.sealai_state", sealai_state_mod)

    draft_mod = _load_module(
        "testmods_node_draft_answer",
        LANGGRAPH_V2_DIR / "nodes" / "answer_subgraph" / "node_draft_answer.py",
    )
    finalize_mod = _load_module(
        "testmods_node_finalize",
        LANGGRAPH_V2_DIR / "nodes" / "answer_subgraph" / "node_finalize.py",
    )

    return {
        "state": sealai_state_mod,
        "draft": draft_mod,
        "finalize": finalize_mod,
    }


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
async def test_node_draft_answer_streams_chunks_and_forwards_config(answer_modules):
    state_mod = answer_modules["state"]
    draft_mod = answer_modules["draft"]

    contract = state_mod.AnswerContract(
        resolved_parameters={"pressure_bar": 80},
        calc_results={"safety_factor": 1.5},
        selected_fact_ids=["F-1001"],
        required_disclaimers=["Nur innerhalb Spezifikation einsetzen."],
    )
    state = SimpleNamespace(answer_contract=contract, flags={"existing": True})
    fake_llm = _FakeLLM(["Hallo", " Welt"])
    config = {"configurable": {"thread_id": "thread-123"}, "callbacks": ["cb"]}

    with patch.object(draft_mod, "_DRAFT_LLM", fake_llm):
        patch_result = await draft_mod.node_draft_answer(state, config=config)

    expected_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    assert patch_result["draft_text"] == "Hallo Welt"
    assert patch_result["draft_base_hash"] == expected_hash
    assert patch_result["flags"]["answer_contract_hash"] == expected_hash
    assert fake_llm.calls and fake_llm.calls[0]["config"] == config


@pytest.mark.asyncio
async def test_node_draft_answer_hash_is_stable_across_drip_patterns(answer_modules):
    state_mod = answer_modules["state"]
    draft_mod = answer_modules["draft"]
    contract = state_mod.AnswerContract(
        resolved_parameters={"temperature_C": 120, "pressure_bar": 80},
        calc_results={"margin": 12.0},
        selected_fact_ids=["F-2001", "F-2002"],
        required_disclaimers=["Keine Freigabe ohne Endpruefung."],
    )
    expected_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    config = {"configurable": {"run_id": "run-1"}}

    state_a = SimpleNamespace(answer_contract=contract, flags={})
    fake_llm_a = _FakeLLM(["Hal", "lo", " ", "Welt"])
    with patch.object(draft_mod, "_DRAFT_LLM", fake_llm_a):
        patch_a = await draft_mod.node_draft_answer(state_a, config=config)

    state_b = SimpleNamespace(answer_contract=contract, flags={})
    fake_llm_b = _FakeLLM(["Hallo Welt"])
    with patch.object(draft_mod, "_DRAFT_LLM", fake_llm_b):
        patch_b = await draft_mod.node_draft_answer(state_b, config=config)

    assert patch_a["draft_text"] == "Hallo Welt"
    assert patch_b["draft_text"] == "Hallo Welt"
    assert patch_a["draft_base_hash"] == expected_hash
    assert patch_b["draft_base_hash"] == expected_hash
    assert fake_llm_a.calls[0]["config"] == config
    assert fake_llm_b.calls[0]["config"] == config


@pytest.mark.asyncio
async def test_node_draft_answer_short_circuits_on_low_quality_rag(answer_modules):
    state_mod = answer_modules["state"]
    draft_mod = answer_modules["draft"]

    contract = state_mod.AnswerContract(
        resolved_parameters={"pressure_bar": 80},
        calc_results={},
        selected_fact_ids=["F-1001"],
        required_disclaimers=[],
    )
    state = SimpleNamespace(answer_contract=contract, flags={"rag_low_quality_results": True})
    fake_llm = _FakeLLM(["Should not be used"])

    with patch.object(draft_mod, "_DRAFT_LLM", fake_llm):
        patch_result = await draft_mod.node_draft_answer(state, config={"configurable": {"thread_id": "thread-123"}})

    expected_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    assert "keinen exakten Treffer gefunden" in patch_result["draft_text"]
    assert patch_result["final_answer"] == patch_result["draft_text"]
    assert patch_result["draft_base_hash"] == expected_hash
    assert patch_result["flags"]["rag_low_quality_results"] is True
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_node_draft_answer_short_circuits_on_empty_contract(answer_modules):
    state_mod = answer_modules["state"]
    draft_mod = answer_modules["draft"]

    contract = state_mod.AnswerContract(
        resolved_parameters={},
        calc_results={},
        selected_fact_ids=[],
        required_disclaimers=[],
    )
    state = SimpleNamespace(answer_contract=contract, flags={"rag_low_quality_results": False})
    fake_llm = _FakeLLM(["Should not be used"])

    with patch.object(draft_mod, "_DRAFT_LLM", fake_llm):
        patch_result = await draft_mod.node_draft_answer(state, config={"configurable": {"thread_id": "thread-123"}})

    expected_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    assert "keinen exakten Treffer gefunden" in patch_result["draft_text"]
    assert patch_result["final_answer"] == patch_result["draft_text"]
    assert patch_result["draft_base_hash"] == expected_hash
    assert patch_result["flags"]["rag_low_quality_results"] is False
    assert fake_llm.calls == []


def test_node_finalize_appends_ai_message_without_dropping_history(answer_modules):
    finalize_mod = answer_modules["finalize"]
    history = [HumanMessage(content="Welche Dichtung passt bei 80 bar?")]
    state = SimpleNamespace(
        draft_text="Empfehlung: PTFE bei 80 bar.",
        final_text="Empfehlung: PTFE bei 80 bar.",
        final_answer="",
        messages=history,
        phase="consulting",
    )

    patch_result = finalize_mod.node_finalize(state)
    messages = patch_result["messages"]

    assert len(messages) == 2
    assert messages[0] is history[0]
    assert isinstance(messages[1], AIMessage)
    assert messages[1].content == "Empfehlung: PTFE bei 80 bar."
    assert patch_result["final_text"] == "Empfehlung: PTFE bei 80 bar."
    assert patch_result["final_answer"] == "Empfehlung: PTFE bei 80 bar."
