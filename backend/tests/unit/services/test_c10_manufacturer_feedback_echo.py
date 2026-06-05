"""C10 (P2-1 TEIL B) — manufacturer-feedback echo-path doctrine.

A post-RFQ manufacturer response, when reproduced in chat, must surface ONLY as
an ``rag_supported``-class knowledge note — NEVER as a confirmed brief fact and
NEVER with release/approval wording.

These tests are the executable contract for the echo path and the structural
brief-gate backstop. Red-before-green: the self_declared / user_entered
laundering cases (1) and (2) FAIL before the ``_blocked_reason`` short-circuit
because ``_normalize_origin`` maps a self_declared manufacturer_response field to
``user_entered``, which returns before the source-type denylist is consulted.
"""

from __future__ import annotations

from app.agent.runtime.output_guard import check_fast_path_output
from app.agent.state.models import GovernedSessionState
from app.agent.v92.dashboard_contract import build_v92_dashboard_contract
from app.domain.source_validation import source_validation_metadata
from app.services.rwdr_mvp_brief import (
    EvidenceConfirmationIntelligence,
    _manufacturer_feedback_envelope,
    build_rwdr_brief_from_confirmed_fields,
    manufacturer_response_echo_notes,
)


def _mfr_field(
    *,
    validation_status: str = "self_declared",
    origin: str | None = None,
    status: str | None = None,
    field_name: str = "material",
    value: object = "FKM",
) -> dict[str, object]:
    env: dict[str, object] = {
        "field_name": field_name,
        "value": value,
        "source_type": "manufacturer_response",
        "validation_status": validation_status,
    }
    if origin is not None:
        env["origin"] = origin
    if status is not None:
        env["status"] = status
    return env


def _project_one(env: dict[str, object]):
    fields = EvidenceConfirmationIntelligence().project([env])
    assert len(fields) == 1
    return fields[0]


# --- Brief gate: manufacturer_response is NEVER a confirmed brief fact ----------


def test_manufacturer_response_self_declared_never_confirmed_fact() -> None:
    """RED before fix: self_declared launders origin → user_entered → allowed."""
    field = _project_one(_mfr_field(validation_status="self_declared"))
    assert field.source_type == "manufacturer_response"
    assert field.liability_bearing is True
    assert field.allowed_in_brief is False
    assert field.blocked_reason and "manufacturer_response" in field.blocked_reason


def test_manufacturer_response_cannot_be_laundered_via_user_entered_origin() -> None:
    """RED before fix: explicit origin=user_entered is the adversarial leak."""
    field = _project_one(
        _mfr_field(validation_status="self_declared", origin="user_entered")
    )
    assert field.allowed_in_brief is False
    assert field.blocked_reason and "manufacturer_response" in field.blocked_reason


def test_manufacturer_response_documented_blocked() -> None:
    field = _project_one(_mfr_field(validation_status="documented"))
    assert field.allowed_in_brief is False


def test_manufacturer_response_validated_blocked() -> None:
    field = _project_one(_mfr_field(validation_status="validated"))
    assert field.allowed_in_brief is False


def test_manufacturer_response_candidate_blocked() -> None:
    field = _project_one(_mfr_field(validation_status="candidate"))
    assert field.allowed_in_brief is False


# --- Source validation: never authoritative / never a release basis -------------


def test_manufacturer_response_source_is_not_authoritative() -> None:
    meta = source_validation_metadata(
        source_type="manufacturer_response", validation_status="self_declared"
    )
    assert meta.authoritative is False
    assert meta.not_for_release_decisions is True


# --- Output guard: the echo path cannot carry release / approval wording ---------


def test_release_wording_in_manufacturer_echo_is_blocked_by_fast_guard() -> None:
    safe, _category = check_fast_path_output(
        "Freudenberg empfiehlt für diesen Fall FKM."
    )
    assert safe is False


def test_approval_wording_in_manufacturer_echo_is_blocked_by_fast_guard() -> None:
    safe, _category = check_fast_path_output(
        "Der Hersteller hat die Dichtung final freigegeben."
    )
    assert safe is False


# --- Echo render: surfaces as an rag_supported knowledge note, not a fact --------


def test_manufacturer_feedback_echoes_as_rag_supported_note() -> None:
    state = GovernedSessionState()
    state.governed_answer_context = {
        "knowledge_notes": [
            {
                "label": "Hersteller-Rückmeldung: FKM bei 120 °C genannt",
                "status": "rag_supported",
            }
        ]
    }
    contract = build_v92_dashboard_contract(
        state, turn_id="t1", route="engineering_case_update", case_id="case-1"
    )
    assert contract.knowledge_notes == [
        {
            "label": "Hersteller-Rückmeldung: FKM bei 120 °C genannt",
            "status": "rag_supported",
        }
    ]


