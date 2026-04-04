from __future__ import annotations

from typing import Any

from app.agent.graph import GraphState
from app.agent.state.models import (
    AssertedClaim,
    ContextHintState,
    DispatchContractState,
    DispatchState,
    ExportProfileState,
    AssertedState,
    GovernanceState,
    GovernedSessionState,
    ManufacturerRef,
    ManufacturerMappingState,
    MatchingState,
    ObservedExtraction,
    ObservedState,
    RecipientRef,
    RequirementClass,
    RfqState,
    SealaiNormIdentity,
    SealaiNormMaterial,
    SealaiNormState,
)
from app.agent.state.projections import project_for_ui
from app.agent.state.reducers import (
    reduce_asserted_to_governance,
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)
from app.agent.services.medium_context import build_medium_context


def _observed(*extractions: tuple[str, Any, float]) -> ObservedState:
    observed = ObservedState()
    for field_name, raw_value, confidence in extractions:
        observed = observed.with_extraction(
            ObservedExtraction(
                field_name=field_name,
                raw_value=raw_value,
                source="llm",
                confidence=confidence,
                turn_index=0,
            )
        )
    return observed


def _state_from_observed(observed: ObservedState) -> GovernedSessionState:
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    governance = reduce_asserted_to_governance(asserted)
    return GovernedSessionState(
        observed=observed,
        normalized=normalized,
        asserted=asserted,
        governance=governance,
    )


def _full_state() -> GovernedSessionState:
    return _state_from_observed(
        _observed(
            ("medium", "Dampf", 0.95),
            ("pressure_bar", 12.0, 0.95),
            ("temperature_c", 180.0, 0.95),
        )
    )


def test_project_for_ui_full_state_populates_all_tiles() -> None:
    result = project_for_ui(_full_state())

    assert result.parameter.parameter_count == 3
    assert len(result.assumption.items) == 0
    assert result.recommendation.scope_status == "complete"
    assert result.compute.items == []
    assert result.matching.status == "pending"
    assert result.rfq.status == "pending"
    assert result.norm.status == "pending"
    assert result.export_profile.status == "pending"
    assert result.manufacturer_mapping.status == "pending"
    assert result.dispatch_contract.status == "pending"


def test_project_for_ui_empty_state_returns_valid_empty_projection() -> None:
    result = project_for_ui(None)

    assert result.parameter.parameters == []
    assert result.assumption.items == []
    assert result.recommendation.scope_status == "pending"
    assert result.compute.items == []
    assert result.matching.status == "pending"
    assert result.rfq.status == "pending"
    assert result.norm.status == "pending"
    assert result.export_profile.status == "pending"
    assert result.manufacturer_mapping.status == "pending"
    assert result.dispatch_contract.status == "pending"


def test_projection_output_does_not_expose_internal_state_keys() -> None:
    dumped = project_for_ui(_full_state()).model_dump()

    assert "gov_class" not in dumped
    assert "raw_extractions" not in str(dumped)
    assert "assertions" not in str(dumped)
    assert "blocking_unknowns" not in str(dumped)
    assert "partner_id" not in str(dumped)


def test_normalized_parameters_map_to_parameter_tile() -> None:
    tile = project_for_ui(_full_state()).parameter

    by_name = {entry.field_name: entry for entry in tile.parameters}
    assert by_name["pressure_bar"].value == 12.0
    assert by_name["pressure_bar"].unit is None
    assert by_name["pressure_bar"].confidence == "confirmed"
    assert by_name["medium"].value == "Dampf"


def test_assumptions_and_open_points_map_to_assumption_tile() -> None:
    state = _state_from_observed(
        _observed(
            ("medium", "Unbekannt", 0.35),
            ("pressure_bar", 12.0, 0.95),
        )
    )

    tile = project_for_ui(state).assumption

    assert any(item.kind == "assumption" for item in tile.items)
    assert any(item.kind == "open_point" for item in tile.items)
    assert any("Medium" in item or "Medium angeben" in item for item in tile.open_points)
    assert "Betriebstemperatur" in tile.open_points
    assert tile.has_open_points is True


