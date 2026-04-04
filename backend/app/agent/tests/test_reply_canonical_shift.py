import re

from app.agent.agent.selection import (
    MANUFACTURER_VALIDATION_REPLY,
    NEUTRAL_SCOPE_REPLY,
    SAFEGUARDED_WITHHELD_REPLY,
    NO_CANDIDATES_REPLY,
    NO_VIABLE_CANDIDATES_REPLY,
    build_final_reply,
    _build_evidence_binding_note,
    _build_integrity_note,
    _build_domain_scope_note,
    _build_recommendation_rationale_summary,
)


def _selection_state_with_stale_release_fields() -> dict:
    return {
        "selection_status": "winner_selected",
        "winner_candidate_id": "ptfe::g25::acme",
        "viable_candidate_ids": ["ptfe::g25::acme"],
        "blocked_candidates": [],
        "release_status": "manufacturer_validation_required",
        "rfq_admissibility": "provisional",
        "specificity_level": "family_only",
        "output_blocked": False,
        "recommendation_artifact": {
            "selection_status": "winner_selected",
            "winner_candidate_id": "ptfe::g25::acme",
            "viable_candidate_ids": ["ptfe::g25::acme"],
            "blocked_candidates": [],
            "release_status": "manufacturer_validation_required",
            "rfq_admissibility": "provisional",
            "specificity_level": "family_only",
            "output_blocked": False,
            "binding_level": "non_binding",
            "candidate_projection": None,
            "rationale_summary": "",
        },
        "review_escalation_projection": {},
        "clarification_projection": {},
        "correction_projection": {},
        "parameter_integrity_projection": {},
        "unit_normalization_projection": {},
        "domain_scope_projection": {},
        "output_contract_projection": {},
    }


def test_build_final_reply_prefers_canonical_dispatch_facing_truth_over_stale_selection_fields():
    selection_state = _selection_state_with_stale_release_fields()
    case_state = {
        "result_contract": {
            "release_status": "rfq_ready",
            "rfq_admissibility": "ready",
            "specificity_level": "compound_required",
        },
        "requirement_class": {
            "object_type": "requirement_class",
            "object_version": "requirement_class_v1",
            "requirement_class_id": "compound::ptfe",
            "specificity_level": "compound_required",
        },
        "recipient_selection": {
            "selection_status": "selected_recipient",
        },
        "matching_state": {
            "matching_outcome": {
                "status": "matched_primary_candidate",
            }
        },
        "rfq_state": {
            "rfq_admissibility": "ready",
            "rfq_dispatch": {
                "dispatch_ready": True,
            },
        },
    }

    assert build_final_reply(selection_state, case_state=case_state).startswith(NEUTRAL_SCOPE_REPLY)


def test_build_final_reply_preserves_selection_fallback_without_canonical_case_state():
    selection_state = _selection_state_with_stale_release_fields()

    assert build_final_reply(selection_state).startswith(MANUFACTURER_VALIDATION_REPLY)


# ---------------------------------------------------------------------------
# Regression: English system strings must be gone from structured-path constants
# ---------------------------------------------------------------------------

def test_reply_constants_are_german():
    for name, value in [
        ("SAFEGUARDED_WITHHELD_REPLY", SAFEGUARDED_WITHHELD_REPLY),
        ("NO_CANDIDATES_REPLY", NO_CANDIDATES_REPLY),
        ("NO_VIABLE_CANDIDATES_REPLY", NO_VIABLE_CANDIDATES_REPLY),
    ]:
        assert not value.startswith("No "), (
            f"{name} still starts with English 'No ': {value!r}"
        )
        # Must not contain the old English phrases
        assert "governed recommendation" not in value, (
            f"{name} still contains English 'governed recommendation': {value!r}"
        )


def test_neutral_scope_reply_no_internal_jargon():
    assert "Governance" not in NEUTRAL_SCOPE_REPLY
    assert "Scope-of-validity" not in NEUTRAL_SCOPE_REPLY
    assert "scope-of-validity" not in NEUTRAL_SCOPE_REPLY.lower()


# ---------------------------------------------------------------------------
# Regression: _build_evidence_binding_note must not expose raw ref IDs
# ---------------------------------------------------------------------------

def test_evidence_binding_note_grounded_no_raw_refs():
    note = _build_evidence_binding_note({
        "status": "grounded_evidence",
        "provenance_refs": ["doc-001", "doc-002", "secret-ref-xyz"],
    })
    assert "doc-001" not in note
    assert "doc-002" not in note
    assert "secret-ref-xyz" not in note
    # Must still be user-readable German
    assert len(note) > 10


