from __future__ import annotations

import pytest

from sealai_v2.memory.curated import (
    NEVER_INJECTABLE_STATUSES,
    MemoryItem,
    MemoryScope,
    MemorySource,
    MemoryStatus,
    MemoryType,
)


def _item(**overrides) -> MemoryItem:
    defaults = dict(
        id="mem-1",
        tenant_id="tenant-a",
        scope=MemoryScope.SESSION,
        scope_id="session-1",
        type=MemoryType.PREFERENCE,
        status=MemoryStatus.CANDIDATE,
        content="prefers metric units",
        semantic_key="pref:units:metric",
    )
    defaults.update(overrides)
    return MemoryItem(**defaults)


def test_scope_enum_has_all_six_documented_levels():
    assert {s.value for s in MemoryScope} == {
        "user",
        "workspace",
        "tenant",
        "project",
        "case",
        "session",
    }


def test_status_enum_has_all_seven_documented_states():
    assert {s.value for s in MemoryStatus} == {
        "candidate",
        "implicit_context",
        "confirmed",
        "rejected",
        "deprecated",
        "deleted_pending_purge",
        "purged",
    }


def test_type_enum_has_the_full_nine_types_from_the_final_concept_doc():
    # Patch 9 reconciliation: the earlier 3-value set (preference/technical_note/case_parameter)
    # was a correct-but-incomplete inference — this is now the full §3 enum.
    assert {t.value for t in MemoryType} == {
        "preference",
        "workflow_instruction",
        "project_context",
        "case_parameter",
        "technical_note",
        "manufacturer_feedback",
        "rfq_pattern",
        "risk_note",
        "conversation_summary",
    }


def test_memory_item_rejects_blank_tenant():
    with pytest.raises(ValueError, match="tenant_id"):
        _item(tenant_id="  ")


def test_memory_item_rejects_blank_scope_id():
    with pytest.raises(ValueError, match="scope_id"):
        _item(scope_id="")


def test_memory_item_rejects_blank_semantic_key():
    with pytest.raises(ValueError, match="semantic_key"):
        _item(semantic_key="")


@pytest.mark.parametrize(
    "status",
    [MemoryStatus.CANDIDATE, MemoryStatus.IMPLICIT_CONTEXT, MemoryStatus.CONFIRMED],
)
def test_is_injectable_true_for_live_statuses(status):
    assert _item(status=status).is_injectable is True


@pytest.mark.parametrize(
    "status",
    [
        MemoryStatus.REJECTED,
        MemoryStatus.DEPRECATED,
        MemoryStatus.DELETED_PENDING_PURGE,
        MemoryStatus.PURGED,
    ],
)
def test_is_injectable_false_for_terminal_statuses(status):
    assert _item(status=status).is_injectable is False


def test_never_injectable_statuses_matches_is_injectable_property():
    # Single source of truth check: the frozenset and the property must never diverge.
    for status in MemoryStatus:
        item = _item(status=status)
        assert item.is_injectable == (status not in NEVER_INJECTABLE_STATUSES)


def test_memory_item_defaults_are_pure_no_clock_no_io():
    item = _item()
    assert item.created_at == "" and item.updated_at == ""
    assert item.deleted_at is None and item.purge_after is None
    assert item.version == 1
    assert item.sources == ()


def test_memory_item_patch9_fields_have_safe_inert_defaults():
    # Patch 9 additions: wired for persistence but not yet consumed by any policy rule — defaults
    # must be the most conservative choice (full confidence, internal sensitivity, no conflict links).
    item = _item()
    assert item.confidence == 1.0
    assert item.sensitivity == "internal"
    assert item.subject_hash is None
    assert item.supersedes_memory_id is None
    assert item.deprecated_by_memory_id is None


def test_memory_source_is_a_plain_immutable_record():
    src = MemorySource(
        kind="user_stated", session_id="s1", turn_id="t1", note="said explicitly"
    )
    assert src.kind == "user_stated"
    with pytest.raises(AttributeError):
        src.kind = "other"  # type: ignore[misc]  # frozen dataclass


def test_memory_source_patch9_reference_fields_default_to_none():
    src = MemorySource(kind="user_stated")
    assert src.source_ref is None
    assert src.message_id is None
    assert src.document_id is None
    assert src.case_snapshot_id is None


def test_memory_source_patch9_reference_fields_can_be_set():
    src = MemorySource(
        kind="doc_extracted",
        source_ref="upload-42",
        message_id="msg-7",
        document_id="doc-9",
        case_snapshot_id="case-snap-3",
    )
    assert src.source_ref == "upload-42"
    assert src.message_id == "msg-7"
    assert src.document_id == "doc-9"
    assert src.case_snapshot_id == "case-snap-3"


def test_memory_item_is_frozen():
    item = _item()
    with pytest.raises(AttributeError):
        item.content = "changed"  # type: ignore[misc]