def test_assumption_tile_renders_family_only_medium_open_point_status_aware() -> None:
    state = _state_from_observed(_observed(("pressure_bar", 12.0, 0.95))).model_copy(
        update={
            "asserted": AssertedState(
                assertions={"pressure_bar": AssertedClaim(field_name="pressure_bar", asserted_value=12.0, confidence="confirmed")},
                blocking_unknowns=["medium", "temperature_c"],
                conflict_flags=[],
            ),
            "governance": GovernanceState(
                gov_class="B",
                rfq_admissible=False,
                open_validation_points=["medium", "temperature_c"],
            ),
            "medium_capture": {
                "raw_mentions": ["alkalische reinigungsloesung"],
                "primary_raw_text": "alkalische reinigungsloesung",
            },
            "medium_classification": {
                "family": "chemisch_aggressiv",
                "confidence": "medium",
                "status": "family_only",
            },
        }
    )

    tile = project_for_ui(state).assumption
    assert any("Reinigungsloesung" in item for item in tile.open_points)
    assert all(item != "Medium" for item in tile.open_points)


def test_assumption_tile_prioritizes_application_anchor_before_pressure_for_recognized_medium() -> None:
    state = GraphState.model_validate(
        {
            **_state_from_observed(_observed()).model_dump(),
            "pending_message": "ich muss salzwasser draussen halten",
            "asserted": AssertedState(
                assertions={"medium": AssertedClaim(field_name="medium", asserted_value="Salzwasser", confidence="confirmed")},
                blocking_unknowns=["pressure_bar", "temperature_c"],
                conflict_flags=[],
            ),
            "governance": GovernanceState(
                gov_class="B",
                rfq_admissible=False,
                open_validation_points=["pressure_bar", "temperature_c"],
            ),
            "medium_capture": {
                "raw_mentions": ["salzwasser"],
                "primary_raw_text": "salzwasser",
            },
            "medium_classification": {
                "canonical_label": "Salzwasser",
                "family": "waessrig_salzhaltig",
                "confidence": "high",
                "status": "recognized",
            },
        }
    )

    tile = project_for_ui(state).assumption
    recommendation = project_for_ui(state).recommendation

    assert tile.open_points[0] == "Anwendungs- und Bewegungsart präzisieren"
    assert recommendation.open_points[0] == "Anwendungs- und Bewegungsart präzisieren"


def test_assumption_tile_uses_persisted_rotary_hint_before_pressure_after_reload() -> None:
    state = GraphState.model_validate(
        {
            **_state_from_observed(_observed()).model_dump(),
            "asserted": AssertedState(
                assertions={"medium": AssertedClaim(field_name="medium", asserted_value="Salzwasser", confidence="confirmed")},
                blocking_unknowns=["pressure_bar", "temperature_c"],
                conflict_flags=[],
            ),
            "governance": GovernanceState(
                gov_class="B",
                rfq_admissible=False,
                open_validation_points=["pressure_bar", "temperature_c"],
            ),
            "medium_capture": {
                "raw_mentions": ["salzwasser"],
                "primary_raw_text": "salzwasser",
            },
            "medium_classification": {
                "canonical_label": "Salzwasser",
                "family": "waessrig_salzhaltig",
                "confidence": "high",
                "status": "recognized",
            },
            "motion_hint": ContextHintState(
                label="rotary",
                confidence="high",
                source_turn_ref="turn:2",
                source_turn_index=2,
                source_type="deterministic_text_inference",
            ),
            "application_hint": ContextHintState(
                label="shaft_sealing",
                confidence="medium",
                source_turn_ref="turn:2",
                source_turn_index=2,
                source_type="deterministic_text_inference",
            ),
        }
    )

    tile = project_for_ui(state).assumption
    recommendation = project_for_ui(state).recommendation

    assert tile.open_points[0] == "Drehzahl der rotierenden Welle"
    assert recommendation.open_points[0] == "Drehzahl der rotierenden Welle"


def test_governance_class_a_recommendation_shows_rfq_admissible() -> None:
    tile = project_for_ui(_full_state()).recommendation

    assert tile.scope_status == "complete"
    assert tile.rfq_admissible is True


