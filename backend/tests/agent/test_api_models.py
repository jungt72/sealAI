import pytest
from pydantic import ValidationError
from app.agent.api.models import (
    CaseActionResponse,
    ChatRequest,
    ChatResponse,
    QualifiedActionAuditEventResponse,
    QualifiedActionContract,
    QualifiedActionStatusResponse,
)
from app.agent.domain.rwdr import RWDRSelectorInputDTO, RWDRSelectorInputPatchDTO, RWDRSelectorOutputDTO
from app.agent.case_state import _build_visible_delta_status, _build_visible_qualification_status, build_visible_case_narrative

def test_chat_request_valid():
    """
    Test: Gültige ChatRequest-Instanziierung.
    """
    req = ChatRequest(message="Hallo", session_id="session-1")
    assert req.message == "Hallo"
    assert req.session_id == "session-1"

def test_chat_request_default_session():
    """
    Test: ChatRequest nutzt Standardwert für session_id.
    """
    req = ChatRequest(message="Hallo")
    assert req.session_id == "default"

def test_chat_request_empty_message():
    """
    Test: ChatRequest lehnt leere Nachrichten ab (min_length=1).
    """
    with pytest.raises(ValidationError):
        ChatRequest(message="")

def test_chat_request_extra_fields():
    """
    Test: ChatRequest lehnt unbekannte Felder ab (extra="forbid").
    """
    with pytest.raises(ValidationError):
        ChatRequest(message="Hallo", unknown_field="Ups")

def test_chat_response_valid():
    """
    Test: Gültige ChatResponse-Instanziierung.
    """
    res = ChatResponse(
        reply="Hallo zurück",
        session_id="session-123",
        interaction_class="structured_case",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        has_case_state=False,
    )
    assert res.reply == "Hallo zurück"
    assert res.session_id == "session-123"

def test_chat_response_extra_fields():
    """
    Test: ChatResponse lehnt unbekannte Felder ab (extra="forbid").
    """
    with pytest.raises(ValidationError):
        ChatResponse(
            reply="Antwort",
            session_id="id",
            extra="unzulässig"
        )


def test_chat_request_accepts_rwdr_input_contract():
    req = ChatRequest(
        message="Bitte RWDR vorselektieren",
        rwdr_input=RWDRSelectorInputDTO(
            motion_type="single_direction_rotation",
            shaft_diameter_mm=35.0,
            max_speed_rpm=2800.0,
            pressure_profile="light_pressure_upto_0_5_bar",
            inner_lip_medium_scenario="oil_bath",
            maintenance_mode="new_shaft",
            confidence={"pressure_profile": "known"},
        ),
    )

    assert req.rwdr_input is not None
    assert req.rwdr_input.shaft_diameter_mm == 35.0


def test_chat_request_accepts_rwdr_input_patch_contract():
    req = ChatRequest(
        message="RWDR weiterfuehren",
        rwdr_input_patch=RWDRSelectorInputPatchDTO(
            max_speed_rpm=2800.0,
            pressure_profile="light_pressure_upto_0_5_bar",
            confidence={"pressure_profile": "known"},
        ),
    )

    assert req.rwdr_input_patch is not None
    assert req.rwdr_input_patch.max_speed_rpm == 2800.0


def test_chat_response_accepts_rwdr_output_contract():
    res = ChatResponse(
        reply="RWDR-Struktur erfasst",
        session_id="session-123",
        interaction_class="structured_case",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        has_case_state=False,
        rwdr_output=RWDRSelectorOutputDTO(
            type_class="rwdr_with_dust_lip",
            modifiers=["installation_sleeve_required"],
            warnings=[],
            review_flags=["review_due_to_geometry"],
            hard_stop=None,
            reasoning=["API contract exposes typed RWDR output."],
        ),
    )

    assert res.rwdr_output is not None
    assert res.rwdr_output.review_flags == ["review_due_to_geometry"]


