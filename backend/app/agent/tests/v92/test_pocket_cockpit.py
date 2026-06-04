"""Patch 3 tests — Pocket Cockpit projection + Action Chips (Blueprint §4, §11.3/.4).

Pure projection over an existing ``V92DashboardContract``; no dispatch/runtime
change. Action chips are affordances only (no state mutation).
"""

from __future__ import annotations

from app.agent.v92.contracts import ActionChip, PocketCockpitPatch, V92DashboardContract
from app.agent.v92.pocket_cockpit import (
    build_action_chips,
    build_pocket_cockpit,
    build_pocket_cockpit_patch,
)


def _contract(**overrides) -> V92DashboardContract:
    base: dict = {
        "turn_id": "t1",
        "route": "engineering_case_update",
        "readiness_band": "screening_possible",
        "current_facts": [
            {"field_name": "Dichtungstyp", "value": "RWDR", "confidence": "confirmed"},
            {
                "field_name": "Maße",
                "value": "45x62x8",
                "unit": "mm",
                "confidence": "confirmed",
            },
            {
                "field_name": "Drehzahl",
                "value": 1500,
                "unit": "rpm",
                "confidence": "estimated",
            },
            {"field_name": "Medium", "value": "Öl", "confidence": "confirmed"},
            {"field_name": "Anwendung", "value": "Getriebe", "confidence": "confirmed"},
        ],
        "blocking_missing_fields": [
            {"key": "shaft_surface_condition", "label": "Wellenlauffläche"},
        ],
        "risk_matrix": [
            {"label": "Wellenlauffläche prüfen", "severity": "high"},
        ],
        "recommendation_card": {"next_action": "check_shaft_counterface"},
    }
    base.update(overrides)
    return V92DashboardContract(**base)


def test_pocket_patch_compresses_to_four_sections() -> None:
    patch = build_pocket_cockpit_patch(_contract())

    assert isinstance(patch, PocketCockpitPatch)
    # Radically compressed for mobile (§4.3): at most 4 recognized, 3 critical.
    assert len(patch.recognized) == 4
    assert len(patch.critical) <= 3
    assert patch.collapsed_by_default is True
    assert patch.details_available is True


def test_recognized_carries_label_value_status() -> None:
    patch = build_pocket_cockpit_patch(_contract())
    first = patch.recognized[0]
    assert first["label"] == "Dichtungstyp"
    assert first["value"] == "RWDR"
    assert first["status"] == "confirmed"
    # Unit is folded into the displayed value.
    masse = next(item for item in patch.recognized if item["label"] == "Maße")
    assert masse["value"] == "45x62x8 mm"
    # Non-confirmed confidence degrades to candidate.
    rpm = next(item for item in patch.recognized if item["label"] == "Drehzahl")
    assert rpm["status"] == "candidate"


def test_critical_prefers_risks_then_blocking_missing() -> None:
    patch = build_pocket_cockpit_patch(_contract())
    assert patch.critical[0] == {"label": "Wellenlauffläche prüfen", "severity": "high"}


def test_next_step_from_pending_question_overrides_recommendation() -> None:
    patch = build_pocket_cockpit_patch(
        _contract(),
        pending_question={"field": "shaft_rotates", "text": "Dreht sich die Welle?"},
    )
    assert patch.next_step == {
        "question": "Dreht sich die Welle?",
        "field": "shaft_rotates",
    }


def test_next_step_falls_back_to_recommendation_action() -> None:
    patch = build_pocket_cockpit_patch(_contract())
    assert patch.next_step == {"action": "check_shaft_counterface"}


def test_rfq_status_maps_readiness_band() -> None:
    assert (
        build_pocket_cockpit_patch(_contract(readiness_band="not_ready")).rfq_status
        == "DRAFT"
    )
    assert (
        build_pocket_cockpit_patch(
            _contract(readiness_band="rfq_ready_for_expert_review")
        ).rfq_status
        == "MANUFACTURER_REVIEW_READY"
    )


def test_action_chips_yes_no_question() -> None:
    chips = build_action_chips({"field": "shaft_rotates", "answer_type": "yes_no"})
    assert [c.label for c in chips] == ["Ja", "Nein", "Weiß ich nicht", "Foto senden"]
    assert all(isinstance(c, ActionChip) for c in chips)
    assert chips[0].value == "yes" and chips[0].field == "shaft_rotates"
    assert chips[-1].action == "upload_photo"


def test_action_chips_from_options() -> None:
    chips = build_action_chips(
        {
            "field": "shaft_surface_condition",
            "options": ["glatt", "Rille sichtbar", "Rost"],
        }
    )
    labels = [c.label for c in chips]
    assert labels == ["glatt", "Rille sichtbar", "Rost", "Weiß ich nicht"]


def test_no_pending_question_yields_no_chips() -> None:
    patch, chips = build_pocket_cockpit(_contract())
    assert chips == []
    assert patch.rfq_status == "DRAFT"
