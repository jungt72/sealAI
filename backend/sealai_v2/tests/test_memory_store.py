"""In-process memory store — layers 1-3 + the trivial layer-4 seam (build-spec §7).

The headline invariant is tenant isolation (P0): a durable cross-tenant leak is the worst case,
so it is a MODEL invariant tested here now, not a persistence afterthought.
"""

from __future__ import annotations

import pytest

from sealai_v2.core.contracts import RememberedFact
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.security.tenant import TenantScopeError


def _mem() -> InProcessConversationMemory:
    return InProcessConversationMemory()


def test_tenant_isolation_p0_no_cross_tenant_read():
    mem = _mem()
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="EPDM in Öl?",
        answer="...",
        facts=(RememberedFact("medium", "Hydrauliköl"),),
    )
    # SAME session id, DIFFERENT tenant → must never see tenant A's state (P0)
    other = mem.recall(tenant_id="B", session_id="s1")
    assert other.is_empty
    assert mem.case_state(tenant_id="B", session_id="s1") == ()
    assert mem.history(tenant_id="B", session_id="s1") == ()
    assert "s1" not in {s.case_id for s in mem.sessions(tenant_id="B")}
    # tenant A still sees its own
    mine = mem.recall(tenant_id="A", session_id="s1")
    assert not mine.is_empty
    assert any(f.feld == "medium" for f in mine.case_state)


def test_tenant_and_session_mandatory_fail_closed():
    mem = _mem()
    for bad in ("", "   "):
        with pytest.raises(TenantScopeError):
            mem.recall(tenant_id=bad, session_id="s1")
    with pytest.raises(ValueError):
        mem.recall(tenant_id="A", session_id="")


def test_record_turn_builds_bounded_window_and_full_history():
    mem = InProcessConversationMemory(window_turns=2)
    for i in range(4):
        mem.record_turn(
            tenant_id="A", session_id="s1", question=f"q{i}", answer=f"a{i}"
        )
    view = mem.recall(tenant_id="A", session_id="s1")
    # window bounded to the last 2 exchanges (4 messages); history keeps all 8
    assert len(view.window) == 4
    assert view.window[0].text == "q2" and view.window[0].role == "user"
    assert len(mem.history(tenant_id="A", session_id="s1")) == 8


def test_case_state_merge_last_wins_and_stamps_turn():
    mem = _mem()
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="q1",
        answer="a1",
        facts=(RememberedFact("medium", "Hydrauliköl"),),
    )
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="q2",
        answer="a2",
        facts=(RememberedFact("medium", "Wasser"), RememberedFact("temp", "120°C")),
    )
    facts = {f.feld: f for f in mem.case_state(tenant_id="A", session_id="s1")}
    assert facts["medium"].wert == "Wasser"  # last value wins
    assert facts["medium"].as_of_turn == 2  # re-stamped to the current turn (staleness)
    assert facts["temp"].wert == "120°C"


def test_user_control_edit_delete_clear():
    mem = _mem()
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="q",
        answer="a",
        facts=(RememberedFact("medium", "Öl"),),
    )
    mem.edit_fact(tenant_id="A", session_id="s1", feld="medium", wert="Wasser")
    state = {f.feld: f for f in mem.case_state(tenant_id="A", session_id="s1")}
    assert state["medium"].wert == "Wasser"
    assert (
        state["medium"].provenance == "user-edited"
    )  # honesty: provenance reflects the edit
    mem.delete_fact(tenant_id="A", session_id="s1", feld="medium")
    assert mem.case_state(tenant_id="A", session_id="s1") == ()
    mem.clear(tenant_id="A", session_id="s1")
    assert mem.recall(tenant_id="A", session_id="s1").is_empty


def test_sessions_returns_summaries_sorted_by_updated_at_desc():
    mem = _mem()
    mem.record_turn(
        tenant_id="A",
        session_id="s-older",
        question="erste Frage",
        answer="a",
        now="2026-07-01T00:00:00Z",
    )
    mem.record_turn(
        tenant_id="A",
        session_id="s-newer",
        question="zweite Frage",
        answer="a",
        now="2026-07-02T00:00:00Z",
    )
    summaries = mem.sessions(tenant_id="A")
    assert [s.case_id for s in summaries] == ["s-newer", "s-older"]
    assert summaries[0].updated_at == "2026-07-02T00:00:00Z"


def test_record_turn_without_now_leaves_title_and_timestamps_unset():
    mem = _mem()
    mem.record_turn(tenant_id="A", session_id="s1", question="q", answer="a")
    summary = mem.sessions(tenant_id="A")[0]
    assert summary.title is None
    assert summary.created_at is None
    assert summary.updated_at is None


def test_record_turn_stamps_title_from_first_question_and_bumps_updated_at():
    mem = _mem()
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="Welche Dichtung passt für EPDM in Hydrauliköl bei 120°C?",
        answer="a1",
        now="2026-07-03T00:00:00Z",
    )
    first = mem.sessions(tenant_id="A")[0]
    assert first.title == "Welche Dichtung passt für EPDM in Hydrauliköl bei 120°C?"
    assert first.created_at == "2026-07-03T00:00:00Z"
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="und bei 150°C?",
        answer="a2",
        now="2026-07-03T01:00:00Z",
    )
    second = mem.sessions(tenant_id="A")[0]
    assert second.title == first.title  # title never changes after the first turn
    assert second.created_at == "2026-07-03T00:00:00Z"  # created_at never moves
    assert second.updated_at == "2026-07-03T01:00:00Z"  # updated_at bumps every turn


def test_cross_session_seam_inert_but_tenant_scoped():
    x = InProcessCrossSessionMemory()
    x.remember_durable(tenant_id="A", facts=(RememberedFact("anwendung", "RWDR"),))
    # door open, logic deferred → nothing injected back yet (dedicated sub-gate)
    assert x.relevant_facts(tenant_id="A", query="RWDR") == ()
    with pytest.raises(TenantScopeError):
        x.relevant_facts(tenant_id="", query="x")
