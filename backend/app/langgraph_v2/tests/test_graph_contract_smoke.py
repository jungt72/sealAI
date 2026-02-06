from __future__ import annotations

"""Offline smoke tests for the v2 graph state contract.

These tests intentionally avoid DB/network/LLM execution and validate only
deterministic node/contract behavior:
- mode routing into knowledge/advisory/engineering flows
- SSE `state_update` contract keys and audit-trace capping (50 events)
- intake round behavior (open-first, then close-gaps)
- supervisor calc loop-guard (`calc_input_signature` + `calc_done`)
"""

from typing import Any, Dict

from langchain_core.messages import HumanMessage

from app.api.v1.endpoints.langgraph_v2 import _build_state_update_payload
from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.nodes.nodes_discovery import confirm_gate_node
from app.langgraph_v2.nodes.nodes_flows import calculator_node
from app.langgraph_v2.nodes.nodes_supervisor import (
    ACTION_FINALIZE,
    ACTION_RUN_PANEL_CALC,
    supervisor_policy_node,
)
from app.langgraph_v2.sealai_graph_v2 import (
    advisory_entry_node,
    engineering_entry_node,
    knowledge_entry_node,
    mode_flow_router,
    mode_router_node,
)
from app.langgraph_v2.state import (
    CalcResults,
    CaseSheet,
    RangeValue,
    SealAIState,
    TechnicalParameters,
    TraceEvent,
)


class DummyGraph:
    """Offline contract harness for mode-routing smoke tests."""

    @staticmethod
    def _apply_patch(state: SealAIState, patch: Dict[str, Any]) -> SealAIState:
        return state.model_copy(update=patch, deep=True)

    def invoke(self, user_text: str, **overrides: Any) -> SealAIState:
        state = SealAIState.model_validate(
            {
                "messages": [HumanMessage(content=user_text)],
                **overrides,
            }
        )

        state = self._apply_patch(state, mode_router_node(state))
        route = mode_flow_router(state)

        if route == "knowledge":
            state = self._apply_patch(state, knowledge_entry_node(state))
            return state

        if route == "advisory":
            state = self._apply_patch(state, advisory_entry_node(state))
            return self._apply_patch(
                state,
                {
                    "ask_missing_scope": "technical",
                    "awaiting_user_input": True,
                    "ask_missing_request": AskMissingRequest(
                        intro_text="Für eine belastbare Materialauswahl brauche ich noch Eckdaten.",
                        questions=["Welches Medium liegt an?"],
                    ),
                    "last_node": "advisory_intake_node",
                },
            )

        if route == "engineering":
            state = self._apply_patch(state, engineering_entry_node(state))
            return self._apply_patch(state, calculator_node(state))

        return state


def test_graph_contract_smoke_knowledge_mode_routes_to_knowledge_entry() -> None:
    graph = DummyGraph()
    state = graph.invoke("Wie unterscheiden sich O-Ring und Stangendichtung im Einsatz?")

    assert state.mode == "knowledge"
    assert state.last_node == "knowledge_entry_node"


def test_graph_contract_smoke_advisory_mode_triggers_intake_or_material_reasoning() -> None:
    graph = DummyGraph()
    state = graph.invoke("Welches Material ist für Heißdampf geeignet?")

    assert state.mode == "advisory"
    assert (state.ask_missing_request is not None) or bool((state.plan or {}).get("material_reasoning"))


def test_graph_contract_smoke_engineering_mode_calculates_surface_speed() -> None:
    graph = DummyGraph()
    state = graph.invoke(
        "Bitte berechne die Umfangsgeschwindigkeit.",
        case_sheet=CaseSheet(
            rpm=RangeValue(unit="rpm", nom=3000.0, source="user_text"),
            pressure=RangeValue(unit="bar", nom=25.0, source="user_text"),
            temperature=RangeValue(unit="C", nom=180.0, source="user_text"),
            geometry={"diameter_mm": 50.0},
        ),
        parameters=TechnicalParameters(),
    )

    assert state.mode == "engineering"
    assert state.calc_results is not None
    assert "surface_speed_m_per_min" in (state.calc_results.outputs or {})


