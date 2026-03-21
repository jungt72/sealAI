from __future__ import annotations

import pytest
from app._legacy_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app._legacy_v2.nodes.answer_subgraph.node_finalize import node_finalize
from app._legacy_v2.state.sealai_state import SealAIState, AnswerContract, RFQDraft, GovernanceMetadata
from app._legacy_v2.state.governance_types import ReleaseStatus

def test_answer_contract_contains_v12_mandatory_fields():
    state = SealAIState(
        reasoning={
            "current_assertion_cycle_id": 5,
            "asserted_profile_revision": 12,
            "flags": {"is_safety_critical": True}
        },
        working_profile={"engineering_profile": {"medium": "Wasser", "pressure_bar": 10.0}}
    )

    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]

    assert isinstance(contract, AnswerContract)
    assert contract.contract_id == "contract-c5-r12"
    assert contract.snapshot_parent_revision == 12
    assert contract.release_status in ["inadmissible", "precheck_only", "manufacturer_validation_required", "rfq_ready"]
    assert contract.rfq_admissibility is not None
    assert contract.rfq_admissibility.derived_from_assertion_cycle_id == 5

def test_inadmissible_release_status_prevents_rfq_draft_generation():
    # Setup state that is inadmissible (e.g. missing critical params)
    state = SealAIState(
        system={
            "answer_contract": AnswerContract(
                release_status="inadmissible",
                rfq_admissibility={"status": "inadmissible", "blockers": ["missing_pressure"]}
            ),
            "draft_text": "Verified answer draft"
        },
        reasoning={"phase": "final"}
    )

    patch = node_finalize(state)
    
    assert patch["system"]["rfq_draft"] is None
    # Ensure it's explicitly None in the patch to overwrite any previous draft if necessary
    assert "rfq_draft" in patch["system"]

def test_rfq_ready_release_status_allows_rfq_draft_generation():
    state = SealAIState(
        system={
            "answer_contract": AnswerContract(
                release_status="rfq_ready",
                rfq_admissibility={"status": "ready", "governed_ready": True},
                resolved_parameters={"pressure_bar": 10.0}
            ),
            "draft_text": "Verified answer draft",
            "sealing_requirement_spec": {
                "operating_envelope": {"pressure_bar": 10.0}
            }
        },
        reasoning={"phase": "final"}
    )

    patch = node_finalize(state)
    
    assert isinstance(patch["system"]["rfq_draft"], RFQDraft)
    assert patch["system"]["rfq_draft"].rfq_basis_status == "rfq_ready"

def test_contract_id_format_handles_missing_cycle_ids():
    state = SealAIState(reasoning={"phase": "final"}) # Default cycle_id is 0 or None
    
    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]
    
    # Prefix-c0-r0 or empty string depending on implementation
    # current _artifact_id returns "" for cycle_id <= 0
    assert contract.contract_id == ""

def test_governance_metadata_blockers_impact_admissibility():
    state = SealAIState(
        reasoning={
            "current_assertion_cycle_id": 1,
            "asserted_profile_revision": 1,
            "phase": "final",
            "missing_params": ["pressure_bar"]
        },
        working_profile={"engineering_profile": {"medium": "Wasser"}}
    )
    
    patch = node_prepare_contract(state)
    contract = patch["system"]["answer_contract"]
    
    # "pressure_bar" is critical, so it should be in blockers and release_status should be inadmissible
    assert "pressure_bar" in contract.rfq_admissibility.blockers
    assert contract.release_status == "inadmissible"
