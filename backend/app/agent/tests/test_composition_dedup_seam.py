"""Group C (T5.1) — composition/dedup seam.

A side-turn must render ONE acknowledgment, never a double seam, when the base
answer and the appended resume/context template name the same fact.

Two roots, both OUTPUT-TEXT assembly only (no mutation/routing/enforcement):
  - chat.py `_side_answer_with_resume` medium_candidate branch (~516-533) appended
    the "Ich habe <value> … erkannt" seam unconditionally, while the resume path
    (chat.py:550) already had the dedup guard
    (`if target_question.casefold() not in base.casefold()`).
  - active_case_side_claim_policy.py `_ensure_required_context` (:422) joined
    `additions` without an overlap-check, so an addition already present in the
    answer duplicated. The no-medium sentence "Ich setze dabei kein Medium voraus…"
    evades its own keyword guard (which checks "ich setze kein medium voraus" —
    without "dabei"), so it is the concrete duplicate.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agent.api.routes import chat as chat_routes
from app.agent.communication.active_case_side_claim_policy import (
    ActiveCaseSideSpeakableFacts,
    _ensure_required_context,
    _normalize,
)


def _medium_slot_decision(value: str) -> SimpleNamespace:
    return SimpleNamespace(
        slot_answer_detected=True,
        detected_slot_value=value,
        detected_slot_field="medium",
        resume_target_question="",
        next_runtime_action="",
    )


# --- chat.py _side_answer_with_resume (S8 repro) ------------------------------


def test_side_answer_dedups_medium_value_already_in_base() -> None:
    # base already names the detected value → one acknowledgment, no second seam.
    base = "Öl ist als Schmiermedium verbreitet und chemisch vergleichsweise gutartig."
    result = chat_routes._side_answer_with_resume(base, _medium_slot_decision("Öl"))
    assert result == base


def test_side_answer_keeps_medium_seam_when_value_absent() -> None:
    # value genuinely new → the seam is preserved (guard against over-dedup).
    base = "Schmiermedien sind chemisch oft vergleichsweise gutartig."
    result = chat_routes._side_answer_with_resume(base, _medium_slot_decision("Öl"))
    assert result != base
    assert len(result) > len(base)


# --- active_case_side_claim_policy _ensure_required_context (:422) ------------

_NO_MEDIUM = (
    "Ich setze dabei kein Medium voraus; dieser Wert ist im aktuellen Fall noch offen."
)


def test_ensure_required_context_does_not_duplicate_existing_addition() -> None:
    answer = f"Das Medium ist im Fall noch offen. {_NO_MEDIUM}"
    result = _ensure_required_context(
        latest_user_message="warum ist das medium wichtig fuer die dichtung?",
        answer_markdown=answer,
        speakable_facts=ActiveCaseSideSpeakableFacts(missing_fields=("medium",)),
    )
    assert _normalize(result).count(_normalize(_NO_MEDIUM)) == 1
