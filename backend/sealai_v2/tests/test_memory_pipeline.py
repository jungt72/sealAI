"""M5 memory threaded through ``pipeline.run`` (build-spec §7).

Covers the headline keystone (the re-ask fix — prior STATED facts + the working window reach the
turn-2 prompt), per-turn tenant isolation (P0) at the integration level, and the byte-identical
no-op when no session is threaded (the eval's single-turn path: empty memory + NO distill call).
``understand``/L3 are disabled so the scripted call sequence is exactly generate→distill per turn.
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig, SessionContext
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import FakeLlmClient, ScriptedFakeLlmClient


def _memory_pipeline(client, *, with_distiller: bool = True) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        distiller=(
            Distiller(client, DistillPromptAssembler(), ModelConfig("fake-helper"))
            if with_distiller
            else None
        ),
    )


def test_re_ask_keystone_carries_prior_facts_and_window_into_turn2():
    # per turn the script is generate→distill; calls[2] is the turn-2 GENERATE call.
    client = ScriptedFakeLlmClient(
        [
            "EPDM quillt in Hydrauliköl wegen Unpolarität.",  # t1 generate
            '{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}]}',  # t1 distill
            "Bei 120 °C zusätzlich Versprödung beachten.",  # t2 generate
            '{"facts": [{"feld": "temperatur", "wert": "120°C"}]}',  # t2 distill
        ]
    )
    p = _memory_pipeline(client)
    tenant, session = TenantContext("t1"), SessionContext("sess-1")
    asyncio.run(
        p.run("EPDM quillt in Hydrauliköl, warum?", tenant=tenant, session=session)
    )
    asyncio.run(p.run("und bei 120 °C?", tenant=tenant, session=session))

    t2_system = client.calls[2]["system"]
    # the prior STATED fact reached the turn-2 prompt as remembered case-state (the re-ask fix)
    assert "Hydrauliköl" in t2_system
    assert "Bereits bekannter Fallkontext" in t2_system
    assert "NICHT erneut erfragen" in t2_system
    # the working window carried turn-1 verbatim → anaphora ("und bei …?") is resolvable
    assert "Gesprächsverlauf" in t2_system
    assert "EPDM quillt in Hydrauliköl, warum?" in t2_system


def test_pipeline_memory_is_tenant_scoped_p0():
    client = ScriptedFakeLlmClient(
        [
            "Antwort A",  # tenantA t1 generate
            '{"facts": [{"feld": "medium", "wert": "Spezialöl-X"}]}',  # tenantA t1 distill
            "Antwort B",  # tenantB t1 generate (same session id)
            '{"facts": []}',  # tenantB t1 distill
        ]
    )
    p = _memory_pipeline(client)
    session = SessionContext("shared-session-id")
    asyncio.run(
        p.run("EPDM in Spezialöl-X?", tenant=TenantContext("tenantA"), session=session)
    )
    # DIFFERENT tenant, SAME session id → must never inherit tenant A's case-state (P0)
    asyncio.run(p.run("und?", tenant=TenantContext("tenantB"), session=session))
    t2_system = client.calls[2]["system"]
    assert "Spezialöl-X" not in t2_system
    assert "Bereits bekannter Fallkontext" not in t2_system


def test_session_none_is_byte_identical_noop_and_skips_distill():
    # WITH a session → 2 LLM calls (generate + distill).
    client_with = ScriptedFakeLlmClient(["ANS", '{"facts": []}'])
    asyncio.run(
        _memory_pipeline(client_with).run(
            "Frage?", tenant=TenantContext("t1"), session=SessionContext("s1")
        )
    )
    assert len(client_with.calls) == 2

    # WITHOUT a session → 1 LLM call (generate only); NO distill call fires.
    client_without = ScriptedFakeLlmClient(["ANS"])
    asyncio.run(
        _memory_pipeline(client_without).run("Frage?", tenant=TenantContext("t1"))
    )
    assert len(client_without.calls) == 1

    # and the generate prompt is byte-identical to a pipeline with NO memory wired at all.
    fake_plain = FakeLlmClient("ANS")
    plain = Pipeline(
        generator=L1Generator(fake_plain, PromptAssembler(), ModelConfig("fake-l1")),
        client=fake_plain,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
    )
    asyncio.run(plain.run("Frage?", tenant=TenantContext("t1")))
    assert client_without.calls[0]["system"] == fake_plain.calls[0]["system"]
    assert client_without.calls[0]["user"] == fake_plain.calls[0]["user"] == "Frage?"
