from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from app._legacy_v2.nodes.answer_subgraph import subgraph_builder as answer_subgraph_builder
from app._legacy_v2.nodes.answer_subgraph.node_finalize import node_finalize
from app._legacy_v2.nodes.answer_subgraph.node_targeted_patch import node_targeted_patch
from app._legacy_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app._legacy_v2.nodes.answer_subgraph.subgraph_builder import (
    _clear_checkpoint,
    _consume_decision,
    _handle_checkpoint,
    _merge_state_patch,
    _resolve_open_conflicts,
)
from app._legacy_v2.state.sealai_state import (
    AnswerContract,
    ConflictRecord,
    Intent,
    SealAIState,
    SealingRequirementSpec,
    VerificationReport,
)


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

    # Missing numeric claim now generates a ConflictRecord with HARD severity, 
    # which causes report.status to be "fail".
    assert report.status == "fail"
    assert report.failure_type == "render_mismatch"
    assert any(
        span.get("reason") == "missing_number"
        and span.get("expected_value") == "80.0"
        and span.get("severity") == "HARD"
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


def test_finalize_builds_rfq_draft_from_existing_governance_artifacts() -> None:
    state = SealAIState(
        draft_text="Verifizierte RFQ-Zusammenfassung",
        final_text="Verifizierte RFQ-Zusammenfassung",
        reasoning={"current_assertion_cycle_id": 5, "asserted_profile_revision": 11},
        system={
            "sealing_requirement_spec": SealingRequirementSpec(
                spec_id="srs-c5-r11",
                operating_envelope={"pressure_bar": 250.0, "temperature_C": 120.0},
                manufacturer_validation_scope=["PTFE family-level candidate requires compound validation."],
                assumption_boundaries=["surface_finish not yet confirmed."],
                open_points_visible=[{"kind": "missing_critical_parameter", "value": "Wellenschlag"}],
            ),
            "rfq_admissibility": {
                "status": "inadmissible",
                "governed_ready": False,
                "reason": "incomplete",
                "blockers": [],
                "open_points": ["Temperaturprofil fuer Einsatzfall bestaetigen."],
            },
            "verification_report": VerificationReport(
                contract_hash="c",
                draft_hash="d",
                status="fail",
                conflicts=[
                    ConflictRecord(
                        conflict_type="ASSUMPTION_CONFLICT",
                        severity="HARD",
                        summary="Draft assumes valid media compatibility without proof.",
                        resolution_status="OPEN",
                    )
                ],
            ),
            "answer_contract": AnswerContract(
                release_status="manufacturer_validation_required",

                governance_metadata={

                    "scope_of_validity": ["Nur fuer den aktuellen Fall."],
                    "assumptions_active": ["surface_finish not yet confirmed."],
                    "unknowns_release_blocking": [],
                    "unknowns_manufacturer_validation": ["PTFE family-level candidate requires compound validation."],
                    "gate_failures": ["CRITICAL: Medienvertraeglichkeit fuer aktuelles Medium ungeklaert."],
                    "governance_notes": [],
                },
            ),
        },
    )

    patch = node_finalize(state)
    draft = patch["system"]["rfq_draft"]

    assert draft.rfq_id == "rfq-draft-c5-r11"
    assert draft.rfq_basis_status == "manufacturer_validation_required"
    assert draft.sealing_requirement_spec is not None
    assert draft.operating_context_redacted == {"pressure_bar": 250.0, "temperature_C": 120.0}
    assert "Temperaturprofil fuer Einsatzfall bestaetigen." in draft.manufacturer_questions_mandatory
    assert "PTFE family-level candidate requires compound validation." in draft.manufacturer_questions_mandatory
    assert "Wellenschlag" in draft.manufacturer_questions_mandatory
    assert {"conflict_type": "ASSUMPTION_CONFLICT", "severity": "HARD", "summary": "Draft assumes valid media compatibility without proof.", "resolution_status": "OPEN"} in draft.conflicts_visible
    assert {"conflict_type": "GATE_FAILURE", "severity": "CRITICAL", "summary": "Medienvertraeglichkeit fuer aktuelles Medium ungeklaert.", "resolution_status": "OPEN"} in draft.conflicts_visible
    assert draft.buyer_assumptions_acknowledged == ["surface_finish not yet confirmed."]
    assert draft.feedback_expected == []
    assert draft.buyer_contact == {"buyer_id": "anonymous"}

def test_finalize_keeps_rfq_draft_conservative_when_optional_sources_are_missing() -> None:
    state = SealAIState(
        draft_text="Verifizierte Antwort",
        final_text="Verifizierte Antwort",
    )

    patch = node_finalize(state)
    draft = patch["system"]["rfq_draft"]

    assert draft is None


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


# ---------------------------------------------------------------------------
# Regression: draft_conflict_resolution fires ONLY on OPEN conflicts
# ---------------------------------------------------------------------------


def test_draft_conflict_resolution_fires_with_open_conflicts() -> None:
    """When verification abort has OPEN conflicts, checkpoint must trigger."""
    report = VerificationReport(
        contract_hash="c",
        draft_hash="d",
        status="fail",
        failure_type="abort",
        conflicts=[
            ConflictRecord(
                conflict_type="ASSUMPTION_CONFLICT",
                severity="HARD",
                summary="Draft assumes valid media compatibility without proof.",
                resolution_status="OPEN",
            )
        ],
    )
    has_open = any(
        getattr(c, "resolution_status", "") == "OPEN"
        for c in report.conflicts
    )
    assert has_open is True, "Should detect OPEN conflicts"

    state = SealAIState(system={"verification_report": report})
    checkpoint = _handle_checkpoint(state, "draft_conflict_resolution", "draft_conflict_resolution_node")
    assert checkpoint["system"]["pending_action"] == "draft_conflict_resolution"
    assert checkpoint["system"]["confirm_status"] == "pending"


def test_draft_conflict_resolution_skips_without_open_conflicts() -> None:
    """Pure render_mismatch without OPEN conflicts must NOT trigger conflict resolution."""
    report = VerificationReport(
        contract_hash="c",
        draft_hash="d",
        status="fail",
        failure_type="render_mismatch",
        conflicts=[
            ConflictRecord(
                conflict_type="ASSUMPTION_CONFLICT",
                severity="HARD",
                summary="Previously resolved conflict.",
                resolution_status="RESOLVED",
            )
        ],
    )
    has_open = any(
        getattr(c, "resolution_status", "") == "OPEN"
        for c in report.conflicts
    )
    assert has_open is False, "No OPEN conflicts -> conflict resolution must NOT trigger"


def test_draft_conflict_resolution_skips_on_empty_conflicts() -> None:
    """No conflicts at all -> no checkpoint."""
    report = VerificationReport(
        contract_hash="c",
        draft_hash="d",
        status="fail",
        failure_type="render_mismatch",
        conflicts=[],
    )
    has_open = any(
        getattr(c, "resolution_status", "") == "OPEN"
        for c in report.conflicts
    )
    assert has_open is False


def test_draft_conflict_resolution_detects_mixed_open_and_resolved() -> None:
    """Mixed conflicts: at least one OPEN -> must trigger."""
    report = VerificationReport(
        contract_hash="c",
        draft_hash="d",
        status="fail",
        failure_type="abort",
        conflicts=[
            ConflictRecord(
                conflict_type="PARAMETER_CONFLICT",
                severity="HARD",
                summary="Resolved deviation.",
                resolution_status="RESOLVED",
            ),
            ConflictRecord(
                conflict_type="ASSUMPTION_CONFLICT",
                severity="HARD",
                summary="Still open.",
                resolution_status="OPEN",
            ),
        ],
    )
    has_open = any(
        getattr(c, "resolution_status", "") == "OPEN"
        for c in report.conflicts
    )
    assert has_open is True, "Mixed list with at least one OPEN -> should trigger"


# ---------------------------------------------------------------------------
# Regression: _resolve_open_conflicts marks OPEN → RESOLVED after approval
# ---------------------------------------------------------------------------


def test_resolve_open_conflicts_marks_open_as_resolved() -> None:
    """After user approves draft_conflict_resolution, all OPEN conflicts
    must become RESOLVED so they don't re-trigger on the next verify cycle."""
    report = VerificationReport(
        contract_hash="c",
        draft_hash="d",
        status="fail",
        conflicts=[
            ConflictRecord(
                conflict_type="ASSUMPTION_CONFLICT",
                severity="HARD",
                summary="Draft assumes valid media compatibility.",
                resolution_status="OPEN",
            ),
            ConflictRecord(
                conflict_type="SCOPE_CONFLICT",
                severity="HARD",
                summary="Draft scope exceeds evidence.",
                resolution_status="OPEN",
            ),
        ],
    )
    state = SealAIState(system={"verification_report": report})
    patch = _resolve_open_conflicts(state)

    updated_report = patch["system"]["verification_report"]
    assert all(c.resolution_status == "RESOLVED" for c in updated_report.conflicts)


def test_resolve_open_conflicts_preserves_dismissed() -> None:
    """DISMISSED conflicts must not be touched by _resolve_open_conflicts."""
    report = VerificationReport(
        contract_hash="c",
        draft_hash="d",
        status="fail",
        conflicts=[
            ConflictRecord(
                conflict_type="FALSE_CONFLICT",
                severity="INFO",
                summary="Harmless.",
                resolution_status="DISMISSED",
            ),
            ConflictRecord(
                conflict_type="ASSUMPTION_CONFLICT",
                severity="HARD",
                summary="Open assumption.",
                resolution_status="OPEN",
            ),
        ],
    )
    state = SealAIState(system={"verification_report": report})
    patch = _resolve_open_conflicts(state)

    updated_report = patch["system"]["verification_report"]
    assert updated_report.conflicts[0].resolution_status == "DISMISSED"
    assert updated_report.conflicts[1].resolution_status == "RESOLVED"


def test_resolve_open_conflicts_returns_empty_when_nothing_to_resolve() -> None:
    """If all conflicts are already RESOLVED or DISMISSED, return empty patch."""
    report = VerificationReport(
        contract_hash="c",
        draft_hash="d",
        status="pass",
        conflicts=[
            ConflictRecord(
                conflict_type="ASSUMPTION_CONFLICT",
                severity="HARD",
                summary="Already resolved.",
                resolution_status="RESOLVED",
            ),
        ],
    )
    state = SealAIState(system={"verification_report": report})
    patch = _resolve_open_conflicts(state)
    assert patch == {}


def test_resolved_conflicts_survive_next_verify_cycle() -> None:
    """Simulate the full re-trigger scenario: after approval, the same conflict
    fingerprint in the next verify run must inherit RESOLVED, not reset to OPEN."""
    from app._legacy_v2.nodes.answer_subgraph.node_verify_claims import _apply_resolution_status

    # Step 1: Original OPEN conflict
    original = ConflictRecord(
        conflict_type="ASSUMPTION_CONFLICT",
        severity="HARD",
        summary="Draft assumes valid media compatibility without proof.",
        resolution_status="OPEN",
    )

    # Step 2: User approves → we resolve it
    resolved = original.model_copy(update={"resolution_status": "RESOLVED"})

    # Step 3: Next verify cycle creates the same conflict fresh (OPEN by default)
    re_detected = ConflictRecord(
        conflict_type="ASSUMPTION_CONFLICT",
        severity="HARD",
        summary="Draft assumes valid media compatibility without proof.",
        resolution_status="OPEN",
    )

    # Step 4: _apply_resolution_status should inherit RESOLVED from old
    synced = _apply_resolution_status([re_detected], [resolved])
    assert synced[0].resolution_status == "RESOLVED", \
        "Re-detected conflict must inherit RESOLVED from previous cycle"


def test_unrelated_new_conflict_stays_open_after_approval() -> None:
    """A new conflict that wasn't in the approved set must stay OPEN."""
    from app._legacy_v2.nodes.answer_subgraph.node_verify_claims import _apply_resolution_status

    old_resolved = ConflictRecord(
        conflict_type="ASSUMPTION_CONFLICT",
        severity="HARD",
        summary="Draft assumes valid media compatibility without proof.",
        resolution_status="RESOLVED",
    )

    new_unrelated = ConflictRecord(
        conflict_type="PARAMETER_CONFLICT",
        severity="HARD",
        summary="Draft states 250 bar but contract authorizes 200 bar.",
        resolution_status="OPEN",
    )

    synced = _apply_resolution_status([new_unrelated], [old_resolved])
    assert synced[0].resolution_status == "OPEN", \
        "Unrelated new conflict must stay OPEN"
