"""Regression tests for robust message parsing in extraction nodes."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app._legacy_v2.state import SealAIState
from app.services.rag.nodes.p1_context import _P1Extraction, _invoke_extraction
from app.services.rag.nodes.p4a_extract import node_p4a_extract
from app.services.rag.state import WorkingProfile


def test_p1_invoke_sanitizes_raw_dict_history_before_llm_call() -> None:
    captured: dict[str, object] = {}

    class _FakeStructured:
        def invoke(self, messages):
            captured["messages"] = messages
            return _P1Extraction(pressure_max_bar=40.0, temperature_max_c=180.0)

    class _FakeLLM:
        def with_structured_output(self, *_args, **_kwargs):
            return _FakeStructured()

    raw_history = [
        {"type": "ai", "content": [{"type": "text", "text": "Bitte gib den Druck an."}]},
        {"type": "human", "content": [{"type": "text", "text": "40 bar und 180 C"}]},
    ]

    with patch("app.services.rag.nodes.p1_context.ChatOpenAI", return_value=_FakeLLM()):
        extracted = _invoke_extraction("40 bar und 180 C", raw_history)

    assert extracted.pressure_max_bar == 40.0
    assert extracted.temperature_max_c == 180.0

    messages = captured["messages"]
    assert isinstance(messages, list)
    assert isinstance(messages[0], SystemMessage)
    assert all(not isinstance(msg, dict) for msg in messages)
    assert any(isinstance(msg, HumanMessage) for msg in messages)
    assert any(isinstance(msg, AIMessage) for msg in messages)
    assert all(isinstance(getattr(msg, "content", None), str) for msg in messages)


def test_p4a_skip_path_still_carries_mapped_params_in_extracted_params() -> None:
    state = SealAIState(
        messages=[{"type": "human", "content": [{"type": "text", "text": "40 bar 180 C Dampf"}]}],
        working_profile=WorkingProfile(
            pressure_max_bar=40.0,
            temperature_max_c=180.0,
            medium="Dampf",
        ),
        recommendation_ready=False,
        gap_report={"recommendation_ready": False},
        extracted_params={},
    )

    result = node_p4a_extract(state)
    merged = result["working_profile"]["extracted_params"]

    assert merged["pressure_max_bar"] == 40.0
    assert merged["temperature_max_c"] == 180.0
    assert merged["medium"] == "Dampf"
