from __future__ import annotations

import hashlib

from app.langgraph_v2.nodes.answer_subgraph.node_targeted_patch import node_targeted_patch
from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState, VerificationReport


def _contract_hash(contract: AnswerContract) -> str:
    return hashlib.sha256(contract.model_dump_json().encode()).hexdigest()


def test_verify_claims_detects_numeric_render_mismatch() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80.0})
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Das System haelt 100 bar aus.",
    )

    patch = node_verify_claims(state)
    report = patch["verification_report"]

    assert report.status == "fail"
    assert report.failure_type == "render_mismatch"
    assert any(span.get("wrong_span") == "100" for span in report.failed_claim_spans)


def test_verify_claims_detects_missing_required_disclaimer() -> None:
    contract = AnswerContract(
        resolved_parameters={"pressure_bar": 80.0},
        required_disclaimers=["Pruefung erforderlich"],
    )
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Empfohlener Druckbereich: 80.0 bar.",
    )

    patch = node_verify_claims(state)
    report = patch["verification_report"]

    assert report.status == "fail"
    assert report.failure_type == "render_mismatch"
    assert any(
        span.get("reason") == "missing_disclaimer" and span.get("expected_value") == "Pruefung erforderlich"
        for span in report.failed_claim_spans
    )


def test_targeted_patch_replaces_wrong_number_with_contract_value() -> None:
    report = VerificationReport(
        contract_hash="h",
        draft_hash="d",
        status="fail",
        failure_type="render_mismatch",
        failed_claim_spans=[
            {
                "reason": "unexpected_number",
                "wrong_span": "100",
                "expected_value": "80.0",
            }
        ],
    )
    state = SealAIState(
        draft_text="Das System haelt 100 bar aus.",
        verification_report=report,
    )

    patch = node_targeted_patch(state)

    assert patch["draft_text"] == "Das System haelt 80.0 bar aus."
    assert patch["flags"]["answer_subgraph_patch_attempts"] == 1


def test_verify_claims_whitelists_bracket_references() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80.0})
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Kyrolon haelt 80.0 bar [1].",
    )

    patch = node_verify_claims(state)
    report = patch["verification_report"]

    assert report.status == "pass"
    assert report.failed_claim_spans == []


def test_targeted_patch_is_idempotent_on_second_run() -> None:
    report = VerificationReport(
        contract_hash="h",
        draft_hash="d",
        status="fail",
        failure_type="render_mismatch",
        failed_claim_spans=[
            {
                "reason": "unexpected_number",
                "wrong_span": "100",
                "expected_value": "80.0",
            }
        ],
    )
    first_state = SealAIState(
        draft_text="Das System haelt 100 bar aus.",
        verification_report=report,
        flags={},
    )
    first_patch = node_targeted_patch(first_state)

    second_state = SealAIState(
        draft_text=first_patch["draft_text"],
        verification_report=report,
        flags=first_patch["flags"],
    )
    second_patch = node_targeted_patch(second_state)

    assert first_patch["draft_text"] == "Das System haelt 80.0 bar aus."
    assert second_patch["draft_text"] == first_patch["draft_text"]
    assert second_patch["flags"]["answer_subgraph_patch_attempts"] == 2
