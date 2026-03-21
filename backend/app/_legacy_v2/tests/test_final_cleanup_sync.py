from __future__ import annotations

import pytest
from app._legacy_v2.nodes.answer_subgraph.node_draft_answer import _render_fact_sheet
from app._legacy_v2.state.sealai_state import AnswerContract, FactItem, SealAIState
from app._legacy_v2.nodes.worm_evidence_node import worm_evidence_node

def test_render_fact_sheet_applies_redaction():
    contract = AnswerContract(
        resolved_parameters={
            "medium": "Wasser",
            "pressure_bar": 10.123456,
            "internal_id": "HIDDEN-123"
        }
    )
    rendered = _render_fact_sheet(contract)
    
    assert "medium: Wasser" in rendered
    assert "pressure_bar: 10.1" in rendered # Rounded
    assert "internal_id" not in rendered # Redacted

def test_worm_evidence_node_syncs_claims():
    state = SealAIState(
        reasoning={
            "claims": [
                FactItem(value="Claim 1", claim_type="deterministic_fact", claim_origin="deterministic")
            ]
        }
    )
    
    patch = worm_evidence_node(state)
    bundle = patch["system"]["evidence_bundle"]
    
    # Check if claims are in metadata
    claims_in_audit = bundle.metadata.get("governance_claims")
    assert len(claims_in_audit) == 1
    assert claims_in_audit[0]["value"] == "Claim 1"