def test_graph_contract_smoke_sse_state_update_payload_contract_and_trace_cap() -> None:
    trace = [
        TraceEvent(ts=float(idx), type="decision", node=f"node_{idx}", data={"idx": idx})
        for idx in range(60)
    ]
    state = SealAIState(
        mode="engineering",
        assumption_mode=True,
        intake_round=2,
        case_sheet=CaseSheet(
            rpm=RangeValue(unit="rpm", nom=3000.0, source="user_text"),
            pressure=RangeValue(unit="bar", nom=25.0, source="user_text"),
            temperature=RangeValue(unit="C", nom=180.0, source="user_text"),
            geometry={"diameter_mm": 50.0},
        ),
        calc_results_ok=True,
        calc_results=CalcResults(outputs={"surface_speed_m_per_min": 471.23889803846896}),
        audit_trace=trace,
    )

    payload = _build_state_update_payload(state)

    assert payload["mode"] == "engineering"
    assert payload["assumption_mode"] is True
    assert payload["intake_round"] == 2
    assert "case_sheet" in payload
    assert payload["calc_results_ok"] is True
    assert "calc_results" in payload
    assert "audit_trace" in payload
    assert isinstance(payload["audit_trace"], list)
    assert len(payload["audit_trace"]) == 50
    assert payload["audit_trace"][0]["data"]["idx"] == 10
    assert payload["audit_trace"][-1]["data"]["idx"] == 59


def _extract_question(patch: Dict[str, Any]) -> str:
    """
    Normalizes ask-missing output across dict/model variants.
    Prefer `question`, fallback to first element of `questions`.
    """
    request = patch.get("ask_missing_request")
    if request is None:
        return ""

    # dict-like payload
    if isinstance(request, dict):
        value = request.get("question")
        if value:
            return str(value)
        questions = request.get("questions")
        if isinstance(questions, list) and questions:
            return str(questions[0])
        return ""

    # pydantic model instance
    if hasattr(request, "model_dump"):
        dumped = request.model_dump()
        value = dumped.get("question")
        if value:
            return str(value)
        questions = dumped.get("questions")
        if isinstance(questions, list) and questions:
            return str(questions[0])
        return ""

    # attribute fallback
    value = getattr(request, "question", None)
    if value:
        return str(value)
    questions = getattr(request, "questions", None)
    if isinstance(questions, list) and questions:
        return str(questions[0])

    return ""


def test_graph_contract_smoke_advisory_intake_rounds_open_first_then_close_gaps() -> None:
    initial = SealAIState(mode="advisory", intake_round=0, parameters=TechnicalParameters())

    round0_patch = confirm_gate_node(initial)
    round0_question = _extract_question(round0_patch).lower()
    assert round0_patch.get("ask_missing_request") is not None
    assert round0_patch.get("intake_round") == 1
    assert "damit ich passend empfehlen kann" in round0_question

    round1_state = initial.model_copy(update=round0_patch, deep=True)
    round1_patch = confirm_gate_node(round1_state)
    round1_question = _extract_question(round1_patch).lower()
    assert round1_patch.get("ask_missing_request") is not None
    assert round1_patch.get("intake_round") == 2
    assert "ich schließe jetzt die fehlenden angaben" in round1_question


def test_graph_contract_smoke_supervisor_calc_guard_finalizes_when_input_unchanged() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Bitte berechne die Umfangsgeschwindigkeit.")],
        last_node="calculator_node",
        calc_done=True,
        calc_input_signature="Bitte berechne die Umfangsgeschwindigkeit.",
    )

    patch = supervisor_policy_node(state)

    assert patch["next_action"] != ACTION_RUN_PANEL_CALC
    assert patch["next_action"] in {ACTION_FINALIZE, "FINALIZE"}
    assert "calc_already_done_no_new_input" in str(patch.get("next_action_reason", ""))
