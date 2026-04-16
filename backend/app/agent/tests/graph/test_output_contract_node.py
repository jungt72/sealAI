"""
Tests for graph/nodes/output_contract_node.py — Phase F-C.1

Key invariants under test:
    1. Response class is derived deterministically from GovernanceState.
    2. No LLM call under any input.
    3. Invariant 8: output_public contains no raw internal state objects.
    4. output_public always has required top-level keys.
    5. output_reply is always a non-empty string.

Coverage:
    1.  gov_class None (empty) → structured_clarification
    2.  gov_class D → structured_clarification
    3.  gov_class C → structured_clarification
    4.  gov_class B → structured_clarification
    5.  gov_class A + no compute → governed_state_update
    6.  gov_class A + compute → technical_preselection
    7.  output_public["response_class"] matches output_response_class
    8.  output_public has required keys (Invariant 8 shape)
    9.  output_public["parameters"] contains asserted field values
    10. output_public["missing_fields"] = blocking_unknowns
    11. output_public["conflicts"] = conflict_flags
    12. output_public["inquiry_admissible"] correct per gov_class
    13. output_public["compute"] is a list
    14. RWDR compute result trimmed (no raw internal fields in compute entry)
    15. output_reply non-empty for all gov_classes
    16. structured_clarification reply mentions missing field
    17. structured_clarification reply mentions conflict field
    18. governed_state_update reply mentions captured parameters
    19. technical_preselection reply contains technical header
    20. ObservedState, NormalizedState, AssertedState, GovernanceState unchanged
    21. No LLM call (openai never invoked)
    22. output_public does NOT contain 'raw_extractions' key (Invariant 8)
    23. output_public does NOT contain 'assertions' key (Invariant 8)
    24. _determine_response_class returns correct class for all gov_classes
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.agent.graph import GraphState
from app.agent.graph.nodes.output_contract_node import (
    _determine_response_class,
    _is_fast_confirm_applicable,
    _reply_clarification,
    _reply_state_update,
    build_governed_conversation_strategy_contract,
    output_contract_node,
)
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    ContextHintState,
    DispatchContractState,
    DispatchState,
    ExportProfileState,
    GovernanceState,
    ManufacturerRef,
    ManufacturerMappingState,
    MediumCaptureState,
    MediumClassificationState,
    EvidenceState,
    MatchingState,
    RequirementClass,
    RfqState,
    SealaiNormIdentity,
    SealaiNormMaterial,
    SealaiNormState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claim(field: str, value, confidence: str = "confirmed") -> AssertedClaim:
    return AssertedClaim(field_name=field, asserted_value=value, confidence=confidence)


def _gov(
    gov_class=None,
    rfq_admissible: bool = False,
    validity_limits: list[str] | None = None,
    open_validation_points: list[str] | None = None,
) -> GovernanceState:
    return GovernanceState(
        gov_class=gov_class,
        rfq_admissible=rfq_admissible,
        validity_limits=validity_limits or [],
        open_validation_points=open_validation_points or [],
    )


def _full_a_state(with_compute: bool = False) -> GraphState:
    assertions = {
        "medium":        _claim("medium",        "Dampf",  "confirmed"),
        "pressure_bar":  _claim("pressure_bar",  12.0,     "confirmed"),
        "temperature_c": _claim("temperature_c", 180.0,    "confirmed"),
    }
    governance = _gov(gov_class="A", rfq_admissible=True)
    compute = [{"calc_type": "rwdr", "status": "ok", "v_surface_m_s": 3.93,
                "pv_value_mpa_m_s": 0.39, "dn_value": 75000.0,
                "dn_warning": False, "pv_warning": False,
                "hrc_warning": False, "notes": []}] if with_compute else []
    return GraphState(
        asserted=AssertedState(assertions=assertions),
        governance=governance,
        compute_results=compute,
    )


def _b_state(missing: list[str] | None = None) -> GraphState:
    assertions = {
        "medium":       _claim("medium",       "Dampf", "confirmed"),
        "pressure_bar": _claim("pressure_bar", 12.0,    "confirmed"),
    }
    governance = _gov(gov_class="B", rfq_admissible=False,
                      open_validation_points=missing or ["temperature_c"])
    return GraphState(
        asserted=AssertedState(
            assertions=assertions,
            blocking_unknowns=missing or ["temperature_c"],
        ),
        governance=governance,
    )


_REQUIRED_KEYS = {
    "response_class", "gov_class", "inquiry_admissible",
    "parameters", "missing_fields", "conflicts",
    "validity_notes", "open_points", "compute", "matching", "rfq", "dispatch", "norm", "export_profile", "manufacturer_mapping", "dispatch_contract", "message",
}


# ---------------------------------------------------------------------------
# 1–6. Response class selection
# ---------------------------------------------------------------------------

class TestResponseClassSelection:
    def test_none_gov_class_clarification(self):
        state = GraphState()  # empty → gov_class None
        assert _determine_response_class(state) == "structured_clarification"

    def test_class_d_clarification(self):
        state = GraphState(governance=_gov(gov_class="D"))
        assert _determine_response_class(state) == "structured_clarification"

    def test_class_c_clarification(self):
        state = GraphState(governance=_gov(gov_class="C"))
        assert _determine_response_class(state) == "structured_clarification"

    def test_class_b_clarification(self):
        state = GraphState(governance=_gov(gov_class="B"))
        assert _determine_response_class(state) == "structured_clarification"

    def test_class_a_no_compute_state_update(self):
        state = _full_a_state(with_compute=False)
        assert _determine_response_class(state) == "governed_state_update"

    def test_class_a_with_compute_recommendation(self):
        state = _full_a_state(with_compute=True)
        assert _determine_response_class(state) == "technical_preselection"

    def test_class_a_with_compute_and_blocking_evidence_gap_stays_state_update(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "evidence": EvidenceState(
                    evidence_present=True,
                    evidence_count=1,
                    deterministic_findings=["pressure_bar", "temperature_c"],
                    evidence_gaps=["missing_source_for_medium"],
                    unresolved_open_points=["missing_source_for_medium"],
                )
            }
        )
        assert _determine_response_class(state) == "governed_state_update"

    def test_matching_result_overrides_to_candidate_shortlist(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="ready_for_matching",
                    shortlist_ready=True,
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                )
            }
        )
        assert _determine_response_class(state) == "candidate_shortlist"

    def test_rfq_ready_overrides_matching_result(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="ready_for_matching",
                    shortlist_ready=True,
                    inquiry_ready=True,
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                ),
                "rfq": RfqState(
                    status="rfq_ready",
                    rfq_ready=True,
                    rfq_admissible=True,
                ),
            }
        )
        assert _determine_response_class(state) == "inquiry_ready"

    def test_matching_result_without_release_stays_preselection(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="not_released",
                    release_blockers=["demo_matching_catalog"],
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                )
            }
        )
        assert _determine_response_class(state) == "technical_preselection"

    def test_class_a_with_requirement_class_and_boundary_anchor_becomes_recommendation(self):
        state = _full_a_state(with_compute=False).model_copy(
            update={
                "asserted": AssertedState(
                    assertions={
                        "medium": _claim("medium", "Dampf", "confirmed"),
                        "pressure_bar": _claim("pressure_bar", 12.0, "confirmed"),
                        "temperature_c": _claim("temperature_c", 180.0, "confirmed"),
                        "geometry_context": _claim("geometry_context", "Nut im Gehaeuse", "confirmed"),
                    }
                ),
                "governance": GovernanceState(
                    gov_class="A",
                    rfq_admissible=True,
                    requirement_class=RequirementClass(
                        class_id="PTFE10",
                        description="Steam sealing class",
                    ),
                    open_validation_points=[],
                ),
            }
        )
        assert _determine_response_class(state) == "technical_preselection"

    def test_class_a_without_boundary_anchor_stays_state_update(self):
        state = _full_a_state(with_compute=False).model_copy(
            update={
                "governance": GovernanceState(
                    gov_class="A",
                    rfq_admissible=True,
                    requirement_class=RequirementClass(
                        class_id="PTFE10",
                        description="Steam sealing class",
                    ),
                    open_validation_points=[],
                ),
            }
        )
        assert _determine_response_class(state) == "governed_state_update"

    def test_class_a_with_preselection_blocker_stays_structured_clarification(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "governance": GovernanceState(
                    gov_class="A",
                    rfq_admissible=True,
                    requirement_class=RequirementClass(
                        class_id="PTFE10",
                        description="Steam sealing class",
                    ),
                    preselection_blockers=["duty_profile"],
                    type_sensitive_required=["duty_profile"],
                ),
            }
        )
        assert _determine_response_class(state) == "structured_clarification"


# ---------------------------------------------------------------------------
# 7. output_response_class matches output_public["response_class"]
# ---------------------------------------------------------------------------

class TestResponseClassConsistency:
    @pytest.mark.asyncio
    async def test_response_class_consistent(self):
        for state in [GraphState(), _b_state(), _full_a_state(), _full_a_state(True)]:
            result = await output_contract_node(state)
            assert result.output_response_class == result.output_public["response_class"]

    def test_family_only_medium_changes_primary_question(self):
        state = GraphState(
            asserted=AssertedState(
                assertions={"pressure_bar": _claim("pressure_bar", 12.0, "confirmed")},
                blocking_unknowns=["medium", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["medium", "temperature_c"]),
            medium_capture=MediumCaptureState(
                raw_mentions=["alkalische reinigungsloesung"],
                primary_raw_text="alkalische reinigungsloesung",
                source_turn_ref="turn:1",
                source_turn_index=1,
            ),
            medium_classification=MediumClassificationState(
                family="chemisch_aggressiv",
                confidence="medium",
                status="family_only",
                normalization_source="deterministic_family_hint:alkalisch_reinigend",
            ),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")
        assert strategy.primary_question is not None
        assert "Reinigungsloesung" in strategy.primary_question or "Stoff" in strategy.primary_question

    def test_mentioned_unclassified_medium_changes_primary_question(self):
        state = GraphState(
            asserted=AssertedState(
                assertions={"pressure_bar": _claim("pressure_bar", 12.0, "confirmed")},
                blocking_unknowns=["medium", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["medium", "temperature_c"]),
            medium_capture=MediumCaptureState(
                raw_mentions=["XY-Compound 4711"],
                primary_raw_text="XY-Compound 4711",
                source_turn_ref="turn:2",
                source_turn_index=2,
            ),
            medium_classification=MediumClassificationState(
                family="unknown",
                confidence="low",
                status="mentioned_unclassified",
                normalization_source="deterministic_capture_only",
            ),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")
        assert strategy.primary_question is not None
        assert "XY-Compound 4711" in strategy.primary_question

    def test_recognized_medium_uses_targeted_followup_instead_of_generic_medium_question(self):
        state = GraphState(
            asserted=AssertedState(
                assertions={"pressure_bar": _claim("pressure_bar", 12.0, "confirmed")},
                blocking_unknowns=["medium", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["medium", "temperature_c"]),
            medium_capture=MediumCaptureState(
                raw_mentions=["dampf"],
                primary_raw_text="dampf",
                source_turn_ref="turn:1",
                source_turn_index=1,
            ),
            medium_classification=MediumClassificationState(
                canonical_label="Dampf",
                family="dampffoermig",
                confidence="medium",
                status="recognized",
                normalization_source="deterministic_alias_map",
                mapping_confidence="requires_confirmation",
                followup_question="Handelt es sich um Sattdampf oder Heißdampf, und in welchem Druck- und Temperaturbereich arbeiten Sie?",
            ),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")
        assert strategy.primary_question is not None
        assert "Sattdampf" in strategy.primary_question
        assert "Welches Medium soll abgedichtet werden?" not in strategy.primary_question

    def test_unavailable_medium_keeps_generic_medium_question(self):
        state = GraphState(
            asserted=AssertedState(
                assertions={"pressure_bar": _claim("pressure_bar", 12.0, "confirmed")},
                blocking_unknowns=["medium", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["medium", "temperature_c"]),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")
        assert strategy.primary_question == "Welches Medium soll abgedichtet werden?"

    def test_recognized_medium_without_application_anchor_prioritizes_application_before_pressure(self):
        state = GraphState(
            pending_message="ich muss salzwasser draussen halten",
            asserted=AssertedState(
                assertions={"medium": _claim("medium", "Salzwasser", "confirmed")},
                blocking_unknowns=["pressure_bar", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["pressure_bar", "temperature_c"]),
            medium_capture=MediumCaptureState(
                raw_mentions=["salzwasser"],
                primary_raw_text="salzwasser",
                source_turn_ref="turn:1",
                source_turn_index=1,
            ),
            medium_classification=MediumClassificationState(
                canonical_label="Salzwasser",
                family="waessrig_salzhaltig",
                confidence="high",
                status="recognized",
                normalization_source="deterministic_alias_map",
                mapping_confidence="confirmed",
            ),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")

        assert strategy.primary_question is not None
        assert "Einbausituation" in strategy.primary_question or "bewegten Stelle" in strategy.primary_question
        assert "Betriebsdruck" not in strategy.primary_question

    def test_rotary_context_prioritizes_rotary_core_parameter_before_pressure(self):
        state = GraphState(
            pending_message="es ist eine rotierende welle",
            asserted=AssertedState(
                assertions={"medium": _claim("medium", "Salzwasser", "confirmed")},
                blocking_unknowns=["pressure_bar", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["pressure_bar", "temperature_c"]),
            medium_capture=MediumCaptureState(
                raw_mentions=["salzwasser"],
                primary_raw_text="salzwasser",
                source_turn_ref="turn:1",
                source_turn_index=1,
            ),
            medium_classification=MediumClassificationState(
                canonical_label="Salzwasser",
                family="waessrig_salzhaltig",
                confidence="high",
                status="recognized",
                normalization_source="deterministic_alias_map",
                mapping_confidence="confirmed",
            ),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")

        assert strategy.primary_question is not None
        assert "Drehzahl" in strategy.primary_question or "Wellendurchmesser" in strategy.primary_question
        assert "Betriebsdruck" not in strategy.primary_question

    def test_persisted_rotary_hint_prioritizes_rotary_core_parameter_after_followup_turn(self):
        state = GraphState(
            asserted=AssertedState(
                assertions={"medium": _claim("medium", "Salzwasser", "confirmed")},
                blocking_unknowns=["pressure_bar", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["pressure_bar", "temperature_c"]),
            medium_capture=MediumCaptureState(
                raw_mentions=["salzwasser"],
                primary_raw_text="salzwasser",
                source_turn_ref="turn:1",
                source_turn_index=1,
            ),
            medium_classification=MediumClassificationState(
                canonical_label="Salzwasser",
                family="waessrig_salzhaltig",
                confidence="high",
                status="recognized",
                normalization_source="deterministic_alias_map",
                mapping_confidence="confirmed",
            ),
            motion_hint=ContextHintState(
                label="rotary",
                confidence="high",
                source_turn_ref="turn:2",
                source_turn_index=2,
                source_type="deterministic_text_inference",
            ),
            application_hint=ContextHintState(
                label="shaft_sealing",
                confidence="medium",
                source_turn_ref="turn:2",
                source_turn_index=2,
                source_type="deterministic_text_inference",
            ),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")

        assert strategy.primary_question is not None
        assert "Drehzahl" in strategy.primary_question or "Wellendurchmesser" in strategy.primary_question
        assert "Betriebsdruck" not in strategy.primary_question

    def test_filled_shaft_diameter_is_not_asked_again(self):
        state = GraphState(
            asserted=AssertedState(
                assertions={
                    "medium": _claim("medium", "Salzwasser", "confirmed"),
                    "shaft_diameter_mm": _claim("shaft_diameter_mm", 40.0, "confirmed"),
                },
                blocking_unknowns=["pressure_bar", "temperature_c"],
            ),
            governance=_gov(gov_class="B", open_validation_points=["pressure_bar", "temperature_c"]),
            medium_capture=MediumCaptureState(
                raw_mentions=["salzwasser"],
                primary_raw_text="salzwasser",
                source_turn_ref="turn:1",
                source_turn_index=1,
            ),
            medium_classification=MediumClassificationState(
                canonical_label="Salzwasser",
                family="waessrig_salzhaltig",
                confidence="high",
                status="recognized",
                normalization_source="deterministic_alias_map",
                mapping_confidence="confirmed",
            ),
            motion_hint=ContextHintState(
                label="rotary",
                confidence="high",
                source_turn_ref="turn:2",
                source_turn_index=2,
                source_type="deterministic_text_inference",
            ),
            application_hint=ContextHintState(
                label="shaft_sealing",
                confidence="medium",
                source_turn_ref="turn:2",
                source_turn_index=2,
                source_type="deterministic_text_inference",
            ),
        )

        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")

        assert strategy.primary_question is not None
        assert "Wellendurchmesser" not in strategy.primary_question
        assert "Betriebsdruck" not in strategy.primary_question
        assert "Drehzahl" in strategy.primary_question or "Einbausituation" in strategy.primary_question


# ---------------------------------------------------------------------------
# 8. output_public required keys (Invariant 8 shape)
# ---------------------------------------------------------------------------

class TestOutputPublicShape:
    @pytest.mark.asyncio
    async def test_required_keys_present_empty_state(self):
        result = await output_contract_node(GraphState())
        assert _REQUIRED_KEYS.issubset(result.output_public.keys())

    @pytest.mark.asyncio
    async def test_required_keys_present_class_a(self):
        result = await output_contract_node(_full_a_state(with_compute=True))
        assert _REQUIRED_KEYS.issubset(result.output_public.keys())

    @pytest.mark.asyncio
    async def test_output_public_contains_evidence_classification(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "evidence": EvidenceState(
                    evidence_present=True,
                    evidence_count=1,
                    trusted_sources_present=True,
                    source_backed_findings=["medium"],
                    deterministic_findings=["pressure_bar", "temperature_c"],
                    assumption_based_findings=["installation"],
                    evidence_gaps=["missing_source_for_compliance"],
                )
            }
        )
        result = await output_contract_node(state)
        evidence = result.output_public["evidence"]

        assert evidence["evidence_present"] is True
        assert evidence["source_backed_findings"] == ["medium"]
        assert evidence["deterministic_findings"] == ["pressure_bar", "temperature_c"]
        assert evidence["assumption_based_findings"] == ["installation"]
        assert evidence["blocking_evidence_gaps"] == ["missing_source_for_compliance"]

    @pytest.mark.asyncio
    async def test_no_raw_extractions_key(self):
        """Invariant 8: raw ObservedState must not leak."""
        result = await output_contract_node(_full_a_state())
        assert "raw_extractions" not in result.output_public

    @pytest.mark.asyncio
    async def test_no_assertions_key(self):
        """Invariant 8: raw AssertedState must not leak."""
        result = await output_contract_node(_full_a_state())
        assert "assertions" not in result.output_public

    @pytest.mark.asyncio
    async def test_no_user_overrides_key(self):
        result = await output_contract_node(_full_a_state())
        assert "user_overrides" not in result.output_public

    @pytest.mark.asyncio
    async def test_matching_public_contains_only_clean_summary(self):
        state = _full_a_state().model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="ready_for_matching",
                    selected_manufacturer_ref=ManufacturerRef(
                        manufacturer_name="Acme",
                        candidate_ids=["registry-ptfe-g25-acme"],
                    ),
                    manufacturer_refs=[
                        ManufacturerRef(
                            manufacturer_name="Acme",
                            candidate_ids=["registry-ptfe-g25-acme"],
                        )
                    ],
                    matching_notes=["Matching uses the current demo manufacturer catalog."],
                )
            }
        )
        result = await output_contract_node(state)
        matching = result.output_public["matching"]

        assert matching["selected_manufacturer"] == "Acme"
        assert matching["manufacturer_count"] == 1
        assert "event_id" not in str(matching)
        assert "candidate_ids" not in str(matching)

    @pytest.mark.asyncio
    async def test_rfq_public_contains_only_clean_summary(self):
        state = _full_a_state().model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="ready_for_matching",
                    shortlist_ready=True,
                    inquiry_ready=True,
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                ),
                "rfq": RfqState(
                    status="rfq_ready",
                    rfq_ready=True,
                    rfq_admissible=True,
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                    recipient_refs=[{"manufacturer_name": "Acme", "qualified_for_rfq": True}],
                    qualified_material_ids=["registry-ptfe-g25-acme"],
                    confirmed_parameters={"medium": "Wasser"},
                    dimensions={"shaft_diameter_mm": 50.0},
                    notes=["Governed output is releasable and handover-ready."],
                )
            }
        )
        result = await output_contract_node(state)
        rfq = result.output_public["rfq"]

        assert rfq["status"] == "rfq_ready"
        assert rfq["rfq_ready"] is True
        assert rfq["selected_manufacturer"] == "Acme"
        assert "event_id" not in str(rfq)
        assert "event_key" not in str(rfq)

    @pytest.mark.asyncio
    async def test_dispatch_public_contains_only_clean_summary(self):
        state = _full_a_state().model_copy(
            update={
                "dispatch": DispatchState(
                    dispatch_ready=True,
                    dispatch_status="envelope_ready",
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                    recipient_refs=[{"manufacturer_name": "Acme", "qualified_for_rfq": True}],
                    transport_channel="internal_transport_envelope",
                    dispatch_notes=["Internal transport envelope is ready for later sender/connector consumption."],
                )
            }
        )
        result = await output_contract_node(state)
        dispatch = result.output_public["dispatch"]

        assert dispatch["dispatch_ready"] is True
        assert dispatch["dispatch_status"] == "envelope_ready"
        assert dispatch["selected_manufacturer"] == "Acme"
        dumped = str(dispatch).lower()
        assert "transport_channel" not in dispatch
        assert "transport" not in dumped
        assert "event_id" not in dumped
        assert "event_key" not in dumped

    @pytest.mark.asyncio
    async def test_norm_public_contains_only_clean_summary(self):
        state = _full_a_state().model_copy(
            update={
                "sealai_norm": SealaiNormState(
                    status="rfq_ready",
                    identity=SealaiNormIdentity(
                        sealai_request_id="sealai-phaseh-norm-001",
                        norm_version="sealai_norm_v1",
                        requirement_class_id="PTFE10",
                        seal_family="Flachdichtung",
                    ),
                    application_summary="Wasser, 180°C, 12 bar",
                    geometry={"dn_mm": 50.0},
                    material=SealaiNormMaterial(
                        material_family="PTFE",
                        qualified_materials=["PTFE virgin"],
                    ),
                )
            }
        )
        result = await output_contract_node(state)
        norm = result.output_public["norm"]

        assert norm["status"] == "rfq_ready"
        assert norm["norm_version"] == "sealai_norm_v1"
        assert norm["requirement_class"] == "PTFE10"
        assert "event_id" not in str(norm)
        assert "candidate_ids" not in str(norm)

    @pytest.mark.asyncio
    async def test_export_profile_public_contains_only_clean_summary(self):
        state = _full_a_state().model_copy(
            update={
                "export_profile": ExportProfileState(
                    status="ready",
                    export_profile_version="sealai_export_profile_v1",
                    sealai_request_id="sealai-phaseh-export-001",
                    selected_manufacturer="Acme",
                    recipient_refs=["Acme"],
                    requirement_class_id="PTFE10",
                    application_summary="Wasser, 180°C, 12 bar",
                    dimensions_summary=["dn_mm=50.0"],
                    material_summary="PTFE (1 qualified material candidates)",
                    rfq_ready=True,
                    dispatch_ready=True,
                    export_notes=["Governed output is releasable and handover-ready."],
                )
            }
        )
        result = await output_contract_node(state)
        export_profile = result.output_public["export_profile"]

        assert export_profile["status"] == "ready"
        assert export_profile["export_profile_version"] == "sealai_export_profile_v1"
        assert export_profile["selected_manufacturer"] == "Acme"
        assert export_profile["recipient_count"] == 1
        assert "event_id" not in str(export_profile)
        assert "candidate_ids" not in str(export_profile)

    @pytest.mark.asyncio
    async def test_manufacturer_mapping_public_contains_only_clean_summary(self):
        state = _full_a_state().model_copy(
            update={
                "manufacturer_mapping": ManufacturerMappingState(
                    status="mapped",
                    mapping_version="manufacturer_mapping_v1",
                    selected_manufacturer="Acme",
                    mapped_product_family="Flachdichtung",
                    mapped_material_family="PTFE",
                    geometry_export_hint="dn_mm=50.0",
                    mapping_notes=["Mapping remains category-level only; no SKU or compound code is inferred."],
                )
            }
        )
        result = await output_contract_node(state)
        mapping = result.output_public["manufacturer_mapping"]

        assert mapping["status"] == "mapped"
        assert mapping["mapping_version"] == "manufacturer_mapping_v1"
        assert mapping["selected_manufacturer"] == "Acme"
        assert mapping["mapped_material_family"] == "PTFE"
        dumped = str(mapping).lower()
        assert "manufacturer_sku" not in dumped
        assert "candidate_id" not in dumped
        assert "compound_code" not in dumped

    @pytest.mark.asyncio
    async def test_dispatch_contract_public_contains_only_clean_summary(self):
        state = _full_a_state().model_copy(
            update={
                "dispatch_contract": DispatchContractState(
                    status="ready",
                    contract_version="dispatch_contract_v1",
                    sealai_request_id="sealai-phasei-contract-001",
                    selected_manufacturer="Acme",
                    recipient_refs=["Acme"],
                    requirement_class_id="PTFE10",
                    application_summary="Wasser, 180°C, 12 bar",
                    material_summary="PTFE (1 qualified material candidates)",
                    dimensions_summary=["dn_mm=50.0"],
                    rfq_ready=True,
                    dispatch_ready=True,
                    mapping_summary="material_family=PTFE",
                    handover_notes=["Connector-ready contract remains systemneutral and transport-free."],
                )
            }
        )
        result = await output_contract_node(state)
        contract = result.output_public["dispatch_contract"]

        assert contract["status"] == "ready"
        assert contract["contract_version"] == "dispatch_contract_v1"
        assert contract["selected_manufacturer"] == "Acme"
        dumped = str(contract).lower()
        assert "transport" not in dumped
        assert "event_id" not in dumped
        assert "event_key" not in dumped
        assert "partner_id" not in dumped
        assert "manufacturer_sku" not in dumped


# ---------------------------------------------------------------------------
# 9–11. Parameters, missing_fields, conflicts
# ---------------------------------------------------------------------------

class TestOutputPublicContent:
    @pytest.mark.asyncio
    async def test_parameters_contains_asserted_fields(self):
        state = _full_a_state()
        result = await output_contract_node(state)
        params = result.output_public["parameters"]
        assert "medium" in params
        assert "pressure_bar" in params
        assert "temperature_c" in params

    @pytest.mark.asyncio
    async def test_parameters_value_correct(self):
        state = _full_a_state()
        result = await output_contract_node(state)
        assert result.output_public["parameters"]["medium"]["value"] == "Dampf"
        assert result.output_public["parameters"]["pressure_bar"]["value"] == 12.0

    @pytest.mark.asyncio
    async def test_parameters_confidence_present(self):
        state = _full_a_state()
        result = await output_contract_node(state)
        assert result.output_public["parameters"]["medium"]["confidence"] == "confirmed"

    @pytest.mark.asyncio
    async def test_missing_fields_from_blocking_unknowns(self):
        state = _b_state(missing=["temperature_c", "material"])
        result = await output_contract_node(state)
        assert "temperature_c" in result.output_public["missing_fields"]

    @pytest.mark.asyncio
    async def test_conflicts_from_conflict_flags(self):
        asserted = AssertedState(
            assertions={"medium": _claim("medium", "Dampf")},
            conflict_flags=["medium"],
        )
        gov = _gov(gov_class="C")
        state = GraphState(asserted=asserted, governance=gov)
        result = await output_contract_node(state)
        assert "medium" in result.output_public["conflicts"]


# ---------------------------------------------------------------------------
# 12. inquiry_admissible
# ---------------------------------------------------------------------------

class TestInquiryAdmissible:
    @pytest.mark.asyncio
    async def test_class_a_inquiry_admissible_true(self):
        state = _full_a_state()
        result = await output_contract_node(state)
        assert result.output_public["inquiry_admissible"] is True
        assert "rfq_admissible" not in result.output_public

    @pytest.mark.asyncio
    async def test_class_b_inquiry_admissible_false(self):
        state = _b_state()
        result = await output_contract_node(state)
        assert result.output_public["inquiry_admissible"] is False
        assert "rfq_admissible" not in result.output_public

    @pytest.mark.asyncio
    async def test_empty_state_inquiry_admissible_false(self):
        result = await output_contract_node(GraphState())
        assert result.output_public["inquiry_admissible"] is False
        assert "rfq_admissible" not in result.output_public


# ---------------------------------------------------------------------------
# 13–14. Compute summary
# ---------------------------------------------------------------------------

class TestComputeSummary:
    @pytest.mark.asyncio
    async def test_compute_is_list(self):
        result = await output_contract_node(_full_a_state(with_compute=True))
        assert isinstance(result.output_public["compute"], list)

    @pytest.mark.asyncio
    async def test_compute_has_one_entry_for_rwdr(self):
        result = await output_contract_node(_full_a_state(with_compute=True))
        assert len(result.output_public["compute"]) == 1

    @pytest.mark.asyncio
    async def test_compute_entry_has_calc_type(self):
        result = await output_contract_node(_full_a_state(with_compute=True))
        assert result.output_public["compute"][0]["calc_type"] == "rwdr"

    @pytest.mark.asyncio
    async def test_compute_entry_has_status(self):
        result = await output_contract_node(_full_a_state(with_compute=True))
        assert "status" in result.output_public["compute"][0]

    @pytest.mark.asyncio
    async def test_no_compute_means_empty_list(self):
        result = await output_contract_node(_full_a_state(with_compute=False))
        assert result.output_public["compute"] == []


# ---------------------------------------------------------------------------
# 15–19. Reply text content
# ---------------------------------------------------------------------------

class TestReplyText:
    @pytest.mark.asyncio
    async def test_reply_non_empty_all_classes(self):
        states = [GraphState(), _b_state(), _full_a_state(), _full_a_state(True)]
        for state in states:
            result = await output_contract_node(state)
            assert result.output_reply != ""
            assert isinstance(result.output_reply, str)

    @pytest.mark.asyncio
    async def test_clarification_reply_mentions_missing_field(self):
        state = _b_state(missing=["temperature_c"])
        result = await output_contract_node(state)
        # The reply should reference temperature somehow
        assert "temperature" in result.output_reply.lower() or "temperatur" in result.output_reply.lower()

    @pytest.mark.asyncio
    async def test_clarification_reply_prioritizes_single_missing_question_without_formula_reason_block(self):
        state = _b_state(missing=["pressure_bar", "temperature_c"])
        result = await output_contract_node(state)

        assert result.output_response_class == "structured_clarification"
        assert "betriebsdruck" in result.output_reply.lower()
        assert "damit ich" not in result.output_reply.lower()
        assert "der druck bestimmt" not in result.output_reply.lower()
        forbidden_fragment = "fehlen" + " noch"
        assert forbidden_fragment not in result.output_reply.lower()

    @pytest.mark.asyncio
    async def test_clarification_reply_mentions_conflict(self):
        asserted = AssertedState(
            assertions={"medium": _claim("medium", "Dampf")},
            conflict_flags=["medium"],
        )
        state = GraphState(asserted=asserted, governance=_gov(gov_class="C"))
        result = await output_contract_node(state)
        assert "medium" in result.output_reply.lower()

    @pytest.mark.asyncio
    async def test_clarification_reply_turns_conflict_into_targeted_question(self):
        asserted = AssertedState(
            assertions={
                "pressure_bar": _claim("pressure_bar", 12.0),
                "temperature_c": _claim("temperature_c", 80.0),
            },
            conflict_flags=["pressure_bar"],
        )
        state = GraphState(asserted=asserted, governance=_gov(gov_class="C"))
        result = await output_contract_node(state)

        assert result.output_response_class == "structured_clarification"
        assert "welcher betriebsdruck" in result.output_reply.lower()
        assert "widerspr" not in result.output_reply.lower()

    def test_clarification_reply_uses_conversation_strategy_question_and_reason_operatively(self):
        state = _b_state(missing=["medium", "pressure_bar"])
        strategy = build_governed_conversation_strategy_contract(state, "structured_clarification")

        reply = _reply_clarification(state, strategy)

        assert strategy.primary_question is not None
        assert strategy.primary_question_reason is not None
        assert strategy.primary_question in reply
        assert strategy.primary_question_reason not in reply
        assert reply.count("?") == 1

    @pytest.mark.asyncio
    async def test_preselection_blocker_uses_prioritized_single_question(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "governance": GovernanceState(
                    gov_class="A",
                    rfq_admissible=True,
                    preselection_blockers=["sealing_type", "duty_profile"],
                )
            }
        )

        result = await output_contract_node(state)

        assert result.output_response_class == "structured_clarification"
        assert result.output_reply.count("?") == 1
        assert "Dichtungstyp" in result.output_reply or "Dichtprinzip" in result.output_reply
        assert result.output_public["preselection_blockers"] == ["sealing_type", "duty_profile"]

    def test_clarification_reply_falls_back_cleanly_without_strategy(self):
        state = _b_state(missing=["temperature_c"])

        reply = _reply_clarification(state, None)

        assert "temperatur" in reply.lower()
        assert "einsatzfenster" not in reply.lower()

    def test_governed_state_update_uses_priority_question_when_one_decisive_field_is_missing(self):
        state = GraphState(
            asserted=AssertedState(
                assertions={
                    "medium": _claim("medium", "Salzwasser"),
                    "pressure_bar": _claim("pressure_bar", 10.0),
                    "temperature_c": _claim("temperature_c", 80.0),
                    "shaft_diameter_mm": _claim("shaft_diameter_mm", 50.0),
                },
                blocking_unknowns=["speed_rpm"],
            ),
            governance=_gov(gov_class="A"),
            motion_hint=ContextHintState(label="rotary", confidence="high", source_turn_index=1),
        )

        reply = _reply_state_update(state)

        assert "Betriebsparameter erfasst:" in reply
        assert "Drehzahl" in reply
        assert "Die technischen Grenzen werden geprüft." not in reply

    @pytest.mark.asyncio
    async def test_recommendation_reply_uses_turn_context_summaries(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "governance": _gov(
                    gov_class="A",
                    rfq_admissible=True,
                    open_validation_points=["Werkstoffgrenze pruefen"],
                )
            }
        )
        result = await output_contract_node(state)

        assert "Bestaetigte Basis:" in result.output_reply
        assert "Medium: Dampf" in result.output_reply
        assert "Offene Pruefpunkte:" in result.output_reply

    @pytest.mark.asyncio
    async def test_matching_reply_uses_turn_context_summaries(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="ready_for_matching",
                    shortlist_ready=True,
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                    matching_notes=["Kandidat liegt im gueltigen Eignungsraum."],
                ),
                "governance": _gov(
                    gov_class="A",
                    rfq_admissible=True,
                    open_validation_points=["Herstellerfreigabe offen"],
                ),
            }
        )
        result = await output_contract_node(state)

        assert "Technische Basis:" in result.output_reply
        assert "Medium: Dampf" in result.output_reply
        assert "Offene Pruefpunkte:" in result.output_reply

    @pytest.mark.asyncio
    async def test_rfq_reply_uses_turn_context_summaries(self):
        from unittest.mock import patch as _patch
        from app.agent.domain.admissibility import AdmissibilityResult
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "matching": MatchingState(
                    status="matched_primary_candidate",
                    matchability_status="ready_for_matching",
                    shortlist_ready=True,
                    inquiry_ready=True,
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                ),
                "rfq": RfqState(
                    status="rfq_ready",
                    rfq_ready=True,
                    rfq_admissible=True,
                    requirement_class=RequirementClass(class_id="RC-1"),
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                ),
                "dispatch_contract": DispatchContractState(
                    unresolved_points=["Zeichnung pruefen"],
                ),
                "dispatch": DispatchState(
                    dispatch_ready=True,
                    dispatch_status="envelope_ready",
                ),
            }
        )
        _admissible = AdmissibilityResult(admissible=True, blocking_reasons=(), basis_hash="test")
        with (
            _patch(
                "app.agent.graph.nodes.output_contract_node.check_inquiry_admissibility",
                return_value=_admissible,
            ),
            _patch(
                "app.agent.graph.nodes.output_contract_node.interrupt",
                return_value={"confirmed": True},
            ),
        ):
            result = await output_contract_node(state)

        assert "Anfragebasis:" in result.output_reply
        assert "Medium: Dampf" in result.output_reply
        assert "Restpunkte:" in result.output_reply

    @pytest.mark.asyncio
    async def test_state_update_reply_non_empty(self):
        state = _full_a_state(with_compute=False)
        result = await output_contract_node(state)
        assert len(result.output_reply) > 10

    @pytest.mark.asyncio
    async def test_recommendation_reply_non_empty(self):
        state = _full_a_state(with_compute=True)
        result = await output_contract_node(state)
        assert len(result.output_reply) > 20

    @pytest.mark.asyncio
    async def test_rfq_ready_reply_does_not_expose_internal_transport_wording(self):
        state = _full_a_state(with_compute=True).model_copy(
            update={
                "rfq": RfqState(
                    status="rfq_ready",
                    rfq_ready=True,
                    rfq_admissible=True,
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                ),
                "dispatch": DispatchState(
                    dispatch_ready=True,
                    dispatch_status="envelope_ready",
                    selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                ),
            }
        )

        result = await output_contract_node(state)

        dumped = result.output_reply.lower()
        assert "interne dispatch" not in dumped
        assert "transport" not in dumped


# ---------------------------------------------------------------------------
# 20. Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    @pytest.mark.asyncio
    async def test_observed_unchanged(self):
        state = _full_a_state()
        original = list(state.observed.raw_extractions)
        result = await output_contract_node(state)
        assert list(result.observed.raw_extractions) == original

    @pytest.mark.asyncio
    async def test_asserted_unchanged(self):
        state = _full_a_state()
        original_keys = set(state.asserted.assertions.keys())
        result = await output_contract_node(state)
        assert set(result.asserted.assertions.keys()) == original_keys

    @pytest.mark.asyncio
    async def test_governance_unchanged(self):
        state = _full_a_state()
        result = await output_contract_node(state)
        assert result.governance.gov_class == "A"
        assert result.governance.rfq_admissible is True

    @pytest.mark.asyncio
    async def test_normalized_unchanged(self):
        state = _full_a_state()
        original_params = dict(state.normalized.parameters)
        result = await output_contract_node(state)
        assert dict(result.normalized.parameters) == original_params

    @pytest.mark.asyncio
    async def test_analysis_cycle_unchanged(self):
        state = _full_a_state()
        state = state.model_copy(update={"analysis_cycle": 2})
        result = await output_contract_node(state)
        assert result.analysis_cycle == 2


# ---------------------------------------------------------------------------
# 21. No LLM call
# ---------------------------------------------------------------------------

class TestNoLLM:
    @pytest.mark.asyncio
    async def test_openai_never_called(self):
        state = _full_a_state(with_compute=True)
        with patch("openai.AsyncOpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create = AsyncMock(
                side_effect=AssertionError("LLM must not be called in output_contract_node")
            )
            result = await output_contract_node(state)
        mock_cls.assert_not_called()
        assert result.output_response_class == "technical_preselection"


# ---------------------------------------------------------------------------
# Fast-confirm path: 4+ core params → assumptions instead of questions
# ---------------------------------------------------------------------------

def _four_core_params_state(missing_optional: list[str] | None = None) -> GraphState:
    """State with 4+ confirmed core params and only optional fields missing."""
    assertions = {
        "medium":           _claim("medium",           "Salzwasser", "confirmed"),
        "sealing_type":     _claim("sealing_type",     "RWDR",       "confirmed"),
        "temperature_c":    _claim("temperature_c",    80.0,         "confirmed"),
        "pressure_bar":     _claim("pressure_bar",     10.0,         "confirmed"),
        "shaft_diameter_mm":_claim("shaft_diameter_mm", 50.0,        "confirmed"),
        "speed_rpm":        _claim("speed_rpm",        6000.0,       "confirmed"),
    }
    governance = _gov(
        gov_class="B",
        open_validation_points=missing_optional or ["installation"],
    )
    return GraphState(
        asserted=AssertedState(
            assertions=assertions,
            blocking_unknowns=missing_optional or ["installation"],
        ),
        governance=governance,
    )


class TestFastConfirmPath:
    """When 4+ core params confirmed and all missing fields are optional,
    the system must emit governed_state_update with param confirmation
    instead of structured_clarification with a question."""

    # ── _is_fast_confirm_applicable ─────────────────────────────────────────

    def test_is_fast_confirm_true_with_all_6_core_params(self):
        state = _four_core_params_state(missing_optional=["installation"])
        assert _is_fast_confirm_applicable(state) is True

    def test_is_fast_confirm_false_with_only_3_core_params(self):
        assertions = {
            "medium":       _claim("medium",       "Salzwasser", "confirmed"),
            "temperature_c":_claim("temperature_c", 80.0,        "confirmed"),
            "pressure_bar": _claim("pressure_bar",  10.0,        "confirmed"),
        }
        state = GraphState(
            asserted=AssertedState(assertions=assertions, blocking_unknowns=["installation"]),
            governance=_gov(gov_class="B"),
        )
        assert _is_fast_confirm_applicable(state) is False

    def test_is_fast_confirm_false_when_required_field_missing(self):
        assertions = {
            "medium":           _claim("medium",           "Salzwasser", "confirmed"),
            "sealing_type":     _claim("sealing_type",     "RWDR",       "confirmed"),
            "temperature_c":    _claim("temperature_c",    80.0,         "confirmed"),
            "pressure_bar":     _claim("pressure_bar",     10.0,         "confirmed"),
            "shaft_diameter_mm":_claim("shaft_diameter_mm", 50.0,        "confirmed"),
        }
        state = GraphState(
            asserted=AssertedState(assertions=assertions, blocking_unknowns=["speed_rpm"]),
            governance=_gov(gov_class="B"),
        )
        assert _is_fast_confirm_applicable(state) is False

    def test_is_fast_confirm_false_with_conflict(self):
        state = _four_core_params_state(missing_optional=["installation"])
        state = state.model_copy(update={
            "asserted": state.asserted.model_copy(update={"conflict_flags": ["pressure_bar"]})
        })
        assert _is_fast_confirm_applicable(state) is False

    # ── _determine_response_class upgrades B → governed_state_update ────────

    def test_response_class_is_governed_state_update_when_fast_confirm(self):
        state = _four_core_params_state(missing_optional=["installation"])
        assert _determine_response_class(state) == "governed_state_update"

    def test_response_class_stays_clarification_when_below_threshold(self):
        assertions = {
            "medium":       _claim("medium",       "Salzwasser", "confirmed"),
            "temperature_c":_claim("temperature_c", 80.0,        "confirmed"),
            "pressure_bar": _claim("pressure_bar",  10.0,        "confirmed"),
        }
        state = GraphState(
            asserted=AssertedState(assertions=assertions, blocking_unknowns=["installation"]),
            governance=_gov(gov_class="B"),
        )
        assert _determine_response_class(state) == "structured_clarification"

    def test_response_class_stays_clarification_when_required_field_missing(self):
        assertions = {
            "medium":           _claim("medium",           "Salzwasser", "confirmed"),
            "sealing_type":     _claim("sealing_type",     "RWDR",       "confirmed"),
            "temperature_c":    _claim("temperature_c",    80.0,         "confirmed"),
            "pressure_bar":     _claim("pressure_bar",     10.0,         "confirmed"),
            "shaft_diameter_mm":_claim("shaft_diameter_mm", 50.0,        "confirmed"),
        }
        state = GraphState(
            asserted=AssertedState(assertions=assertions, blocking_unknowns=["speed_rpm"]),
            governance=_gov(gov_class="B"),
        )
        assert _determine_response_class(state) == "structured_clarification"

    # ── _reply_state_update generates assumption text ───────────────────────

    def test_reply_state_update_fast_confirm_has_no_question_mark(self):
        state = _four_core_params_state(missing_optional=["installation"])
        reply = _reply_state_update(state)
        assert "?" not in reply

    def test_reply_state_update_fast_confirm_contains_medium(self):
        state = _four_core_params_state(missing_optional=["installation"])
        reply = _reply_state_update(state)
        assert "Salzwasser" in reply

    def test_reply_state_update_fast_confirm_invites_correction(self):
        state = _four_core_params_state(missing_optional=["installation"])
        reply = _reply_state_update(state)
        assert "korrigieren" in reply.lower()

    def test_reply_state_update_fast_confirm_mentions_assumption(self):
        state = _four_core_params_state(missing_optional=["installation"])
        reply = _reply_state_update(state)
        assert "Pumpen-Einbau" in reply or "Annahmen" in reply

    def test_reply_state_update_fast_confirm_multiple_optional(self):
        state = _four_core_params_state(
            missing_optional=["installation", "geometry_context", "contamination"]
        )
        reply = _reply_state_update(state)
        assert "?" not in reply
        assert "Betriebsparameter erfasst" in reply

    # ── Conflicts always bypass fast-confirm ────────────────────────────────

    def test_conflict_keeps_structured_clarification(self):
        assertions = {
            "medium":           _claim("medium",           "Salzwasser", "confirmed"),
            "sealing_type":     _claim("sealing_type",     "RWDR",       "confirmed"),
            "temperature_c":    _claim("temperature_c",    80.0,         "confirmed"),
            "pressure_bar":     _claim("pressure_bar",     10.0,         "confirmed"),
            "shaft_diameter_mm":_claim("shaft_diameter_mm", 50.0,        "confirmed"),
        }
        state = GraphState(
            asserted=AssertedState(
                assertions=assertions,
                blocking_unknowns=["installation"],
                conflict_flags=["pressure_bar"],
            ),
            governance=_gov(gov_class="B"),
        )
        assert _determine_response_class(state) == "structured_clarification"

    # ── Golden path ─────────────────────────────────────────────────────────

    def test_golden_path_gleitring_80c_salzwasser_6000rpm_10bar(self):
        """'Gleitring 80°C Salzwasser 6000rpm 10bar' → governed_state_update, no question."""
        state = _four_core_params_state(missing_optional=["installation", "duty_profile"])
        assert _determine_response_class(state) == "governed_state_update"
        reply = _reply_state_update(state)
        assert "?" not in reply
        assert "Betriebsparameter erfasst" in reply
