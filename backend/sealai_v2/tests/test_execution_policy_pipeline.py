from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import (
    GroundingFact,
    LlmResult,
    ModelConfig,
    MemoryView,
    RetrievalResult,
    SessionContext,
)
from sealai_v2.core.case_state import CaseField, CaseFieldStatus, CaseStateV2
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.pipeline.semantic_router import SemanticRouter
from sealai_v2.orchestration.answer_cache import InProcessExactAnswerCache
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext


class _RecordingClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[ModelConfig] = []
        self.systems: list[str] = []
        self.users: list[str] = []

    async def generate(self, *, system, user, model_config):
        self.calls.append(model_config)
        self.systems.append(system)
        self.users.append(user)
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
        self.queries: list[str] = []
        self.limits: list[int] = []

    async def retrieve(self, query, *, tenant_id, k=5):
        self.calls += 1
        self.queries.append(query)
        self.limits.append(k)
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


class _TrapOnlyRetriever:
    async def retrieve(self, query, *, tenant_id, k=5):
        return RetrievalResult(
            grounding_facts=(
                GroundingFact(
                    text="policy trap",
                    quelle="trap",
                    card_id="trap-1",
                    kind="trap",
                ),
            )
        )


class _RequiredMissingMemory:
    # Every RWDR-required field EXCEPT betriebstemperatur is already confirmed, so
    # pipeline.py's stage-2 wiring (core/interview/policy.py::compute_required_missing)
    # derives required_missing=("Betriebstemperatur",) itself on this turn -- this is no
    # longer a hand-fed placeholder, it exercises the real production computation.
    _known_values = {
        "dichtungstyp": "rwdr",
        "anwendungsziel": "new_design",
        "medium": "Hydrauliköl HLP 46",
        "druck": "0,2 bar",
        "wellendurchmesser": "50 mm",
        "drehzahl": "1500 U/min",
    }
    state = CaseStateV2(
        case_id="case-1",
        revision=3,
        fields=tuple(
            CaseField(key=key, value=value, status=CaseFieldStatus.CONFIRMED)
            for key, value in _known_values.items()
        ),
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
    assert "# Fachantwort-Profil" in standard.systems[0]
    assert "Einordnung und Werkstoffstruktur" in standard.systems[0]


def test_unclassified_regional_greeting_uses_bounded_semantic_router():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=0)
    router_client = _RecordingClient(
        json.dumps(
            {
                "primary_route": "smalltalk_navigation",
                "speech_act": "social",
                "conversation_relation": "new_topic",
                "case_bound": False,
                "contains_technical_request": False,
                "confidence": 0.99,
            }
        )
    )
    pipeline.semantic_router_enabled = True
    pipeline.semantic_router = SemanticRouter(
        router_client,
        ModelConfig("ministral-8b-2512", max_output_tokens=96),
    )

    result = asyncio.run(pipeline.run("Moin", tenant=TenantContext("tenant-1")))

    assert result.route_name == "smalltalk_navigation"
    assert len(router_client.calls) == 1
    assert router_client.calls[0].model == "ministral-8b-2512"
    assert helper.calls == []
    assert frontier.calls == []
    assert len(standard.calls) == 1


def test_deep_well_sourced_knowledge_stays_one_standard_call():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    result = asyncio.run(
        pipeline.run("Details zu PTFE", tenant=TenantContext("tenant-1"))
    )

    assert helper.calls == frontier.calls == []
    assert len(standard.calls) == 1
    assert result.turn_state.execution_class == "S0"
    assert result.turn_state.model_tier == "standard"


def test_followup_comparison_uses_typed_prior_subject_without_raw_history_prompt():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.memory = InProcessConversationMemory()
    session = SessionContext("comparison-session")
    tenant = TenantContext("tenant-1")
    first_question = "Hallo, bitte gib mir detaillierte Informationen ueber NBR"
    second_question = "danke, bitte vergleiche mit ptfe"

    asyncio.run(pipeline.run(first_question, tenant=tenant, session=session))
    result = asyncio.run(pipeline.run(second_question, tenant=tenant, session=session))

    assert result.route_name == "material_comparison"
    assert "NBR und PTFE" in pipeline.retriever.queries[-1]
    assert pipeline.retriever.limits[-1] == 12
    final_client = next(
        client
        for client in (standard, frontier)
        if any("NBR und PTFE" in user for user in client.users)
    )
    final_system = final_client.systems[-1]
    assert "Profil: material_comparison" in final_system
    assert "Gegenstand: NBR, PTFE" in final_system
    assert first_question not in final_system
    assert "NBR und PTFE" in final_client.users[-1]
    assert helper.calls == []


def test_plural_material_comparison_binds_both_prior_subjects_end_to_end():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.memory = InProcessConversationMemory()
    session = SessionContext("plural-comparison-session")
    tenant = TenantContext("tenant-1")

    asyncio.run(
        pipeline.run("Bitte gib mir nur Infos zu PTFE", tenant=tenant, session=session)
    )
    asyncio.run(pipeline.run("Jetzt bitte ueber NBR", tenant=tenant, session=session))
    result = asyncio.run(
        pipeline.run("bitte vergleiche nun beide", tenant=tenant, session=session)
    )

    assert result.route_name == "material_comparison"
    assert "PTFE und NBR" in pipeline.retriever.queries[-1]
    final_client = next(
        client
        for client in (standard, frontier)
        if client.users and "PTFE und NBR" in client.users[-1]
    )
    assert "PTFE und NBR" in final_client.users[-1]
    assert "Profil: material_comparison" in final_client.systems[-1]
    assert "Gegenstand: PTFE, NBR" in final_client.systems[-1]
    assert helper.calls == []


