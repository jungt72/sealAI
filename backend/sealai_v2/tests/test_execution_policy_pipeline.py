from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import (
    GroundingFact,
    LlmResult,
    ModelConfig,
    MemoryView,
    RetrievalResult,
    SessionContext,
)
from sealai_v2.core.case_state import CaseStateV2
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.orchestration.answer_cache import InProcessExactAnswerCache
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext


class _RecordingClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[ModelConfig] = []

    async def generate(self, *, system, user, model_config):
        self.calls.append(model_config)
        return LlmResult(text=self.text, model=model_config.model, finish_reason="stop")

    async def generate_structured(self, **kwargs):
        return await self.generate(
            system=kwargs["system"],
            user=kwargs["user"],
            model_config=kwargs["model_config"],
        )


class _EvidenceRetriever:
    def __init__(self, count: int) -> None:
        self.count = count
        self.calls = 0

    async def retrieve(self, query, *, tenant_id, k=5):
        self.calls += 1
        return RetrievalResult(
            grounding_facts=tuple(
                GroundingFact(
                    text=f"reviewed fact {index}",
                    quelle=f"ledger:{index}",
                    card_id=f"claim-{index}",
                    sources=(f"document-{index}",),
                )
                for index in range(self.count)
            )
        )


class _RequiredMissingMemory:
    state = CaseStateV2(
        case_id="case-1", revision=3, required_missing=("temperature_c",)
    )

    def recall(self, **kwargs):
        return MemoryView(case_state_v2=self.state)

    def record_turn(self, **kwargs):
        return None


def _generator(client: _RecordingClient, model: str) -> L1Generator:
    return L1Generator(client, PromptAssembler(), ModelConfig(model=model))


def _pipeline(*, evidence_count: int = 0):
    helper = _RecordingClient("helper")
    standard = _RecordingClient("standard answer")
    frontier = _RecordingClient("frontier answer")
    return (
        Pipeline(
            generator=_generator(frontier, "frontier"),
            client=helper,
            helper_model=ModelConfig("helper"),
            standard_generator=_generator(standard, "standard"),
            frontier_generator=_generator(frontier, "frontier"),
            execution_policy_enabled=True,
            understand_enabled=True,
            retriever=_EvidenceRetriever(evidence_count),
        ),
        helper,
        standard,
        frontier,
    )


def test_low_risk_knowledge_is_one_standard_call_without_helper():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=1)
    result = asyncio.run(
        pipeline.run("Was ist PTFE?", tenant=TenantContext("tenant-1"))
    )

    assert helper.calls == []
    assert frontier.calls == []
    assert len(standard.calls) == 1
    assert standard.calls[0].reasoning_effort == "none"
    assert result.turn_state.execution_class == "S0"
    assert result.turn_state.model_tier == "standard"
    assert result.turn_state.verification_mode == "deterministic"


def test_complex_multidocument_case_goes_frontier_directly():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    result = asyncio.run(
        pipeline.run(
            "RWDR 40x62x8 bei 8000 U/min einordnen",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert helper.calls == []
    assert standard.calls == []
    assert len(frontier.calls) == 1
    assert frontier.calls[0].reasoning_effort == "high"
    assert result.turn_state.execution_class == "C1"
    assert result.turn_state.model_tier == "frontier"


def test_ungrounded_high_risk_case_never_calls_a_model():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=0)
    result = asyncio.run(
        pipeline.run(
            "ATEX: RWDR 40x62x8 bei 8000 U/min einordnen",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert helper.calls == standard.calls == frontier.calls == []
    assert result.answer.model == "deterministic-policy"
    assert result.turn_state.execution_class == "H1"
    assert result.turn_state.verification_mode == "human"
    assert result.turn_state.needs_human_review is True


def test_known_required_field_stops_before_retrieval_and_models():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    retriever = pipeline.retriever
    pipeline.memory = _RequiredMissingMemory()
    result = asyncio.run(
        pipeline.run(
            "Bitte den RWDR-Fall technisch einordnen",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("case-1"),
        )
    )

    assert retriever.calls == 0
    assert helper.calls == standard.calls == frontier.calls == []
    assert result.turn_state.execution_class == "D1"
    assert "temperature_c" in result.answer.text


def test_second_identical_low_risk_turn_is_tenant_scoped_d0_cache_hit():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=1)
    pipeline.answer_cache = InProcessExactAnswerCache()
    pipeline.answer_cache_namespace = "knowledge-v1:policy-v1:standard-v1"

    first = asyncio.run(pipeline.run("Was ist PTFE?", tenant=TenantContext("tenant-1")))
    second = asyncio.run(
        pipeline.run("  was   ist PTFE? ", tenant=TenantContext("tenant-1"))
    )
    third = asyncio.run(pipeline.run("Was ist PTFE?", tenant=TenantContext("tenant-2")))

    assert first.turn_state.execution_class == "S0"
    assert second.turn_state.execution_class == "D0"
    assert second.answer.text == first.answer.text
    assert third.turn_state.execution_class == "S0"
    assert len(standard.calls) == 2
    assert helper.calls == frontier.calls == []
