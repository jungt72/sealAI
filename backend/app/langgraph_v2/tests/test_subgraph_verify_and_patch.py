from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

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
    report = patch["system"]["verification_report"]

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
    report = patch["system"]["verification_report"]

    assert report.status == "fail"
    assert report.failure_type == "render_mismatch"
    assert any(
        span.get("reason") == "missing_disclaimer" and span.get("expected_value") == "Pruefung erforderlich"
        for span in report.failed_claim_spans
    )


def test_verify_claims_treats_missing_numbers_as_warning_only() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80.0})
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Das System ist ausgeschlossen.",
    )

    patch = node_verify_claims(state)
    report = patch["system"]["verification_report"]

    assert report.status == "pass"
    assert report.failure_type is None
    assert any(
        span.get("reason") == "missing_number"
        and span.get("expected_value") == "80.0"
        and span.get("severity") == "warning"
        for span in report.failed_claim_spans
    )
    assert not any(span.get("reason") == "unexpected_number" for span in report.failed_claim_spans)


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

    assert patch["system"]["draft_text"] == "Das System haelt 80.0 bar aus."
    assert patch["reasoning"]["flags"]["answer_subgraph_patch_attempts"] == 1


def test_verify_claims_whitelists_bracket_references() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80.0})
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Kyrolon haelt 80.0 bar [1].",
    )

    patch = node_verify_claims(state)
    report = patch["system"]["verification_report"]

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
        draft_text=first_patch["system"]["draft_text"],
        verification_report=report,
        flags=first_patch["reasoning"]["flags"],
    )
    second_patch = node_targeted_patch(second_state)

    assert first_patch["system"]["draft_text"] == "Das System haelt 80.0 bar aus."
    assert second_patch["system"]["draft_text"] == first_patch["system"]["draft_text"]
    assert second_patch["reasoning"]["flags"]["answer_subgraph_patch_attempts"] == 2


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
    report = patch["system"]["verification_report"]

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
    report = patch["system"]["verification_report"]

    assert report.status == "pass"
    assert not any(span.get("reason") in {"missing_number", "unexpected_number"} for span in report.failed_claim_spans)


def test_verify_claims_accepts_numbers_from_rag_sources() -> None:
    contract = AnswerContract(resolved_parameters={"pressure_bar": 80.0})
    state = SealAIState(
        answer_contract=contract,
        draft_base_hash=_contract_hash(contract),
        draft_text="Kyrolon erreicht 45 MPa und 80.0 bar.",
        system={"sources": [{"snippet": "Kyrolon: tensile strength 45 MPa."}]},
    )

    patch = node_verify_claims(state)
    report = patch["system"]["verification_report"]

    assert report.status == "pass"
    assert report.failed_claim_spans == []


def test_safe_fallback_uses_sidekick_message_at_max_patch_attempts() -> None:
    state = SealAIState(
        draft_text="Irrelevanter Draft.",
        flags={"answer_subgraph_patch_attempts": answer_subgraph_builder.MAX_PATCH_ATTEMPTS},
    )

    patch = answer_subgraph_builder._safe_fallback_node(state)

    final_text = str(patch["system"]["final_text"] or "")
    assert "keinen belastbaren Volltreffer gefunden" in final_text
    assert "keine ungesicherten Eigenschaften behaupten" in final_text
    assert patch["system"]["final_answer"] == final_text


def test_extract_patch_keeps_terminal_final_text_even_if_unchanged() -> None:
    before = SealAIState(final_text="RFQ-Text", final_answer="RFQ-Text")
    after = SealAIState(final_text="RFQ-Text", final_answer="RFQ-Text")

    patch = answer_subgraph_builder._extract_patch(before, after)

    assert patch["final_text"] == "RFQ-Text"
    assert patch["final_answer"] == "RFQ-Text"