def test_governance_class_d_recommendation_shows_out_of_scope() -> None:
    state = _state_from_observed(ObservedState())

    assert project_for_ui(state).recommendation.scope_status == "out_of_scope"


def test_matching_and_rfq_tiles_stay_pending_when_unavailable() -> None:
    state = _full_state()
    projection = project_for_ui(state)

    assert projection.matching.status == "pending"
    assert projection.rfq.status == "pending"
    assert projection.rfq.rfq_admissible is True


def test_medium_context_tile_projects_orienting_context_separately() -> None:
    state = _full_state().model_copy(
        update={"medium_context": build_medium_context("Salzwasser")}
    )

    tile = project_for_ui(state).medium_context

    assert tile.status == "available"
    assert tile.medium_label == "Salzwasser"
    assert tile.scope == "orientierend"
    assert "wasserbasiert" in tile.properties
    assert tile.not_for_release_decisions is True


def test_medium_context_tile_stays_unavailable_without_medium() -> None:
    tile = project_for_ui(_state_from_observed(ObservedState())).medium_context

    assert tile.status == "unavailable"
    assert tile.medium_label is None
    assert tile.properties == []


def test_medium_classification_tile_projects_capture_and_status() -> None:
    state = _full_state().model_copy(
        update={
            "medium_capture": {
                "raw_mentions": ["salzwasser"],
                "primary_raw_text": "salzwasser",
                "source_turn_ref": "turn:1",
                "source_turn_index": 1,
            },
            "medium_classification": {
                "canonical_label": "Salzwasser",
                "family": "waessrig_salzhaltig",
                "confidence": "high",
                "status": "recognized",
                "normalization_source": "deterministic_alias_map",
                "mapping_confidence": "confirmed",
            },
        }
    )

    tile = project_for_ui(state).medium_classification
    assert tile.canonical_label == "Salzwasser"
    assert tile.family == "waessrig_salzhaltig"
    assert tile.primary_raw_text == "salzwasser"


