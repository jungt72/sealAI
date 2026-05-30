"""Completion tests — full V1.6 chat-style template family (Blueprint §10.5 / §18.2).

Closes the registry gap: every ``ChatReplyStyle`` declared in the v9.2 contract
must have a registered template + metadata and render through the No-Go guard.
Additive and test-only; no production logic changed.
"""

from __future__ import annotations

import typing

import pytest

from app.agent.templates.registry import CHAT_TEMPLATE_REGISTRY, render_chat_reply
from app.agent.v92.contracts import ChatReplyStyle


def test_every_declared_style_is_registered() -> None:
    declared = set(typing.get_args(ChatReplyStyle))
    registered = set(CHAT_TEMPLATE_REGISTRY)
    assert declared == registered, f"unregistered styles: {sorted(declared - registered)}"


@pytest.mark.parametrize("style", sorted(typing.get_args(ChatReplyStyle)))
def test_each_style_renders_with_empty_fields(style: str) -> None:
    reply = render_chat_reply(style, {})  # required fields default to ""
    assert reply.template_id == CHAT_TEMPLATE_REGISTRY[style].template_id
    assert isinstance(reply.markdown, str)


def test_knowledge_explainer_renders_three_part_answer() -> None:
    reply = render_chat_reply(
        "knowledge_explainer",
        {
            "definition": "FFKM ist ein perfluorierter Elastomerwerkstoff für anspruchsvolle Medien.",
            "practical_relevance": "Interessant, wenn normale Elastomere chemisch oder thermisch an Grenzen kommen.",
            "bounded_summary": "Kurz gesagt: ein Spezialwerkstoff für harte Randbedingungen, kein Allheilmittel.",
        },
    )
    assert "FFKM" in reply.markdown
    assert reply.disclaimer_mode == "suppress_normal_turn"
    assert reply.template_id == "chat.knowledge_explainer.v1"


def test_case_aware_explainer_keeps_review_framing() -> None:
    reply = render_chat_reply(
        "case_aware_explainer",
        {
            "case_relevance": "In deinem Getriebeöl-Fall wäre FKM wegen Öl und Temperaturreserve ein Prüfpunkt.",
            "decisive_factors": "Entscheidend sind Ölart, Additive, Temperatur an der Dichtlippe und Wellenzustand.",
            "review_note": "Ich würde FKM im Herstellerbrief als zu prüfende Werkstoffrichtung aufnehmen.",
        },
    )
    assert "FKM" in reply.markdown
    assert reply.disclaimer_mode == "suppress_normal_turn"


def test_measurement_guide_carries_action_chips() -> None:
    reply = render_chat_reply(
        "measurement_guide",
        {
            "measurement_intro": "So misst du den Ring sauber aus.",
            "measurement_steps": "Innendurchmesser d1, Außendurchmesser D und Breite b mit dem Messschieber.",
        },
        action_chips=["So messe ich d1/D/b", "Neues Foto machen"],
    )
    assert "d1" in reply.markdown
    assert "ACTIONS:" in reply.markdown


def test_ui_help_uses_static_disclaimer() -> None:
    reply = render_chat_reply(
        "ui_help",
        {
            "help_text": "Links führt der Chat, rechts dokumentiert das Cockpit die erkannten Werte.",
            "follow_up": "Frag einfach, wenn du wissen willst, wo ein Wert herkommt.",
        },
    )
    assert reply.disclaimer_mode == "ui_static_only"


def test_sheet_comment_acknowledges_and_adds_consequence() -> None:
    reply = render_chat_reply(
        "sheet_comment",
        {
            "acknowledgement": "90 °C ist übernommen.",
            "relevant_consequence": "Für die Werkstoffprüfung wäre wichtig, ob das Dauerbetrieb oder ein Spitzenwert ist.",
        },
    )
    assert "90" in reply.markdown
    assert reply.disclaimer_mode == "suppress_normal_turn"


def test_conflict_resolution_states_conflict_and_question() -> None:
    reply = render_chat_reply(
        "conflict_resolution",
        {
            "conflict_statement": "Die Temperatur widerspricht der bisherigen Angabe von 90 °C.",
            "resolution_question": "Soll 190 °C den bisherigen Wert ersetzen oder ist das ein Spitzenwert?",
        },
    )
    assert "190" in reply.markdown
    assert reply.disclaimer_mode == "suppress_normal_turn"


def test_rfq_confirmation_uses_rfq_disclaimer() -> None:
    reply = render_chat_reply(
        "rfq_confirmation",
        {
            "confirmation": "Ja, als erste Herstelleranfrage geht das — mit offenen Punkten.",
            "open_points_note": "Ich markiere Temperatur, Druckdifferenz und Wellenzustand als offen.",
            "confirm_question": "Soll der Brief mit diesen offenen Punkten erzeugt werden?",
        },
    )
    assert reply.disclaimer_mode == "rfq_required"


def test_rfq_one_pager_intro_uses_rfq_disclaimer() -> None:
    reply = render_chat_reply(
        "rfq_one_pager_intro",
        {
            "intro": "Anfrageziel: Ersatz für einen undichten RWDR an einem Getriebe.",
            "scope_note": "Bekannte Daten und offene Punkte sind klar getrennt; keine finale Freigabe durch sealingAI.",
        },
    )
    assert reply.disclaimer_mode == "rfq_required"
