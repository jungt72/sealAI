import hashlib

from app._legacy_v2.nodes.answer_subgraph.node_finalize import node_finalize
from app._legacy_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app._legacy_v2.state import AnswerContract, SealAIState


def test_finalize_ignores_reference_and_list_numbers() -> None:
    draft = "Empfohlener Druckbereich: 80 bar."
    polished = "Empfohlener Druckbereich: 80 bar [1].\n1. Bitte Betriebszustand pruefen."
    state = SealAIState(draft_text=draft, final_text=polished)

    patch = node_finalize(state)

    assert patch["final_text"] == polished
    assert patch["final_answer"] == polished
    assert "error" not in patch


def test_finalize_guard_keeps_final_text_non_empty() -> None:
    state = SealAIState(draft_text="", final_text="Empfehlung: 120 bar.")

    patch = node_finalize(state)

    assert patch["final_text"].strip()
    assert patch["final_answer"] == patch["final_text"]
    assert "No-New-Numbers guard blocked" in patch["error"]


def test_verify_claims_ignores_formatting_numbers() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80})
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    draft = "Druckbereich: 80 bar [1].\n1. Sicherheitsabstand einplanen."
    state = SealAIState(
        draft_text=draft,
        answer_contract=contract,
        draft_base_hash=contract_hash,
    )

    patch = node_verify_claims(state)
    report = patch["system"]["verification_report"]

    assert report.status == "pass"
    assert report.failed_claim_spans == []


def test_finalize_allows_new_numbers_from_state_parameters() -> None:
    final_text = "Auslegung fuer 300 bar, 50 mm und 1500 rpm."
    state = SealAIState(
        draft_text="RFQ-Zusammenfassung wird vorbereitet.",
        final_text=final_text,
        extracted_params={"pressure_max_bar": 300.0, "shaft_d1_mm": 50, "rpm": 1500},
    )

    patch = node_finalize(state)

    assert patch["final_text"] == final_text
    assert patch["final_answer"] == final_text
    assert "error" not in patch


def test_finalize_bypasses_number_guard_for_commercial_rfq_intent() -> None:
    final_text = "Empfehlung fuer RFQ: PV=118 und Haerte 58 HRC."
    state = SealAIState(
        draft_text="RFQ-Zusammenfassung wird vorbereitet.",
        final_text=final_text,
        flags={"frontdoor_intent_category": "COMMERCIAL", "frontdoor_task_intents": ["commercial", "rfq"]},
    )

    patch = node_finalize(state)

    assert patch["final_text"] == final_text
    assert patch["final_answer"] == final_text
    assert "error" not in patch
