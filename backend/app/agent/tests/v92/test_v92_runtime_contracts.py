from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.api.governed_runtime import run_governed_graph_turn
from app.agent.graph import GraphState
from app.agent.state.models import GovernedSessionState
from app.agent.state.projections import project_for_ui
from app.agent.v92.contracts import FinalAnswerContext, NonTechnicalAnswerContext, TurnEnvelope
from app.agent.v92.final_guard import validate_final_output
from app.agent.v92.runtime_contract import (
    apply_v92_contracts_to_payload,
    build_final_answer_context,
    build_turn_envelope,
)
from app.agent.v92.dashboard_contract import build_v92_dashboard_contract
from app.services.auth.dependencies import RequestUser


def _request_user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="user-1",
        sub="user-1",
        roles=["user"],
        scopes=[],
        tenant_id="tenant-1",
    )


def test_turn_envelope_rejects_direct_streaming_for_technical_turn() -> None:
    with pytest.raises(ValueError):
        TurnEnvelope(
            turn_id="turn-1",
            session_id="case-1",
            case_id="case-1",
            user_message="Empfiehl mir EPDM",
            route="engineering_recommendation",
            intent="engineering_recommendation",
            is_technical=True,
            state_mutation_policy="case_revision_allowed",
            requires_engine=True,
            requires_evidence=True,
            requires_adversarial_review=True,
            requires_final_guard=True,
            streaming_policy="direct_stream_allowed",
            created_at="2026-05-18T00:00:00+00:00",
            trace_id="trace-1",
        )


def test_final_guard_blocks_unscoped_material_suitability_claim() -> None:
    state = GovernedSessionState()
    envelope = build_turn_envelope(
        session_id="case-1",
        user_message="Ist EPDM geeignet?",
        route="engineering_recommendation",
        state=state,
    )
    dashboard = build_v92_dashboard_contract(
        state,
        turn_id=envelope.turn_id,
        route="engineering_recommendation",
        case_id="case-1",
    )
    context = build_final_answer_context(
        envelope=envelope,
        state=state,
        dashboard_projection=dashboard.model_dump(mode="json"),
    )

    result = validate_final_output("EPDM ist geeignet.", context=context)

    assert result.decision == "block"
    assert result.final_stream_allowed is False
    assert "suitability_without_scope" in result.detected_forbidden_claims


def test_final_guard_blocks_compound_or_product_claim_without_evidence_layer() -> None:
    context = FinalAnswerContext(
        turn_id="turn-1",
        case_id="case-1",
        case_revision=1,
        route="engineering_recommendation",
        intent="engineering_recommendation",
        is_technical=True,
        user_message="Kann ich das Produkt nehmen?",
        allowed_claim_level="L3_deterministic_calculation",
    )

    result = validate_final_output("Das Produkt ist geeignet.", context=context)

    assert result.decision == "block"
    assert "compound_or_product_claim_without_evidence_layer" in result.detected_forbidden_claims
    assert result.evidence_failures


def test_final_guard_blocks_norm_conformity_when_standards_have_gaps() -> None:
    context = FinalAnswerContext(
        turn_id="turn-1",
        case_id="case-1",
        case_revision=1,
        route="standards_or_compliance",
        intent="standards_or_compliance",
        is_technical=True,
        user_message="Ist das normkonform?",
        standards_summary={"blocking_gaps": ["norm_din_3760_iso_6194:seal_width_mm"]},
        allowed_claim_level="L3_deterministic_calculation",
    )

    result = validate_final_output("Die Auslegung ist normkonform.", context=context)

    assert result.decision == "block"
    assert "standards_guard_failed" in result.blocked_reasons
    assert result.final_stream_allowed is False


def test_final_guard_revises_stale_calculation_usage() -> None:
    context = FinalAnswerContext(
        turn_id="turn-1",
        case_id="case-1",
        case_revision=2,
        route="engineering_recommendation",
        intent="engineering_recommendation",
        is_technical=True,
        user_message="Was ergibt die Berechnung?",
        calculation_results=[
            {
                "calculation_id": "rwdr.surface_speed",
                "status": "stale",
                "validity_status": "stale",
            }
        ],
        stale_items=[{"item_id": "rwdr.surface_speed", "kind": "calculation", "status": "stale"}],
    )

    result = validate_final_output("Die Berechnung ergibt aktuell 7,85 m/s.", context=context)

    assert result.decision == "revise"
    assert result.stale_failures
    assert "do_not_use_stale_calculation_as_current_basis" in result.required_revisions