def test_chat_response_accepts_typed_governed_output_contracts():
    res = ChatResponse(
        reply="Strukturierter Pfad aktiv",
        session_id="session-456",
        interaction_class="structured_case",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="QUALIFIED_PRESELECTION",
        has_case_state=True,
        qualified_action_gate={
            "action": "download_rfq",
            "allowed": False,
            "rfq_ready": False,
            "binding_level": "ORIENTATION",
            "source_type": "deterministic_governance",
            "source_ref": "case_state.qualified_action_gate",
            "block_reasons": ["missing_medium"],
            "summary": "qualified_action_blocked",
        },
        case_state={
            "case_meta": {
                "analysis_cycle_id": "session_test_1",
                "state_revision": 1,
                "runtime_path": "STRUCTURED_QUALIFICATION",
                "binding_level": "QUALIFIED_PRESELECTION",
            },
            "result_contract": {
                "analysis_cycle_id": "session_test_1",
                "state_revision": 1,
                "binding_level": "ORIENTATION",
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "scope_of_validity": None,
                "contract_obsolete": False,
                "invalidation_requires_recompute": False,
                "invalidation_reasons": [],
                "qualified_action": {
                    "action": "download_rfq",
                    "allowed": False,
                    "rfq_ready": False,
                    "binding_level": "ORIENTATION",
                    "summary": "qualified_action_blocked",
                    "block_reasons": [],
                },
                "evidence_ref_count": 0,
                "evidence_refs": [],
                "source_ref": "case_state.default_result_contract",
            },
            "candidate_clusters": [],
            "sealing_requirement_spec": {
                "contract_type": "sealing_requirement_spec",
                "contract_version": "sealing_requirement_spec_v1",
                "rendering_status": "not_wired",
                "rendering_message": "Structured sealing requirement spec is available. File export/rendering is not wired yet.",
                "analysis_cycle_id": "session_test_1",
                "state_revision": 1,
                "binding_level": "ORIENTATION",
                "runtime_path": "STRUCTURED_QUALIFICATION",
                "release_status": "inadmissible",
                "rfq_admissibility": "inadmissible",
                "specificity_level": "family_only",
                "scope_of_validity": None,
                "contract_obsolete": False,
                "qualified_action": {
                    "action": "download_rfq",
                    "allowed": False,
                    "rfq_ready": False,
                    "binding_level": "ORIENTATION",
                    "summary": "qualified_action_blocked",
                    "block_reasons": [],
                },
                "selection_snapshot": None,
                "candidate_clusters": [],
                "render_artifact": {
                    "artifact_type": "sealing_requirement_spec_markdown",
                    "artifact_version": "sealing_requirement_spec_render_v1",
                    "mime_type": "text/markdown",
                    "filename": "sealing-requirement-spec-session-test-1.md",
                    "content": "# Sealing Requirement Spec",
                    "source_ref": "case_state.default_rendered_sealing_requirement_spec",
                },
                "source_ref": "case_state.default_sealing_requirement_spec",
            },
            "qualified_action_gate": {
                "action": "download_rfq",
                "allowed": False,
                "rfq_ready": False,
                "binding_level": "ORIENTATION",
                "source_type": "deterministic_governance",
                "source_ref": "case_state.qualified_action_gate",
                "block_reasons": ["missing_medium"],
                "summary": "qualified_action_blocked",
            },
            "qualified_action_history": [],
        },
        visible_case_narrative={
            "governed_summary": "Aktuelle technische Richtung: No active technical direction.",
            "technical_direction": [
                {
                    "key": "technical_direction_current",
                    "label": "Current Direction",
                    "value": "No active technical direction",
                    "detail": None,
                    "severity": "low",
                },
                {
                    "key": "technical_direction_authority",
                    "label": "Direction Authority",
                    "value": "No active direction authority",
                    "detail": None,
                    "severity": "low",
                }
            ],
            "validity_envelope": [],
            "next_best_inputs": [],
            "suggested_next_questions": [],
            "failure_analysis": [],
            "case_summary": [],
            "qualification_status": [],
        },
    )

    assert res.qualified_action_gate is not None
    assert res.qualified_action_gate.source_ref == "case_state.qualified_action_gate"
    assert res.case_state is not None
    assert res.case_state.case_meta is not None
    assert res.case_state.case_meta.state_revision == 1
    assert res.case_state.raw_inputs == {}
    assert res.case_state.derived_calculations == {}
    assert res.case_state.engineering_signals == {}
    assert res.case_state.qualification_results == {}
    assert res.case_state.audit_trail == []
    assert res.visible_case_narrative is not None
    assert res.visible_case_narrative.governed_summary.startswith("Aktuelle technische Richtung")


