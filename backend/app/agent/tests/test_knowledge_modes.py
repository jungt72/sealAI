"""Patch 7 tests — Knowledge Contract mode separation + mutation policy.

Covers Blueprint §8 (seven modes) and §27.5 (no mutation without new facts):
non-mutating modes leave case_revision unchanged; knowledge_case_mutating runs
only the supplied facts through the State Gate; why-question explains without
mutation or full-case mirroring.
"""

from __future__ import annotations

import pytest

from app.agent.communication.knowledge_modes import (
    KNOWLEDGE_MODE_MUTATES,
    apply_knowledge_turn,
    build_why_question_reply,
    has_new_technical_facts,
    mode_mutates,
    resolve_knowledge_mode,
)
from app.agent.state.models import GovernedSessionState
from app.agent.v92.dashboard_contract import extract_case_revision


# --- Mode separation (§8) ---------------------------------------------------


def test_knowledge_general_when_no_case() -> None:
    assert (
        resolve_knowledge_mode("Was ist FFKM?", has_active_case=False)
        == "knowledge_general"
    )


def test_knowledge_case_aware_when_case_present_no_facts() -> None:
    assert (
        resolve_knowledge_mode("Was bedeutet FKM in meinem Fall?", has_active_case=True)
        == "knowledge_case_aware"
    )


def test_knowledge_case_mutating_when_new_facts_present() -> None:
    mode = resolve_knowledge_mode(
        "Wir verwenden FKM, Öltemperatur 100 °C", has_active_case=True
    )
    assert mode == "knowledge_case_mutating"
    assert has_new_technical_facts("Wir verwenden FKM, Öltemperatur 100 °C") is True


def test_comparison_modes_split_by_case_presence() -> None:
    assert (
        resolve_knowledge_mode("Was ist besser, NBR oder FKM?", has_active_case=False)
        == "comparison_general"
    )
    assert (
        resolve_knowledge_mode("NBR oder FKM für meinen Fall?", has_active_case=True)
        == "comparison_case_aware"
    )


def test_norm_documentation_mode() -> None:
    assert (
        resolve_knowledge_mode(
            "Was bedeutet WRAS bei einem RWDR?", has_active_case=True
        )
        == "norm_documentation_knowledge"
    )


def test_why_question_mode_requires_active_case() -> None:
    assert (
        resolve_knowledge_mode("Warum fragst du nach der Welle?", has_active_case=True)
        == "why_question_active_case"
    )
    # Without a case a bare "why" degrades to general knowledge, not a case mode.
    assert (
        resolve_knowledge_mode("Warum ist das wichtig?", has_active_case=False)
        == "knowledge_general"
    )


# --- Mutation policy (§8.2 / §27.5) -----------------------------------------


def test_only_case_mutating_mutates() -> None:
    mutating = [mode for mode, flag in KNOWLEDGE_MODE_MUTATES.items() if flag]
    assert mutating == ["knowledge_case_mutating"]
    assert mode_mutates("knowledge_general") is False
    assert mode_mutates("why_question_active_case") is False
    assert mode_mutates("knowledge_case_mutating") is True


@pytest.mark.parametrize(
    ("message", "has_case"),
    [
        ("Was ist FFKM?", False),  # knowledge_general
        ("Was bedeutet FKM in meinem Fall?", True),  # knowledge_case_aware
        ("Warum fragst du nach der Welle?", True),  # why_question_active_case
        ("Was ist besser, NBR oder FKM?", False),  # comparison_general
        ("Was bedeutet WRAS?", True),  # norm_documentation_knowledge
    ],
)
def test_non_mutating_modes_leave_case_revision_unchanged(
    message: str, has_case: bool
) -> None:
    state = GovernedSessionState()
    revision_before = extract_case_revision(state)
    result = apply_knowledge_turn(state, message, has_active_case=has_case)
    # No mutation at all: same object, same revision.
    assert result is state
    assert extract_case_revision(result) == revision_before


def test_case_mutating_runs_only_supplied_facts_through_state_gate() -> None:
    state = GovernedSessionState()
    result = apply_knowledge_turn(
        state, "Wir verwenden FKM, Öltemperatur 100 °C", has_active_case=True
    )
    # State actually changed (a new object) and the fact entered via the gate.
    assert result is not state
    assert "temperature_c" in result.normalized.parameters
    assert result.normalized.parameters["temperature_c"].value == 100
    # Only the supplied facts were applied — no unrelated fields invented.
    applied = set(result.normalized.parameters)
    assert applied.issubset(
        {
            "temperature_c",
            "pressure_bar",
            "shaft_diameter_mm",
            "speed_rpm",
            "medium",
            "material",
        }
    )


# --- why-question reply (§8.10) reuses senior_engineer_short + No-Go guard ---


def test_why_question_reply_uses_senior_engineer_short_and_suppresses_disclaimer() -> (
    None
):
    reply = build_why_question_reply(
        opening="Weil der neue Ring auf genau dieser Stelle läuft.",
        technical_hint="Ist die Welle dort eingelaufen, dichtet auch ein neuer RWDR oft nicht lange.",
        primary_question="Ist die Stelle glatt, oder siehst du eine Spur/Rille?",
    )
    assert reply.style == "senior_engineer_short"
    assert reply.disclaimer_mode == "suppress_normal_turn"
    assert "Weil der neue Ring" in reply.markdown
    # Must not mirror the whole case / use a No-Go protocol phrase.
    assert "Ich verstehe den Fall aktuell als" not in reply.markdown