def test_final_guard_revises_material_counterindication_guardrail_violation() -> None:
    context = FinalAnswerContext(
        turn_id="turn-1",
        case_id="case-1",
        case_revision=2,
        route="engineering_recommendation",
        intent="engineering_recommendation",
        is_technical=True,
        user_message="Kann ich EPDM in HLP nutzen?",
        calculation_results=[
            {
                "calculation_id": "material.chemical_resistance_screening",
                "status": "warning",
                "validity_status": "requires_expert_review",
                "guardrail_violations": ["counterindication_rating_c"],
            }
        ],
    )

    result = validate_final_output("EPDM nur als Prüfhypothese behandeln.", context=context)

    assert result.decision == "revise"
    assert result.calculation_failures[0]["guardrail_violations"] == ["counterindication_rating_c"]


def test_final_guard_allows_nontechnical_smalltalk_without_engine_context() -> None:
    context = NonTechnicalAnswerContext(
        turn_id="turn-1",
        route="smalltalk",
        intent="smalltalk",
        user_message="Danke",
        answer_scope="smalltalk",
        state_mutation_policy="none",
    )

    result = validate_final_output("Gern.", context=context)

    assert result.decision == "pass"
    assert result.final_stream_allowed is True


def test_apply_v92_contracts_revises_material_family_claim_before_payload_leaves() -> None:
    payload = {
        "reply": "EPDM ist geeignet.",
        "answer_markdown": "EPDM ist geeignet.",
        "response_class": "technical_preselection",
        "run_meta": {"answer_trace": {"answer_mode": "engineering_recommendation"}},
        "ui": {},
    }

    result = apply_v92_contracts_to_payload(
        payload,
        session_id="case-1",
        user_message="Kann ich EPDM nehmen?",
        state=GovernedSessionState(),
        route_hint="engineering_recommendation",
        case_id="case-1",
    )

    assert result["turn_envelope"]["requires_final_guard"] is True
    assert result["final_answer_context"]["is_technical"] is True
    assert "ist geeignet" not in result["answer_markdown"].casefold()
    assert result["final_guard_result"]["final_stream_allowed"] is True
    assert result["v92_dashboard"]["schema_version"] == "v92_dashboard_contract_1"
    assert result["run_meta"]["v92"]["adversarial_review_source"] == "deterministic"
    assert result["run_meta"]["v92"]["adversarial_review_decision"] == "revise"
    assert result["run_meta"]["v92"]["revision_applied"] is True
    assert result["run_meta"]["v92"]["guarded_fallback_used"] is False


def test_project_for_ui_exposes_legacy_v92_tile() -> None:
    ui = project_for_ui(GovernedSessionState()).model_dump(mode="json")

    assert ui["v92"]["seal_system"]["seal_type"] == "unknown_seal"
    assert ui["v92"]["dossier"]["no_final_technical_release"] is True


@pytest.mark.asyncio
async def test_governed_runtime_never_enables_visible_composer_streaming() -> None:
    class FakeGraph:
        graph_input: GraphState | None = None

        async def astream(self, graph_input, *, config, stream_mode):  # noqa: ANN001
            self.graph_input = graph_input
            yield ("values", GraphState(output_reply="Bitte Medium angeben."))

    fake_graph = FakeGraph()

    with (
        patch(
            "app.agent.api.governed_runtime._load_live_governed_state",
            AsyncMock(return_value=GovernedSessionState()),
        ),
        patch(
            "app.agent.api.governed_runtime.get_governed_graph",
            AsyncMock(return_value=fake_graph),
        ),
        patch(
            "app.agent.api.governed_runtime._update_governed_state_post_graph",
            AsyncMock(return_value=GovernedSessionState()),
        ),
        patch("app.agent.api.governed_runtime.emit_quality_trace"),
    ):
        await run_governed_graph_turn(
            request=SimpleNamespace(session_id="case-1", message="Technische Empfehlung?"),
            current_user=_request_user(),
            collect_progress=True,
        )

    assert fake_graph.graph_input is not None
    assert fake_graph.graph_input.stream_visible_answer_composer is False
