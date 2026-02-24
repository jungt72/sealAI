from __future__ import annotations

from typing import Iterable

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Send

import app.langgraph_v2.nodes.nodes_frontdoor as nodes_frontdoor
from app.langgraph_v2.nodes.nodes_frontdoor import frontdoor_discovery_node
from app.langgraph_v2.nodes.nodes_supervisor import supervisor_policy_node
from app.langgraph_v2.nodes.reducer import reducer_node
from app.langgraph_v2.sealai_graph_v2 import (
    _frontdoor_router,
    _reducer_router,
    create_sealai_graph_v2,
)
from app.langgraph_v2.state import SealAIIntentOutput, SealAIState


def _build_graph():
    return create_sealai_graph_v2(checkpointer=MemorySaver(), store=InMemoryStore())


def _apply_patch(state: SealAIState, patch: dict) -> SealAIState:
    return state.model_copy(update=patch, deep=True)


def _send_nodes(goto_value: object) -> set[str]:
    if isinstance(goto_value, Send):
        return {goto_value.node}
    if isinstance(goto_value, Iterable) and not isinstance(goto_value, (str, bytes, dict)):
        return {
            item.node
            for item in goto_value
            if isinstance(item, Send) and isinstance(getattr(item, "node", None), str)
        }
    return set()


def _fake_structured(
    *,
    intent_category: str,
    is_safety_critical: bool,
    requires_rag: bool,
    needs_pricing: bool,
    reasoning: str,
):
    def _inner(_state: SealAIState, _user_text: str) -> SealAIIntentOutput:
        return SealAIIntentOutput(
            intent_category=intent_category,
            is_safety_critical=is_safety_critical,
            requires_rag=requires_rag,
            needs_pricing=needs_pricing,
            reasoning=reasoning,
        )

    return _inner


@pytest.mark.parametrize(
    "query,expected_severity",
    [
        ("Wir brauchen eine Dichtung für 150 bar Wasserstoff", 4),
        ("O2 Pipeline bei 200°C", 4),
        ("H2-Kompressor mit 180 bar braucht neue Dichtung", 4),
        (
            "Wir planen einen Radialwellendichtring für einen Wasserstoff-Kompressor. Die Welle dreht mit 5000 U/min, der Systemdruck liegt bei 5 bar.",
            4,
        ),
        ("Brauchen einen RWDR zur Abdichtung einer Welle für flüssigen Wasserstoff (LH2) bei -253°C.", 4),
        ("Radialwellendichtring für eine H2-Turbine, 15 bar Systemdruck, Einsatz im absoluten Trockenlauf.", 4),
        ("RWDR für eine Sauerstoffpumpe, 100% reines O2, 20 bar, FKM-Lippe mit Standard-Montagefett.", 4),
        ("Benötigen einen Wellendichtring für flüssigen Sauerstoff (LOX) bei 3000 U/min.", 4),
        (
            "Ich brauche einen Standard-RWDR Form A aus NBR für eine Hydraulikpumpe mit 150 bar dynamischem Druck.",
            4,
        ),
        ("Wellendichtring für einen Hochdruck-Autoklaven, 50 bar, 150°C, Welle dreht mit 500 U/min.", 4),
        ("PTFE-Manschette als Wellendichtung für 200 bar, Welle 40mm, 1500 U/min.", 4),
        ("Suche einen RWDR für eine Rührwelle, die direkt in 98%iger Schwefelsäure (H2SO4) läuft.", 4),
        ("Wellendichtring für Flusssäure (HF) bei 80°C, Welledurchmesser 50mm.", 4),
        ("Abdichtung einer rotierenden Welle in reinem Chlorgas, 2500 U/min.", 4),
        ("PTFE Radialwellendichtring für eine Anlage mit Phosgengas.", 4),
        ("RWDR für einen Ammoniak-Verdichter, 25 bar, 120°C.", 4),
        (
            "Brauche einen FKM Wellendichtring für eine Werkzeugspindel, die mit 45.000 U/min dreht (Welle 40mm).",
            4,
        ),
        ("RWDR NBR für ein 180°C heißes Thermalölbad, Welle dreht mit 3000 U/min.", 4),
        ("Wir bauen einen Mischer für Raketentreibstoff (Hydrazin), RWDR mit Staublippe benötigt.", 4),
        (
            "Wellendichtring für eine Zentrifuge in der Nukleartechnik, rotierendes System im radioaktiven Kühlwasser, 10 bar.",
            4,
        ),
    ],
)
def test_golden_set_safety_critical(monkeypatch, query: str, expected_severity: int) -> None:
    graph = _build_graph()
    assert "human_review_node" in set(graph.interrupt_before_nodes)

    monkeypatch.setattr(
        nodes_frontdoor,
        "_invoke_frontdoor_structured",
        _fake_structured(
            intent_category="ENGINEERING_CALCULATION",
            is_safety_critical=True,
            requires_rag=False,
            needs_pricing=False,
            reasoning="Safety-critical engineering request.",
        ),
    )

    state = SealAIState(messages=[HumanMessage(content=query)])
    frontdoor_patch = frontdoor_discovery_node(state)
    state_after_frontdoor = _apply_patch(state, frontdoor_patch)

    command = supervisor_policy_node(state_after_frontdoor)
    send_nodes = _send_nodes(command.goto)
    assert "safety_agent" in send_nodes

    reducer_patch = reducer_node(
        state_after_frontdoor,
        results=[
            {
                "last_node": "safety_agent",
                "safety_review": {
                    "severity": expected_severity,
                    "code": "SAFETY_CRITICAL_H2_APPLICATION",
                },
            }
        ],
    )
    state_after_reducer = _apply_patch(state_after_frontdoor, reducer_patch)

    assert state_after_reducer.requires_human_review is True
    assert _reducer_router(state_after_reducer) == "human_review"


