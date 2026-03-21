"""Tests for SEALAI v4.4.0 Router Node (Sprint 3).

Acceptance criterion: Router classifies 10 test cases correctly.
All tests are deterministic — no LLM mocking required.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from app._legacy_v2.nodes.node_router import classify_input, node_router
from app._legacy_v2.state import SealAIState, WorkingMemory
from app.services.rag.state import WorkingProfile


def _state_with_message(text: str, **kwargs) -> SealAIState:
    """Helper: minimal state with a single user message."""
    return SealAIState(
        messages=[HumanMessage(content=text)],
        **kwargs,
    )


# ── 1. Empty state + greeting → new_case ──────────────────────────────────


def test_empty_state_greeting_classifies_as_new_case() -> None:
    state = _state_with_message("Hallo, ich brauche eine Dichtung")
    assert classify_input(state, "Hallo, ich brauche eine Dichtung") == "new_case"


# ── 2. Empty state + technical question → new_case ────────────────────────


def test_empty_state_technical_question_classifies_as_new_case() -> None:
    state = _state_with_message("Welche Dichtung hält 200 bar bei 300°C?")
    assert classify_input(state, "Welche Dichtung hält 200 bar bei 300°C?") == "new_case"


# ── 3. Has parameters + user changes pressure → follow_up ─────────────────


def test_existing_params_pressure_change_classifies_as_follow_up() -> None:
    state = _state_with_message(
        "Ändere den Druck auf 150 bar",
        working_profile=WorkingProfile(pressure_bar=100.0, medium="Hydrauliköl"),
    )
    assert classify_input(state, "Ändere den Druck auf 150 bar") == "follow_up"


# ── 4. Has parameters + user changes medium → follow_up ───────────────────


def test_existing_params_medium_change_classifies_as_follow_up() -> None:
    state = _state_with_message(
        "Stattdessen Dampf als Medium",
        working_profile=WorkingProfile(pressure_bar=50.0, medium="Wasser"),
    )
    assert classify_input(state, "Stattdessen Dampf als Medium") == "follow_up"


# ── 5. Has response + "Warum?" → clarification ────────────────────────────


def test_prior_response_warum_classifies_as_clarification() -> None:
    state = _state_with_message(
        "Warum?",
        working_memory=WorkingMemory(response_text="Empfehlung: PTFE-Spiraldichtung"),
    )
    assert classify_input(state, "Warum?") == "clarification"


# ── 6. Has response + "Erkläre das genauer" → clarification ───────────────


def test_prior_response_erklaere_classifies_as_clarification() -> None:
    state = _state_with_message(
        "Erkläre das genauer",
        working_memory=WorkingMemory(response_text="Empfehlung: FKM O-Ring"),
    )
    assert classify_input(state, "Erkläre das genauer") == "clarification"


# ── 7. "Angebote einholen" → rfq_trigger ──────────────────────────────────


def test_angebote_einholen_classifies_as_rfq_trigger() -> None:
    state = _state_with_message("Angebote einholen")
    assert classify_input(state, "Angebote einholen") == "rfq_trigger"


# ── 8. "RFQ senden" → rfq_trigger ─────────────────────────────────────────


def test_rfq_senden_classifies_as_rfq_trigger() -> None:
    state = _state_with_message("Bitte RFQ senden")
    assert classify_input(state, "Bitte RFQ senden") == "rfq_trigger"


@pytest.mark.parametrize(
    "user_text",
    [
        "Kannst du ein Angebot für FKM erstellen?",
        "Das ist eine Preisanfrage für 100 Stück.",
        "Ich brauche ein Angebot für FFKM.",
        "Quote for 50 pieces, please.",
        "Bitte um ein Angebot für EPDM.",
    ],
)
def test_natural_language_rfq_intents_classify_as_rfq_trigger(user_text: str) -> None:
    state = _state_with_message(user_text)
    assert classify_input(state, user_text) == "rfq_trigger"


# ── 9. HITL awaiting confirmation → resume ─────────────────────────────────


def test_hitl_awaiting_confirmation_classifies_as_resume() -> None:
    state = _state_with_message(
        "Ja, freigeben",
        awaiting_user_confirmation=True,
        confirm_decision="approve",
    )
    assert classify_input(state, "Ja, freigeben") == "resume"


# ── 9b. Pending HITL/QGate without decision must not fall back to new_case ──


def test_pending_hitl_without_decision_classifies_as_resume() -> None:
    state = _state_with_message(
        "Wie geht es weiter?",
        awaiting_user_confirmation=True,
        confirm_decision=None,
        pending_action="qgate_blockers",
        qgate_has_blockers=True,
    )
    assert classify_input(state, "Wie geht es weiter?") == "resume"


# ── 10. Existing params + explicit "neue Anfrage" → new_case ──────────────


def test_existing_params_neue_anfrage_classifies_as_new_case() -> None:
    state = _state_with_message(
        "Neue Anfrage starten",
        working_profile=WorkingProfile(pressure_bar=100.0, medium="H2"),
    )
    assert classify_input(state, "Neue Anfrage starten") == "new_case"


# ── Integration: node_router returns correct state shape ───────────────────


def test_node_router_returns_expected_state_keys() -> None:
    state = _state_with_message("Hallo")
    result = node_router(state)
    assert result["conversation"]["router_classification"] == "new_case"
    assert result["reasoning"]["phase"] == "routing"
    assert result["reasoning"]["last_node"] == "node_router"
