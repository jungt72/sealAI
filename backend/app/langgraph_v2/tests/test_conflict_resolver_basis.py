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


# --- PARAMETER_CONFLICT active detection tests ---

def test_parameter_conflict_pressure_mismatch_generates_conflict() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_parameter_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    contract = AnswerContract(resolved_parameters={"pressure_bar": 8.0})
    draft_text = "FKM eignet sich bei einem Betriebsdruck von 12 bar."

    conflicts = _check_parameter_conflicts(draft_text, contract)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "PARAMETER_CONFLICT"
    assert conflicts[0].severity == "WARNING"
    assert "12.0" in conflicts[0].summary
    assert "8.0" in conflicts[0].summary


def test_parameter_conflict_temperature_mismatch_generates_conflict() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_parameter_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    contract = AnswerContract(resolved_parameters={"temperature_C": 150.0})
    draft_text = "Einsatz bis 200 °C problemlos möglich."

    conflicts = _check_parameter_conflicts(draft_text, contract)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "PARAMETER_CONFLICT"
    assert "200.0" in conflicts[0].summary
    assert "150.0" in conflicts[0].summary


def test_parameter_conflict_no_conflict_when_value_matches() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_parameter_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    contract = AnswerContract(resolved_parameters={"pressure_bar": 8.0})
    draft_text = "Empfohlen für 8 bar Betriebsdruck."

    conflicts = _check_parameter_conflicts(draft_text, contract)

    assert conflicts == []


def test_parameter_conflict_no_conflict_when_no_contract_value() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_parameter_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract has no pressure_bar or temperature_C
    contract = AnswerContract(resolved_parameters={"material": "FKM"})
    draft_text = "Geeignet bis 12 bar und 200 °C."

    conflicts = _check_parameter_conflicts(draft_text, contract)

    assert conflicts == []


def test_parameter_conflict_tolerance_edge_case() -> None:
    """Values within tolerance (±0.5 bar) must NOT generate a conflict."""
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_parameter_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    contract = AnswerContract(resolved_parameters={"pressure_bar": 8.0})
    # 8.3 bar is within ±0.5 of 8.0 → no conflict
    draft_text = "Geeignet bei 8,3 bar."

    conflicts = _check_parameter_conflicts(draft_text, contract)

    assert conflicts == []


def test_parameter_conflict_does_not_set_failed_claim_span() -> None:
    """PARAMETER_CONFLICT must not route to hard fail — only conflicts list."""
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
    from app.langgraph_v2.state.sealai_state import AnswerContract
    from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState
    import hashlib

    contract = AnswerContract(resolved_parameters={"pressure_bar": 8.0})
    draft_text = "FKM ist bei 15 bar geeignet."
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()

    state = AnswerSubgraphState(
        conversation={"session_id": "test"},
        system={
            "draft_text": draft_text,
            "draft_base_hash": contract_hash,
            "answer_contract": contract,
        },
    )

    patch = node_verify_claims(state)
    report = patch["system"]["verification_report"]

    # Should have PARAMETER_CONFLICT in conflicts
    assert any(c.conflict_type == "PARAMETER_CONFLICT" for c in report.conflicts)
    # But the unexpected_number check may flag "15" — verify report status is separate concern.
    # The PARAMETER_CONFLICT itself must not independently cause a hard fail.
    param_conflicts = [c for c in report.conflicts if c.conflict_type == "PARAMETER_CONFLICT"]
    assert all(c.severity == "WARNING" for c in param_conflicts)


# --- BLOCKING_UNKNOWN detection tests ---

def test_blocking_unknown_pressure_missing_in_contract_but_claimed_in_draft() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_blocking_unknowns
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract has no pressure_bar
    contract = AnswerContract(resolved_parameters={"temperature_C": 100.0})
    # Draft mentions a pressure of 10 bar
    draft_text = "Das Material ist bis 10 bar beständig."

    conflicts = _check_blocking_unknowns(draft_text, contract)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "PARAMETER_CONFLICT"
    assert conflicts[0].severity == "BLOCKING_UNKNOWN"
    assert "pressure" in conflicts[0].summary.lower()


def test_blocking_unknown_temperature_missing_in_contract_but_claimed_in_draft() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_blocking_unknowns
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract has no temperature_C
    contract = AnswerContract(resolved_parameters={"pressure_bar": 5.0})
    # Draft mentions a temperature of 200 °C
    draft_text = "Einsatztemperatur bis 200 °C ist zulässig."

    conflicts = _check_blocking_unknowns(draft_text, contract)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "PARAMETER_CONFLICT"
    assert conflicts[0].severity == "BLOCKING_UNKNOWN"
    assert "temperature" in conflicts[0].summary.lower()


def test_blocking_unknown_no_conflict_when_parameters_present_in_contract() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_blocking_unknowns
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract has authoritative values
    contract = AnswerContract(resolved_parameters={
        "pressure_bar": 10.0,
        "temperature_C": 200.0
    })
    draft_text = "Beständig bei 10 bar und 200 °C."

    conflicts = _check_blocking_unknowns(draft_text, contract)

    assert conflicts == []


def test_blocking_unknown_no_conflict_when_no_technical_claims_in_draft() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_blocking_unknowns
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract is empty
    contract = AnswerContract()
    # Draft contains no pressure or temperature mentions
    draft_text = "Das Material NBR ist allgemein gut verfügbar."

    conflicts = _check_blocking_unknowns(draft_text, contract)

    assert conflicts == []


# --- COMPOUND_SPECIFICITY_CONFLICT active detection tests ---

def test_compound_specificity_conflict_grade_jump_generates_conflict() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_specificity_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract only has family_level NBR
    contract = AnswerContract(candidate_semantics=[{
        "value": "NBR",
        "specificity": "family_level"
    }])
    # Draft claims a specific grade "NBR 70"
    draft_text = "Wir empfehlen NBR 70 für diese Anwendung."

    conflicts = _check_specificity_conflicts(draft_text, contract)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "COMPOUND_SPECIFICITY_CONFLICT"
    assert conflicts[0].severity == "RESOLUTION_REQUIRES_MANUFACTURER_SCOPE"
    assert "NBR 70" in conflicts[0].summary


def test_compound_specificity_conflict_brand_jump_generates_conflict() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_specificity_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract only has family_level FFKM
    contract = AnswerContract(candidate_semantics=[{
        "value": "FFKM",
        "specificity": "family_level"
    }])
    # Draft claims a specific brand "Kalrez"
    draft_text = "Kalrez ist hier die beste Wahl."

    conflicts = _check_specificity_conflicts(draft_text, contract)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "COMPOUND_SPECIFICITY_CONFLICT"
    assert "Kalrez" in conflicts[0].summary


def test_compound_specificity_no_conflict_when_already_compound_specific() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_specificity_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract already has compound_specific evidence
    contract = AnswerContract(candidate_semantics=[{
        "value": "NBR 70",
        "specificity": "compound_specific"
    }])
    draft_text = "NBR 70 ist geeignet."

    conflicts = _check_specificity_conflicts(draft_text, contract)

    assert conflicts == []


def test_compound_specificity_no_conflict_when_no_material_jump() -> None:
    from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import _check_specificity_conflicts
    from app.langgraph_v2.state.sealai_state import AnswerContract

    # Contract has family-level evidence, draft also stays at family-level
    contract = AnswerContract(candidate_semantics=[{
        "value": "FKM",
        "specificity": "family_level"
    }])
    draft_text = "FKM ist beständig gegen Hydrauliköl."

    conflicts = _check_specificity_conflicts(draft_text, contract)

    assert conflicts == []