@pytest.mark.parametrize(
    "query",
    [
        "Wie wird das Wetter morgen?",
        "Schreibe ein Gedicht über den Mond.",
        "Erzähl mir einen Witz.",
    ],
)
def test_golden_set_chit_chat(monkeypatch, query: str) -> None:
    graph = _build_graph()
    node_ids = set(graph.get_graph().nodes.keys())
    assert "smalltalk_node" in node_ids

    monkeypatch.setattr(
        nodes_frontdoor,
        "_invoke_frontdoor_structured",
        _fake_structured(
            intent_category="CHIT_CHAT",
            is_safety_critical=False,
            requires_rag=False,
            needs_pricing=False,
            reasoning="Non-technical social chat.",
        ),
    )

    state = SealAIState(messages=[HumanMessage(content=query)])
    frontdoor_patch = frontdoor_discovery_node(state)
    state_after_frontdoor = _apply_patch(state, frontdoor_patch)

    assert state_after_frontdoor.flags.get("frontdoor_intent_category") in {"CHIT_CHAT", "OUT_OF_SCOPE"}
    assert state_after_frontdoor.intent is not None
    assert state_after_frontdoor.intent.goal in {"smalltalk", "out_of_scope"}
    assert state_after_frontdoor.flags.get("frontdoor_bypass_supervisor") is True
    assert _frontdoor_router(state_after_frontdoor) == "smalltalk"


@pytest.mark.parametrize(
    "query",
    [
        "Gibt es Datenblätter zu EPDM 70?",
        "Ich brauche technische Infos zum FKM Datenblatt.",
    ],
)
def test_golden_set_retrieval(monkeypatch, query: str) -> None:
    graph = _build_graph()
    node_ids = set(graph.get_graph().nodes.keys())
    assert "material_agent" in node_ids
    assert "reducer_node" in node_ids

    monkeypatch.setattr(
        nodes_frontdoor,
        "_invoke_frontdoor_structured",
        _fake_structured(
            intent_category="MATERIAL_RESEARCH",
            is_safety_critical=False,
            requires_rag=True,
            needs_pricing=False,
            reasoning="Material research requires technical sources.",
        ),
    )

    state = SealAIState(messages=[HumanMessage(content=query)])
    frontdoor_patch = frontdoor_discovery_node(state)
    state_after_frontdoor = _apply_patch(state, frontdoor_patch)

    assert state_after_frontdoor.requires_rag is True

    command = supervisor_policy_node(state_after_frontdoor)
    send_nodes = _send_nodes(command.goto)

    assert command.update.get("next_action") == "MAP_REDUCE_PARALLEL"
    assert command.update.get("requires_rag") is True
    assert "material_agent" in send_nodes
