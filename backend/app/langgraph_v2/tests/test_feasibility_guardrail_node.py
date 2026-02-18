from __future__ import annotations

from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.nodes_guardrail import (
    feasibility_guardrail_node,
    feasibility_guardrail_router,
)
from app.langgraph_v2.state import SealAIState, TechnicalParameters


def test_guardrail_blocks_api682() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Bitte auslegen nach API 682 für die Dichtung.")],
    )

    patch = feasibility_guardrail_node(state)
    patched = state.model_copy(update=patch, deep=True)

    assert patch.get("awaiting_user_input") is True
    assert patch.get("ask_missing_request") is not None
    assert feasibility_guardrail_router(patched) == "ask_missing"
    assert "HUMAN_REQUIRED" in " ".join((patch["recommendation"].risk_hints or []))


def test_guardrail_blocks_hydrogen() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Wir fahren mit Wasserstoff bei 40 bar.")],
    )

    patch = feasibility_guardrail_node(state)
    patched = state.model_copy(update=patch, deep=True)

    assert patch.get("awaiting_user_input") is True
    assert patch.get("ask_missing_request") is not None
    assert feasibility_guardrail_router(patched) == "ask_missing"
    assert patch.get("flags", {}).get("risk_level") == "critical"


def test_guardrail_sets_critical_when_pv_near_limit() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Bitte fortfahren.")],
        parameters=TechnicalParameters(
            pressure_bar=10.0,
            speed_rpm=3000.0,
            shaft_diameter=70.0,
        ),
    )

    patch = feasibility_guardrail_node(state)

    assert patch.get("awaiting_user_input") is False
    assert patch.get("ask_missing_request") is None
    assert patch.get("flags", {}).get("risk_level") == "critical"
    assert any("PV" in hint for hint in (patch["recommendation"].risk_hints or []))


def test_guardrail_sets_unknown_coverage_for_steam_without_peak_duration_and_routes_to_ask_missing() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Dampf bei 135 C im Prozess, bitte auslegen.")],
        parameters=TechnicalParameters(medium="steam", temperature_C=135.0),
    )

    patch = feasibility_guardrail_node(state)
    patched = state.model_copy(update=patch, deep=True)

    steam = patch.get("guardrail_coverage", {}).get("steam_cip_sip", {})
    assert steam.get("coverage") == "unknown"
    assert steam.get("status") == "hard_block"
    assert patch.get("guardrail_escalation_reason")
    assert patch.get("awaiting_user_input") is True
    assert feasibility_guardrail_router(patched) == "ask_missing"


def test_guardrail_sets_unknown_coverage_for_gas_dp_without_depress_time_and_routes_to_ask_missing() -> None:
    state = SealAIState(
        messages=[HumanMessage(content="Prozessgas mit Delta P 150 bar, bitte weiter.")],
        parameters=TechnicalParameters(medium="gas"),
    )

    patch = feasibility_guardrail_node(state)
    patched = state.model_copy(update=patch, deep=True)

    gas = patch.get("guardrail_coverage", {}).get("gas_decompression", {})
    assert gas.get("coverage") == "unknown"
    assert gas.get("status") == "hard_block"
    assert patch.get("guardrail_escalation_reason")
    assert patch.get("awaiting_user_input") is True
    assert feasibility_guardrail_router(patched) == "ask_missing"


def test_guardrail_questions_capped_to_three() -> None:
    state = SealAIState(
        messages=[
            HumanMessage(
                content=(
                    "API 682, Wasserstoff, H2S, Dampf 130 C, Gas Delta P 200 bar, "
                    "Medium ist nur oil/water."
                )
            )
        ],
        parameters=TechnicalParameters(medium="steam"),
    )

    patch = feasibility_guardrail_node(state)
    questions = patch.get("guardrail_questions") or []
    request = patch.get("ask_missing_request")

    assert isinstance(questions, list)
    assert 1 <= len(questions) <= 3
    assert request is not None
    assert len(getattr(request, "questions", []) or []) <= 3
