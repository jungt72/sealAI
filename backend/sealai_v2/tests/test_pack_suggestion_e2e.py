"""2026-07-04 routing/extraction audit — pack suggestion / medium hint threaded through
``pipeline.run`` end-to-end (offline). Flag OFF is byte-identical to before (no new instruction
reaches the understand call, no new block reaches the L1 prompt); flag ON, with an already-committed
seal_type / already-known medium, likewise asks for and injects nothing (never nags once resolved).
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig, RememberedFact
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.core.contracts import SessionContext

_UNDERSTAND_MARKER = "Du klassifizierst eine Nutzer-Nachricht"


class _RoutingFakeLlmClient:
    """Routes by system prompt: the understand call (its prompt opens with the fixed classifier
    instruction) gets ``understand_json``; every other call (L1 generate) gets ``answer``."""

    def __init__(self, understand_json: str, answer: str = "Antwort.") -> None:
        self.understand_json = understand_json
        self.answer = answer
        self.calls: list[dict] = []

    async def generate(self, *, system: str, user: str, model_config: ModelConfig):
        from sealai_v2.core.contracts import LlmResult

        self.calls.append({"system": system, "user": user, "model": model_config.model})
        text = self.understand_json if _UNDERSTAND_MARKER in system else self.answer
        return LlmResult(text=text, model=model_config.model, finish_reason="stop")


def _pipeline(client, *, pack_suggestion_enabled: bool, seed_facts=()) -> Pipeline:
    memory = InProcessConversationMemory()
    if seed_facts:
        memory.record_turn(
            tenant_id="t1",
            session_id="s1",
            question="vorheriger Turn",
            answer="ok",
            facts=seed_facts,
        )
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=True,
        pack_suggestion_enabled=pack_suggestion_enabled,
        retriever=None,
        matrix=InProcessCompatibilityMatrix(),
        memory=memory,
    )


def _generate_call(client) -> dict:
    non_understand = [c for c in client.calls if _UNDERSTAND_MARKER not in c["system"]]
    assert len(non_understand) == 1
    return non_understand[0]


def _understand_call(client) -> dict:
    understand = [c for c in client.calls if _UNDERSTAND_MARKER in c["system"]]
    assert len(understand) == 1
    return understand[0]


def test_flag_off_asks_nothing_new_and_injects_nothing_new():
    client = _RoutingFakeLlmClient('{"intent":"fallarbeit","rationale":"x"}')
    p = _pipeline(client, pack_suggestion_enabled=False)
    asyncio.run(
        p.run(
            "Ich habe ein Problem mit Teig.",
            tenant=TenantContext("t1"),
            session=SessionContext("s1"),
        )
    )
    assert "suggested_seal_type" not in _understand_call(client)["system"]
    assert "medium_hint" not in _understand_call(client)["system"]
    assert "Möglicher Fall-Typ" not in _generate_call(client)["system"]
    assert "nicht erkanntes Medium" not in _generate_call(client)["system"]


def test_flag_on_no_seal_type_yet_and_no_medium_yet_asks_for_both():
    client = _RoutingFakeLlmClient(
        '{"intent":"fallarbeit","rationale":"x","suggested_seal_type":"hydraulik","medium_hint":"Teig"}'
    )
    p = _pipeline(client, pack_suggestion_enabled=True)
    asyncio.run(
        p.run(
            "Ich habe ein Problem mit Teig.",
            tenant=TenantContext("t1"),
            session=SessionContext("s1"),
        )
    )
    system = _understand_call(client)["system"]
    assert "suggested_seal_type" in system
    assert "medium_hint" in system
    l1_system = _generate_call(client)["system"]
    assert "hydraulik" in l1_system
    assert "Möglicher Fall-Typ" in l1_system
    assert "Teig" in l1_system
    assert "nicht erkanntes Medium" in l1_system


def test_flag_on_but_seal_type_already_committed_never_asks_or_injects_pack_suggestion():
    client = _RoutingFakeLlmClient('{"intent":"fallarbeit","rationale":"x"}')
    p = _pipeline(
        client,
        pack_suggestion_enabled=True,
        seed_facts=(RememberedFact(feld="dichtungstyp", wert="rwdr"),),
    )
    asyncio.run(
        p.run(
            "Noch eine Frage zu meinem Fall.",
            tenant=TenantContext("t1"),
            session=SessionContext("s1"),
        )
    )
    assert "suggested_seal_type" not in _understand_call(client)["system"]
    assert "Möglicher Fall-Typ" not in _generate_call(client)["system"]


def test_flag_on_but_medium_already_known_never_asks_or_injects_medium_hint():
    client = _RoutingFakeLlmClient('{"intent":"fallarbeit","rationale":"x"}')
    p = _pipeline(
        client,
        pack_suggestion_enabled=True,
        seed_facts=(RememberedFact(feld="medium", wert="Hydrauliköl"),),
    )
    asyncio.run(
        p.run(
            "Noch eine Frage zu meinem Fall.",
            tenant=TenantContext("t1"),
            session=SessionContext("s1"),
        )
    )
    assert "medium_hint" not in _understand_call(client)["system"]
    assert "nicht erkanntes Medium" not in _generate_call(client)["system"]
