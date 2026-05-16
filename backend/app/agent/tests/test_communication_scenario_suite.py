from __future__ import annotations

import pytest

import app.agent.graph.nodes.intake_observe_node as intake_module
import app.agent.graph.nodes.matching_node as matching_node_module
from app.agent.domain.governed_data import GovernedMaterialRecord
from app.agent.graph import GraphState
from app.agent.graph.nodes.assert_node import assert_node
from app.agent.graph.nodes.dispatch_contract_node import dispatch_contract_node
from app.agent.graph.nodes.dispatch_node import dispatch_node
from app.agent.graph.nodes.export_profile_node import export_profile_node
from app.agent.graph.nodes.governance_node import governance_node
from app.agent.graph.nodes.governed_answer_composer_node import governed_answer_composer_node
from app.agent.graph.nodes.matching_node import matching_node
from app.agent.graph.nodes.norm_node import norm_node
from app.agent.graph.nodes.output_contract_node import output_contract_node
from app.agent.graph.nodes.rfq_handover_node import rfq_handover_node
from app.agent.graph.nodes.v92_dossier_node import v92_dossier_node
from app.agent.graph.nodes.v92_engineering_node import v92_engineering_node
from app.agent.graph.nodes.normalize_node import normalize_node
from app.agent.graph.nodes.compute_node import compute_node
from app.agent.graph.output_contract_assembly import _determine_response_class
from app.agent.communication.active_case_resume import reevaluate_active_case_resume
from app.agent.communication.governed_answer_composer import (
    GovernedAnswerComposerInput,
    GovernedAnswerComposerOutput,
)
from app.agent.communication import governed_answer_composer as composer_module
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    ConversationMessage,
    GovernedSessionState,
    GovernanceState,
    RequirementClass,
)


@pytest.fixture(autouse=True)
def _offline_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake_module, "_ENABLE_LLM_EXTRACTION", False)
    monkeypatch.delenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", raising=False)


async def _run_governed_turn(
    state: GraphState | None,
    message: str,
    *,
    turn_index: int = 1,
) -> GraphState:
    base = state or GraphState()
    next_state = base.model_copy(
        update={
            "pending_message": message,
            "conversation_messages": [
                *list(base.conversation_messages or []),
                ConversationMessage(role="user", content=message),
            ],
            "user_turn_index": turn_index,
            "defer_visible_answer_composer": True,
            "output_reply": "",
            "output_response_class": "",
            "output_public": {},
            "output_answer_markdown": "",
            "output_answer_markdown_source": "",
        }
    )
    for node in (
        intake_module.intake_observe_node,
        normalize_node,
        assert_node,
        compute_node,
        v92_engineering_node,
        governance_node,
        output_contract_node,
    ):
        next_state = await node(next_state)
    return next_state


def _persistable(state: GraphState) -> GovernedSessionState:
    return GovernedSessionState.model_validate(state.model_dump(mode="python"))


@pytest.mark.asyncio
async def test_rwdr_pressure_context_answer_is_bound_and_not_asked_again() -> None:
    first = await _run_governed_turn(
        None,
        "salzwasser, 40 grad, 5 bar und eine welle von 40mm und 4000 u/min",
        turn_index=1,
    )

    assert first.pending_question is not None
    assert first.pending_question.target_field == "pressure_bar"
    assert first.pending_question.expected_answer_type == "pressure_context"
    assert "Druck direkt an der Dichtung" in first.pending_question.question_text

    resume_decision = reevaluate_active_case_resume(
        latest_user_message="direkt an der dichtung",
        governed_state=_persistable(first),
        turn_decision=None,
    )
    assert resume_decision.slot_answer_detected is True
    assert resume_decision.detected_slot_field == "pressure_bar"
    assert resume_decision.next_runtime_action == "route_pending_slot_answer"

    second = await _run_governed_turn(
        GraphState.model_validate(first.model_dump(mode="python")),
        "direkt an der dichtung",
        turn_index=2,
    )

    pressure = second.asserted.assertions["pressure_bar"]
    assert pressure.asserted_value == 5.0
    assert pressure.engineering_value.interpretation == "direct_at_seal"
    assert second.last_slot_answer_binding is not None
    assert second.last_slot_answer_binding.target_field == "pressure_bar"
    assert "meinst du damit den Druck direkt" not in second.output_reply
    assert second.pending_question is None or second.pending_question.target_field != "pressure_bar"


