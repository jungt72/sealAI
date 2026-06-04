"""Patch 1 contract tests for the V1.6 multi-output turn envelope.

These guard the additive ``AssistantTurnEnvelope`` family (Blueprint §11, §28):
defaults, serialization shape and JSON round-trip. No runtime wiring yet.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.v92.contracts import (
    ActionChip,
    AssistantTurnEnvelope,
    ChatReply,
    CockpitPatch,
    ComputedValue,
    KnownField,
    PocketCockpitPatch,
    ReviewFlag,
)


def test_minimal_envelope_defaults() -> None:
    envelope = AssistantTurnEnvelope(
        chat_reply=ChatReply(style="senior_engineer_short", markdown="Okay.")
    )

    # Defaults match Blueprint §28.2 reference schema.
    assert envelope.chat_reply.disclaimer_mode == "suppress_normal_turn"
    assert isinstance(envelope.cockpit_patch, CockpitPatch)
    assert envelope.cockpit_patch.known_fields == []
    assert envelope.pocket_cockpit_patch is None
    assert envelope.action_chips == []
    assert envelope.pending_question is None
    assert envelope.trace == {}


def test_full_envelope_serializes_and_round_trips() -> None:
    envelope = AssistantTurnEnvelope(
        chat_reply=ChatReply(
            style="mobile_triage",
            markdown="Ich prüfe das als möglichen Leckagefall.",
            primary_question={
                "field": "shaft_rotates",
                "text": "Dreht sich die Welle?",
            },
            template_id="chat.mobile_triage.v1",
        ),
        cockpit_patch=CockpitPatch(
            known_fields=[
                KnownField(
                    field="speed_rpm",
                    label="Drehzahl",
                    value=1500,
                    unit="rpm",
                    status="confirmed",
                    origin="user_direct_answer",
                    approximate=True,
                )
            ],
            computed_values=[
                ComputedValue(
                    field="surface_speed_ms",
                    label="Umfangsgeschwindigkeit",
                    value=3.53,
                    unit="m/s",
                    formula="pi * d1_mm * rpm / 60000",
                )
            ],
            review_flags=[
                ReviewFlag(
                    key="shaft_counterface",
                    label="Wellenlauffläche prüfen",
                    severity="high",
                    reason="Altteil undicht; Lauffläche entscheidend.",
                )
            ],
            active_question={"field": "shaft_surface_condition"},
        ),
        pocket_cockpit_patch=PocketCockpitPatch(
            recognized=[{"label": "Fall", "value": "Leckage", "status": "candidate"}],
            critical=[{"label": "Wellenlauffläche prüfen", "severity": "high"}],
            next_step={"question": "Dreht sich die Welle?"},
            rfq_status="DRAFT",
        ),
        action_chips=[
            ActionChip(label="Ja", value="yes", field="shaft_rotates"),
            ActionChip(label="Foto senden", action="upload_photo"),
        ],
        pending_question={"field": "shaft_surface_condition"},
        trace={"route": "mobile_leakage_triage", "tier": 2},
    )

    dumped = envelope.model_dump()
    assert dumped["chat_reply"]["style"] == "mobile_triage"
    assert dumped["cockpit_patch"]["computed_values"][0]["origin"] == "calculated"
    assert dumped["pocket_cockpit_patch"]["rfq_status"] == "DRAFT"
    assert [chip["label"] for chip in dumped["action_chips"]] == ["Ja", "Foto senden"]

    # JSON round-trip preserves the contract.
    restored = AssistantTurnEnvelope.model_validate_json(envelope.model_dump_json())
    assert restored == envelope


def test_invalid_chat_reply_style_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ChatReply(style="not_a_real_style", markdown="x")


def test_computed_value_origin_is_locked_to_calculated() -> None:
    value = ComputedValue(field="x", label="X", value=1)
    assert value.origin == "calculated"
