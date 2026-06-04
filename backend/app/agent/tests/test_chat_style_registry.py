"""Patch 2 tests — chat-style template registry + No-Go phrase guard.

Covers Blueprint §10.4 (registry metadata), §10.6/§10.7 (template rendering),
§18.3/§27.1/§31 (No-Go phrase guard) and §22.2 (disclaimer suppression on
normal turns). Additive only; the live composer/final-guard are not touched.
"""

from __future__ import annotations

import pytest

from app.agent.templates import (
    CHAT_TEMPLATE_REGISTRY,
    FORBIDDEN_NORMAL_TURN_PHRASES,
    NoGoPhraseError,
    assert_no_no_go,
    detect_no_go_phrases,
    get_chat_template_meta,
    render_chat_reply,
    sanitize_no_go,
)
from app.agent.v92.contracts import ChatReply

REQUIRED_STYLES = {
    "senior_engineer_short",
    "smalltalk_fast",
    "mobile_triage",
    "visual_low_confidence_guidance",
    "blocked_boundary",
}


# --- Registry metadata (§10.4) ---------------------------------------------


def test_registry_covers_required_styles() -> None:
    assert REQUIRED_STYLES.issubset(set(CHAT_TEMPLATE_REGISTRY))


@pytest.mark.parametrize("style", sorted(REQUIRED_STYLES))
def test_every_meta_has_required_blueprint_fields(style: str) -> None:
    meta = get_chat_template_meta(style)  # type: ignore[arg-type]
    assert meta.template_id and meta.template_id.startswith("chat.")
    assert meta.path.startswith("chat/") and meta.path.endswith(".j2")
    assert meta.allowed_modes  # non-empty
    assert meta.max_questions == 1
    assert meta.disclaimer_policy in {
        "suppress_normal_turn",
        "ui_static_only",
        "rfq_required",
        "explicit_boundary_required",
    }
    assert isinstance(meta.forbidden_phrases, tuple)


# --- Rendering (§10.6/§10.7) + disclaimer (§22.2) --------------------------


def test_senior_engineer_short_renders_clean_reply() -> None:
    reply = render_chat_reply(
        "senior_engineer_short",
        {
            "opening": "Okay, damit kann man arbeiten.",
            "technical_hint": "Bei einem undichten Altteil zuerst die Lauffläche prüfen.",
            "primary_question": "Siehst du auf der Welle eine Rille, Korrosion oder eine blanke Spur?",
        },
        primary_question={"field": "shaft_surface_condition"},
    )

    assert isinstance(reply, ChatReply)
    assert reply.style == "senior_engineer_short"
    assert reply.template_id == "chat.senior_engineer_short.v1"
    # Normal turn suppresses the per-turn liability disclaimer (§22.2).
    assert reply.disclaimer_mode == "suppress_normal_turn"
    assert reply.primary_question == {"field": "shaft_surface_condition"}
    assert "Okay, damit kann man arbeiten." in reply.markdown
    assert reply.markdown.rstrip().endswith("blanke Spur?")


def test_senior_engineer_short_omits_empty_optionals() -> None:
    reply = render_chat_reply(
        "senior_engineer_short",
        {"primary_question": "Dreht sich die Welle im Betrieb?"},
    )
    assert reply.markdown == "Dreht sich die Welle im Betrieb?"


def test_mobile_triage_emits_action_chips_block() -> None:
    reply = render_chat_reply(
        "mobile_triage",
        {
            "immediate_context": "Ich prüfe das als möglichen Leckagefall an einer Wellendichtung.",
            "primary_question": "Dreht sich die Welle im Betrieb?",
        },
        action_chips=["Ja", "Nein", "Weiß ich nicht", "Foto vom Einbauort"],
    )
    assert reply.style == "mobile_triage"
    assert "ACTIONS:" in reply.markdown
    assert "Foto vom Einbauort" in reply.markdown


def test_blocked_boundary_keeps_explicit_boundary_disclaimer() -> None:
    reply = render_chat_reply(
        "blocked_boundary",
        {
            "boundary_statement": "Das kann ich nicht seriös als Garantie freigeben.",
            "constructive_alternative": "Ich kann den Fall aber für eine Herstellerbewertung vorbereiten.",
            "offer_question": "Soll ich daraus einen Technical RFQ Brief erstellen?",
        },
    )
    assert reply.disclaimer_mode == "explicit_boundary_required"
    # A legitimate refusal must NOT be blocked by the final-release guard.
    assert "freigeben" in reply.markdown


# --- No-Go phrase guard (§18.3 / §27.1 / §31) ------------------------------


@pytest.mark.parametrize("phrase", FORBIDDEN_NORMAL_TURN_PHRASES)
def test_detect_flags_each_forbidden_normal_turn_phrase(phrase: str) -> None:
    assert detect_no_go_phrases(f"... {phrase} ...") == [
        phrase
    ] or phrase in detect_no_go_phrases(f"... {phrase} ...")


def test_render_blocks_forbidden_structural_phrase() -> None:
    with pytest.raises(NoGoPhraseError):
        render_chat_reply(
            "senior_engineer_short",
            {
                "opening": "Ich verstehe den Fall aktuell als Getriebeleckage.",
                "primary_question": "Dreht sich die Welle?",
            },
        )


def test_render_blocks_final_release_wording() -> None:
    with pytest.raises(NoGoPhraseError):
        render_chat_reply(
            "senior_engineer_short",
            {
                "opening": "Der optimale Dichtring ist ein FKM 45x62x8.",
                "primary_question": "Passt das?",
            },
        )


def test_assert_no_no_go_passes_clean_text() -> None:
    # Should not raise.
    assert_no_no_go("Okay, damit kann man arbeiten. Dreht sich die Welle?")


def test_sanitize_removes_forbidden_phrase() -> None:
    cleaned = sanitize_no_go("Grenze: nur ein Hinweis. Dreht sich die Welle?")
    assert "Grenze:" not in cleaned
    assert "Dreht sich die Welle?" in cleaned


def test_visual_low_confidence_blocks_final_identification() -> None:
    with pytest.raises(NoGoPhraseError):
        render_chat_reply(
            "visual_low_confidence_guidance",
            {
                "uncertainty_statement": "Das ist sicher ein RWDR 45x62x8.",
                "useful_next_step": "Miss d1, D und b.",
            },
        )
