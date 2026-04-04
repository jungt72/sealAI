from __future__ import annotations

from app.agent.services.medium_context import resolve_medium_context


def test_medium_context_builds_orienting_payload_for_recognized_medium() -> None:
    context = resolve_medium_context("Salzwasser")

    assert context.status == "available"
    assert context.medium_label == "Salzwasser"
    assert context.scope == "orientierend"
    assert context.source_type == "llm_general_knowledge"
    assert context.not_for_release_decisions is True
    assert "Temperatur" in context.followup_points


def test_medium_context_builds_orienting_payload_for_meerwasser_alias_family() -> None:
    context = resolve_medium_context("Meerwasser")

    assert context.status == "available"
    assert context.medium_label == "Meerwasser"
    assert context.source_medium_key == "meerwasser"


def test_medium_context_can_fall_back_to_medium_family() -> None:
    context = resolve_medium_context(None, medium_family="chemisch_aggressiv")

    assert context.status == "available"
    assert context.medium_label == "Chemisch aggressives Medium"
    assert context.source_medium_key == "chemisch_aggressiv"


def test_medium_context_returns_unavailable_without_medium() -> None:
    context = resolve_medium_context(None)

    assert context.status == "unavailable"
    assert context.properties == []
    assert context.challenges == []


def test_medium_context_reuses_cached_payload_when_medium_is_unchanged() -> None:
    previous = resolve_medium_context("Salzwasser")

    resolved = resolve_medium_context("Salzwasser", previous=previous)

    assert resolved is previous


def test_medium_context_updates_when_medium_changes() -> None:
    previous = resolve_medium_context("Salzwasser")

    resolved = resolve_medium_context("Oel", previous=previous)

    assert resolved.medium_label == "Oel"
    assert resolved.source_medium_key != previous.source_medium_key


def test_medium_context_filters_release_style_claims_from_payload() -> None:
    context = resolve_medium_context("Chemikalien")

    dumped = " ".join(context.properties + context.challenges + context.followup_points).lower()
    assert "freigabe" not in dumped
    assert "rfq" not in dumped
    assert "geeignet" not in dumped
