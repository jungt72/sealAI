"""0B.1: Promoted Candidate Registry — governance authority hardening.

Verifies that:
  - demo_only entries do NOT resolve as promoted trust anchors
  - governed entries DO resolve
  - missing registry_authority defaults to demo_only (safe default)
  - candidates matched only against demo_only entries fall back to transition / exploratory
  - has_promoted_candidate_source is False when only demo entries exist
  - qualification_status becomes exploratory_candidate_source_only, not rfq-ready, for demo-only cases
  - a genuinely governed entry (monkeypatched) restores the full promoted path
"""
from unittest.mock import patch

import pytest

from app.agent.material_core import (
    PROMOTED_SOURCE_ORIGIN,
    TRANSITION_SOURCE_ORIGIN,
    PromotedCandidateRegistryRecordDTO,
    classify_material_candidate_sources,
    evaluate_material_qualification_core,
    load_promoted_candidate_registry_records,
    resolve_promoted_candidate_records_for_material_case,
    resolve_candidate_registry_records_for_material_case,
)
from app.agent.agent.selection import build_selection_state, build_final_reply, NEUTRAL_SCOPE_REPLY, SAFEGUARDED_WITHHELD_REPLY

# ── Helpers ─────────────────────────────────────────────────────────────────

_PTFE_ACME_CANDIDATE = [
    {
        "candidate_id": "ptfe::g25::acme",
        "material_family": "PTFE",
        "grade_name": "G25",
        "manufacturer_name": "Acme",
        "candidate_kind": "manufacturer_grade",
        "evidence_refs": [],
    }
]

_PTFE_ACME_FACT_CARD = {
    "evidence_id": "fc-governed-1",
    "topic": "PTFE G25 Acme datasheet",
    "content": "PTFE grade G25 from Acme hat ein Temperaturlimit von max. 260 C.",
    "retrieval_rank": 1,
    "source_ref": "datasheet-acme-g25",
    "source_type": "manufacturer_datasheet",
    "source_rank": 1,
    "metadata": {
        "material_family": "PTFE",
        "grade_name": "G25",
        "manufacturer_name": "Acme",
    },
}

_GOVERNANCE_STATE_OPEN = {
    "release_status": "rfq_ready",
    "rfq_admissibility": "ready",
    "specificity_level": "compound_required",
    "conflicts": [],
}

_ASSERTED_STATE = {"operating_conditions": {"temperature": 200.0}}


def _governed_registry():
    """A governed registry entry for PTFE G25 Acme — used only in monkeypatched tests."""
    return (
        PromotedCandidateRegistryRecordDTO(
            registry_record_id="registry-ptfe-g25-acme-governed",
            material_family="PTFE",
            grade_name="G25",
            manufacturer_name="Acme",
            candidate_kind="manufacturer_grade",
            promotion_state="promoted",
            registry_authority="governed",
            source_refs=["registry:ptfe:g25:acme:governed"],
            evidence_refs=[],
        ),
    )


# ── 1. DTO field defaults ────────────────────────────────────────────────────

def test_registry_authority_default_is_demo_only():
    """Missing registry_authority field defaults to 'demo_only' (safe default)."""
    record = PromotedCandidateRegistryRecordDTO(
        registry_record_id="r1",
        material_family="PTFE",
        grade_name="G25",
        manufacturer_name="TestMfr",
    )
    assert record.registry_authority == "demo_only"


def test_governed_registry_authority_is_accepted():
    record = PromotedCandidateRegistryRecordDTO(
        registry_record_id="r1",
        material_family="PTFE",
        grade_name="G25",
        manufacturer_name="TestMfr",
        registry_authority="governed",
    )
    assert record.registry_authority == "governed"


def test_demo_only_registry_authority_is_accepted():
    record = PromotedCandidateRegistryRecordDTO(
        registry_record_id="r1",
        material_family="PTFE",
        grade_name="G25",
        manufacturer_name="TestMfr",
        registry_authority="demo_only",
    )
    assert record.registry_authority == "demo_only"


# ── 2. Registry JSON — actual file reflects 0B.1 ────────────────────────────

def test_registry_json_entry_has_demo_only_authority():
    """The production JSON entry (Acme) is now explicitly marked demo_only."""
    records = load_promoted_candidate_registry_records()
    assert len(records) >= 1
    acme = next((r for r in records if r.registry_record_id == "registry-ptfe-g25-acme"), None)
    assert acme is not None, "Acme registry entry not found"
    assert acme.registry_authority == "demo_only"


# ── 3. Resolution gate ───────────────────────────────────────────────────────

def test_demo_only_entry_not_resolved_as_promoted_trust_anchor():
    """demo_only entries must NOT appear in the trust-granting resolved set."""
    result = resolve_promoted_candidate_records_for_material_case(_PTFE_ACME_CANDIDATE)
    assert "ptfe::g25::acme" not in result
    assert result == {}


def test_governed_entry_is_resolved_as_promoted_trust_anchor(monkeypatch):
    """governed entries MUST appear in the trust-granting resolved set."""
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        _governed_registry,
    )
    result = resolve_promoted_candidate_records_for_material_case(_PTFE_ACME_CANDIDATE)
    assert "ptfe::g25::acme" in result
    assert result["ptfe::g25::acme"].registry_authority == "governed"