def test_case_action_response_accepts_rendered_spec_artifact():
    response = CaseActionResponse(
        case_id="rfq-case-1",
        action="download_rfq",
        allowed=True,
        executed=True,
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="RFQ_BASIS",
        action_payload={
            "sealing_requirement_spec": {
                "contract_type": "sealing_requirement_spec",
                "contract_version": "sealing_requirement_spec_v1",
                "rendering_status": "not_wired",
                "rendering_message": "Structured sealing requirement spec is available. File export/rendering is not wired yet.",
                "analysis_cycle_id": "cycle-3",
                "state_revision": 3,
                "binding_level": "RFQ_BASIS",
                "runtime_path": "STRUCTURED_QUALIFICATION",
                "release_status": "rfq_ready",
                "rfq_admissibility": "ready",
                "specificity_level": "compound_required",
                "scope_of_validity": ["material_selection_projection"],
                "contract_obsolete": False,
                "qualified_action": {
                    "action": "download_rfq",
                    "allowed": True,
                    "rfq_ready": True,
                    "binding_level": "RFQ_BASIS",
                    "summary": "qualified_action_enabled",
                    "block_reasons": [],
                },
                "selection_snapshot": {
                    "winner_candidate_id": "ptfe::g25::acme",
                    "direction_authority": "governed_authority",
                    "viable_candidate_ids": ["ptfe::g25::acme"],
                    "qualified_candidate_ids": ["ptfe::g25::acme"],
                    "candidate_source_origin": "promoted_registry",
                    "output_blocked": False,
                    "material_direction_contract": {
                        "authority_layer": "governed_authority",
                        "direction_layer": "governed_direction",
                        "source_provenance": "promoted_registry",
                    },
                },
                "candidate_clusters": [],
                "render_artifact": {
                    "artifact_type": "sealing_requirement_spec_markdown",
                    "artifact_version": "sealing_requirement_spec_render_v1",
                    "mime_type": "text/markdown",
                    "filename": "sealing-requirement-spec-cycle-3.md",
                    "content": "# Sealing Requirement Spec",
                    "source_ref": "case_state.rendered_sealing_requirement_spec",
                },
                "source_ref": "case_state.sealing_requirement_spec",
            },
            "contract_version": "sealing_requirement_spec_v1",
            "rendering_status": "rendered",
            "message": "Deterministic markdown artifact generated from sealing_requirement_spec.",
            "render_artifact": {
                "artifact_type": "sealing_requirement_spec_markdown",
                "artifact_version": "sealing_requirement_spec_render_v1",
                "mime_type": "text/markdown",
                "filename": "sealing-requirement-spec-cycle-3.md",
                "content": "# Sealing Requirement Spec",
                "source_ref": "case_state.rendered_sealing_requirement_spec",
            },
        },
    )

    assert response.action_payload is not None
    assert response.action_payload.render_artifact.filename == "sealing-requirement-spec-cycle-3.md"
    assert response.action_payload.render_artifact.mime_type == "text/markdown"
    assert response.action_payload.sealing_requirement_spec.selection_snapshot is not None
    assert response.action_payload.sealing_requirement_spec.selection_snapshot.material_direction_contract is not None
    assert (
        response.action_payload.sealing_requirement_spec.selection_snapshot.material_direction_contract.authority_layer
        == "governed_authority"
    )


def test_qualified_action_contract_rejects_unknown_action_identifier():
    with pytest.raises(ValidationError):
        QualifiedActionContract(
            action="download_rfq_artifact",
            allowed=True,
            rfq_ready=True,
            binding_level="RFQ_BASIS",
            summary="qualified_action_enabled",
            block_reasons=[],
        )


def test_qualified_action_status_rejects_unknown_lifecycle_status():
    with pytest.raises(ValidationError):
        QualifiedActionStatusResponse(
            action="download_rfq",
            last_status="pending",
            allowed_at_execution_time=False,
            executed=False,
            block_reasons=[],
            timestamp="2026-03-13T00:00:00+00:00",
            binding_level="ORIENTATION",
            runtime_path="STRUCTURED_QUALIFICATION",
            source_ref="api.agent.actions.download_rfq_action",
            current_gate_allows_action=False,
        )


def test_qualified_action_audit_event_rejects_legacy_event_type():
    with pytest.raises(ValidationError):
        QualifiedActionAuditEventResponse(
            event_type="qualified_action_executed",
            timestamp="2026-03-13T00:00:00+00:00",
            source_ref="api.agent.actions",
            details={
                "action": "download_rfq",
                "status": "executed",
                "executed": True,
                "block_reasons": [],
            },
        )