class _NonDemoProvider:
    def list_material_records(self) -> list[GovernedMaterialRecord]:
        return [
            GovernedMaterialRecord(
                record_id="registry-ptfe-g25-acme",
                material_family="PTFE",
                grade_name="G25",
                manufacturer_name="Acme Sealing",
                source_name="Governed Registry",
                source_version="v1",
                release_status="active",
                coverage_metadata={
                    "max_temp_c": 260,
                    "max_pressure_bar": 16,
                    "allowed_media": ["steam"],
                    "requirement_class_ids": ["PTFE10"],
                    "supported_seal_types": ["radial_shaft_seal", "rwdr"],
                    "capability_hints": ["steam_service"],
                },
                is_demo_only=False,
            ),
            GovernedMaterialRecord(
                record_id="registry-ptfe-g10-sealtech",
                material_family="PTFE",
                grade_name="G10",
                manufacturer_name="SealTech",
                source_name="Governed Registry",
                source_version="v1",
                release_status="active",
                coverage_metadata={
                    "max_temp_c": 210,
                    "max_pressure_bar": 14,
                    "allowed_media": ["steam"],
                    "requirement_class_ids": ["PTFE10"],
                    "supported_seal_types": ["radial_shaft_seal", "rwdr"],
                    "capability_hints": ["steam_service"],
                },
                is_demo_only=False,
            ),
        ]

    def get_material_record(self, record_id: str) -> GovernedMaterialRecord | None:
        for record in self.list_material_records():
            if record.record_id == record_id:
                return record
        return None

    def list_active_material_records(self) -> list[GovernedMaterialRecord]:
        return self.list_material_records()


def _claim(field: str, value: object, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _matchable_state() -> GraphState:
    return GraphState(
        asserted=AssertedState(
            assertions={
                "medium": _claim("medium", "Dampf"),
                "pressure_bar": _claim("pressure_bar", 12.0),
                "temperature_c": _claim("temperature_c", 180.0),
                "sealing_type": _claim("sealing_type", "rwdr"),
                "material": _claim("material", "PTFE"),
            }
        ),
        governance=GovernanceState(
            gov_class="A",
            rfq_admissible=True,
            requirement_class=RequirementClass(
                class_id="PTFE10",
                description="High-temperature steam application - PTFE sealing class",
            ),
        ),
        defer_visible_answer_composer=True,
    )


@pytest.mark.asyncio
async def test_full_ready_case_reaches_bounded_manufacturer_shortlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        matching_node_module,
        "get_default_domain_data_provider",
        lambda: _NonDemoProvider(),
    )
    state = _matchable_state()
    for node in (
        matching_node,
        rfq_handover_node,
        dispatch_node,
        norm_node,
        export_profile_node,
        dispatch_contract_node,
        v92_dossier_node,
    ):
        state = await node(state)

    assert state.matching.status == "matched_primary_candidate"
    assert state.matching.selected_manufacturer_ref is not None
    assert state.matching.selected_manufacturer_ref.manufacturer_name == "Acme Sealing"
    assert _determine_response_class(state) in {"candidate_shortlist", "inquiry_ready"}
    visible = (
        f"{state.matching.selected_manufacturer_ref.manufacturer_name}\n"
        + "\n".join(state.matching.matching_notes)
    ).casefold()
    assert "acme sealing" in visible
    assert "freigegeben" not in visible
    assert "garantiert" not in visible


@pytest.mark.asyncio
async def test_governed_answers_use_llm_wording_pass_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER", "true")

    async def fake_compose(self: object, request: GovernedAnswerComposerInput) -> GovernedAnswerComposerOutput:
        assert request.deterministic_reply
        return GovernedAnswerComposerOutput(
            answer_markdown=(
                "Ich habe den Fallstand eingeordnet und formuliere daraus eine natuerliche, "
                "technisch vorsichtige Antwort. Welche Mediumdetails sind noch bekannt?"
            ),
            confidence_note=None,
        )

    monkeypatch.setattr(composer_module.GovernedAnswerComposer, "compose", fake_compose)
    state = GraphState(
        output_reply="Welche Mediumdetails sind bekannt?",
        governed_answer_context={
            "latest_user_message": "Dampf bei 180 Grad und 12 bar",
            "response_class": "structured_clarification",
            "next_best_question": "Welche Mediumdetails sind bekannt?",
            "missing_fields": ["medium_qualifiers"],
        },
    )

    result = await governed_answer_composer_node(state)

    assert result.output_answer_markdown_source == "governed_composer"
    assert "natuerliche" in result.output_answer_markdown
