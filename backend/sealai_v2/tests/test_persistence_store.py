"""Durable persistence — ``PostgresConversationMemory`` parity + restart-survival (gap #1).

Mirrors ``test_memory_store.py`` against the SQLAlchemy adapter (sqlite-backed here; Postgres in
prod — same dialect-agnostic SQL). The headline is **restart-survival**: a fresh adapter built
against the SAME database recalls a conversation + its case-state — the exact thing the in-process
store loses on a process restart. Tenant isolation (P0) is verified on the durable store too.
"""

from __future__ import annotations

import pytest

from sealai_v2.core.contracts import (
    CaseRevisionConflict,
    ConversationAccessDenied,
    DerivedFact,
    RememberedFact,
)
from sealai_v2.db.conversation_memory import PostgresConversationMemory
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import V2Message, V2Session
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
    assert "s1" not in {s.case_id for s in mem.sessions(tenant_id="B")}
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


def test_legacy_session_without_owned_state_is_inaccessible_even_to_matching_subject(
    db_url,
):
    session_factory = make_sessionmaker(make_engine(db_url))
    with session_factory.begin() as session:
        row = V2Session(
            tenant_id="A",
            session_id="legacy",
            owner_subject="subject-1",
            ownership_state="owned",
            turns=0,
            case_revision=0,
        )
        session.add(row)
        session.flush()
        row.ownership_state = None

    mem = _mem(db_url)
    with pytest.raises(ConversationAccessDenied, match="conversation not found"):
        mem.assert_session_access(
            tenant_id="A", session_id="legacy", owner_subject="subject-1"
        )
    assert mem.sessions(tenant_id="A", owner_subject="subject-1") == ()


@pytest.mark.parametrize("operation", ["record_turn", "merge_facts", "edit_fact"])
def test_owner_bound_write_never_implicitly_claims_orphan_payload(db_url, operation):
    session_factory = make_sessionmaker(make_engine(db_url))
    with session_factory.begin() as session:
        session.add(
            V2Message(
                tenant_id="A",
                session_id="orphan",
                idx=0,
                role="user",
                text="legacy payload",
            )
        )

    mem = _mem(db_url)
    with pytest.raises(ConversationAccessDenied, match="conversation not found"):
        if operation == "record_turn":
            mem.record_turn(
                tenant_id="A",
                session_id="orphan",
                question="new question",
                answer="new answer",
                owner_subject="subject-1",
            )
        elif operation == "merge_facts":
            mem.merge_facts(
                tenant_id="A",
                session_id="orphan",
                facts=(RememberedFact("medium", "water"),),
                owner_subject="subject-1",
            )
        else:
            mem.edit_fact(
                tenant_id="A",
                session_id="orphan",
                feld="medium",
                wert="water",
                owner_subject="subject-1",
            )

    with session_factory() as session:
        assert session.get(V2Session, ("A", "orphan")) is None
        message = session.get(V2Message, ("A", "orphan", 0))
        assert message is not None
        assert message.text == "legacy payload"


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
    view = mem.recall(tenant_id="A", session_id="s1")
    assert view.case_state_v2 is not None
    assert view.case_state_v2.revision == 2
    assert view.case_state_v2.field("medium").value == "Wasser"


def test_case_state_metadata_survives_restart(db_url):
    mem = _mem(db_url)
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="q",
        answer="a",
        facts=(
            RememberedFact(
                feld="temperature",
                wert="120",
                unit="degC",
                status="document_extracted",
                provenance="document-extracted",
                source_ref="DOC-1#p3",
                observed_at="2026-07-10T10:00:00Z",
                document_id="DOC-1",
                document_version="v2",
                page=3,
                bbox=(1.0, 2.0, 3.0, 4.0),
                confidence=0.95,
            ),
        ),
    )
    state = _mem(db_url).recall(tenant_id="A", session_id="s1").case_state_v2
    assert state is not None
    field = state.field("temperature")
    assert field.unit == "degC"
    assert field.source.document_id == "DOC-1"
    assert field.source.bbox == (1.0, 2.0, 3.0, 4.0)
    assert field.confidence == 0.95


def test_record_turn_rejects_stale_case_revision_atomically(db_url):
    mem = _mem(db_url)
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question="q1",
        answer="a1",
        facts=(RememberedFact("medium", "Öl"),),
        expected_case_revision=0,
    )
    with pytest.raises(CaseRevisionConflict):
        mem.record_turn(
            tenant_id="A",
            session_id="s1",
            question="stale",
            answer="must-not-land",
            expected_case_revision=0,
        )
    history = mem.history(tenant_id="A", session_id="s1")
    assert [turn.text for turn in history] == ["q1", "a1"]


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
    assert state["medium"].status == "confirmed"
    assert mem.recall(tenant_id="A", session_id="s1").case_state_v2.revision == 2
    mem.delete_fact(tenant_id="A", session_id="s1", feld="medium")
    assert mem.case_state(tenant_id="A", session_id="s1") == ()
    assert mem.recall(tenant_id="A", session_id="s1").case_state_v2.revision == 3
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
    assert "s1" in {s.case_id for s in after.sessions(tenant_id="A")}


def test_sessions_returns_summaries_sorted_by_updated_at_desc(db_url):
    mem = _mem(db_url)
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


def test_record_turn_without_now_leaves_title_and_timestamps_unset(db_url):
    # Backward compatibility: a caller that never passes `now` (none exist today outside the
    # pipeline's remember stage) gets today's exact behavior — no stamping, no error.
    mem = _mem(db_url)
    mem.record_turn(tenant_id="A", session_id="s1", question="q", answer="a")
    summary = mem.sessions(tenant_id="A")[0]
    assert summary.title is None
    assert summary.created_at is None
    assert summary.updated_at is None


def test_record_turn_stamps_title_from_first_question_and_bumps_updated_at(db_url):
    mem = _mem(db_url)
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
    assert first.updated_at == "2026-07-03T00:00:00Z"
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


def test_long_question_title_truncates_at_word_boundary(db_url):
    mem = _mem(db_url)
    long_question = "Welche Werkstoffkombination eignet sich für einen Radialwellendichtring in einer Hydraulikpumpe mit hoher Drehzahl und wechselnden Temperaturen"
    mem.record_turn(
        tenant_id="A",
        session_id="s1",
        question=long_question,
        answer="a",
        now="2026-07-03T00:00:00Z",
    )
    title = mem.sessions(tenant_id="A")[0].title
    assert len(title) <= 61  # 60 chars + the "…" ellipsis
    assert title.endswith("…")
    assert not title[:-1].endswith(" ")  # trimmed to a full word, no trailing space
