from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.agent.api.dispatch import _contextualized_knowledge_message
from app.agent.domain.fit_score import rank_manufacturers
from app.agent.state.models import (
    DispatchContractState,
    DispatchState,
    ExportProfileState,
    GovernedSessionState,
    ManufacturerMappingState,
    ManufacturerRef,
    MatchingState,
    ObservedExtraction,
    ObservedState,
    RecipientRef,
    RequirementClass,
    RfqState,
    SealaiNormIdentity,
    SealaiNormMaterial,
    SealaiNormOperatingConditions,
    SealaiNormState,
)
from app.agent.state.projections import project_for_ui
from app.agent.state.reducers import (
    reduce_asserted_to_governance,
    reduce_normalized_to_asserted,
    reduce_observed_to_normalized,
)
from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge_service import KnowledgeService
from app.services.pre_gate_classifier import PreGateClassifier


_GOVERNED_FALLBACK_TEXT = (
    "Ich kann diesen Schritt gerade nicht sicher in den geregelten Fallfluss geben"
)

_MANUFACTURERS_PATH = (
    Path(__file__).parent.parent / "data" / "manufacturers" / "pilot_manufacturers.json"
)


@dataclass(frozen=True, slots=True)
class JourneyTurn:
    phase: str
    message: str
    expected_classification: PreGateClassification
    expected_escalate_to_graph: bool


FULL_SOLUTION_JOURNEY: tuple[JourneyTurn, ...] = (
    JourneyTurn(
        phase="greeting",
        message="Moin",
        expected_classification=PreGateClassification.GREETING,
        expected_escalate_to_graph=False,
    ),
    JourneyTurn(
        phase="open_case_intent",
        message="Ich möchte mit dir eine Dichtungslösung entwickeln.",
        expected_classification=PreGateClassification.DOMAIN_INQUIRY,
        expected_escalate_to_graph=True,
    ),
    JourneyTurn(
        phase="case_facts",
        message=(
            "Es geht um eine Pharma-Pumpe mit PTFE O-Ring, Welle 30 mm, "
            "Dampf/CIP, 120 °C und 5 bar."
        ),
        expected_classification=PreGateClassification.DOMAIN_INQUIRY,
        expected_escalate_to_graph=True,
    ),
    JourneyTurn(
        phase="request_rfq_summary",
        message="Bitte fasse die Anfragebasis für den Hersteller zusammen.",
        expected_classification=PreGateClassification.DOMAIN_INQUIRY,
        expected_escalate_to_graph=True,
    ),
    JourneyTurn(
        phase="select_best_fit_candidate",
        message="Welcher Hersteller ist auf Basis der Falldaten der passendste Kandidat?",
        expected_classification=PreGateClassification.DOMAIN_INQUIRY,
        expected_escalate_to_graph=True,
    ),
    JourneyTurn(
        phase="create_rfq_handover",
        message="Erstelle bitte die Anfrage an den ausgewählten Hersteller.",
        expected_classification=PreGateClassification.DOMAIN_INQUIRY,
        expected_escalate_to_graph=True,
    ),
)


def test_full_solution_journey_question_suite_routes_each_phase() -> None:
    classifier = PreGateClassifier()

    for turn in FULL_SOLUTION_JOURNEY:
        result = classifier.classify(turn.message)
        assert result.classification is turn.expected_classification, turn.phase
        assert result.escalate_to_graph is turn.expected_escalate_to_graph, turn.phase


def test_free_manufacturer_recommendation_stays_blocked_but_case_bound_selection_enters_governed() -> None:
    classifier = PreGateClassifier()

    free_recommendation = classifier.classify("Welchen Hersteller empfiehlst du?")
    assert free_recommendation.classification is PreGateClassification.BLOCKED
    assert free_recommendation.escalate_to_graph is False

    case_bound_selection = classifier.classify(
        "Welcher Hersteller ist auf Basis der vorhandenen Falldaten der passendste Kandidat?"
    )
    assert case_bound_selection.classification is PreGateClassification.DOMAIN_INQUIRY
    assert case_bound_selection.escalate_to_graph is True
    assert case_bound_selection.reasoning == "deterministic_governed_manufacturer_handover"


