"""Memory policy (Patch 7) — the full doctrine matrix, plus the structural check that MemoryUsage
has no "recommendation"/"full-trust" value at all (the actual enforcement mechanism)."""

from __future__ import annotations

import pytest

from sealai_v2.memory.curated import (
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)
from sealai_v2.memory.policy import MemoryUsage, usage_for


def _item(**overrides) -> MemoryItem:
    defaults = dict(
        id="mem-1",
        tenant_id="tenant-a",
        scope=MemoryScope.SESSION,
        scope_id="session-1",
        type=MemoryType.PREFERENCE,
        status=MemoryStatus.CONFIRMED,
        content="prefers metric units",
        semantic_key="pref:units:metric",
        sources=(MemorySource(kind="user_stated", session_id="session-1"),),
        created_at="2026-07-03T00:00:00Z",
        updated_at="2026-07-03T00:00:00Z",
    )
    defaults.update(overrides)
    return MemoryItem(**defaults)


def test_memory_usage_has_no_recommendation_or_full_trust_value():
    # The actual enforcement of "Memory darf technische Eignung niemals allein begründen": there is
    # structurally no value this policy can hand out that means "safe to recommend from".
    values = {u.value for u in MemoryUsage}
    assert values == {
        "style_only",
        "ask_clarifying_question_only",
        "context_only",
        "never",
    }
    assert not any("recommend" in v for v in values)


@pytest.mark.parametrize("status", [MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED])
def test_preference_is_always_style_only(status):
    item = _item(type=MemoryType.PREFERENCE, status=status)
    assert usage_for(item) == MemoryUsage.STYLE_ONLY


@pytest.mark.parametrize(
    "item_type",
    [MemoryType.PREFERENCE, MemoryType.TECHNICAL_NOTE, MemoryType.CASE_PARAMETER],
)
def test_implicit_context_status_overrides_type_always_clarifying_question_only(
    item_type,
):
    item = _item(
        type=item_type, status=MemoryStatus.IMPLICIT_CONTEXT, scope=MemoryScope.CASE
    )
    assert usage_for(item) == MemoryUsage.ASK_CLARIFYING_QUESTION_ONLY


@pytest.mark.parametrize("status", [MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED])
def test_technical_note_is_always_context_only_never_recommendation(status):
    item = _item(type=MemoryType.TECHNICAL_NOTE, status=status)
    assert usage_for(item) == MemoryUsage.CONTEXT_ONLY


def test_case_parameter_confirmed_and_case_scoped_is_context_only():
    item = _item(
        type=MemoryType.CASE_PARAMETER,
        status=MemoryStatus.CONFIRMED,
        scope=MemoryScope.CASE,
        scope_id="case-1",
    )
    assert usage_for(item) == MemoryUsage.CONTEXT_ONLY


def test_case_parameter_unconfirmed_is_never_even_if_case_scoped():
    item = _item(
        type=MemoryType.CASE_PARAMETER,
        status=MemoryStatus.CANDIDATE,
        scope=MemoryScope.CASE,
        scope_id="case-1",
    )
    assert usage_for(item) == MemoryUsage.NEVER


@pytest.mark.parametrize(
    "scope",
    [
        MemoryScope.SESSION,
        MemoryScope.USER,
        MemoryScope.PROJECT,
        MemoryScope.WORKSPACE,
        MemoryScope.TENANT,
    ],
)
def test_case_parameter_confirmed_but_not_case_scoped_is_never(scope):
    item = _item(
        type=MemoryType.CASE_PARAMETER, status=MemoryStatus.CONFIRMED, scope=scope
    )
    assert usage_for(item) == MemoryUsage.NEVER


@pytest.mark.parametrize(
    "status",
    [
        MemoryStatus.REJECTED,
        MemoryStatus.DEPRECATED,
        MemoryStatus.DELETED_PENDING_PURGE,
        MemoryStatus.PURGED,
    ],
)
@pytest.mark.parametrize(
    "item_type",
    [MemoryType.PREFERENCE, MemoryType.TECHNICAL_NOTE, MemoryType.CASE_PARAMETER],
)
def test_never_injectable_statuses_are_always_never_regardless_of_type(
    status, item_type
):
    # Fail-closed defense in depth: Patch 6's revalidate() should already have excluded these, but
    # if a caller somehow hands policy a non-revalidated item, it must not grant anything.
    item = _item(type=item_type, status=status, scope=MemoryScope.CASE)
    assert usage_for(item) == MemoryUsage.NEVER
