"""L4 cross-session SURFACING — the owner's three HALT checks (gap #1 addition).

This is the only NEW behaviour the offline eval does not cover (the eval is single-turn / no-session
→ memory inert). Verified at two levels:

1. Adapter (``PostgresCrossSessionMemory``): a durable fact persisted under tenant A surfaces for a
   relevant query; an unrelated query surfaces nothing; a DIFFERENT tenant surfaces nothing (P0);
   the durable fact survives a restart.
2. Pipeline (end-to-end, fake LLM): a fact stated in session A surfaces in a NEW session B (same
   tenant) THROUGH the honest "aus früheren Gesprächen — bei Bedarf bestätigen" frame — never as a
   current/confirmed fact — and does NOT surface for a different tenant.

Any failure here is a HALT: it would mean cross-session surfacing leaks across tenants or mis-frames
a remembered fact as current truth.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from sealai_v2.core.contracts import ModelConfig, RememberedFact, SessionContext
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.db.conversation_memory import PostgresConversationMemory
from sealai_v2.db.cross_session_memory import PostgresCrossSessionMemory
from sealai_v2.db.engine import Base, make_engine, make_sessionmaker
from sealai_v2.db.models import V2DurableFact
from sealai_v2.memory.distiller import Distiller
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext, TenantScopeError
from sealai_v2.tests._fakes import ScriptedFakeLlmClient


@pytest.fixture
def db_url(tmp_path) -> str:
    url = f"sqlite:///{tmp_path / 'v2.db'}"
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    engine.dispose()
    return url


# --- 1. adapter level ----------------------------------------------------------------------------


def _x(url: str) -> PostgresCrossSessionMemory:
    return PostgresCrossSessionMemory(make_sessionmaker(make_engine(url)))


def test_durable_fact_surfaces_for_relevant_query_same_tenant(db_url):
    x = _x(db_url)
    x.remember_durable(
        tenant_id="A", facts=(RememberedFact("anwendung", "RWDR Getriebe"),)
    )
    got = x.relevant_facts(
        tenant_id="A", query="Welcher Werkstoff für meine Getriebe-Anwendung?"
    )
    assert any(f.feld == "anwendung" and "Getriebe" in f.wert for f in got)


def test_unrelated_query_surfaces_nothing(db_url):
    x = _x(db_url)
    x.remember_durable(tenant_id="A", facts=(RememberedFact("medium", "Hydrauliköl"),))
    assert x.relevant_facts(tenant_id="A", query="Was ist ein O-Ring?") == ()


def test_cross_tenant_durable_isolation_p0(db_url):
    x = _x(db_url)
    x.remember_durable(
        tenant_id="A", facts=(RememberedFact("anwendung", "RWDR Getriebe"),)
    )
    # a DIFFERENT tenant must never surface tenant A's durable facts
    assert x.relevant_facts(tenant_id="B", query="Getriebe-Anwendung?") == ()
    with pytest.raises(TenantScopeError):
        x.relevant_facts(tenant_id="", query="x")
    with pytest.raises(TenantScopeError):
        x.remember_durable(tenant_id="  ", facts=(RememberedFact("x", "y"),))


def test_same_tenant_durable_facts_are_isolated_by_verified_subject(db_url):
    x = _x(db_url)
    x.remember_durable(
        tenant_id="A",
        owner_subject="user-A",
        facts=(RememberedFact("anwendung", "RWDR Getriebe"),),
    )
    assert (
        x.relevant_facts(
            tenant_id="A",
            owner_subject="user-B",
            query="Getriebe-Anwendung?",
        )
        == ()
    )
    visible = x.relevant_facts(
        tenant_id="A",
        owner_subject="user-A",
        query="Getriebe-Anwendung?",
    )
    assert any(f.feld == "anwendung" and "Getriebe" in f.wert for f in visible)


def test_legacy_durable_fact_is_neither_read_nor_implicitly_claimed(db_url):
    x = _x(db_url)
    x.remember_durable(
        tenant_id="A",
        owner_subject="user-A",
        facts=(RememberedFact("anwendung", "legacy value"),),
    )
    session_factory = make_sessionmaker(make_engine(db_url))
    with session_factory.begin() as session:
        row = session.scalars(select(V2DurableFact)).one()
        row.ownership_state = None

    assert (
        x.relevant_facts(tenant_id="A", owner_subject="user-A", query="legacy value")
        == ()
    )
    with pytest.raises(PermissionError, match="ownership is unresolved"):
        x.remember_durable(
            tenant_id="A",
            owner_subject="user-A",
            facts=(RememberedFact("anwendung", "new value"),),
        )
    with session_factory() as session:
        assert session.scalars(select(V2DurableFact)).one().wert == "legacy value"


def test_durable_facts_survive_restart(db_url):
    _x(db_url).remember_durable(
        tenant_id="A", facts=(RememberedFact("anwendung", "RWDR Getriebe"),)
    )
    after = _x(db_url)  # fresh engine = simulated restart
    got = after.relevant_facts(tenant_id="A", query="Getriebe-Anwendung Werkstoff?")
    assert any(f.feld == "anwendung" for f in got)


# --- 2. assembler-level framing (pure, no LLM) ---------------------------------------------------


def test_durable_context_renders_honest_cross_session_frame():
    sys = PromptAssembler().system_prompt(
        durable_context=[{"feld": "anwendung", "wert": "RWDR Getriebe"}]
    )
    assert "Aus früheren Gesprächen" in sys
    assert "aus früheren Gesprächen — bei Bedarf bestätigen" in sys
    # header carries the "never current/confirmed" boundary on one line
    assert "NICHT aus diesem Gespräch, NICHT verifiziert" in sys
    # empty durable → no block → byte-identical to the no-cross-session prompt
    assert "Aus früheren Gesprächen" not in PromptAssembler().system_prompt()


# --- 3. pipeline end-to-end (fake LLM): surface + frame + tenant isolation ------------------------


def _pipeline(url: str, client) -> Pipeline:
    sf = make_sessionmaker(make_engine(url))
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        memory=PostgresConversationMemory(sf),
        cross_session=PostgresCrossSessionMemory(sf),
        distiller=Distiller(
            client, DistillPromptAssembler(), ModelConfig("fake-helper")
        ),
    )


def test_pipeline_surfaces_durable_fact_in_new_session_honestly_and_tenant_scoped(
    db_url,
):
    # per turn the script is generate→distill (understand + L3 off).
    client = ScriptedFakeLlmClient(
        [
            "Antwort A",  # session A generate
            '{"facts": [{"feld": "anwendung", "wert": "RWDR Getriebe"}]}',  # session A distill → durable
            "Antwort B",  # session B generate (same tenant, NEW session)
            '{"facts": []}',  # session B distill
            "Antwort C",  # different tenant generate (same query)
            '{"facts": []}',  # different tenant distill
        ]
    )
    p = _pipeline(db_url, client)
    q = "Welcher Werkstoff für meine Getriebe-Anwendung?"

    async def main():
        await p.run(
            "Meine Anwendung ist ein RWDR im Getriebe.",
            tenant=TenantContext("A"),
            session=SessionContext("sessA"),
        )
        await p.flush_memory(
            tenant_id="A", session_id="sessA"
        )  # land the durable promotion
        await p.run(q, tenant=TenantContext("A"), session=SessionContext("sessB"))
        await p.flush_memory(tenant_id="A", session_id="sessB")
        await p.run(q, tenant=TenantContext("OTHER"), session=SessionContext("sessC"))
        await p.flush_memory(tenant_id="OTHER", session_id="sessC")

    asyncio.run(main())

    gen_b = client.calls[2]["system"]  # session B (same tenant) generate prompt
    assert "Aus früheren Gesprächen" in gen_b  # the durable fact SURFACED
    assert "Getriebe" in gen_b
    assert "aus früheren Gesprächen — bei Bedarf bestätigen" in gen_b  # honest frame
    # the cross-session fact must NOT have leaked into this-session "Bereits bekannter Fallkontext"
    # (it is framed as durable/earlier, never as current confirmed case-state)
    assert "RWDR Getriebe (zuvor genannt" not in gen_b

    gen_other = client.calls[4]["system"]  # different tenant, same query
    assert "Aus früheren Gesprächen" not in gen_other  # P0 — no cross-tenant surfacing
    assert "Getriebe" not in gen_other