def test_journey_can_start_with_free_knowledge_then_continue_into_case() -> None:
    history: list[dict[str, str]] = []
    first_question = "Bitte gib mir zuerst Informationen zu PTFE."

    route = PreGateClassifier().classify(first_question)
    assert route.classification is PreGateClassification.KNOWLEDGE_QUERY
    assert route.escalate_to_graph is False

    answer = KnowledgeService().answer(first_question)
    assert answer.no_case_created is True
    assert _GOVERNED_FALLBACK_TEXT not in answer.content
    assert "PTFE" in answer.content

    history.append({"role": "user", "content": first_question})
    history.append({"role": "assistant", "content": answer.content})
    follow_up = _contextualized_knowledge_message(
        "und was ist mit PEEK?",
        recent_history=tuple(history),
    )
    follow_up_answer = KnowledgeService().answer(follow_up)
    assert follow_up_answer.no_case_created is True
    assert "PEEK" in follow_up_answer.content

    case_turn = PreGateClassifier().classify(
        "Jetzt konkret: Pharma-Pumpe, Dampf/CIP, PTFE O-Ring, 120 °C, 5 bar, Welle 30 mm."
    )
    assert case_turn.classification is PreGateClassification.DOMAIN_INQUIRY
    assert case_turn.escalate_to_graph is True


