from __future__ import annotations

import asyncio
import json

from sealai_v2.core.contracts import (
    GroundingFact,
    LlmResult,
    ModelConfig,
    MemoryView,
    RememberedFact,
    RetrievalResult,
    SessionContext,
    Turn,
)
from sealai_v2.core.case_state import CaseField, CaseFieldStatus, CaseStateV2
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.archetypes import load_archetypes
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


class _GlrdSolutionRetriever:
    def __init__(self) -> None:
        self.calls = 0
        self.queries: list[str] = []

    async def retrieve(self, query, *, tenant_id, k=5):
        self.calls += 1
        self.queries.append(query)
        return RetrievalResult(
            grounding_facts=(
                GroundingFact(
                    text=(
                        "Bei anspruchsvollen Medien ist das Versorgungssystem Teil der "
                        "Dichtfunktion; Puffer- oder Sperrmedium, Umwälzung und Kühlung "
                        "müssen zur Anordnung passen."
                    ),
                    quelle="reviewed-profile",
                    card_id="FK-GLRD-ENGINEERING-PROFILE",
                    claim_id="GLRD-SUPPLY",
                    sources=("primary-source",),
                    answer_facets=("design_interfaces", "operating_factors"),
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
        return MemoryView(
            case_state=tuple(
                RememberedFact(feld=key, wert=value, provenance="user-form")
                for key, value in self._known_values.items()
            ),
            case_state_v2=self.state,
        )

    def record_turn(self, **kwargs):
        return None

    def set_derived(self, **kwargs):
        return None


class _UnknownScopeMemory:
    state = CaseStateV2(
        case_id="case-unknown-scope",
        revision=1,
        fields=(
            CaseField(
                key="medium",
                value="Hydrauliköl HLP 46",
                status=CaseFieldStatus.CONFIRMED,
            ),
        ),
    )

    def recall(self, **kwargs):
        return MemoryView(case_state_v2=self.state)

    def record_turn(self, **kwargs):
        return None


class _UnitlessCalculationMemory:
    _known_values = {
        "dichtungstyp": "rwdr",
        "anwendungsziel": "new_design",
        "medium": "Mineralöl",
        "betriebstemperatur": "60 °C",
        "druck": "0,2 bar",
        "wellendurchmesser": "40 mm",
        "drehzahl": "8000",
    }
    state = CaseStateV2(
        case_id="calc-context-case",
        revision=2,
        fields=tuple(
            CaseField(key=key, value=value, status=CaseFieldStatus.CONFIRMED)
            for key, value in _known_values.items()
        ),
    )

    def recall(self, **kwargs):
        return MemoryView(
            case_state=tuple(
                RememberedFact(feld=key, wert=value, provenance="user-stated")
                for key, value in self._known_values.items()
            ),
            case_state_v2=self.state,
            window=(
                Turn(
                    role="user",
                    text="Wie hoch ist die Umfangsgeschwindigkeit bei meinem RWDR?",
                ),
                Turn(role="assistant", text="Nenne Durchmesser und Drehzahl."),
                Turn(role="user", text="40 mm und 8000"),
            ),
        )

    def record_turn(self, **kwargs):
        return None

    def set_derived(self, **kwargs):
        return None


class _ResolvedCalculationMemory(_RequiredMissingMemory):
    def recall(self, **kwargs):
        base = super().recall(**kwargs)
        return MemoryView(
            case_state=base.case_state,
            case_state_v2=base.case_state_v2,
            window=(
                Turn(
                    role="user",
                    text="Wie hoch ist die Umfangsgeschwindigkeit bei meinem RWDR?",
                ),
                Turn(
                    role="assistant",
                    text="Wellendurchmesser und Drehzahl sind im Fall erfasst.",
                ),
            ),
        )


class _SteamGuidanceMemory:
    _known_values = {
        "dichtungstyp": "rwdr",
        "medium": "Heißwasser",
        "medium_kategorie": "Wasser",
        "temperatur": "90 °C",
        "drehzahl": "200 U/min",
    }
    state = CaseStateV2(
        case_id="steam-guidance-case",
        revision=2,
        fields=tuple(
            CaseField(key=key, value=value, status=CaseFieldStatus.CONFIRMED)
            for key, value in _known_values.items()
        ),
    )

    def recall(self, **kwargs):
        return MemoryView(
            case_state=tuple(
                RememberedFact(feld=key, wert=value, provenance="user-stated")
                for key, value in self._known_values.items()
            ),
            case_state_v2=self.state,
        )

    def record_turn(self, **kwargs):
        return None

    def set_derived(self, **kwargs):
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


def test_owner_reported_intake_is_case_aware_without_retrieval_or_model_call():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    question = (
        "Hallo und guten Morgen, ich möchte eine dichtungslösung entwickeln. "
        "was benötigst du von mir?"
    )

    result = asyncio.run(pipeline.run(question, tenant=TenantContext("tenant-1")))

    assert result.route_name == "case_intake_invite"
    assert result.turn_state.model_tier == "none"
    assert pipeline.retriever.calls == 0
    assert helper.calls == standard.calls == frontier.calls == []
    assert result.answer.grounding_facts == ()
    assert result.answer.text == (
        "Guten Morgen – gern, wir entwickeln die Dichtungslösung Schritt für Schritt. "
        "Welche Anwendung und Dichtstelle möchtest du abdichten? Davon hängt ab, welche "
        "Betriebs-, Geometrie- und Sicherheitsangaben ich als Nächstes gezielt von dir brauche."
    )
    assert result.answer.text.count("?") == 1
    assert "Quelle" not in result.answer.text


def test_owner_reported_intake_with_active_case_clarifies_context_without_model():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.memory = _RequiredMissingMemory()

    result = asyncio.run(
        pipeline.run(
            "ich möchte eine dichtungslösung besprechen",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("case-1"),
        )
    )

    assert result.route_name == "case_intake_invite"
    assert result.turn_state.model_tier == "none"
    assert pipeline.retriever.calls == 0
    assert helper.calls == standard.calls == frontier.calls == []
    assert result.answer.grounding_facts == ()
    assert result.answer.text.count("?") == 1
    assert "bestehenden Fallkontext im Blick" in result.answer.text
    assert (
        "aktuellen Fall weiterführen oder eine neue Dichtungslösung beginnen"
        in result.answer.text
    )
    assert "Technische Einordnung" not in result.answer.text
    assert "quellengebunden" not in result.answer.text


def test_unrecognized_active_case_intent_uses_semantic_router_then_static_intake():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.memory = _RequiredMissingMemory()
    router_client = _RecordingClient(
        json.dumps(
            {
                "primary_route": "case_intake_invite",
                "speech_act": "initiate_case",
                "conversation_relation": "unclear",
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
            "Ich würde das Thema Dichtung gerne mit dir durchgehen.",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("case-1"),
        )
    )

    assert result.route_name == "case_intake_invite"
    assert len(router_client.calls) == 1
    assert "ACTIVE_CASE: true" in router_client.users[0]
    assert pipeline.retriever.calls == 0
    assert helper.calls == standard.calls == frontier.calls == []
    assert result.answer.text.count("?") == 1
    assert "bestehenden Fallkontext im Blick" in result.answer.text
    assert "Technische Einordnung" not in result.answer.text


def test_active_case_semantic_router_failure_abstains_instead_of_dumping_context():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.memory = _RequiredMissingMemory()
    router_client = _RecordingClient("not-json")
    pipeline.semantic_router_enabled = True
    pipeline.semantic_router = SemanticRouter(
        router_client,
        ModelConfig("ministral-8b-2512", max_output_tokens=96),
    )

    result = asyncio.run(
        pipeline.run(
            "Ich brauche erstmal Orientierung für eine Abdichtung.",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("case-1"),
        )
    )

    assert result.route_name == "unsupported_or_ambiguous"
    assert len(router_client.calls) == 1
    assert pipeline.retriever.calls == 0
    assert helper.calls == standard.calls == frontier.calls == []
    assert result.answer.text.count("?") == 1
    assert "eindeutigen Aufgabe" in result.answer.text
    assert "Technische Einordnung" not in result.answer.text


def test_bare_application_case_uses_deterministic_bounded_clarification() -> None:
    pipeline, _helper, standard, frontier = _pipeline(evidence_count=8)

    result = asyncio.run(
        pipeline.run(
            "Ich brauche eine Dichtung für meine Pumpe.",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.route_name == "engineering_case"
    assert result.answer.model == "deterministic-context-clarification"
    assert result.answer.text.count("?") == 1
    assert "rotierende Wellenabdichtung" in result.answer.text
    assert "welches Medium" in result.answer.text
    assert "Vollkatalog" in result.answer.text
    assert standard.calls == frontier.calls == []


def test_unclassified_colloquial_social_turn_uses_bounded_semantic_router():
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

    result = asyncio.run(
        pipeline.run("Na, wie läuft's bei dir?", tenant=TenantContext("tenant-1"))
    )

    assert result.route_name == "smalltalk_navigation"
    assert len(router_client.calls) == 1
    assert router_client.calls[0].model == "ministral-8b-2512"
    assert helper.calls == []
    assert frontier.calls == []
    assert len(standard.calls) == 1


def test_deterministic_domain_boundary_cannot_be_overridden_by_semantic_router():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=0)
    router_client = _RecordingClient(
        json.dumps(
            {
                "primary_route": "general_sealing_knowledge",
                "speech_act": "request_recommendation",
                "conversation_relation": "new_topic",
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
            "Welchen Elektromotor soll ich für mein Rührwerk nehmen?",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.route_name == "unsupported_or_ambiguous"
    assert router_client.calls == []
    assert helper.calls == standard.calls == frontier.calls == []
    assert "außerhalb meiner Dichtungstechnik-Kompetenz" in result.answer.text
    assert "Drehzahl" in result.answer.text and "Wellendichtung" in result.answer.text


def test_domain_boundary_handles_embedded_question_with_german_verb_final_order():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=0)
    result = asyncio.run(
        pipeline.run(
            "Kannst du mir auch sagen, welchen Elektromotor ich für mein Rührwerk nehmen soll?",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.route_name == "unsupported_or_ambiguous"
    assert helper.calls == standard.calls == frontier.calls == []
    assert "außerhalb meiner Dichtungstechnik-Kompetenz" in result.answer.text
    assert "Drehzahl" in result.answer.text and "Wellendichtung" in result.answer.text


def test_mixed_drive_and_seal_turn_keeps_both_intents_out_of_free_generation():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=0)
    result = asyncio.run(
        pipeline.run(
            "Welchen Motor soll ich nehmen? Ich möchte auch eine passende Dichtung besprechen.",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.route_name == "unsupported_or_ambiguous"
    assert helper.calls == standard.calls == frontier.calls == []
    assert "außerhalb meiner Dichtungstechnik-Kompetenz" in result.answer.text
    assert "Den Dichtungsteil deiner Anfrage bearbeite ich gern" in result.answer.text
    assert result.answer.text.count("?") == 1


def test_seal_request_with_motor_as_location_is_not_intercepted_by_drive_boundary():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    result = asyncio.run(
        pipeline.run(
            "Ich brauche eine Dichtung für den Motor, kannst du sie auslegen?",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.route_name == "engineering_case"
    assert helper.calls == []
    assert len(standard.calls) + len(frontier.calls) == 1
    assert "außerhalb meiner Dichtungstechnik-Kompetenz" not in result.answer.text


def test_ambiguous_same_gender_anaphora_never_reaches_free_generation():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    result = asyncio.run(
        pipeline.run(
            "Motor für die Anlage, wir brauchen eine Bewertung des Werkstoffs, kannst du ihn auslegen?",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.route_name == "unsupported_or_ambiguous"
    assert helper.calls == standard.calls == frontier.calls == []
    assert "den Bezug" in result.answer.text
    assert result.answer.text.count("?") == 1


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


def test_general_material_orientation_keeps_computation_as_telemetry_only():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    pipeline.engine = CascadeCalcEngine()

    result = asyncio.run(
        pipeline.run(
            "RWDR 40x62x8 bei 6000 U/min: Welche Werkstoffe kommen grundsätzlich infrage?",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.computed_values
    systems = standard.systems + frontier.systems
    assert systems
    assert "v_m_s = 12.57 m/s" not in systems[-1]
    assert "12.57 m/s" not in result.answer.text
    assert helper.calls == []


def test_closed_standard_lip_question_receives_rwdr_derived_kernel_result():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    pipeline.engine = CascadeCalcEngine()

    result = asyncio.run(
        pipeline.run(
            "RWDR 40x62x8 aus Standard-NBR bei 6000 U/min: Reicht das?",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.computed_values
    systems = standard.systems + frontier.systems
    assert systems
    assert "v_m_s = 12.5664 m/s" in systems[-1]
    assert helper.calls == []


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
    assert "Welche minimale, normale und maximale Temperatur" in result.answer.text
    assert result.answer.text.count("?") == 1


def test_contextual_calculation_followup_asks_only_for_missing_unit() -> None:
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    pipeline.memory = _UnitlessCalculationMemory()
    pipeline.engine = CascadeCalcEngine()

    result = asyncio.run(
        pipeline.run(
            "Und wie hoch ist sie jetzt genau?",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("calc-context-case"),
        )
    )

    assert result.route_name == "engineering_case"
    assert result.turn_state.execution_class == "D1"
    assert result.computed_values == ()
    assert "bereits genannte Drehzahl" in result.answer.text
    assert "U/min" in result.answer.text
    assert "Anwendungsziel" not in result.answer.text
    assert helper.calls == standard.calls == frontier.calls == []
    assert result.turn_state.model_tier == "none"
    assert result.answer.text.count("?") == 1


def test_resolved_calculation_followup_keeps_computed_value_answer_relevant() -> None:
    pipeline, helper, standard, frontier = _pipeline(evidence_count=1)
    pipeline.engine = CascadeCalcEngine()
    pipeline.memory = _ResolvedCalculationMemory()

    result = asyncio.run(
        pipeline.run(
            "Und wie hoch ist sie jetzt genau?",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("case-1"),
        )
    )

    computed = {item.calc_id: item for item in result.computed_values}
    assert computed["umfangsgeschwindigkeit"].value == 3.927
    systems = standard.systems + frontier.systems
    assert systems and "v_m_s = 3.927 m/s" in systems[-1]
    assert helper.calls == []


def test_material_guidance_retrieval_is_bound_to_typed_case_context() -> None:
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    pipeline.memory = _SteamGuidanceMemory()

    result = asyncio.run(
        pipeline.run(
            "Worauf sollte ich bei der Werkstoffwahl achten?",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("steam-guidance-case"),
        )
    )

    assert result.route_name == "engineering_case"
    assert result.turn_state.execution_class != "D1"
    assert (
        "Verbindlicher Fallkontext aus Nutzereingaben" in pipeline.retriever.queries[-1]
    )
    assert "medium: Heißwasser" in pipeline.retriever.queries[-1]
    assert "temperatur: 90 °C" in pipeline.retriever.queries[-1]
    assert standard.calls or frontier.calls
    assert helper.calls == []


def test_explicit_calculation_uses_complete_target_inputs_before_pack_clarification():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=1)
    retriever = pipeline.retriever
    pipeline.engine = CascadeCalcEngine()
    pipeline.memory = _RequiredMissingMemory()

    result = asyncio.run(
        pipeline.run(
            "Wie hoch ist die Umfangsgeschwindigkeit?",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("case-1"),
        )
    )

    computed = {item.calc_id: item for item in result.computed_values}
    assert "umfangsgeschwindigkeit" in computed
    assert computed["umfangsgeschwindigkeit"].value == 3.927
    assert retriever.calls == 1
    assert "Welche minimale, normale und maximale Temperatur" not in result.answer.text
    assert helper.calls == []
    assert len(standard.calls) + len(frontier.calls) == 1


def test_reviewed_archetype_expands_only_the_retrieval_query_for_solution_work():
    pipeline, _helper, standard, frontier = _pipeline(evidence_count=1)
    pipeline.archetypes = load_archetypes()
    original = (
        "Getriebe, Mineralöl, 80 °C, belüftet, 40-mm-Welle, 1500 U/min, "
        "staubige Umgebung. Was wäre der sinnvolle Ansatz?"
    )

    result = asyncio.run(pipeline.run(original, tenant=TenantContext("tenant-1")))

    assert result.route_name == "engineering_case"
    assert pipeline.retriever.calls == 1
    assert "RWDR" in pipeline.retriever.queries[0]
    called_users = [user for client in (standard, frontier) for user in client.users]
    assert called_users == [original]
    assert "ARCHETYPE-GETRIEBE" in {
        fact.card_id for fact in result.grounding_facts
    }
    called_systems = [
        system for client in (standard, frontier) for system in client.systems
    ]
    assert any("EP/AW-Additive" in system for system in called_systems)
    assert any("# Erkannte Maschinen-Art: getriebe" in system for system in called_systems)


def test_mixer_first_turn_uses_reviewed_archetype_instead_of_generic_evidence_dump():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=8)
    pipeline.archetypes = load_archetypes()
    pipeline.generator = L1Generator(
        frontier,
        PromptAssembler(),
        ModelConfig("frontier"),
        structured_output_enabled=True,
    )
    pipeline.frontier_generator = pipeline.generator
    pipeline.standard_generator = L1Generator(
        standard,
        PromptAssembler(),
        ModelConfig("standard"),
        structured_output_enabled=True,
    )

    result = asyncio.run(
        pipeline.run(
            "Vertikaler Mischer mit rotierender Welle, Wasser bei 70 °C und 2 bar.",
            tenant=TenantContext("tenant-1"),
        )
    )

    assert result.route_name == "engineering_case"
    assert result.answer.finish_reason == "deterministic_reviewed_archetype"
    assert helper.calls == standard.calls == frontier.calls == []
    assert "Prozessmedium" in result.answer.text
    assert "Trockenlauf" in result.answer.text
    assert "Wellenauslenkung" in result.answer.text
    assert "O-Ring" not in result.answer.text
    assert "Welches Prozessmedium" not in result.answer.text
    assert "Hygiene-/Reinigungsregime" in result.answer.text
    assert result.answer.text.count("?") == 1
    assert "ARCHETYPE-RUEHRWERK" in {
        fact.card_id for fact in result.grounding_facts
    }


def test_solution_direction_paraphrase_reaches_grounded_solution_synthesis_end_to_end():
    pipeline, helper, standard, frontier = _pipeline()
    pipeline.retriever = _GlrdSolutionRetriever()
    question = (
        "Die Gleitringdichtung am Mischer wird mit abrasivem Medium bei 145 °C heiß "
        "und leckt. Entwickle bitte eine sinnvolle Lösungsrichtung."
    )

    result = asyncio.run(pipeline.run(question, tenant=TenantContext("tenant-1")))

    assert result.route_name == "leakage_troubleshooting"
    assert helper.calls == standard.calls == []
    assert len(frontier.calls) == 1
    assert result.turn_state.model_tier == "frontier"
    assert result.turn_state.verification_mode == "claim_llm"
    assert "provisional_solution_direction" in frontier.systems[0]
    assert "Welches konkrete Medium" in frontier.systems[0]


def test_active_unknown_scope_guidance_uses_case_without_rag_or_reasking_known_fact():
    pipeline, helper, standard, frontier = _pipeline(evidence_count=4)
    pipeline.memory = _UnknownScopeMemory()

    result = asyncio.run(
        pipeline.run(
            "Was brauchst du noch?",
            tenant=TenantContext("tenant-1"),
            session=SessionContext("case-unknown-scope"),
        )
    )

    assert result.route_name == "engineering_case"
    assert result.turn_state.execution_class == "D1"
    assert pipeline.retriever.calls == 0
    assert helper.calls == standard.calls == frontier.calls == []
    assert "Fallkontext" in result.answer.text
    assert "Dichtungsart oder konkrete Dichtstelle" in result.answer.text
    assert "Hydrauliköl" not in result.answer.text
    assert result.answer.text.count("?") == 1


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