def test_finalize_stamps_assertion_binding() -> None:
    state = SealAIState(
        draft_text="Verifizierte Antwort",
        final_text="Verifizierte Antwort",
        answer_contract=AnswerContract(
            resolved_parameters={},
            calc_results={},
            selected_fact_ids=[],
            governance_metadata={
                "scope_of_validity": ["Nur fuer den aktuellen Fall."],
                "assumptions_active": ["Annahme A"],
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": ["PTFE erfordert Herstellerfreigabe."],
                "gate_failures": [],
                "governance_notes": ["Hinweis 1"],
            },
        ),
        reasoning={"current_assertion_cycle_id": 4, "asserted_profile_revision": 9},
    )

    patch = answer_subgraph_builder.node_finalize(state)

    assert patch["system"]["derived_from_assertion_cycle_id"] == 4
    assert patch["system"]["derived_from_assertion_revision"] == 9
    assert patch["system"]["derived_artifacts_stale"] is False
    assert patch["system"]["governance_metadata"]["scope_of_validity"] == ["Nur fuer den aktuellen Fall."]
    assert patch["system"]["governance_metadata"]["unknowns_manufacturer_validation"] == ["PTFE erfordert Herstellerfreigabe."]


@pytest.mark.asyncio
async def test_answer_subgraph_node_async_reads_live_calc_tile_from_working_profile(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        answer_subgraph_builder,
        "node_prepare_contract",
        lambda state, *_a, **_k: {
            "system": {
                "answer_contract": AnswerContract(
                    resolved_parameters={},
                    calc_results={},
                    selected_fact_ids=[],
                    required_disclaimers=[],
                    respond_with_uncertainty=False,
                ),
            },
            "reasoning": {"last_node": "node_prepare_contract", "flags": {}},
        },
    )

    async def _draft(state, *_a, **_k):
        captured["state"] = state
        captured["config"] = _k.get("config")
        return {
            "system": {"draft_text": "Draft", "draft_base_hash": "draft-hash"},
            "reasoning": {"last_node": "node_draft_answer", "flags": {}},
        }

    monkeypatch.setattr(answer_subgraph_builder, "node_draft_answer", _draft)
    monkeypatch.setattr(
        answer_subgraph_builder,
        "node_verify_claims",
        lambda state, *_a, **_k: {
            "system": {
                "verification_report": VerificationReport(
                    contract_hash="draft-hash",
                    draft_hash="draft-hash",
                    status="pass",
                    failure_type=None,
                    failed_claim_spans=[],
                )
            },
            "reasoning": {"last_node": "node_verify_claims"},
        },
    )
    monkeypatch.setattr(
        answer_subgraph_builder,
        "node_finalize",
        lambda state, *_a, **_k: {
            "system": {"final_text": "Final", "final_answer": "Final"},
            "reasoning": {"last_node": "node_finalize"},
            "conversation": {"messages": list(state.conversation.messages or [])},
        },
    )

    state = SealAIState(
        working_profile={
            "live_calc_tile": {
                "status": "ok",
                "v_surface_m_s": 15.71,
            }
        }
    )

    patch = await answer_subgraph_builder.answer_subgraph_node_async(
        state,
        config={"configurable": {"thread_id": "kyrolon-thread"}},
    )

    draft_state = captured["state"]
    assert isinstance(draft_state, SealAIState)
    assert draft_state.working_profile is not None
    assert captured["config"] == {"configurable": {"thread_id": "kyrolon-thread"}}
    assert patch["last_node"] == "answer_subgraph_node"


@pytest.mark.asyncio
async def test_answer_subgraph_node_async_low_quality_material_rag_finishes_with_fallback() -> None:
    state = SealAIState(
        conversation={"messages": []},
        working_profile={
            "engineering_profile": {},
            "material_choice": {
                "material": "Technical datasheet",
                "confidence": "retrieved",
                "details": "Kontext aus technischer Dokumentensuche.",
            },
        },
        reasoning={
            "flags": {
                "rag_low_quality_results": True,
                "frontdoor_intent_category": "MATERIAL_RESEARCH",
            },
            "working_memory": {
                "panel_material": {
                    "technical_docs": [
                        {
                            "document_id": "kyrolon-doc",
                            "source": "kyrolon.pdf",
                            "snippet": "Kyrolon snippet",
                            "score": 0.01,
                        }
                    ]
                }
            },
            "context": "Kyrolon snippet",
        },
        system={"sources": [{"source": "kyrolon.pdf", "snippet": "Kyrolon snippet", "metadata": {"score": 0.01}}]},
    )

    patch = await answer_subgraph_builder.answer_subgraph_node_async(state)

    final_text = str(patch.get("final_text") or "")
    assert "keinen belastbaren Volltreffer gefunden" in final_text
    assert "Kyrolon snippet" in final_text
    assert "belastbare technische Einordnung" in final_text
    assert patch["final_answer"] == patch["final_text"]
    assert patch["last_node"] == "answer_subgraph_node"