def test_deterministic_manufacturer_selection_rfq_projection_and_export_contract_are_clean() -> None:
    manufacturers = json.loads(_MANUFACTURERS_PATH.read_text())
    derived = {
        "pressure_bar": 5.0,
        "temp_c": 120.0,
        "detected_industries": ["pharma", "lebensmittel"],
        "sealing_type": "STS-TYPE-OR-A",
        "material": "STS-MAT-PTFE-A1",
    }
    normalized = {
        "shaft_diameter_mm": 30.0,
        "sealing_type": "STS-TYPE-OR-A",
        "material": "STS-MAT-PTFE-A1",
    }

    ranked = rank_manufacturers(manufacturers, derived, normalized)
    top_score, top_manufacturer = ranked[0]
    assert top_manufacturer["id"] == "mfr-002"
    assert top_manufacturer["name"] == "PharmaSeal Südwest GmbH"
    assert top_score > 0.75

    state = _governed_pharma_o_ring_state()
    selected_ref = ManufacturerRef(
        manufacturer_name=top_manufacturer["name"],
        candidate_ids=[top_manufacturer["id"]],
        material_families=["PTFE"],
        capability_hints=[f"deterministic_fit_score={top_score}"],
        source_refs=["pilot_manufacturers.json"],
        qualified_for_rfq=True,
    )
    requirement_class = RequirementClass(
        class_id="PTFE-OR-PHARMA-CIP",
        description="PTFE O-Ring inquiry basis for pharma/CIP operating window",
        seal_type="O-Ring",
    )
    application_summary = "Pharma-Pumpe, Dampf/CIP, PTFE O-Ring, 120 C, 5 bar, Welle 30 mm"

    state = state.model_copy(
        update={
            "matching": MatchingState(
                status="matched_primary_candidate",
                matchability_status="ready_for_matching",
                shortlist_ready=True,
                inquiry_ready=True,
                selected_manufacturer_ref=selected_ref,
                manufacturer_refs=[selected_ref],
                matching_notes=[
                    "Deterministic manufacturer ranking uses fit_score; not a final release.",
                ],
            ),
            "rfq": RfqState(
                status="rfq_ready",
                rfq_ready=True,
                rfq_admissible=True,
                critical_review_status="prequalified",
                critical_review_passed=True,
                selected_manufacturer_ref=selected_ref,
                recipient_refs=[
                    RecipientRef(
                        manufacturer_name=top_manufacturer["name"],
                        qualified_for_rfq=True,
                    )
                ],
                qualified_material_ids=["STS-MAT-PTFE-A1"],
                confirmed_parameters=derived | normalized,
                dimensions={"shaft_diameter_mm": 30.0},
                requirement_class=requirement_class,
                handover_summary=application_summary,
                notes=[
                    "RFQ handover is a governed inquiry basis; manufacturer validation remains required.",
                ],
            ),
            "dispatch": DispatchState(
                dispatch_ready=True,
                dispatch_status="envelope_ready",
                selected_manufacturer_ref=selected_ref,
                recipient_refs=[
                    RecipientRef(
                        manufacturer_name=top_manufacturer["name"],
                        qualified_for_rfq=True,
                    )
                ],
                requirement_class=requirement_class,
                transport_channel="internal_transport_envelope",
                handover_summary=application_summary,
                dispatch_notes=[
                    "Connector-ready handover exists, but no automatic external send is asserted.",
                ],
            ),
            "sealai_norm": SealaiNormState(
                status="rfq_ready",
                identity=SealaiNormIdentity(
                    sealai_request_id="sealai-v10-journey-001",
                    requirement_class_id=requirement_class.class_id,
                    engineering_path="o_ring",
                    seal_family="O-Ring",
                ),
                application_summary=application_summary,
                operating_conditions=SealaiNormOperatingConditions(
                    medium="Dampf/CIP",
                    temperature_c=120.0,
                    pressure_bar=5.0,
                    dynamic_type="static_or_low_dynamic_seal_context",
                ),
                geometry={"shaft_diameter_mm": 30.0},
                material=SealaiNormMaterial(
                    material_family="PTFE",
                    sealing_material_family="PTFE",
                    qualified_materials=["STS-MAT-PTFE-A1"],
                ),
                open_validation_points=["Finale Werkstoff- und Compoundvalidierung durch Hersteller"],
                manufacturer_validation_required=True,
            ),
            "export_profile": ExportProfileState(
                status="ready",
                sealai_request_id="sealai-v10-journey-001",
                selected_manufacturer=top_manufacturer["name"],
                recipient_refs=[top_manufacturer["name"]],
                requirement_class_id=requirement_class.class_id,
                application_summary=application_summary,
                dimensions_summary=["shaft_diameter_mm=30.0"],
                material_summary="PTFE / STS-MAT-PTFE-A1",
                rfq_ready=True,
                dispatch_ready=True,
                unresolved_points=["Herstellerfreigabe und konkrete Compounddaten"],
                export_notes=["No SKU or final approval is inferred."],
            ),
            "manufacturer_mapping": ManufacturerMappingState(
                status="mapped",
                selected_manufacturer=top_manufacturer["name"],
                mapped_product_family="O-Ring",
                mapped_material_family="PTFE",
                geometry_export_hint="shaft_diameter_mm=30.0",
                mapping_notes=[
                    "Mapping remains manufacturer-neutral; no product article is selected.",
                ],
            ),
            "dispatch_contract": DispatchContractState(
                status="ready",
                sealai_request_id="sealai-v10-journey-001",
                selected_manufacturer=top_manufacturer["name"],
                recipient_refs=[top_manufacturer["name"]],
                requirement_class_id=requirement_class.class_id,
                application_summary=application_summary,
                material_summary="PTFE / STS-MAT-PTFE-A1",
                dimensions_summary=["shaft_diameter_mm=30.0"],
                rfq_ready=True,
                dispatch_ready=True,
                unresolved_points=["Herstellerfreigabe und konkrete Compounddaten"],
                mapping_summary="material_family=PTFE; product_family=O-Ring",
                handover_notes=["System-neutral handover; no external transport event is emitted."],
            ),
        }
    )

    projection = project_for_ui(state)

    assert projection.matching.status == "matched_primary_candidate"
    assert projection.matching.selected_manufacturer == top_manufacturer["name"]
    assert projection.rfq.status == "rfq_ready"
    assert projection.rfq.rfq_ready is True
    assert projection.rfq.dispatch_ready is True
    assert projection.rfq.dispatch_status == "envelope_ready"
    assert projection.export_profile.selected_manufacturer == top_manufacturer["name"]
    assert projection.dispatch_contract.selected_manufacturer == top_manufacturer["name"]

    visible_projection = str(projection.model_dump()).lower()
    assert "candidate_ids" not in visible_projection
    assert "transport_channel" not in visible_projection
    assert "event_id" not in visible_projection
    assert "final approval is granted" not in visible_projection
    assert "freigegeben" not in visible_projection


def _governed_pharma_o_ring_state() -> GovernedSessionState:
    observed = ObservedState()
    for field_name, raw_value, confidence in (
        ("medium", "Dampf/CIP", 0.95),
        ("pressure_bar", 5.0, 0.95),
        ("temperature_c", 120.0, 0.95),
        ("material", "PTFE", 0.9),
        ("application", "Pharma-Pumpe", 0.85),
        ("sealing_type", "O-Ring", 0.8),
        ("shaft_diameter_mm", 30.0, 0.9),
    ):
        observed = observed.with_extraction(
            ObservedExtraction(
                field_name=field_name,
                raw_value=raw_value,
                source="llm",
                confidence=confidence,
                turn_index=1,
            )
        )
    normalized = reduce_observed_to_normalized(observed)
    asserted = reduce_normalized_to_asserted(normalized)
    governance = reduce_asserted_to_governance(asserted)
    return GovernedSessionState(
        observed=observed,
        normalized=normalized,
        asserted=asserted,
        governance=governance,
    )
