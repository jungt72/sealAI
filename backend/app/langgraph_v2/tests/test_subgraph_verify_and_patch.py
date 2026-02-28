from __future__ import annotations

import hashlib

from app.langgraph_v2.nodes.answer_subgraph import subgraph_builder as answer_subgraph_builder
from app.langgraph_v2.nodes.answer_subgraph.node_targeted_patch import node_targeted_patch
from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app.langgraph_v2.state.sealai_state import AnswerContract, Intent, SealAIState, VerificationReport


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


def test_verify_claims_ignores_numeric_fact_ids() -> None:
    contract = AnswerContract(
        resolved_parameters={"pressure_bar": 80.0},
        selected_fact_ids=["doc123:chunk9999"],
    )
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Freigegeben bis 80.0 bar.",
    )

    patch = node_verify_claims(state)
    report = patch["verification_report"]

    assert report.status == "pass"
    assert report.failed_claim_spans == []


def test_verify_claims_skips_number_failures_for_explanation_goal() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80.0})
    state = SealAIState(
        intent=Intent(goal="explanation_or_comparison"),
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Kyrolon hat 45 MPa Zugfestigkeit und 80.0 bar Eignung.",
    )

    patch = node_verify_claims(state)
    report = patch["verification_report"]

    assert report.status == "pass"
    assert not any(span.get("reason") in {"missing_number", "unexpected_number"} for span in report.failed_claim_spans)


def test_verify_claims_accepts_numbers_from_rag_sources() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80.0})
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Kyrolon erreicht 45 MPa und 80.0 bar.",
        sources=[{"snippet": "Kyrolon: tensile strength 45 MPa."}],
    )

    patch = node_verify_claims(state)
    report = patch["verification_report"]

    assert report.status == "pass"
    assert report.failed_claim_spans == []


def test_safe_fallback_uses_sidekick_message_at_max_patch_attempts() -> None:
    state = SealAIState(
        draft_text="Irrelevanter Draft.",
        flags={"answer_subgraph_patch_attempts": answer_subgraph_builder.MAX_PATCH_ATTEMPTS},
    )

    patch = answer_subgraph_builder._safe_fallback_node(state)

    expected = (
        "Dazu habe ich in meinen technischen Datenblaettern gerade keinen exakten Treffer gefunden. "
        "Wenn du mir spezifische Einsatzbedingungen (wie Medium, Temperatur und Druck) nennst, "
        "kann ich gezielter fuer dich suchen!"
    )
    assert patch["final_text"] == expected
    assert patch["final_answer"] == expected


def test_extract_patch_keeps_terminal_final_text_even_if_unchanged() -> None:
    before = SealAIState(final_text="RFQ-Text", final_answer="RFQ-Text")
    after = SealAIState(final_text="RFQ-Text", final_answer="RFQ-Text")

    patch = answer_subgraph_builder._extract_patch(before, after)

    assert patch["final_text"] == "RFQ-Text"
    assert patch["final_answer"] == "RFQ-Text"
