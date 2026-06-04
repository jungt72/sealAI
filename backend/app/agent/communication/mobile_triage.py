"""Mobile leakage triage + low-confidence vision guidance (Blueprint §4.8/§4.9, §7.3/§7.4, §15).

Two deterministic, immediately-available builders for the mobile P0 flow:

* :func:`build_mobile_leakage_triage` — the instant, no-empty-spinner first
  output for "photo + sifft": a ``mobile_triage`` chat reply, a Pocket Cockpit
  patch and action chips. It needs no vision, RAG or graph, so it can be
  returned in well under a second, before any slow vision step runs.
* :func:`build_visual_low_confidence_guidance` — measurement/photo guidance for
  unreadable photos (or when vision is unavailable), never a product guess.

Vision is fully optional and encapsulated behind :class:`VisionPort`. The
default :class:`NullVisionPort` returns nothing, so the flow degrades
gracefully to guidance. Any vision result is an uncertain
``VisualCandidate`` — confirmation-required by type, never auto-asserted.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, Sequence

from app.agent.templates.registry import render_chat_reply
from app.agent.v92.contracts import (
    ActionChip,
    AssistantTurnEnvelope,
    CockpitPatch,
    PocketCockpitPatch,
    VisualCandidate,
)

# Leakage / shaft-seal symptom intent (§7.3). Deterministic, language-scoped.
_LEAKAGE_INTENT_RE = re.compile(
    r"\b(?:sifft|siff|undicht|leck(?:t|age)?|tropft|tröpfelt|"
    r"(?:öl|oel|fett|wasser|medium)\s*(?:läuft|laeuft|tritt|austritt|verlust|verliert)|"
    r"ölverlust|oelverlust|nass|feucht|sip+t)\b",
    re.IGNORECASE,
)

_TRIAGE_IMMEDIATE_CONTEXT = (
    "Ich prüfe das als möglichen Leckagefall an einer Wellendichtung."
)
_TRIAGE_PRIMARY_QUESTION = "Dreht sich die Welle im Betrieb?"
_TRIAGE_ACTION_LABELS = ("Ja", "Nein", "Weiß ich nicht", "Foto vom Einbauort")

# Backend pending-slot context for the triage primary question. Shared with the
# action chips (field) so a later "Ja"/"Nein"/"Weiß ich nicht" answer resolves
# through the existing pending-slot machinery without reading assistant copy.
_TRIAGE_PENDING_FIELD = "shaft_rotates"
_TRIAGE_PENDING_ANSWER_TYPE = "yes_no_unknown"

_LOW_CONFIDENCE_UNCERTAINTY = (
    "Die Beschriftung kann ich auf dem Foto nicht sicher lesen."
)
_LOW_CONFIDENCE_NEXT_STEP = (
    "Für die Anfrage hilft jetzt am meisten: Miss Innendurchmesser, "
    "Außendurchmesser und Breite — oder fotografiere die Stirnseite mit "
    "Beschriftung direkt von oben."
)
_LOW_CONFIDENCE_ACTION_LABELS = (
    "So messe ich d1/D/b",
    "Neues Foto machen",
    "Ich weiß die Maße nicht",
)


def mobile_triage_pending_question() -> "PendingQuestion":
    """Canonical pending-question context for the mobile triage primary question.

    Exposes ``Dreht sich die Welle im Betrieb?`` as a structured pending slot so
    the existing :func:`resolve_slot_answer_binding` machinery can interpret a
    later "Ja"/"Nein"/"Weiß ich nicht" answer as ``shaft_rotates`` yes/no/unknown
    — backend state, not rendered chat text, and never an asserted fact.
    """
    from app.agent.state.models import PendingQuestion  # noqa: PLC0415

    return PendingQuestion(
        target_field=_TRIAGE_PENDING_FIELD,
        expected_answer_type=_TRIAGE_PENDING_ANSWER_TYPE,
        question_text=_TRIAGE_PRIMARY_QUESTION,
        source="system",
        status="open",
    )


def is_leakage_triage_intent(
    message: str | None, *, has_attachment: bool = False
) -> bool:
    """Return whether a turn should enter mobile leakage triage (§7.3)."""
    text = str(message or "")
    if _LEAKAGE_INTENT_RE.search(text):
        return True
    # A photo with a tiny/no caption on mobile is treated as a leakage entry.
    if has_attachment and len(text.strip()) <= 24:
        return True
    return False


# --- Optional, encapsulated vision port (graceful degradation) -------------


class VisionPort(Protocol):
    """Optional vision backend. Implementations must return only candidates."""

    def extract(self, attachment: Any) -> Sequence[VisualCandidate]: ...


class NullVisionPort:
    """Default port: no vision available → no candidates (guidance path)."""

    def extract(self, attachment: Any) -> list[VisualCandidate]:  # noqa: ARG002
        return []


def extract_visual_candidates(
    attachment: Any | None = None,
    *,
    vision: VisionPort | None = None,
) -> list[VisualCandidate]:
    """Extract confirmation-required candidates from an attachment, if possible.

    Returns ``[]`` when no attachment or no vision backend (graceful
    degradation). Any failure inside the optional backend degrades to ``[]``
    rather than raising or guessing. Every returned item is, by type, a
    confirmation-required candidate — never an asserted fact.
    """
    if attachment is None or vision is None:
        return []
    try:
        candidates = list(vision.extract(attachment))
    except Exception:  # noqa: BLE001 - vision is best-effort; degrade to guidance
        return []
    # Defensive: keep only well-formed confirmation-required candidates.
    return [
        c
        for c in candidates
        if isinstance(c, VisualCandidate) and c.requires_confirmation
    ]


def to_cockpit_visual_candidates(
    candidates: Sequence[VisualCandidate],
) -> list[dict[str, Any]]:
    """Project candidates for ``CockpitPatch.visual_candidates`` (Patch-4 render)."""
    return [candidate.model_dump(mode="json") for candidate in candidates]


def _triage_action_chips() -> list[ActionChip]:
    return [
        ActionChip(label="Ja", value="yes", field="shaft_rotates"),
        ActionChip(label="Nein", value="no", field="shaft_rotates"),
        ActionChip(label="Weiß ich nicht", value="unknown", field="shaft_rotates"),
        ActionChip(label="Foto vom Einbauort", action="upload_photo"),
    ]


def _guidance_action_chips() -> list[ActionChip]:
    return [
        ActionChip(label="So messe ich d1/D/b", value="measure_guide"),
        ActionChip(label="Neues Foto machen", action="upload_photo"),
        ActionChip(label="Ich weiß die Maße nicht", value="unknown"),
    ]


def _triage_trace(*, has_attachment: bool, candidate_count: int) -> dict[str, Any]:
    return {
        "route": "mobile_leakage_triage",
        "tier": 2,
        "llm_used": False,
        "rag_used": False,
        "graph_used": False,
        "mobile_surface": True,
        "empty_spinner_violated": False,
        "first_progress_ms": 0,
        "has_attachment": has_attachment,
        "visual_candidate_count": candidate_count,
    }


def build_mobile_leakage_triage(
    *,
    has_attachment: bool = False,
    candidates: Sequence[VisualCandidate] | None = None,
) -> AssistantTurnEnvelope:
    """Immediate mobile leakage triage envelope (§4.8). No vision/RAG/graph."""
    candidates = list(candidates or [])
    chat_reply = render_chat_reply(
        "mobile_triage",
        {
            "immediate_context": _TRIAGE_IMMEDIATE_CONTEXT,
            "primary_question": _TRIAGE_PRIMARY_QUESTION,
        },
        primary_question={"field": "shaft_rotates", "text": _TRIAGE_PRIMARY_QUESTION},
        action_chips=list(_TRIAGE_ACTION_LABELS),
    )
    pocket = PocketCockpitPatch(
        recognized=[
            {
                "label": "Fall",
                "value": "Leckage / Dichtstelle unklar",
                "status": "candidate",
            }
        ],
        critical=[
            {"label": "Dichtungstyp und Wellenbewegung klären", "severity": "high"}
        ],
        next_step={"question": _TRIAGE_PRIMARY_QUESTION, "field": "shaft_rotates"},
        rfq_status="DRAFT",
    )
    cockpit = CockpitPatch(visual_candidates=to_cockpit_visual_candidates(candidates))
    return AssistantTurnEnvelope(
        chat_reply=chat_reply,
        cockpit_patch=cockpit,
        pocket_cockpit_patch=pocket,
        action_chips=_triage_action_chips(),
        pending_question={
            "field": "shaft_rotates",
            "question": _TRIAGE_PRIMARY_QUESTION,
        },
        trace=_triage_trace(
            has_attachment=has_attachment, candidate_count=len(candidates)
        ),
    )


def build_visual_low_confidence_guidance(
    *,
    candidates: Sequence[VisualCandidate] | None = None,
) -> AssistantTurnEnvelope:
    """Measurement/photo guidance for an unreadable photo (§4.9/§7.4)."""
    candidates = list(candidates or [])
    chat_reply = render_chat_reply(
        "visual_low_confidence_guidance",
        {
            "uncertainty_statement": _LOW_CONFIDENCE_UNCERTAINTY,
            "useful_next_step": _LOW_CONFIDENCE_NEXT_STEP,
        },
        action_chips=list(_LOW_CONFIDENCE_ACTION_LABELS),
    )
    pocket = PocketCockpitPatch(
        recognized=[
            {
                "label": "Foto",
                "value": "Beschriftung nicht lesbar",
                "status": "candidate",
            }
        ],
        critical=[
            {
                "label": "Maße messen oder Beschriftung neu fotografieren",
                "severity": "high",
            }
        ],
        next_step={
            "question": "Kannst du d1, D und b messen oder die Stirnseite neu fotografieren?"
        },
        rfq_status="DRAFT",
    )
    cockpit = CockpitPatch(visual_candidates=to_cockpit_visual_candidates(candidates))
    return AssistantTurnEnvelope(
        chat_reply=chat_reply,
        cockpit_patch=cockpit,
        pocket_cockpit_patch=pocket,
        action_chips=_guidance_action_chips(),
        trace={
            **_triage_trace(has_attachment=True, candidate_count=len(candidates)),
            "route": "visual_low_confidence_guidance",
        },
    )


def build_mobile_leakage_turn(
    message: str | None = "",
    *,
    attachment: Any | None = None,
    vision: VisionPort | None = None,
) -> AssistantTurnEnvelope:
    """Orchestrate the mobile leakage entry: immediate triage, vision optional.

    Triage is always produced immediately (no spinner). If a photo is present
    but vision yields no usable candidate, the low-confidence guidance variant
    is returned so the user still gets a concrete next step.
    """
    candidates = extract_visual_candidates(attachment, vision=vision)
    if attachment is not None and not candidates:
        return build_visual_low_confidence_guidance()
    return build_mobile_leakage_triage(
        has_attachment=attachment is not None, candidates=candidates
    )