def test_semantic_comparison_intent_still_requires_typed_context_binding():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.memory = InProcessConversationMemory()
    router_client = _RecordingClient(
        json.dumps(
            {
                "primary_route": "material_comparison",
                "speech_act": "request_comparison",
                "conversation_relation": "continuation",
                "case_bound": False,
                "contains_technical_request": True,
                "confidence": 0.99,
            }
        )
    )
    pipeline.semantic_router_enabled = True
    pipeline.semantic_router = SemanticRouter(
        router_client,
        ModelConfig("ministral-8b-2512", max_output_tokens=96),
    )
    session = SessionContext("semantic-comparison-session")
    tenant = TenantContext("tenant-1")

    asyncio.run(pipeline.run("Details zu PTFE", tenant=tenant, session=session))
    asyncio.run(pipeline.run("Details zu NBR", tenant=tenant, session=session))
    result = asyncio.run(
        pipeline.run(
            "Wie verhalten sie sich zueinander?", tenant=tenant, session=session
        )
    )

    assert len(router_client.calls) == 1
    assert result.route_name == "material_comparison"
    assert "PTFE und NBR" in pipeline.retriever.queries[-1]
    assert any(
        "PTFE und NBR" in user
        for client in (standard, frontier)
        for user in client.users
    )


def test_semantic_comparison_without_provable_pair_abstains():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    router_client = _RecordingClient(
        json.dumps(
            {
                "primary_route": "material_comparison",
                "speech_act": "request_comparison",
                "conversation_relation": "continuation",
                "case_bound": False,
                "contains_technical_request": True,
                "confidence": 0.99,
            }
        )
    )
    pipeline.semantic_router_enabled = True
    pipeline.semantic_router = SemanticRouter(
        router_client,
        ModelConfig("ministral-8b-2512", max_output_tokens=96),
    )

    result = asyncio.run(
        pipeline.run(
            "Wie verhalten sie sich zueinander?", tenant=TenantContext("tenant-1")
        )
    )

    assert result.route_name == "material_comparison"
    assert "Welche zwei Gegenstände" in result.answer.text
    assert pipeline.retriever.calls == 0
    assert len(router_client.calls) == 1
    assert helper.calls == standard.calls == frontier.calls == []


def test_context_binding_does_not_downgrade_leakage_hard_route():
    pipeline, _helper, _standard, _frontier = _pipeline(evidence_count=8)
    pipeline.memory = InProcessConversationMemory()
    session = SessionContext("leakage-comparison-session")
    tenant = TenantContext("tenant-1")

    asyncio.run(pipeline.run("Details zu PTFE", tenant=tenant, session=session))
    asyncio.run(pipeline.run("Details zu NBR", tenant=tenant, session=session))
    result = asyncio.run(
        pipeline.run(
            "Vergleiche beide: Beide Dichtungen sind undicht.",
            tenant=tenant,
            session=session,
        )
    )

    assert result.route_name == "leakage_troubleshooting"
    assert "PTFE und NBR" in pipeline.retriever.queries[-1]


def test_unresolved_plural_comparison_clarifies_without_retrieval_or_model_call():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.memory = InProcessConversationMemory()
    session = SessionContext("unresolved-comparison-session")
    tenant = TenantContext("tenant-1")

    result = asyncio.run(
        pipeline.run("Vergleiche bitte beide", tenant=tenant, session=session)
    )

    assert result.route_name == "material_comparison"
    assert "Welche zwei Gegenstände" in result.answer.text
    assert "nenne beide ausdrücklich" in result.answer.text
    assert pipeline.retriever.calls == 0
    assert helper.calls == standard.calls == frontier.calls == []
    assert result.turn_state.execution_class == "D1"


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


def test_irrelevant_calc_inputs_do_not_block_grounded_material_compatibility():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    result = asyncio.run(
        pipeline.run(
            "FKM für Heißdampf-Sterilisation bei 140 °C einordnen",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert helper.calls == []
    assert standard.calls == []
    assert len(frontier.calls) == 1
    assert result.answer.model == "frontier"
    assert "d1_mm" not in result.answer.text
    assert "schnurstaerke_mm" not in result.answer.text
    assert result.turn_state.execution_class == "C2"
    assert result.turn_state.needs_human_review is True


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


def test_trap_only_knowledge_is_not_counted_as_authoritative_evidence():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=0)
    pipeline.retriever = _TrapOnlyRetriever()

    result = asyncio.run(
        pipeline.run(
            "Ist FKM gegen Essigsäure beständig?",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert helper.calls == standard.calls == frontier.calls == []
    assert result.answer.model == "deterministic-policy"
    assert result.turn_state.execution_class == "D1"


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
    assert result.turn_state.model_tier == "none"
    assert "Betriebstemperatur" in result.answer.text
    assert (
        "Für die technische Einordnung fehlen noch: Betriebstemperatur."
        in result.answer.text
    )


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
