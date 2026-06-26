"""P2 (PERF tranche 1): the distill LLM call is OFF the user-facing path.

`stages.remember` (distill + record_turn) runs as a background task when a distiller is wired;
`Pipeline.flush_memory` is the ordering guard — awaited before the next same-session recall
(inside `run`), before memory reads (chips re-fetch), and before user mutations (no
resurrection after "alles vergessen"). Distiller-less remember stays synchronous.
"""

from __future__ import annotations

import asyncio

from sealai_v2.api.routes.conversations import forget_all, view_memory
from sealai_v2.core.contracts import (
    LlmResult,
    ModelConfig,
    SessionContext,
    VerifiedIdentity,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_FACT_JSON = '{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}]}'


def _memory_pipeline(client) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,  # helper tier is then used ONLY by the distiller
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        distiller=Distiller(
            client, DistillPromptAssembler(), ModelConfig("fake-helper")
        ),
    )


class _GatedDistillClient:
    """The distill (helper-tier) response is released only via ``release_distill`` — so a
    synchronous remember blocks ``run`` (old behavior), a backgrounded one does not."""

    def __init__(self) -> None:
        self.release_distill = asyncio.Event()
        self.calls: list[str] = []

    async def generate(self, *, system: str, user: str, model_config: ModelConfig):
        self.calls.append(model_config.model)
        if model_config.model == "fake-helper":
            await asyncio.wait_for(self.release_distill.wait(), timeout=2.0)
            return LlmResult(text=_FACT_JSON, model=model_config.model)
        return LlmResult(text="ANTWORT", model=model_config.model)


def test_run_returns_before_distill_completes_and_flush_lands_the_facts():
    async def main():
        client = _GatedDistillClient()
        p = _memory_pipeline(client)
        res = await asyncio.wait_for(
            p.run(
                "Warum quillt EPDM in Hydrauliköl?",
                tenant=TenantContext("t1"),
                session=SessionContext("s1"),
            ),
            timeout=5.0,
        )
        # the answer is back while the distill call is still blocked → off the user path
        assert res.answer.text == "ANTWORT"
        assert p.memory.case_state(tenant_id="t1", session_id="s1") == ()
        # release + flush → the facts land (nothing is lost, only deferred)
        client.release_distill.set()
        await p.flush_memory(tenant_id="t1", session_id="s1")
        facts = p.memory.case_state(tenant_id="t1", session_id="s1")
        assert [(f.feld, f.wert) for f in facts] == [
            ("medium", "Hydrauliköl"),
            (
                "medium_kategorie",
                "Öl",
            ),  # Phase-1 Medium-Wiring (deterministic, always added)
        ]

    asyncio.run(main())


def test_distill_lands_before_a_subsequent_same_session_recall():
    """The required ordering guard: turn-2's recall (same session) must see turn-1's distilled
    facts — `run` flushes the pending remember before recall, no caller action needed."""
    client = ScriptedFakeLlmClient(
        [
            "Antwort 1.",  # t1 generate
            _FACT_JSON,  # t1 distill (flushed by t2's run, before its recall)
            "Antwort 2.",  # t2 generate
            '{"facts": []}',  # t2 distill (drained by the final flush)
        ]
    )

    async def main():
        p = _memory_pipeline(client)
        tenant, session = TenantContext("t1"), SessionContext("s1")
        await p.run(
            "EPDM quillt in Hydrauliköl, warum?", tenant=tenant, session=session
        )
        await p.run("und bei 120 °C?", tenant=tenant, session=session)
        await p.flush_memory(tenant_id="t1", session_id="s1")

    asyncio.run(main())
    t2_system = client.calls[2]["system"]
    assert "Hydrauliköl" in t2_system  # turn-1's fact reached turn-2's prompt
    assert "Bereits bekannter Fallkontext" in t2_system
    assert "EPDM quillt in Hydrauliköl, warum?" in t2_system  # window carried too


def test_memory_view_route_flushes_so_chips_are_current_after_chat():
    """Fix-A behavior preserved: the chips re-fetch right after /chat sees the fresh facts —
    GET /conversations/current/memory awaits the pending background remember."""
    client = ScriptedFakeLlmClient(["Antwort.", _FACT_JSON])
    ident = VerifiedIdentity("t1", "s1", "u1")

    async def main():
        p = _memory_pipeline(client)
        await p.run(
            "EPDM in Hydrauliköl?",
            tenant=TenantContext("t1"),
            session=SessionContext("s1"),
        )
        return await view_memory(identity=ident, pipeline=p)

    data = asyncio.run(main())
    assert (
        data["case_state"]
        == [
            {
                "feld": "medium",
                "wert": "Hydrauliköl",
                "provenance": "distilled-from-conversation",  # distiller's still wins (prepend)
            },
            {
                "feld": "medium_kategorie",
                "wert": "Öl",
                "provenance": "chat-inline",  # Phase-1 Medium-Wiring (deterministic, always added)
            },
        ]
    )
    assert len(data["history"]) == 2  # the turn itself landed before the read


def test_forget_all_flushes_first_so_a_pending_distill_cannot_resurrect_facts():
    client = ScriptedFakeLlmClient(["Antwort.", _FACT_JSON])
    ident = VerifiedIdentity("t1", "s1", "u1")

    async def main():
        p = _memory_pipeline(client)
        await p.run(
            "EPDM in Hydrauliköl?",
            tenant=TenantContext("t1"),
            session=SessionContext("s1"),
        )
        # user clicks "alles vergessen" while the distill is still pending:
        await forget_all(identity=ident, pipeline=p)
        # nothing may land afterwards — the clear is final
        await p.flush_memory(tenant_id="t1", session_id="s1")
        assert p.memory.case_state(tenant_id="t1", session_id="s1") == ()
        assert p.memory.history(tenant_id="t1", session_id="s1") == ()

    asyncio.run(main())


def test_loop_close_cancels_pending_remember_cleanly():
    """asyncio.run cancels a still-pending remember at loop close: the registry self-cleans
    (done-callback) and a later flush on a fresh loop is a harmless no-op."""
    client = ScriptedFakeLlmClient(["ANS", '{"facts": []}'])
    p = _memory_pipeline(client)
    asyncio.run(
        p.run("Frage?", tenant=TenantContext("t1"), session=SessionContext("s1"))
    )
    assert p._pending_remember == {}  # cancelled + deregistered at loop close
    asyncio.run(p.flush_memory(tenant_id="t1", session_id="s1"))  # no-op, no raise
