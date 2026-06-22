"""Durable persistence — ``PostgresConversationMemory`` parity + restart-survival (gap #1).

Mirrors ``test_memory_store.py`` against the SQLAlchemy adapter (sqlite-backed here; Postgres in
prod — same dialect-agnostic SQL). The headline is **restart-survival**: a fresh adapter built
against the SAME database recalls a conversation + its case-state — the exact thing the in-process
store loses on a process restart. Tenant isolation (P0) is verified on the durable store too.
"""

from __future__ import annotations

import pytest

from sealai_v2.core.contracts import DerivedFact, RememberedFact
from sealai_v2.db.conversation_memory import PostgresConversationMemory
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.security.tenant import TenantScopeError


@pytest.fixture
def db_url(tmp_path) -> str:
    """A fresh sqlite file DB with the V2 schema created (the offline stand-in for Postgres)."""
    url = f"sqlite:///{tmp_path / 'v2.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


def _mem(url: str, *, window_turns: int = 6) -> PostgresConversationMemory:
    # a NEW engine/sessionmaker each call → re-instantiating against the same file models a
    # fresh process (the restart-survival proof).
    return PostgresConversationMemory(
        make_sessionmaker(make_engine(url)), window_turns=window_turns
    )


def test_tenant_isolation_p0_no_cross_tenant_read(db_url):
    mem = _mem(db_url)
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="EPDM in Öl?",
        answer="...",
        facts=(RememberedFact("medium", "Hydrauliköl"),),
    )
    other = mem.recall(
        tenant_id="B", session_id="s1"
    )  # same session id, different tenant
    assert other.is_empty
    assert mem.case_state(tenant_id="B", session_id="s1") == ()
    assert mem.history(tenant_id="B", session_id="s1") == ()
    assert "s1" not in mem.sessions(tenant_id="B")
    mine = mem.recall(tenant_id="A", session_id="s1")
    assert not mine.is_empty
    assert any(f.feld == "medium" for f in mine.case_state)


def test_tenant_and_session_mandatory_fail_closed(db_url):
    mem = _mem(db_url)
    for bad in ("", "   "):
        with pytest.raises(TenantScopeError):
            mem.recall(tenant_id=bad, session_id="s1")
    with pytest.raises(ValueError):
        mem.recall(tenant_id="A", session_id="")


def test_record_turn_builds_bounded_window_and_full_history(db_url):
    mem = _mem(db_url, window_turns=2)
    for i in range(4):
        mem.record_turn(
            tenant_id="A", session_id="s1", question=f"q{i}", answer=f"a{i}"
        )
    view = mem.recall(tenant_id="A", session_id="s1")
    assert len(view.window) == 4  # last 2 exchanges (4 messages)
    assert view.window[0].text == "q2" and view.window[0].role == "user"
    assert len(mem.history(tenant_id="A", session_id="s1")) == 8  # all 8 kept


def test_case_state_merge_last_wins_and_stamps_turn(db_url):
    mem = _mem(db_url)
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
    assert facts["medium"].as_of_turn == 2  # re-stamped to the current exchange
    assert facts["temp"].wert == "120°C"


def test_user_control_edit_delete_clear(db_url):
    mem = _mem(db_url)
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


def test_derived_slice_roundtrip_wholesale_replace(db_url):
    mem = _mem(db_url)
    mem.set_derived(
        tenant_id="A",
        session_id="s1",
        derived=(
            DerivedFact(
                calc_id="v",
                name="v_m_s",
                value=2.5,
                unit="m/s",
                formula="pi*d*n",
                parent_fields=("d1_mm", "rpm"),
            ),
        ),
    )
    got = mem.derived_facts(tenant_id="A", session_id="s1")
    assert (
        len(got) == 1
        and got[0].value == 2.5
        and got[0].parent_fields == ("d1_mm", "rpm")
    )
    # wholesale replace — a stale value can never persist
    mem.set_derived(tenant_id="A", session_id="s1", derived=())
    assert mem.derived_facts(tenant_id="A", session_id="s1") == ()


def test_restart_survival_reinstantiate_against_same_db(db_url):
    """THE gap-#1 proof: write with one adapter, then a BRAND-NEW adapter (fresh engine = a fresh
    process) against the same DB still sees the conversation + case-state. The in-process store
    loses this on restart; the durable store does not."""
    before = _mem(db_url)
    before.record_turn(
        tenant_id="A",
        session_id="s1",
        question="EPDM in Hydrauliköl, warum?",
        answer="EPDM quillt in unpolaren Medien.",
        facts=(RememberedFact("medium", "Hydrauliköl"),),
    )
    after = _mem(db_url)  # simulated restart
    view = after.recall(tenant_id="A", session_id="s1")
    assert any(f.feld == "medium" and f.wert == "Hydrauliköl" for f in view.case_state)
    history = after.history(tenant_id="A", session_id="s1")
    assert [t.text for t in history] == [
        "EPDM in Hydrauliköl, warum?",
        "EPDM quillt in unpolaren Medien.",
    ]
    assert "s1" in after.sessions(tenant_id="A")