def test_matching_tile_projects_clean_result_when_available() -> None:
    state = _full_state().model_copy(
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
    matching = project_for_ui(state).matching

    assert matching.status == "matched_primary_candidate"
    assert matching.selected_manufacturer == "Acme"
    assert matching.manufacturer_count == 1
    assert "candidate_ids" not in str(matching.model_dump())


def test_requirement_class_is_projected_without_raw_governance_class() -> None:
    state = _full_state()
    governance = state.governance.model_copy(
        update={
            "requirement_class": RequirementClass(
                class_id="PTFE10",
                description="High-temperature steam application",
            )
        }
    )
    projection = project_for_ui(state.model_copy(update={"governance": governance}))

    assert projection.recommendation.requirement_class == "PTFE10"
    assert projection.recommendation.requirement_summary == "High-temperature steam application"
    assert projection.recommendation.scope_status != "A"


def test_rfq_tile_projects_clean_result_when_available() -> None:
    state = _full_state().model_copy(
        update={
            "rfq": RfqState(
                status="rfq_ready",
                rfq_ready=True,
                rfq_admissible=True,
                selected_manufacturer_ref=ManufacturerRef(
                    manufacturer_name="Acme",
                    candidate_ids=["registry-ptfe-g25-acme"],
                ),
                recipient_refs=[RecipientRef(manufacturer_name="Acme", qualified_for_rfq=True)],
                qualified_material_ids=["registry-ptfe-g25-acme"],
                requirement_class=RequirementClass(
                    class_id="PTFE10",
                    description="High-temperature PTFE class",
                ),
                notes=["Governed output is releasable and handover-ready."],
            )
        }
    )

    rfq = project_for_ui(state).rfq

    assert rfq.status == "rfq_ready"
    assert rfq.rfq_ready is True
    assert rfq.selected_manufacturer == "Acme"
    assert rfq.recipient_count == 1
    assert rfq.qualified_material_count == 1
    assert rfq.requirement_class == "PTFE10"
    assert rfq.dispatch_ready is False
    assert "candidate_ids" not in str(rfq.model_dump())


def test_rfq_tile_includes_clean_dispatch_visibility_when_available() -> None:
    state = _full_state().model_copy(
        update={
            "rfq": RfqState(
                status="rfq_ready",
                rfq_ready=True,
                rfq_admissible=True,
                selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                recipient_refs=[RecipientRef(manufacturer_name="Acme", qualified_for_rfq=True)],
                qualified_material_ids=["registry-ptfe-g25-acme"],
                requirement_class=RequirementClass(
                    class_id="PTFE10",
                    description="High-temperature PTFE class",
                ),
            ),
            "dispatch": DispatchState(
                dispatch_ready=True,
                dispatch_status="envelope_ready",
                selected_manufacturer_ref=ManufacturerRef(manufacturer_name="Acme"),
                recipient_refs=[RecipientRef(manufacturer_name="Acme", qualified_for_rfq=True)],
                requirement_class=RequirementClass(
                    class_id="PTFE10",
                    description="High-temperature PTFE class",
                ),
                transport_channel="internal_transport_envelope",
                dispatch_notes=["Internal transport envelope is ready for later sender/connector consumption."],
            ),
        }
    )

    rfq = project_for_ui(state).rfq

    assert rfq.dispatch_ready is True
    assert rfq.dispatch_status == "envelope_ready"
    dumped = str(rfq.model_dump()).lower()
    assert "transport_channel" not in dumped
    assert "transport" not in dumped
    assert "event_id" not in dumped


def test_norm_tile_projects_clean_result_when_available() -> None:
    state = _full_state().model_copy(
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
                material=SealaiNormMaterial(
                    material_family="PTFE",
                    qualified_materials=["PTFE virgin"],
                ),
                open_validation_points=["Finale Werkstoffvalidierung durch Hersteller"],
            )
        }
    )

    norm = project_for_ui(state).norm

    assert norm.status == "rfq_ready"
    assert norm.norm_version == "sealai_norm_v1"
    assert norm.requirement_class == "PTFE10"
    assert norm.material_family == "PTFE"
    assert norm.open_points == ["Finale Werkstoffvalidierung durch Hersteller"]
    assert "partner_id" not in str(norm.model_dump())


def test_export_profile_tile_projects_clean_result_when_available() -> None:
    state = _full_state().model_copy(
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
                unresolved_points=[],
                export_notes=["Governed output is releasable and handover-ready."],
            )
        }
    )

    export_profile = project_for_ui(state).export_profile

    assert export_profile.status == "ready"
    assert export_profile.export_profile_version == "sealai_export_profile_v1"
    assert export_profile.selected_manufacturer == "Acme"
    assert export_profile.recipient_count == 1
    assert export_profile.requirement_class == "PTFE10"
    assert export_profile.rfq_ready is True
    assert export_profile.dispatch_ready is True
    assert "partner_id" not in str(export_profile.model_dump())


def test_manufacturer_mapping_tile_projects_clean_result_when_available() -> None:
    state = _full_state().model_copy(
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

    mapping = project_for_ui(state).manufacturer_mapping

    assert mapping.status == "mapped"
    assert mapping.mapping_version == "manufacturer_mapping_v1"
    assert mapping.selected_manufacturer == "Acme"
    assert mapping.mapped_product_family == "Flachdichtung"
    assert mapping.mapped_material_family == "PTFE"
    dumped = str(mapping.model_dump()).lower()
    assert "manufacturer_sku" not in dumped
    assert "candidate_id" not in dumped
    assert "compound_code" not in dumped


def test_dispatch_contract_tile_projects_clean_result_when_available() -> None:
    state = _full_state().model_copy(
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

    contract = project_for_ui(state).dispatch_contract

    assert contract.status == "ready"
    assert contract.contract_version == "dispatch_contract_v1"
    assert contract.selected_manufacturer == "Acme"
    assert contract.recipient_count == 1
    dumped = str(contract.model_dump()).lower()
    assert "transport" not in dumped
    assert "event_id" not in dumped
    assert "event_key" not in dumped
    assert "partner_id" not in dumped
