"""Patch 9 tests — RFQ readiness + manufacturer One-Pager (Blueprint §20, §22, §32.14-16).

Covers the additive readiness band, minimum-viable-core gating, open-point
prioritisation, deterministic per-revision snapshots, and the safety boundary
(no final suitability/release in the one-pager). The 3 existing RWDR statuses
stay intact.
"""

from __future__ import annotations

import pytest

from app.agent.communication.rfq_one_pager import (
    RFQ_READINESS_DRAFT,
    RFQ_READINESS_MANUFACTURER_REVIEW_READY,
    RFQ_READINESS_MINIMAL_RFQ,
    RFQ_READINESS_OUT_OF_SCOPE,
    RFQ_READINESS_WITH_OPEN_POINTS,
    build_rfq_one_pager,
    build_rfq_snapshot,
    evaluate_rfq_readiness,
    prioritize_open_points,
)
from app.agent.templates.no_go_guard import detect_no_go_phrases

# Core present for the canonical Golden-M case (RWDR 45x62x8, Getriebe, Öl, undicht).
_CORE_PRESENT = [
    "sealing_function",
    "shaft_diameter_d1_mm",
    "housing_bore_D_mm",
    "seal_width_b_mm",
    "application",
    "inside_medium",
    "request_goal",
]


# --- The 3 existing RWDR statuses stay intact -------------------------------


def test_existing_rwdr_statuses_unchanged() -> None:
    from app.services import rwdr_mvp_brief as brief

    assert brief.RWDR_STATUS_COMPLETE == "COMPLETE"
    assert brief.RWDR_STATUS_NEEDS_CLARIFICATION == "NEEDS_CLARIFICATION"
    assert brief.RWDR_STATUS_OUT_OF_SCOPE == "OUT_OF_SCOPE"


# --- (a) DRAFT names the missing minimum core (§32.15) ----------------------


def test_draft_when_core_missing_names_minimum_input() -> None:
    # "Dichtung undicht. Mach Anfrage." → only a leakage hint, nothing else.
    readiness = evaluate_rfq_readiness(["leakage_description"])
    assert readiness.status == RFQ_READINESS_DRAFT
    assert readiness.can_generate_brief is False
    # Explicitly names what is still missing.
    assert "Dichtungstyp oder Foto" in readiness.minimum_needed
    assert "Maße (d1/D/b) oder Altteilfoto" in readiness.minimum_needed
    assert "Anwendung/Maschine" in readiness.minimum_needed


# --- (b) RFQ with open points when the core is present (§32.14) -------------


def test_rfq_with_open_points_when_core_present_and_critical_open() -> None:
    readiness = evaluate_rfq_readiness(
        _CORE_PRESENT,
        missing_fields=[
            "shaft_condition_known",
            "temperature_max_c",
            "pressure_differential",
        ],
    )
    assert readiness.status == RFQ_READINESS_WITH_OPEN_POINTS
    assert readiness.can_generate_brief is True
    assert "shaft_condition_known" in readiness.open_points_critical


def test_minimal_rfq_when_core_present_only_helpful_open() -> None:
    readiness = evaluate_rfq_readiness(
        _CORE_PRESENT, missing_fields=["rotation_direction"]
    )
    assert readiness.status == RFQ_READINESS_MINIMAL_RFQ
    assert readiness.can_generate_brief is True


def test_manufacturer_review_ready_when_no_open_points() -> None:
    readiness = evaluate_rfq_readiness(_CORE_PRESENT, missing_fields=[])
    assert readiness.status == RFQ_READINESS_MANUFACTURER_REVIEW_READY
    assert readiness.can_generate_brief is True


def test_out_of_scope_is_blocked() -> None:
    readiness = evaluate_rfq_readiness(_CORE_PRESENT, out_of_scope=True)
    assert readiness.status == RFQ_READINESS_OUT_OF_SCOPE
    assert readiness.can_generate_brief is False


# --- Open-point prioritisation (§20) ----------------------------------------


def test_prioritize_open_points_three_tiers() -> None:
    tiers = prioritize_open_points(
        [
            "shaft_condition_known",
            "rotation_direction",
            "quantity",
            "target_delivery_date",
        ]
    )
    assert tiers["critical"] == ["shaft_condition_known"]
    assert tiers["helpful"] == ["rotation_direction"]
    assert set(tiers["optional"]) == {"quantity", "target_delivery_date"}


# --- (c) Snapshot is deterministic / immutable per case_revision (§20.7) ----


def test_snapshot_stable_for_same_revision() -> None:
    readiness = evaluate_rfq_readiness(
        _CORE_PRESENT, missing_fields=["shaft_condition_known"]
    )
    snap_a = build_rfq_snapshot(
        case_id="c1",
        case_revision=4,
        readiness=readiness,
        confirmed_facts=["RWDR 45x62x8"],
    )
    snap_b = build_rfq_snapshot(
        case_id="c1",
        case_revision=4,
        readiness=readiness,
        confirmed_facts=["RWDR 45x62x8"],
    )
    assert snap_a == snap_b
    assert snap_a["snapshot_id"] == snap_b["snapshot_id"]
    assert snap_a["case_revision"] == 4


def test_snapshot_changes_with_revision() -> None:
    readiness = evaluate_rfq_readiness(
        _CORE_PRESENT, missing_fields=["shaft_condition_known"]
    )
    snap_a = build_rfq_snapshot(case_id="c1", case_revision=4, readiness=readiness)
    snap_b = build_rfq_snapshot(case_id="c1", case_revision=5, readiness=readiness)
    assert snap_a["snapshot_id"] != snap_b["snapshot_id"]


# --- One-pager structure + (d) safety boundary, no suitability/release (§22) -


def test_one_pager_is_short_structured_and_boundary_safe() -> None:
    one_pager = build_rfq_one_pager(
        request_goal="Ersatz für undichten RWDR 45x62x8 im Getriebe.",
        confirmed_facts=["RWDR", "45 × 62 × 8 mm", "Getriebe", "Öl"],
        open_points_critical=["Zustand der Wellenlauffläche"],
        open_points_helpful=["Temperatur", "Druckdifferenz"],
        computed_values=["Umfangsgeschwindigkeit ca. 3,53 m/s"],
        manufacturer_questions=["Ist die Wellenlauffläche eingelaufen?"],
    )
    # Manufacturer one-pager structure (§20.5), not a long report.
    assert "# Technical RWDR RFQ Brief" in one_pager
    assert "## 1. Anfrageziel" in one_pager
    assert "Zustand der Wellenlauffläche" in one_pager
    # Boundary present (§22): manufacturer evaluates, sealingAI does not release.
    assert "Hersteller" in one_pager
    assert "Freigabe erfolgt durch Hersteller" in one_pager
    # No affirmative suitability/release wording anywhere.
    assert detect_no_go_phrases(one_pager, (), include_final_release=True) == []
    assert "ist geeignet" not in one_pager.lower()


def test_one_pager_rejects_injected_release_claim() -> None:
    import pytest as _pytest

    from app.agent.templates.no_go_guard import NoGoPhraseError

    with _pytest.raises(NoGoPhraseError):
        build_rfq_one_pager(
            request_goal="Test",
            confirmed_facts=["Der optimale Dichtring ist FKM 45x62x8."],
        )