# ---------------------------------------------------------------------------
# Whitebox tests: _build_visible_qualification_status delta-reuse contract
# ---------------------------------------------------------------------------

def test_build_visible_qualification_status_uses_precomputed_delta_status():
    """
    Verify that _build_visible_qualification_status() uses the pre-computed
    delta_status passed as a parameter instead of recomputing it.
    This enforces the single-condensation contract: _build_visible_delta_status()
    must be called exactly once per narrative cycle (in build_visible_case_narrative),
    and the result must be reused — not independently recalculated.
    """
    active_case_state = {
        "qualification_results": {},
        "result_contract": {
            "rfq_admissibility": "inadmissible",
            "invalidation_requires_recompute": True,
        },
        "readiness": {},
        "invalidation_state": {
            "requires_recompute": True,
            "recompute_reasons": ["medium_changed"],
        },
    }
    precomputed = _build_visible_delta_status(
        invalidation_state=active_case_state["invalidation_state"],
        result_contract=active_case_state["result_contract"],
    )
    assert precomputed is not None, "Pre-computed delta_status must be non-None for recompute=True state"
    assert precomputed["key"] == "delta_impact"

    items = _build_visible_qualification_status(
        active_case_state=active_case_state,
        binding_level="ORIENTATION",
        delta_status=precomputed,
    )
    delta_item = next((i for i in items if i["key"] == "delta_impact"), None)
    assert delta_item is not None, "delta_impact must appear in qualification_status"
    # The item must be the exact same object that was pre-computed (identity reuse).
    assert delta_item is precomputed, (
        "delta_impact in qualification_status must be the pre-computed instance, "
        "not an independently recomputed one"
    )


def test_build_visible_qualification_status_fallback_computes_delta_when_not_passed():
    """
    Verify the defensive fallback: when delta_status=None (legacy/test call),
    _build_visible_qualification_status() still computes delta from invalidation_state.
    This ensures backward compatibility of the parameter signature change.
    """
    active_case_state = {
        "qualification_results": {},
        "result_contract": {
            "rfq_admissibility": "inadmissible",
            "invalidation_requires_recompute": True,
        },
        "readiness": {},
        "invalidation_state": {
            "requires_recompute": True,
            "recompute_reasons": ["provider_contract_changed"],
        },
    }
    # Call without passing delta_status — must fall back to internal computation.
    items = _build_visible_qualification_status(
        active_case_state=active_case_state,
        binding_level="ORIENTATION",
    )
    delta_item = next((i for i in items if i["key"] == "delta_impact"), None)
    assert delta_item is not None, "Fallback must still produce delta_impact when delta_status not passed"
    assert delta_item["value"] == "Qualification affected"
    assert delta_item["severity"] == "high"


def test_build_visible_case_narrative_delta_status_identity_consistency():
    """
    Blackbox call-site contract: build_visible_case_narrative() must compute
    delta_status exactly once and place the same object at both:
      - narrative["delta_status"]          (top-level delta field)
      - narrative["qualification_status"]  (embedded delta_impact item)
    This proves the call-site wiring at L980/L996/L1009 of case_state.py, which
    the whitebox sub-function tests cannot cover.
    """
    case_state = {
        "qualification_results": {},
        "result_contract": {
            "rfq_admissibility": "inadmissible",
            "invalidation_requires_recompute": True,
        },
        "readiness": {},
        "invalidation_state": {
            "requires_recompute": True,
            "recompute_reasons": ["medium_changed"],
        },
        "case_meta": {"binding_level": "ORIENTATION"},
    }
    narrative = build_visible_case_narrative(state={}, case_state=case_state)

    top_level_delta = narrative.get("delta_status")
    assert top_level_delta is not None, "delta_status must be set at narrative top level"
    assert top_level_delta["key"] == "delta_impact"

    qs_delta = next(
        (i for i in narrative.get("qualification_status", []) if i["key"] == "delta_impact"),
        None,
    )
    assert qs_delta is not None, "delta_impact must appear in qualification_status"
    assert qs_delta is top_level_delta, (
        "delta_impact in qualification_status must be the identical object as "
        "narrative['delta_status'] — single condensation call-site contract"
    )
