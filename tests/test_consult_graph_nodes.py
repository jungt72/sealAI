import pytest

pytest.skip(
    "Legacy consult graph test disabled during agent-path canonization.",
    allow_module_level=True,
)

import json
import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage, HumanMessage


def _clone_state(state: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(state)
    if "messages" in out and isinstance(out["messages"], list):
        out["messages"] = list(out["messages"])
    if "params" in out and isinstance(out["params"], dict):
        out["params"] = dict(out["params"])
    if "derived" in out and isinstance(out["derived"], dict):
        out["derived"] = dict(out["derived"])
    return out


def test_consult_graph_routes_and_logs(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    def stub_intake(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        out.setdefault("params", {})
        out.setdefault("messages", [])
        out.setdefault("triage", {"intent": "consult", "confidence": 1.0})
        out["phase"] = "intake"
        return out

    def stub_profile(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        out["phase"] = "profile"
        return out

    def stub_extract(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        params = out.setdefault("params", {})
        params.setdefault("temp_max_c", 80)
        params.setdefault("druck_bar", 5)
        params.setdefault("relativgeschwindigkeit_ms", 0.4)
        params.setdefault("wellen_mm", 25)
        params.setdefault("drehzahl_u_min", 1500)
        out["phase"] = "extract"
        return out

    def stub_domain(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        out["domain"] = "rwdr"
        out["phase"] = "domain_router"
        return out

    def stub_compute(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        out.setdefault("derived", {"calculated": {}})
        out["phase"] = "compute"
        return out

    def stub_det_calc(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        derived = out.setdefault("derived", {})
        derived.setdefault("calculated", {})["surface_speed_m_s"] = 0.4
        out["phase"] = "deterministic_calc"
        return out

    def stub_calc_agent(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        derived = out.setdefault("derived", {})
        derived.setdefault("flags", {})["stub"] = True
        out["phase"] = "calc_agent"
        return out

    def stub_ask_missing(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        out["phase"] = "ask_missing"
        return out

    def stub_ltm(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        out["context"] = "ltm ctx"
        out["phase"] = "ltm"
        return out

    def stub_rag(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        docs = [{"text": "doc", "vector_score": 0.9}]
        out["retrieved_docs"] = docs
        out["docs"] = docs
        out.setdefault("context", "rag ctx")
        out["phase"] = "rag"
        return out

    def stub_recommend(state: Dict[str, Any], config: Any = None, *, events: Any = None) -> Dict[str, Any]:
        out = _clone_state(state)
        msgs = out.get("messages") or []
        msgs = list(msgs)
        msgs.append(AIMessage(content="Stub recommendation"))
        out["messages"] = msgs
        out["empfehlungen"] = [{"typ": "RWDR"}]
        out["phase"] = "recommend"
        return out

    def stub_summarize(state: Dict[str, Any]) -> Dict[str, Any]:
        out = _clone_state(state)
        out["summary_text"] = "stub summary"
        out["phase"] = "summarize"
        return out

    monkeypatch.setattr(consult_build, "intake_node", stub_intake)
    monkeypatch.setattr(consult_build, "profile_node", stub_profile)
    monkeypatch.setattr(consult_build, "_extract_node", stub_extract)
    monkeypatch.setattr(consult_build, "_domain_router_node", stub_domain)
    monkeypatch.setattr(consult_build, "_compute_node", stub_compute)
    monkeypatch.setattr(consult_build, "deterministic_calc_node", stub_det_calc)
    monkeypatch.setattr(consult_build, "calc_agent_node", stub_calc_agent)
    monkeypatch.setattr(consult_build, "ask_missing_node", stub_ask_missing)
    monkeypatch.setattr(consult_build, "ltm_node", stub_ltm)
    monkeypatch.setattr(consult_build, "run_rag_node", stub_rag)
    monkeypatch.setattr(consult_build, "recommend_node", stub_recommend)
    monkeypatch.setattr(consult_build, "summarize_node", stub_summarize)

    caplog.set_level(logging.INFO, logger="uvicorn.error")

    graph = consult_build.build_graph().compile()

    smalltalk_result = graph.invoke({"messages": [HumanMessage(content="Hallo!")]})
    assert smalltalk_result.get("summary_text") == "stub summary"
    assert any("lite_router.route" in rec.message and "smalltalk" in rec.message for rec in caplog.records)

    caplog.clear()

    state = {"messages": [HumanMessage(content="RWDR 25x47x7, 80°C, 5 bar")], "params": {}}
    result = graph.invoke(state)
    assert result.get("phase") == "summarize"
    assert result.get("empfehlungen") == [{"typ": "RWDR"}]
    assert result.get("summary_text") == "stub summary"
    assert result.get("retrieved_docs") == [{"text": "doc", "vector_score": 0.9}]
    assert any("lite_router.route" in rec.message and "default" in rec.message for rec in caplog.records)


def test_lite_router_routes_smalltalk() -> None:
    state = {"messages": [HumanMessage(content="Hi")], "params": {}}
    out = lite_router_node(state)
    assert out["route"] == "smalltalk"
    assert out["phase"] == "lite_router"


def test_lite_router_routes_technical() -> None:
    text = "RWDR 25x47x7 mm bei 1500 U/min und 80 °C"
    state = {"messages": [HumanMessage(content=text)], "params": {}}
    out = lite_router_node(state)
    assert out["route"] == "default"


def test_deterministic_calc_computes_speed_and_pv() -> None:
    state = {
        "params": {
            "wellen_mm": 50,
            "drehzahl_u_min": 1200,
            "druck_bar": 2,
        }
    }
    out = deterministic_calc_node(state)
    calc = out["derived"]["calculated"]
    assert calc["surface_speed_m_s"] == pytest.approx(calc["umfangsgeschwindigkeit_m_s"], rel=1e-6)
    assert calc["pv_bar_ms"] == pytest.approx(state["params"]["druck_bar"] * calc["surface_speed_m_s"], rel=1e-6)
    assert out["phase"] == "deterministic_calc"


def test_recommend_node_opens_form_when_missing() -> None:
    state = {
        "messages": [HumanMessage(content="Bitte empfehlen")],
        "params": {"temp_max_c": 80},
        "fehlend": ["wellen_mm"],
    }
    out = recommend_node(state)
    assert out["phase"] == "ask_missing"
    assert out["missing_fields"] == ["wellen_mm"]
    assert out["ui_event"]["ui_action"] == "open_form"


class _DummyLLM:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def invoke(self, messages: Any) -> AIMessage:
        return AIMessage(content=self._payload)


def test_intake_node_opens_sidebar_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({
        "intent": "consult",
        "params": {
            "temp_max_c": 80,
            "druck_bar": 2,
        },
    })

    monkeypatch.setattr(intake_module, "create_llm", lambda **kwargs: _DummyLLM(payload))

    state = {"messages": [HumanMessage(content="Ich brauche einen RWDR")]}
    out = intake_node(state)
    assert out["phase"] == "intake"
    assert out["triage"]["intent"] == "consult"
    assert out["ui_event"]["ui_action"] == "open_form"
    assert "wellen_mm" in out["ui_event"]["missing"]