# --- Intake envelope: always an open-point candidate, never confirmed -----------


def test_manufacturer_feedback_envelope_is_open_point_candidate() -> None:
    env = _manufacturer_feedback_envelope(
        {"field": "material", "value": "FKM", "note": "grenzwertig bei 120 °C"}
    )
    assert env["source_type"] == "manufacturer_response"
    assert env["validation_status"] == "candidate"
    assert env["confirmation_status"] == "unconfirmed"
    field = _project_one(env)
    assert field.allowed_in_brief is False


# --- Echo projection: rag_supported notes, guard-scrubbed --------------------------


def test_echo_projection_emits_rag_supported_note() -> None:
    fields = [
        {
            "field": "material",
            "value": "FKM",
            "source_type": "manufacturer_response",
            "manufacturer_note": "im Werk geprüft",
        }
    ]
    notes = manufacturer_response_echo_notes(fields)
    assert len(notes) == 1
    assert notes[0]["status"] == "rag_supported"
    assert "Herstellerrückmeldung" in notes[0]["label"]


def test_echo_projection_scrubs_release_wording_to_safe_fallback() -> None:
    fields = [
        {
            "field": "material",
            "value": "FKM",
            "source_type": "manufacturer_response",
            "manufacturer_note": "wir empfehlen FKM und geben es final frei",
        }
    ]
    notes = manufacturer_response_echo_notes(fields)
    assert notes[0]["status"] == "rag_supported"
    assert "empfehl" not in notes[0]["label"].casefold()
    assert "frei" not in notes[0]["label"].casefold()
    assert "Prüfung" in notes[0]["label"]


def test_echo_projection_ignores_non_manufacturer_fields() -> None:
    fields = [
        {"field": "material", "value": "FKM", "source_type": "user_stated"},
        {"field": "medium", "value": "Öl", "source_type": "deterministic_calculation"},
    ]
    assert manufacturer_response_echo_notes(fields) == []


# --- Brief wiring: a recorded manufacturer response surfaces in the brief --------
# RED before the C10 echo caller is wired: manufacturer_response_echo_notes() has
# no caller, so the brief carries no "manufacturer_echo_notes" key/section even
# though the intake (apply_manufacturer_feedback) already stores the envelope.


def _brief_with_manufacturer_feedback(note: str) -> dict[str, object]:
    env = _manufacturer_feedback_envelope(
        {"field": "material", "value": "FKM", "note": note}
    )
    return build_rwdr_brief_from_confirmed_fields(
        raw_inquiry="RWDR 45x62x8, Getriebe, Öl, 1500 U/min",
        fields=[env],
    )


def _brief_sections_by_id(brief: dict[str, object]) -> dict[str, object]:
    return {
        section["id"]: section
        for section in (brief.get("sections") or [])
        if isinstance(section, dict) and "id" in section
    }


def test_manufacturer_feedback_surfaces_in_brief_as_rag_supported() -> None:
    """RED before wiring: the brief has no manufacturer_echo_notes / section."""
    brief = _brief_with_manufacturer_feedback("im Werk geprüft, grenzwertig bei 120 °C")

    echo_notes = brief.get("manufacturer_echo_notes")
    assert (
        isinstance(echo_notes, list) and echo_notes
    ), "brief must surface recorded manufacturer feedback as echo notes"
    assert echo_notes[0]["status"] == "rag_supported"
    assert "Herstellerrückmeldung" in echo_notes[0]["label"]

    section = _brief_sections_by_id(brief).get("manufacturer_echo_notes")
    assert section is not None, "brief sections must include manufacturer_echo_notes"
    assert section["items"], "the echo section must carry the recorded note(s)"


def test_manufacturer_feedback_brief_echo_never_a_confirmed_fact() -> None:
    """Doctrine invariant: the echo never becomes a confirmed brief fact."""
    brief = _brief_with_manufacturer_feedback("im Werk geprüft")
    confirmed = brief.get("confirmed_case_fields") or []
    assert not any(
        (field.get("source_type") == "manufacturer_response") for field in confirmed
    ), "manufacturer_response must never enter confirmed_case_fields"


def test_manufacturer_feedback_brief_echo_scrubs_release_wording() -> None:
    """Doctrine invariant: release/recommendation wording is scrubbed to fallback."""
    brief = _brief_with_manufacturer_feedback(
        "wir empfehlen FKM und geben es final frei"
    )
    label = brief["manufacturer_echo_notes"][0]["label"].casefold()
    assert "empfehl" not in label
    assert "frei" not in label
    assert "prüfung" in label
