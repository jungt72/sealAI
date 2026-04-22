from __future__ import annotations

from typing import Any, Dict, List

import pytest

pytest.skip('legacy LangGraph v2 tool contracts import removed app.langgraph_v2; migrate to current app.agent service/tool contracts', allow_module_level=True)


def test_set_parameters_returns_working_profile_object() -> None:
    from app.langgraph_v2.state import SealAIState, WorkingProfile
    from app.langgraph_v2.tools.parameter_tools import set_parameters

    state = SealAIState(working_profile=WorkingProfile(medium="öl", temperature_C=60))
    result = set_parameters(temperature_C=80, pressure_bar=5, state=state)  # type: ignore[arg-type]
    assert "working_profile" in result, "set_parameters must return {'working_profile': ...}"
    profile = result["working_profile"]
    assert hasattr(profile, "model_dump"), "working_profile must be a Pydantic model"
    data = profile.model_dump(exclude_none=True)
    assert data.get("temperature_C") == 80
    assert data.get("pressure_bar") == 5
    assert data.get("medium") == "öl"


def test_search_knowledge_base_formats_hits_and_handles_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.langgraph_v2.utils import rag_tool

    def _fake_retrieve(*_args: Any, **_kwargs: Any) -> List[Dict[str, Any]]:
        return [
            {
                "text": "FKM ist temperaturbeständig.",
                "fused_score": 0.9,
                "metadata": {"document_id": "doc1", "section_title": "Werkstoffe", "url": "https://example"},
            }
        ]

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", _fake_retrieve)
    out = rag_tool.search_knowledge_base.invoke(
        {"query": "FKM", "category": "materials", "k": 1, "tenant": "t1"}
    )
    assert "Gefundene Informationen" in out
    assert "doc1" in out

    def _boom(*_args: Any, **_kwargs: Any) -> List[Dict[str, Any]]:
        raise RuntimeError("qdrant down")

    monkeypatch.setattr(rag_tool, "hybrid_retrieve", _boom)
    out2 = rag_tool.search_knowledge_base.invoke(
        {"query": "FKM", "category": "materials", "k": 1, "tenant": "t1"}
    )
    assert "Fehler beim Abrufen" in out2
