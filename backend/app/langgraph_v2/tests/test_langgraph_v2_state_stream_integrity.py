from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.api.v1.endpoints.langgraph_v2 import (
    _engineering_profile_payload,
    _build_state_update_payload,
    _event_belongs_to_current_run,
    _merge_state_like,
    _resolve_final_text,
)
from app.langgraph_v2.state import SealAIState


def test_merge_state_like_keeps_live_calc_tile_when_patch_omits_key() -> None:
    base = SealAIState(
        working_profile={
            "live_calc_tile": {
                "status": "ok",
                "v_surface_m_s": 3.2,
            }
        },
        system={"final_text": "old"},
    )
    patch = {"final_text": "new", "last_node": "answer_subgraph_node"}

    merged = _merge_state_like(base, patch)

    assert isinstance(merged, dict)
    assert merged["final_text"] == "new"
    assert merged["working_profile"]["live_calc_tile"]["status"] == "ok"
    assert merged["working_profile"]["live_calc_tile"]["v_surface_m_s"] == 3.2


def test_merge_state_like_routes_legacy_parameters_into_extracted_params() -> None:
    base = SealAIState(system={"final_text": "old"})

    merged = _merge_state_like(base, {"parameters": {"pressure_bar": 42.0}})

    assert isinstance(merged, dict)
    assert merged["working_profile"]["normalized_profile"]["pressure_bar"] == 42.0
    assert merged["working_profile"]["extracted_params"]["pressure_bar"] == 42.0
    assert "pressure_bar" not in merged["working_profile"]["engineering_profile"]


def test_flat_working_profile_payload_is_staged_not_asserted() -> None:
    state = SealAIState(working_profile={"pressure_bar": 42.0, "medium": "steam"})

    assert state.working_profile.normalized_profile["pressure_bar"] == 42.0
    assert state.working_profile.extracted_params["medium"] == "steam"
    assert state.working_profile.engineering_profile.pressure_bar is None


def test_engineering_profile_payload_ignores_nested_staging_only_payload() -> None:
    payload = _engineering_profile_payload(
        {
            "working_profile": {
                "normalized_profile": {"pressure_bar": 42.0},
                "extracted_params": {"pressure_bar": 42.0},
            }
        }
    )

    assert payload == {}


def test_extracted_params_patch_does_not_mutate_asserted_profile() -> None:
    base = SealAIState(working_profile={"engineering_profile": {"pressure_bar": 5.0}})

    merged = _merge_state_like(
        base,
        {
            "working_profile": {
                "normalized_profile": {"pressure_bar": 42.0},
                "extracted_params": {"pressure_bar": 42.0},
            }
        },
    )

    assert isinstance(merged, dict)
    assert merged["working_profile"]["engineering_profile"]["pressure_bar"] == 5.0
    assert merged["working_profile"]["normalized_profile"]["pressure_bar"] == 42.0
    assert merged["working_profile"]["extracted_params"]["pressure_bar"] == 42.0


def test_build_state_update_payload_omits_live_calc_tile_for_partial_patch() -> None:
    payload = _build_state_update_payload(
        {
            "last_node": "answer_subgraph_node",
            "final_text": "RFQ body",
            "rfq_ready": True,
        }
    )

    assert payload["type"] == "state_update"
    assert payload["data"]["rfq_ready"] is False
    assert payload["data"]["rfq_document"]["ready"] is False
    assert payload["data"]["rfq_admissibility"]["status"] == "inadmissible"
    assert "live_calc_tile" not in payload["data"]


def test_build_state_update_payload_does_not_promote_rfq_artifacts_to_ready() -> None:
    payload = _build_state_update_payload(
        {
            "last_node": "node_p6_generate_pdf",
            "final_text": "RFQ body",
            "rfq_ready": True,
            "rfq_pdf_base64": "JVBERi0xLjQK",
            "rfq_html_report": "<html>rfq</html>",
        }
    )

    assert payload["data"]["rfq_ready"] is False
    assert payload["data"]["rfq_document"] == {
        "ready": False,
        "has_pdf_base64": True,
        "has_pdf_url": False,
        "has_html_report": True,
    }
    assert payload["data"]["rfq_admissibility"]["status"] == "inadmissible"
    assert payload["data"]["rfq_admissibility"]["reason"] == "legacy_rfq_ready_ignored_without_contract"
    assert "rfq_pdf_base64" not in payload["data"]
    assert "rfq_html_report" not in payload["data"]


def test_build_state_update_payload_uses_rfq_contract_as_source_of_truth() -> None:
    payload = _build_state_update_payload(
        {
            "system": {
                "rfq_admissibility": {
                    "status": "ready",
                    "reason": None,
                    "open_points": [],
                    "blockers": [],
                    "governed_ready": True,
                    "derived_from_assertion_cycle_id": 7,
                    "derived_from_assertion_revision": 9,
                }
            }
        }
    )

    assert payload["data"]["rfq_ready"] is True
    assert payload["data"]["rfq_document"]["ready"] is True
    assert payload["data"]["rfq_admissibility"]["derived_from_assertion_cycle_id"] == 7
    assert payload["data"]["rfq_admissibility"]["derived_from_assertion_revision"] == 9


