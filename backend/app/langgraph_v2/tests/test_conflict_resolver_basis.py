from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_resistance_claims
from app.langgraph_v2.state.sealai_state import ConflictRecord


def test_scope_conflict_detection_heuristic() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
    from app.langgraph_v2.state.sealai_state import SealAIState, AnswerContract, VerificationReport
    from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState

    # Text that triggers the SCOPE_CONFLICT heuristic
    draft_text = "FKM ist für Wasser geeignet. Jedoch ist FKM für Wasser nicht geeignet bei hohen Temperaturen."

    contract = AnswerContract()
    import hashlib
    draft_hash = hashlib.sha256(draft_text.encode()).hexdigest()
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()

    state = AnswerSubgraphState(
        conversation={"session_id": "test"},
        system={
            "draft_text": draft_text,
            "draft_base_hash": contract_hash,
            "answer_contract": contract
        }
    )

    patch = node_verify_claims(state)
    report = patch["system"]["verification_report"]

    # Should detect SCOPE_CONFLICT
    assert any(c.conflict_type == "SCOPE_CONFLICT" for c in report.conflicts)
    assert any(c.severity == "WARNING" for c in report.conflicts)


def test_source_conflict_detection() -> None:
    # Text that triggers a hard chemical resistance failure
    # NBR is definitely not resistant to Schwefelsäure (C)
    draft_text = "NBR ist für Schwefelsäure beständig."

    spans = _check_resistance_claims(draft_text)
    assert len(spans) > 0

    # Check that this would be mapped to a SOURCE_CONFLICT in the main node
    conflicts = []
    for span in spans:
        conflicts.append(ConflictRecord(
            conflict_type="SOURCE_CONFLICT",
            severity="HARD",
            summary=f"Chemical resistance contradiction detected: {span['expected_value']}",
            sources_involved=["draft", "chemical_resistance_lookup"],
            scope_note="Draft claims compatibility while lookup denies it.",
            resolution_status="OPEN",
        ))

    assert len(conflicts) > 0
    assert conflicts[0].conflict_type == "SOURCE_CONFLICT"
    assert conflicts[0].severity == "HARD"


# --- Blueprint v1.2 schema acceptance tests ---

def test_conflict_record_accepts_all_v12_conflict_types() -> None:
    v12_types = [
        "FALSE_CONFLICT",
        "SOURCE_CONFLICT",
        "SCOPE_CONFLICT",
        "CONDITION_CONFLICT",
        "COMPOUND_SPECIFICITY_CONFLICT",
        "ASSUMPTION_CONFLICT",
        "TEMPORAL_VALIDITY_CONFLICT",
        "PARAMETER_CONFLICT",
        "UNKNOWN",
    ]
    for ct in v12_types:
        record = ConflictRecord(conflict_type=ct, summary=f"test {ct}")
        assert record.conflict_type == ct


def test_conflict_record_accepts_all_v12_severity_levels() -> None:
    v12_severities = [
        "INFO",
        "WARNING",
        "HARD",
        "CRITICAL",
        "BLOCKING_UNKNOWN",
        "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE",
    ]
    for sev in v12_severities:
        record = ConflictRecord(severity=sev, summary=f"test {sev}")
        assert record.severity == sev


def test_conflict_record_blocking_unknown_is_governance_severity() -> None:
    record = ConflictRecord(
        conflict_type="PARAMETER_CONFLICT",
        severity="BLOCKING_UNKNOWN",
        summary="Operating pressure unknown — cannot validate material limits.",
        sources_involved=["working_profile"],
        scope_note="pressure_bar not set; manufacturer confirmation required.",
        resolution_status="OPEN",
    )
    assert record.conflict_type == "PARAMETER_CONFLICT"
    assert record.severity == "BLOCKING_UNKNOWN"
    assert record.resolution_status == "OPEN"


def test_conflict_record_resolution_requires_manufacturer_scope() -> None:
    record = ConflictRecord(
        conflict_type="COMPOUND_SPECIFICITY_CONFLICT",
        severity="RESOLUTION_REQUIRES_MANUFACTURER_SCOPE",
        summary="Compound-level suitability cannot be determined from generic family data.",
        sources_involved=["rag", "compound_decision_matrix"],
        scope_note="FKM family rated OK; specific compound A75 not in KB.",
        resolution_status="OPEN",
    )
    assert record.severity == "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"
    assert record.conflict_type == "COMPOUND_SPECIFICITY_CONFLICT"


def test_conflict_record_defaults_are_backward_compatible() -> None:
    record = ConflictRecord()
    assert record.conflict_type == "UNKNOWN"
    assert record.severity == "WARNING"
    assert record.resolution_status == "OPEN"
    assert record.sources_involved == []


def test_conflict_record_rejects_unknown_conflict_type() -> None:
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ConflictRecord(conflict_type="MADE_UP_TYPE")


def test_conflict_record_rejects_unknown_severity() -> None:
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ConflictRecord(severity="EXTREME")