def test_demo_only_entry_still_loads_for_auditability():
    """demo_only entries are loaded by the base resolver (auditable), just not trust-granted."""
    all_resolved = resolve_candidate_registry_records_for_material_case(_PTFE_ACME_CANDIDATE)
    assert "ptfe::g25::acme" in all_resolved
    assert all_resolved["ptfe::g25::acme"].registry_authority == "demo_only"


def test_demo_entry_with_promoted_state_but_demo_only_authority_not_trust_granted():
    """promotion_state == 'promoted' alone is insufficient — registry_authority must be 'governed'."""
    result = resolve_promoted_candidate_records_for_material_case(_PTFE_ACME_CANDIDATE)
    # The Acme entry has promotion_state="promoted" but registry_authority="demo_only"
    assert result == {}


# ── 4. Source classification with demo-only registry ────────────────────────

def test_demo_only_candidate_gets_transition_source_origin():
    """Candidate matched only to a demo_only entry falls back to TRANSITION_SOURCE_ORIGIN."""
    assessments = classify_material_candidate_sources(
        candidates=_PTFE_ACME_CANDIDATE,
        relevant_fact_cards=[],
    )
    assert len(assessments) == 1
    assert assessments[0].source_origin == TRANSITION_SOURCE_ORIGIN


def test_demo_only_candidate_is_not_qualified_eligible():
    """demo_only registry match does not grant qualified_eligible status."""
    assessments = classify_material_candidate_sources(
        candidates=_PTFE_ACME_CANDIDATE,
        relevant_fact_cards=[],
    )
    assert assessments[0].qualified_eligible is False
    assert "candidate_source_not_promoted_registry" in assessments[0].source_gate_reasons


def test_governed_candidate_with_evidence_is_qualified_eligible(monkeypatch):
    """A governed registry entry + supporting evidence yields qualified_eligible = True."""
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        _governed_registry,
    )
    candidate_with_evidence = [
        {
            **_PTFE_ACME_CANDIDATE[0],
            "evidence_refs": ["fc-governed-1"],
        }
    ]
    assessments = classify_material_candidate_sources(
        candidates=candidate_with_evidence,
        relevant_fact_cards=[_PTFE_ACME_FACT_CARD],
    )
    assert len(assessments) == 1
    assert assessments[0].source_origin == PROMOTED_SOURCE_ORIGIN
    assert assessments[0].qualified_eligible is True


# ── 5. Material core output — has_promoted_candidate_source ─────────────────

def test_has_promoted_candidate_source_false_with_demo_only_registry():
    """has_promoted_candidate_source must be False when only demo_only entries exist."""
    core_output = evaluate_material_qualification_core(
        relevant_fact_cards=[_PTFE_ACME_FACT_CARD],
        asserted_state=_ASSERTED_STATE,
        governance_state=_GOVERNANCE_STATE_OPEN,
    )
    assert core_output.has_promoted_candidate_source is False


def test_promoted_candidate_ids_empty_with_demo_only_registry():
    """promoted_candidate_ids must be empty when only demo_only entries back the candidate."""
    core_output = evaluate_material_qualification_core(
        relevant_fact_cards=[_PTFE_ACME_FACT_CARD],
        asserted_state=_ASSERTED_STATE,
        governance_state=_GOVERNANCE_STATE_OPEN,
    )
    assert core_output.promoted_candidate_ids == []


def test_qualification_status_exploratory_only_with_demo_registry():
    """With demo_only backing, qualification_status is exploratory_candidate_source_only."""
    core_output = evaluate_material_qualification_core(
        relevant_fact_cards=[_PTFE_ACME_FACT_CARD],
        asserted_state=_ASSERTED_STATE,
        governance_state=_GOVERNANCE_STATE_OPEN,
    )
    assert core_output.qualification_status == "exploratory_candidate_source_only"
    assert core_output.output_blocked is True


# ── 6. Full integration: governed entry restores promoted path ───────────────

def test_governed_entry_enables_promoted_source_and_qualified_path(monkeypatch):
    """End-to-end: a governed registry entry + evidence produces promoted, qualified, released output."""
    monkeypatch.setattr(
        "app.agent.material_core.load_promoted_candidate_registry_records",
        _governed_registry,
    )
    selection_state = build_selection_state(
        [_PTFE_ACME_FACT_CARD],
        {"analysis_cycle_id": "cycle-gov-1"},
        _GOVERNANCE_STATE_OPEN,
        _ASSERTED_STATE,
    )

    assert selection_state["promoted_candidate_ids"] == ["ptfe::g25::acme"]
    assert selection_state["qualified_candidate_ids"] == ["ptfe::g25::acme"]
    assert selection_state["exploratory_candidate_ids"] == []
    assert selection_state["candidate_source_origin"] == PROMOTED_SOURCE_ORIGIN
    assert selection_state["direction_authority"] == "governed_authority"
    assert selection_state["candidates"][0]["candidate_source_class"] == "qualified_candidate_input"
    assert selection_state["output_blocked"] is False
    assert build_final_reply(selection_state) == NEUTRAL_SCOPE_REPLY