def test_build_state_update_payload_exposes_candidate_specificity_from_contract() -> None:
    payload = _build_state_update_payload(
        {
            "system": {
                "answer_contract": {
                    "resolved_parameters": {},
                    "calc_results": {},
                    "selected_fact_ids": [],
                    "candidate_semantics": [
                        {
                            "kind": "material",
                            "value": "Technical datasheet",
                            "specificity": "family_only",
                            "source_kind": "retrieval",
                            "governed": False,
                            "confidence": 0.6,
                        }
                    ],
                    "required_disclaimers": [],
                    "respond_with_uncertainty": False,
                }
            }
        }
    )

    assert payload["data"]["candidate_semantics"][0]["value"] == "Technical datasheet"
    assert payload["data"]["candidate_semantics"][0]["specificity"] == "family_only"
    assert payload["data"]["candidate_semantics"][0]["governed"] is False


def test_build_state_update_payload_exposes_governance_metadata() -> None:
    payload = _build_state_update_payload(
        {
            "system": {
                "governed_output_text": "Freigegebene Antwort",
                "governed_output_ready": True,
                "governance_metadata": {
                    "scope_of_validity": ["Nur fuer den aktuellen Assertion-Stand."],
                    "assumptions_active": ["Annahme A"],
                    "unknowns_release_blocking": ["Druckstufe ungeklaert"],
                    "unknowns_manufacturer_validation": ["PTFE nur family_level"],
                    "gate_failures": ["CRITICAL: Druckstufe ungeklaert"],
                    "governance_notes": ["Human review required before external release."],
                },
            }
        }
    )

    assert payload["data"]["governance_metadata"]["scope_of_validity"] == ["Nur fuer den aktuellen Assertion-Stand."]
    assert payload["data"]["governance_metadata"]["unknowns_release_blocking"] == ["Druckstufe ungeklaert"]
    assert payload["governance_metadata"]["gate_failures"] == ["CRITICAL: Druckstufe ungeklaert"]


def test_build_state_update_payload_exposes_rfq_projection_objects() -> None:
    payload = _build_state_update_payload(
        {
            "system": {
                "sealing_requirement_spec": {
                    "spec_id": "SRS-1",
                    "material_specificity_required": "family_only",
                    "operating_envelope": {"pressure_bar": 10},
                },
                "rfq_draft": {
                    "rfq_id": "RFQ-1",
                    "rfq_basis_status": "provisional",
                    "buyer_contact": {"company": "SealAI Test GmbH"},
                },
                "rfq_confirmed": True,
            }
        }
    )

    assert payload["data"]["sealing_requirement_spec"]["spec_id"] == "SRS-1"
    assert payload["data"]["rfq_draft"]["rfq_id"] == "RFQ-1"
    assert payload["data"]["rfq_confirmed"] is True
    assert payload["sealing_requirement_spec"]["operating_envelope"]["pressure_bar"] == 10
    assert payload["rfq_draft"]["buyer_contact"]["company"] == "SealAI Test GmbH"


def test_resolve_final_text_does_not_promote_latest_ai_message_without_governance() -> None:
    state = SealAIState(
        conversation={
            "messages": [
                HumanMessage(content="Bitte RFQ erstellen"),
                AIMessage(content="RFQ final text from message"),
            ]
        },
    )

    assert _resolve_final_text(state) == ""


def test_resolve_final_text_prefers_governed_output_text() -> None:
    state = SealAIState(
        system={
            "preview_text": "Vorlaeufiger Entwurf",
            "governed_output_text": "Freigegebene Antwort",
            "governed_output_ready": True,
        }
    )

    assert _resolve_final_text(state) == "Freigegebene Antwort"


def test_build_state_update_payload_does_not_promote_preview_text_to_final() -> None:
    payload = _build_state_update_payload(
        {
            "last_node": "reasoning_core_node",
            "system": {
                "preview_text": "Vorlaeufige Antwort",
            },
        }
    )

    assert payload["data"]["preview_text"] == "Vorlaeufige Antwort"
    assert "final_text" not in payload["data"]


def test_build_state_update_payload_skips_default_insufficient_live_tile() -> None:
    state = SealAIState(
        reasoning={"last_node": "answer_subgraph_node", "rfq_ready": True},
        system={"final_text": "RFQ body"},
    )

    payload = _build_state_update_payload(state)

    assert payload["type"] == "state_update"
    assert payload["data"]["rfq_ready"] is False
    assert payload["data"]["rfq_document"]["ready"] is False
    assert payload["data"]["rfq_admissibility"]["status"] == "inadmissible"
    # User Directive: live_calc_tile should NOT be filtered if present.
    # Since SealAIState has a default_factory for live_calc_tile, it is now included.
    assert "live_calc_tile" in payload["data"]


def test_resolve_final_text_does_not_reuse_old_ai_text_before_latest_user() -> None:
    state = SealAIState(
        conversation={
            "messages": [
                HumanMessage(content="Erster Prompt"),
                AIMessage(content="Alte Antwort"),
                HumanMessage(content="Bitte Lastenheft erstellen"),
            ]
        },
    )

    assert _resolve_final_text(state) == ""


def test_event_belongs_to_current_run_filters_mismatched_metadata_run_id() -> None:
    event = {"metadata": {"run_id": "run-old"}}

    assert _event_belongs_to_current_run(event, "run-current") is False
    assert _event_belongs_to_current_run(event, "run-old") is True