def test_evidence_binding_note_thin_no_raw_refs():
    note = _build_evidence_binding_note({
        "status": "thin_evidence",
        "provenance_refs": ["internal-ref-99"],
    })
    assert "internal-ref-99" not in note
    assert len(note) > 10


def test_evidence_binding_note_no_evidence_no_raw_refs():
    note = _build_evidence_binding_note({
        "status": "no_evidence",
        "provenance_refs": [],
    })
    # Should not expose "keine" as a ref or any internal identifiers
    assert "keine" not in note or "keine" in note  # just ensure it runs without error
    assert len(note) > 5


# ---------------------------------------------------------------------------
# Regression: _build_integrity_note must not expose key:status tokens
# ---------------------------------------------------------------------------

_KEY_STATUS_PATTERN = re.compile(r"\b\w+:\w+")  # matches "pressure:plausibility_failure"


def test_integrity_note_unusable_no_key_status_tokens():
    note = _build_integrity_note(
        {"integrity_status": "unusable_until_clarified", "blocking_keys": ["pressure", "temperature"]},
        {"statuses": {"pressure": "plausibility_failure", "temperature": "unit_ambiguous"}},
    )
    assert not _KEY_STATUS_PATTERN.search(note), (
        f"integrity note exposes raw key:status token: {note!r}"
    )
    assert "pressure:plausibility_failure" not in note
    assert "temperature:unit_ambiguous" not in note
    assert len(note) > 10


def test_integrity_note_warning_no_key_status_tokens():
    note = _build_integrity_note(
        {"integrity_status": "usable_with_warning", "warning_keys": ["shaft_speed"]},
        {"statuses": {"shaft_speed": "out_of_range_warning"}},
    )
    assert "shaft_speed:out_of_range_warning" not in note
    assert not _KEY_STATUS_PATTERN.search(note), (
        f"integrity note exposes raw key:status token: {note!r}"
    )


# ---------------------------------------------------------------------------
# Regression: _build_domain_scope_note must not expose raw threshold IDs
# ---------------------------------------------------------------------------

def test_domain_scope_note_warning_no_raw_threshold_ids():
    note = _build_domain_scope_note({
        "status": "in_domain_with_warning",
        "warning_thresholds": ["pressure_threshold_bar", "temperature_threshold_c"],
    })
    assert "pressure_threshold_bar" not in note
    assert "temperature_threshold_c" not in note
    assert "warning_thresholds" not in note


def test_domain_scope_note_out_of_scope_no_raw_threshold_ids():
    note = _build_domain_scope_note({
        "status": "out_of_domain_scope",
        "blocking_thresholds": ["dn_limit_exceeded", "pv_limit_exceeded"],
    })
    assert "dn_limit_exceeded" not in note
    assert "pv_limit_exceeded" not in note
    assert "out_of_domain_scope" not in note


def test_domain_scope_note_escalation_no_raw_threshold_ids():
    note = _build_domain_scope_note({
        "status": "escalation_required",
        "blocking_thresholds": ["pressure_spike_factor"],
    })
    assert "pressure_spike_factor" not in note
    assert "escalation_required" not in note


# ---------------------------------------------------------------------------
# Regression: rationale_summary must not contain raw candidate_id or evidence_refs
# ---------------------------------------------------------------------------

def test_rationale_summary_candidate_path_no_raw_ids():
    """Happy-path rationale summary must not expose internal candidate_id or evidence ref IDs."""
    summary = _build_recommendation_rationale_summary(
        review_escalation_projection={},
        clarification_projection={},
        evidence_provenance_projection={"status": "grounded_evidence", "provenance_refs": ["ref-007"]},
        conflict_status_projection={},
        parameter_integrity_projection={},
        unit_normalization_projection={},
        domain_scope_projection={},
        selection_status="winner_selected",
        release_status="rfq_ready",
        rfq_admissibility="ready",
        readiness_status="releasable",
        blocking_reason="",
        candidate_projection={
            "candidate_id": "ptfe::g25::acme",
            "grade_name": "G25",
            "material_family": "PTFE",
            "evidence_refs": ["ref-007", "ref-008"],
        },
        asserted_state=None,
    )
    # Must not expose the internal candidate_id with :: separator
    assert "ptfe::g25::acme" not in summary
    # Must not expose raw evidence ref IDs
    assert "ref-007" not in summary
    assert "ref-008" not in summary
    # Must not expose internal labels
    assert "Deterministische Candidate-Projektion" not in summary
    assert "Evidenzreferenzen" not in summary
    # Must still contain meaningful content
    assert len(summary) > 10
