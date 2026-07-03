"""Pure status-transition state machine (Patch 4) — no DB, no API, just the rule table."""

from __future__ import annotations

import pytest

from sealai_v2.memory.curated import MemoryStatus, is_valid_transition


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (MemoryStatus.CANDIDATE, MemoryStatus.CONFIRMED),
        (MemoryStatus.CANDIDATE, MemoryStatus.REJECTED),
        (MemoryStatus.CANDIDATE, MemoryStatus.DELETED_PENDING_PURGE),
        (MemoryStatus.IMPLICIT_CONTEXT, MemoryStatus.CONFIRMED),
        (MemoryStatus.IMPLICIT_CONTEXT, MemoryStatus.REJECTED),
        (MemoryStatus.IMPLICIT_CONTEXT, MemoryStatus.DELETED_PENDING_PURGE),
        (MemoryStatus.CONFIRMED, MemoryStatus.DEPRECATED),
        (MemoryStatus.CONFIRMED, MemoryStatus.DELETED_PENDING_PURGE),
        (MemoryStatus.REJECTED, MemoryStatus.DELETED_PENDING_PURGE),
        (MemoryStatus.DEPRECATED, MemoryStatus.DELETED_PENDING_PURGE),
    ],
)
def test_documented_valid_transitions(from_status, to_status):
    assert is_valid_transition(from_status, to_status) is True


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (MemoryStatus.CONFIRMED, MemoryStatus.CANDIDATE),  # no going back to candidate
        (
            MemoryStatus.CONFIRMED,
            MemoryStatus.REJECTED,
        ),  # confirmed → deprecated, never rejected
        (
            MemoryStatus.REJECTED,
            MemoryStatus.CONFIRMED,
        ),  # a rejected fact can't be re-confirmed
        (MemoryStatus.DEPRECATED, MemoryStatus.CONFIRMED),  # no un-deprecating
        (MemoryStatus.DELETED_PENDING_PURGE, MemoryStatus.CONFIRMED),  # terminal
        (MemoryStatus.DELETED_PENDING_PURGE, MemoryStatus.CANDIDATE),  # terminal
        (MemoryStatus.PURGED, MemoryStatus.CANDIDATE),  # fully terminal
        (MemoryStatus.CANDIDATE, MemoryStatus.DEPRECATED),  # must be confirmed first
        (
            MemoryStatus.CANDIDATE,
            MemoryStatus.PURGED,
        ),  # only the purge job can reach PURGED
    ],
)
def test_documented_invalid_transitions(from_status, to_status):
    assert is_valid_transition(from_status, to_status) is False


def test_every_status_has_an_explicit_entry_in_the_transition_table():
    # Guards against a future MemoryStatus addition silently having no transition rule at all.
    for status in MemoryStatus:
        assert (
            is_valid_transition(status, status) is False
        )  # never a no-op "transition"
