from __future__ import annotations

import pytest
from app._legacy_v2.state.sealai_state import FactItem, AnswerContract, SealAIState
from app._legacy_v2.nodes.answer_subgraph.node_verify_claims import _check_evidence_contradictions, node_verify_claims
from app.services.rag.nodes.p2_rag_lookup import _extract_claims_from_hits, _extract_claims_from_deterministic

def test_extract_claims_from_hits_categorization():
    hits = [
        {
            "snippet": "NBR is resistant to water.",
            "source": "manual_pdf",
            "score": 0.8,
            "metadata": {"document_id": "doc1", "chunk_id": "c1"}
        }
    ]
    claims = _extract_claims_from_hits(hits)
    assert len(claims) == 1
    assert claims[0].claim_type == "heuristic_hint"
    assert claims[0].claim_origin == "heuristic"
    assert claims[0].confidence == 0.8
    assert claims[0].evidence_refs == ["doc1:c1"]

def test_extract_claims_from_deterministic_categorization():
    payload = {
        "matches": {
            "din_norms": [
                {"norm_code": "DIN123", "material": "NBR", "medium": "Oil"}
            ],
            "material_limits": [
                {"limit_kind": "temperature", "max_value": 100, "unit": "C", "material": "NBR"}
            ]
        }
    }
    claims = _extract_claims_from_deterministic(payload)
    assert len(claims) == 2
    # DIN Norm
    assert claims[0].claim_type == "deterministic_fact"
    assert claims[0].claim_origin == "deterministic"
    # Material Limit
    assert claims[1].claim_type == "manufacturer_limit"
    assert claims[1].claim_origin == "deterministic"

def test_evidence_contradiction_detection():
    # Heuristic says resistant, but deterministic limit says NOT resistant
    claims = [
        FactItem(
            value="NBR ist beständig gegen Öl.",
            claim_type="heuristic_hint",
            claim_origin="heuristic",
            evidence_refs=["doc1:c1"]
        ),
        FactItem(
            value="NBR ist nicht beständig gegen Öl bei 120C.",
            claim_type="manufacturer_limit",
            claim_origin="deterministic",
            evidence_refs=["sql:limit1"]
        )
    ]
    contract = AnswerContract(claims=claims)
    conflicts = _check_evidence_contradictions(contract)
    
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "SOURCE_CONFLICT"
    assert conflicts[0].severity == "CRITICAL"
    assert "Internal evidence contradiction" in conflicts[0].summary
    assert set(conflicts[0].sources_involved) == {"doc1:c1", "sql:limit1"}

def test_node_verify_claims_includes_evidence_conflicts():
    # Setup a state where the contract already has an internal contradiction
    claims = [
        FactItem(value="FKM ist geeignet.", claim_type="heuristic_hint", claim_origin="heuristic"),
        FactItem(value="FKM ist nicht beständig.", claim_type="manufacturer_limit", claim_origin="deterministic")
    ]
    contract = AnswerContract(claims=claims)
    contract_hash = "fake_hash"
    
    state = SealAIState(
        system={
            "answer_contract": contract,
            "draft_base_hash": contract_hash,
            "draft_text": "FKM ist geeignet."
        }
    )
    
    # We need to mock the hash because node_verify_claims checks it
    import hashlib
    import json
    actual_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    state.system.draft_base_hash = actual_hash
    
    patch = node_verify_claims(state)
    report = patch["system"]["verification_report"]
    
    # Should have the internal contradiction conflict
    assert any("Internal evidence contradiction" in c.summary for c in report.conflicts)
    assert report.status == "fail" # Because of CRITICAL internal conflict
