"""Patch 6 tests — Mobile Leakage Triage + low-confidence vision guidance.

Covers Blueprint §4.8/§4.9, §7.3/§7.4 and §15: immediate no-empty-spinner triage,
measurement guidance instead of product guessing, confirmation-required visual
candidates that are never auto-asserted, optional vision with graceful
degradation, and that the Patch-2 templates are wired (not recreated).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.communication.mobile_triage import (
    NullVisionPort,
    build_mobile_leakage_triage,
    build_mobile_leakage_turn,
    build_visual_low_confidence_guidance,
    extract_visual_candidates,
    is_leakage_triage_intent,
    to_cockpit_visual_candidates,
)
from app.agent.v92.contracts import AssistantTurnEnvelope, VisualCandidate

# Phrases that would be a forbidden final identification (§ Golden H "must not contain").
_FORBIDDEN_IDENTIFICATION = ("Das ist sicher ein", "Material ist", "Artikelnummer ist")


# --- Intent detection (§7.3) ------------------------------------------------


@pytest.mark.parametrize("message", ["sifft", "Die Dichtung sifft", "Öl läuft raus", "undicht"])
def test_leakage_intent_detected(message: str) -> None:
    assert is_leakage_triage_intent(message) is True


def test_photo_with_short_caption_is_triage_entry() -> None:
    assert is_leakage_triage_intent("", has_attachment=True) is True


def test_knowledge_question_is_not_leakage_triage() -> None:
    assert is_leakage_triage_intent("Was ist FFKM und wofür nutzt man es?") is False


# --- Immediate triage output (§4.8, no-empty-spinner) -----------------------


def test_foto_sifft_yields_immediate_triage_output() -> None:
    envelope = build_mobile_leakage_triage(has_attachment=True)

    assert isinstance(envelope, AssistantTurnEnvelope)
    assert envelope.chat_reply.style == "mobile_triage"
    # Template wired (Patch 2), not recreated.
    assert envelope.chat_reply.template_id == "chat.mobile_triage.v1"
    assert "Leckagefall" in envelope.chat_reply.markdown
    # Pocket-first compressed output is present immediately.
    assert envelope.pocket_cockpit_patch is not None
    assert envelope.pocket_cockpit_patch.recognized
    assert envelope.pocket_cockpit_patch.next_step
    assert envelope.pocket_cockpit_patch.rfq_status == "DRAFT"
    # Action chips offered (limited answer).
    assert [c.label for c in envelope.action_chips] == [
        "Ja",
        "Nein",
        "Weiß ich nicht",
        "Foto vom Einbauort",
    ]


def test_triage_trace_proves_no_vision_rag_or_graph_on_first_output() -> None:
    trace = build_mobile_leakage_triage(has_attachment=True).trace
    assert trace["route"] == "mobile_leakage_triage"
    assert trace["llm_used"] is False
    assert trace["rag_used"] is False
    assert trace["graph_used"] is False
    assert trace["empty_spinner_violated"] is False


# --- Low-confidence guidance instead of product guessing (§4.9/§7.4) --------


def test_bad_photo_yields_measurement_guidance_not_identification() -> None:
    envelope = build_visual_low_confidence_guidance()
    assert envelope.chat_reply.style == "visual_low_confidence_guidance"
    assert envelope.chat_reply.template_id == "chat.visual_low_confidence_guidance.v1"
    markdown = envelope.chat_reply.markdown
    assert "messe" in markdown.lower() or "miss" in markdown.lower()
    for forbidden in _FORBIDDEN_IDENTIFICATION:
        assert forbidden not in markdown
    assert [c.label for c in envelope.action_chips] == [
        "So messe ich d1/D/b",
        "Neues Foto machen",
        "Ich weiß die Maße nicht",
    ]


# --- Visual candidates are confirmation-required, never auto-asserted (§15) -


def test_visual_candidate_is_confirmation_required_by_type() -> None:
    candidate = VisualCandidate(candidate_id="c1", candidate_type="seal_type", value="RWDR-artige Bauform")
    assert candidate.requires_confirmation is True
    assert candidate.status == "candidate"
    assert candidate.origin == "visual_candidate"
    assert "material_from_photo" in candidate.forbidden_inferences


def test_visual_candidate_cannot_be_constructed_as_confirmed_fact() -> None:
    # The type forbids requires_confirmation=False and status other than candidate.
    with pytest.raises(ValidationError):
        VisualCandidate(
            candidate_id="c1", candidate_type="seal_type", value="RWDR", requires_confirmation=False
        )
    with pytest.raises(ValidationError):
        VisualCandidate(candidate_id="c1", candidate_type="seal_type", value="RWDR", status="confirmed")


def test_candidates_enter_cockpit_patch_only_as_candidates() -> None:
    candidates = [
        VisualCandidate(candidate_id="c1", candidate_type="seal_type", value="RWDR-artige Bauform"),
    ]
    envelope = build_mobile_leakage_triage(has_attachment=True, candidates=candidates)
    visual = envelope.cockpit_patch.visual_candidates
    assert len(visual) == 1
    assert visual[0]["requires_confirmation"] is True
    assert visual[0]["status"] == "candidate"
    # The triage envelope never produces an asserted/known field for the candidate.
    assert envelope.cockpit_patch.known_fields == []


# --- Optional vision + graceful degradation (§15) ---------------------------


def test_extract_without_vision_returns_no_candidates() -> None:
    assert extract_visual_candidates(attachment={"id": "a1"}, vision=None) == []
    assert extract_visual_candidates(attachment=None, vision=NullVisionPort()) == []
    assert extract_visual_candidates(attachment={"id": "a1"}, vision=NullVisionPort()) == []


def test_vision_failure_degrades_to_empty_not_raise() -> None:
    class BoomVision:
        def extract(self, attachment):  # noqa: ANN001, ARG002
            raise RuntimeError("vision backend down")

    assert extract_visual_candidates(attachment={"id": "a1"}, vision=BoomVision()) == []


def test_turn_without_vision_still_gives_useful_output() -> None:
    # Photo present but no vision backend → guidance (still a concrete next step).
    envelope = build_mobile_leakage_turn("sifft", attachment={"id": "a1"}, vision=None)
    assert envelope.chat_reply.style == "visual_low_confidence_guidance"
    assert envelope.action_chips


def test_turn_with_vision_candidates_routes_to_triage_with_candidates() -> None:
    class StubVision:
        def extract(self, attachment):  # noqa: ANN001, ARG002
            return [VisualCandidate(candidate_id="c1", candidate_type="seal_type", value="RWDR-artige Bauform")]

    envelope = build_mobile_leakage_turn("sifft", attachment={"id": "a1"}, vision=StubVision())
    assert envelope.chat_reply.style == "mobile_triage"
    assert len(envelope.cockpit_patch.visual_candidates) == 1
    assert envelope.cockpit_patch.visual_candidates[0]["requires_confirmation"] is True


def test_no_attachment_text_only_triage() -> None:
    envelope = build_mobile_leakage_turn("die dichtung sifft", attachment=None)
    assert envelope.chat_reply.style == "mobile_triage"
    assert to_cockpit_visual_candidates([]) == []
