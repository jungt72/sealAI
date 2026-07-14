"""P2 (PERF tranche 1): distillation is normally off the user-facing path.

`stages.remember` (distill + record_turn) runs as a background task when a distiller is wired;
`Pipeline.flush_memory` is the ordering guard — awaited before the next same-session recall
(inside `run`), before memory reads (chips re-fetch), and before user mutations (no
resurrection after "alles vergessen"). The visible adaptive interview is the deliberate
exception: it awaits the same call so its next question includes facts stated this turn.
Distiller-less remember stays synchronous.
"""

from __future__ import annotations

import asyncio

from sealai_v2.api.routes.conversations import (
    forget_all,
    list_conversations,
    view_memory,
)
from sealai_v2.core.contracts import (
    LlmResult,
    ModelConfig,
    SessionContext,
    VerifiedIdentity,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.db.interview import InProcessInterviewRepository
from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.pipeline.adaptive_interview import AdaptiveInterviewService
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_FACT_JSON = '{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}]}'
_EMPTY_FACT_JSON = '{"facts": []}'


def _memory_pipeline(client, *, adaptive_interview: bool = False) -> Pipeline:
    service = (
        AdaptiveInterviewService(
            pack=load_rwdr_v1_pack(), repository=InProcessInterviewRepository()
        )
        if adaptive_interview
        else None
    )
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
        adaptive_interview_enabled=adaptive_interview,
        adaptive_interview_service=service,
    )


class _GatedDistillClient:
    """The distill (helper-tier) response is released only via ``release_distill`` — so a
    synchronous remember blocks ``run`` (old behavior), a backgrounded one does not."""

    def __init__(self, *, fact_json: str = _FACT_JSON) -> None:
        self.release_distill = asyncio.Event()
        self.calls: list[str] = []
        self.fact_json = fact_json

    async def generate(self, *, system: str, user: str, model_config: ModelConfig):
        self.calls.append(model_config.model)
        if model_config.model == "fake-helper":
            await asyncio.wait_for(self.release_distill.wait(), timeout=2.0)
            return LlmResult(text=self.fact_json, model=model_config.model)
        return LlmResult(text="ANTWORT", model=model_config.model)


def test_run_returns_before_distill_completes_and_flush_lands_the_facts():
    async def main():
        client = _GatedDistillClient()
        p = _memory_pipeline(client)
        res = await asyncio.wait_for(
            p.run(
                "Warum quillt EPDM in Hydrauliköl?",
                tenant=TenantContext("t1"),
                session=SessionContext("s1", owner_subject="u1"),
            ),
            timeout=5.0,
        )
        # the answer is back while the distill call is still blocked → off the user path
        assert res.answer.text == "ANTWORT"
        immediate = p.memory.case_state(tenant_id="t1", session_id="s1")
        assert [(f.feld, f.wert) for f in immediate] == [
            ("medium", "Hydrauliköl"),
            ("medium_kategorie", "Öl"),
        ]  # deterministic extraction and the turn itself are already durable
        # release + flush → the distilled facts merge (only the LLM work is deferred)
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


def test_visible_adaptive_interview_waits_for_current_turn_facts():
    async def main():
        # Regression for the production entry phrase: the helper deliberately
        # returns no type. The deterministic inline binder must still activate
        # the visible RWDR controller on this same turn.
        client = _GatedDistillClient(fact_json=_EMPTY_FACT_JSON)
        p = _memory_pipeline(client, adaptive_interview=True)
        task = asyncio.create_task(
            p.run(
                "Ich benötige einen RWDR.",
                tenant=TenantContext("t1"),
                session=SessionContext("s1", owner_subject="u1"),
            )
        )
        for _ in range(20):
            if "fake-helper" in client.calls:
                break
            await asyncio.sleep(0)
        assert "fake-helper" in client.calls
        assert not task.done()

        client.release_distill.set()
        result = await asyncio.wait_for(task, timeout=5.0)

        assert result.next_question is not None
        assert result.next_question.question_id == "rwdr.q.application_goal"
        assert result.next_question.pack_version == "1.0.1"
        assert p._pending_remember == {}
        seal_type = result.case_state.field("dichtungstyp")
        assert seal_type is not None
        assert seal_type.value == "RWDR"
        assert seal_type.source.kind == "conversation_distilled"
        stored_type = next(
            fact
            for fact in p.memory.case_state(tenant_id="t1", session_id="s1")
            if fact.feld == "dichtungstyp"
        )
        assert stored_type.provenance == "chat-inline"

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


