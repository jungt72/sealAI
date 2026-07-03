"""Memory context assembler (Patch 8, pure part) — max 8 items, max 750 tokens, max 10% of prompt
budget when known, NEVER-usage items dropped before consuming budget, context_sources mirrors
entries 1:1."""

from __future__ import annotations

from sealai_v2.memory.context_assembler import (
    MAX_ITEMS,
    MAX_TOKENS,
    build_context_bundle,
)
from sealai_v2.memory.curated import (
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
        status=MemoryStatus.CONFIRMED,
        content="prefers metric units",
        semantic_key="pref:units:metric",
        sources=(MemorySource(kind="user_stated", session_id="session-1"),),
        created_at="2026-07-03T00:00:00Z",
        updated_at="2026-07-03T00:00:00Z",
    )
    defaults.update(overrides)
    return MemoryItem(**defaults)


def test_empty_input_yields_empty_bundle():
    bundle = build_context_bundle([])
    assert bundle.is_empty
    assert bundle.total_estimated_tokens == 0
    assert bundle.context_sources == ()


def test_a_single_confirmed_preference_is_included():
    bundle = build_context_bundle([_item()])
    assert len(bundle.entries) == 1
    assert bundle.entries[0].item_id == "mem-1"
    assert bundle.entries[0].usage.value == "style_only"


def test_never_usable_item_is_dropped():
    rejected = _item(status=MemoryStatus.REJECTED)
    bundle = build_context_bundle([rejected])
    assert bundle.is_empty


def test_max_items_cap_is_eight():
    items = [_item(id=f"m{i}", semantic_key=f"k{i}") for i in range(20)]
    bundle = build_context_bundle(items)
    assert len(bundle.entries) == MAX_ITEMS


def test_max_items_respects_a_custom_override():
    items = [_item(id=f"m{i}", semantic_key=f"k{i}") for i in range(20)]
    bundle = build_context_bundle(items, max_items=3)
    assert len(bundle.entries) == 3


def test_never_items_do_not_count_against_max_items():
    # 8 confirmed + 2 rejected, interleaved — the 2 rejected must not "use up" item slots.
    items = []
    for i in range(8):
        items.append(_item(id=f"ok{i}", semantic_key=f"ok{i}"))
    for i in range(2):
        items.append(
            _item(id=f"bad{i}", semantic_key=f"bad{i}", status=MemoryStatus.REJECTED)
        )
    bundle = build_context_bundle(items, max_items=8)
    assert len(bundle.entries) == 8
    assert all(not e.item_id.startswith("bad") for e in bundle.entries)


def test_token_budget_cap_stops_including_items():
    # Each item's content is long enough to individually estimate to ~50 tokens (200 chars / 4).
    long_content = "x" * 200
    items = [
        _item(id=f"m{i}", semantic_key=f"k{i}", content=long_content) for i in range(20)
    ]
    bundle = build_context_bundle(items, max_tokens=120)
    assert bundle.total_estimated_tokens <= 120
    assert len(bundle.entries) < 20  # the token cap bit before max_items did


def test_token_budget_skips_an_oversized_item_but_keeps_trying_smaller_ones():
    huge = _item(
        id="huge", semantic_key="huge", content="x" * 4000
    )  # ~1000 tokens, over budget alone
    small = _item(id="small", semantic_key="small", content="short")
    bundle = build_context_bundle([huge, small], max_tokens=MAX_TOKENS)
    ids = [e.item_id for e in bundle.entries]
    assert "huge" not in ids
    assert (
        "small" in ids
    )  # smaller items after a skipped oversized one still get a chance


def test_prompt_fraction_ten_percent_caps_below_the_flat_token_max():
    long_content = "x" * 2000  # ~500 tokens
    items = [
        _item(id=f"m{i}", semantic_key=f"k{i}", content=long_content) for i in range(5)
    ]
    # 10% of a 1000-token prompt budget = 100 tokens — well below the flat MAX_TOKENS=750 cap.
    bundle = build_context_bundle(items, prompt_token_budget=1000)
    assert bundle.total_estimated_tokens <= 100


def test_prompt_fraction_never_exceeds_the_flat_token_max_even_for_a_huge_prompt():
    long_content = "x" * 4000  # ~1000 tokens each
    items = [
        _item(id=f"m{i}", semantic_key=f"k{i}", content=long_content) for i in range(10)
    ]
    # 10% of a 100,000-token prompt would be 10,000 — the flat MAX_TOKENS=750 cap must still win.
    bundle = build_context_bundle(items, prompt_token_budget=100_000)
    assert bundle.total_estimated_tokens <= MAX_TOKENS


def test_context_sources_mirrors_entries_one_to_one():
    items = [_item(id=f"m{i}", semantic_key=f"k{i}") for i in range(3)]
    bundle = build_context_bundle(items)
    assert len(bundle.context_sources) == len(bundle.entries)
    for src, entry in zip(bundle.context_sources, bundle.entries):
        assert src["item_id"] == entry.item_id
        assert src["usage"] == entry.usage.value
        assert src["scope"] == entry.scope
        assert src["type"] == entry.type


def test_relevance_order_is_preserved_not_resorted():
    items = [
        _item(id="c", semantic_key="c"),
        _item(id="a", semantic_key="a"),
        _item(id="b", semantic_key="b"),
    ]
    bundle = build_context_bundle(items)
    assert [e.item_id for e in bundle.entries] == ["c", "a", "b"]


def test_implicit_context_and_technical_note_usages_are_correctly_labeled():
    hint = _item(
        id="hint",
        semantic_key="hint",
        status=MemoryStatus.IMPLICIT_CONTEXT,
        scope=MemoryScope.SESSION,
    )
    note = _item(
        id="note",
        semantic_key="note",
        type=MemoryType.TECHNICAL_NOTE,
        status=MemoryStatus.CONFIRMED,
    )
    bundle = build_context_bundle([hint, note])
    by_id = {e.item_id: e.usage.value for e in bundle.entries}
    assert by_id["hint"] == "ask_clarifying_question_only"
    assert by_id["note"] == "context_only"