def test_background_distill_cannot_overwrite_a_newer_user_revision():
    async def main():
        client = _GatedDistillClient()
        p = _memory_pipeline(client)
        result = await p.run(
            "EPDM in Hydrauliköl?",
            tenant=TenantContext("t1"),
            session=SessionContext("s1", owner_subject="u1"),
        )
        assert result.turn_state.case_revision_current == 1
        p.memory.edit_fact(
            tenant_id="t1", session_id="s1", feld="medium", wert="Wasser"
        )
        client.release_distill.set()
        await p.flush_memory(tenant_id="t1", session_id="s1")
        state = p.memory.recall(tenant_id="t1", session_id="s1").case_state_v2
        assert state.revision == 2
        assert state.field("medium").value == "Wasser"
        assert len(p.memory.history(tenant_id="t1", session_id="s1")) == 2

    asyncio.run(main())


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
            session=SessionContext("s1", owner_subject="u1"),
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


def test_list_conversations_route_flushes_so_a_brand_new_case_appears_immediately():
    """Reproduces a live bug (2026-07-03): GET /api/v2/conversations never flushed before
    reading, unlike every other route in conversations.py — so a case's very FIRST message
    could resolve, the answer render, and the "Fälle"-Sidebar re-fetch (right after) still show
    "keine Fälle", because record_turn (which creates the case's row) was still an in-flight
    background task. This is the exact ordering-guard gap; flush_all_memory closes it."""
    client = _GatedDistillClient()
    ident = VerifiedIdentity("t1", "s1", "u1")

    async def main():
        p = _memory_pipeline(client)
        await p.run(
            "EPDM in Hydrauliköl?",
            tenant=TenantContext("t1"),
            session=SessionContext("s1", owner_subject="u1"),
        )
        # the answer is back, but the background remember (which creates the case row) is
        # STILL pending here — exactly the window the live bug fell into.
        assert ("t1", "s1") in p._pending_remember
        client.release_distill.set()  # unblock it — list_conversations must await it, not race it
        return await list_conversations(identity=ident, pipeline=p)

    data = asyncio.run(main())
    assert [c["case_id"] for c in data["cases"]] == ["s1"]


def test_forget_all_flushes_first_so_a_pending_distill_cannot_resurrect_facts():
    client = ScriptedFakeLlmClient(["Antwort.", _FACT_JSON])
    ident = VerifiedIdentity("t1", "s1", "u1")

    async def main():
        p = _memory_pipeline(client)
        await p.run(
            "EPDM in Hydrauliköl?",
            tenant=TenantContext("t1"),
            session=SessionContext("s1", owner_subject="u1"),
        )
        # user clicks "alles vergessen" while the distill is still pending:
        await forget_all(identity=ident, pipeline=p)
        # nothing may land afterwards — the clear is final
        await p.flush_memory(tenant_id="t1", session_id="s1")
        assert p.memory.case_state(tenant_id="t1", session_id="s1") == ()
        assert p.memory.history(tenant_id="t1", session_id="s1") == ()

    asyncio.run(main())


def test_flush_all_memory_only_awaits_the_given_tenants_sessions():
    """A deterministic unit test of the filter itself: flush_all_memory(tenant_id="t1") must
    never AWAIT t2's pending task — P0-adjacent isolation for the "Fälle"-Sidebar list endpoint,
    which now flushes across a WHOLE tenant rather than one known session_id. Proven by making
    t2's task block FOREVER (an Event that's never set): if flush_all_memory ever awaited it,
    this test would hang and fail on the timeout below — a scheduling-order-independent proof,
    unlike asserting on which coroutine bodies happened to *run*, which asyncio does not
    guarantee is limited to what was explicitly awaited."""

    async def main():
        p = _memory_pipeline(ScriptedFakeLlmClient(["unused"]))
        never_release = asyncio.Event()

        async def quick() -> None:
            return None

        async def blocks_forever() -> None:
            await never_release.wait()

        p._pending_remember[("t1", "s1")] = asyncio.create_task(quick())
        p._pending_remember[("t2", "s3")] = asyncio.create_task(blocks_forever())

        await asyncio.wait_for(p.flush_all_memory(tenant_id="t1"), timeout=2.0)
        # returned without hanging → t2's still-blocked task was never awaited by that call
        assert not p._pending_remember[("t2", "s3")].done()
        never_release.set()
        await p._pending_remember[
            ("t2", "s3")
        ]  # drain it so nothing dangles past the test

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
