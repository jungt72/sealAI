from __future__ import annotations

from sealai_v2.core.contracts import GroundingFact
from sealai_v2.core.knowledge_answer import (
    build_knowledge_answer_plan,
    knowledge_retrieval_limit,
)
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.tests.reviewed_catalog import independently_reviewed_test_catalog


def test_ptfe_question_builds_engineering_material_profile() -> None:
    facts = (
        GroundingFact(
            text="PTFE ist ein Thermoplast.",
            quelle="source",
            card_id="FK-PTFE",
            claim_kind="definition",
            answer_facets=("definition", "mechanism"),
            subject_type="material",
        ),
        GroundingFact(
            text="Der konkrete Grade ist zu pruefen.",
            quelle="source",
            card_id="FK-PTFE",
            claim_kind="qualification_required",
            answer_facets=("selection_inputs", "standards_validation"),
            subject_type="material",
        ),
    )
    plan = build_knowledge_answer_plan(
        "Bitte gib mir Details zu PTFE",
        material_terms=("PTFE",),
        grounding_facts=facts,
        route_name="material_knowledge",
    )

    assert plan is not None
    assert plan.profile == "material_overview"
    assert plan.subjects == ("PTFE",)
    assert "definition" in plan.available_facets
    assert "parameters" in plan.required_facets
    assert plan.evidence_status == "sparse"


def test_comparison_profile_uses_aligned_material_axes() -> None:
    plan = build_knowledge_answer_plan(
        "Vergleiche NBR und PTFE fuer Dichtungen",
        material_terms=("NBR", "PTFE"),
        route_name="material_comparison",
    )

    assert plan is not None
    assert plan.profile == "material_comparison" and plan.comparison
    assert plan.subjects == ("NBR", "PTFE")
    assert {"parameters", "media_compatibility", "failure_modes"} <= set(
        plan.required_facets
    )


def test_comparison_coverage_is_measured_per_subject_not_from_the_union() -> None:
    all_facets = (
        "definition",
        "mechanism",
        "properties",
        "parameters",
        "variants",
        "tradeoffs",
        "media_compatibility",
        "applications",
        "operating_factors",
        "design_interfaces",
        "limits",
        "failure_modes",
        "selection_inputs",
        "standards_validation",
    )
    plan = build_knowledge_answer_plan(
        "Vergleiche O-Ring und X-Ring",
        grounding_facts=(
            GroundingFact(
                text="O-Ring evidence",
                quelle="source",
                card_id="FK-ORING-ENGINEERING-PROFILE",
                answer_facets=all_facets,
                subject_type="seal_type",
            ),
        ),
        route_name="general_sealing_knowledge",
    )

    assert plan is not None and plan.profile == "seal_type_comparison"
    assert plan.evidence_status == "partial"
    coverage = {subject: set(facets) for subject, facets in plan.subject_facets}
    assert coverage["O-Ring"] == set(all_facets)
    assert coverage["X-Ring"] == set()


def test_rwdr_and_mechanical_seal_get_seal_type_profiles() -> None:
    rwdr = build_knowledge_answer_plan(
        "Erklaere einen RWDR", route_name="general_sealing_knowledge"
    )
    glrd = build_knowledge_answer_plan(
        "Details zur Gleitringdichtung", route_name="general_sealing_knowledge"
    )

    assert rwdr is not None and rwdr.profile == "seal_type_overview"
    assert rwdr.subjects == ("RWDR",)
    assert glrd is not None and glrd.subjects == ("Gleitringdichtung",)


def test_unknown_but_explicit_sealing_medium_uses_medium_method_without_guessing() -> (
    None
):
    plan = build_knowledge_answer_plan(
        "Details zu Skydrol als Dichtungsmedium",
        route_name="general_sealing_knowledge",
    )

    assert plan is not None and plan.profile == "medium_overview"
    assert plan.subject_type == "medium"
    assert plan.subjects == ()
    import asyncio

    result = asyncio.run(
        InProcessRetriever(independently_reviewed_test_catalog()).retrieve(
            "Details zu Skydrol als Dichtungsmedium", tenant_id="test", k=12
        )
    )
    assert {fact.card_id for fact in result.grounding_facts} == {
        "FK-MEDIUM-ENGINEERING-METHOD"
    }


def test_hydraulic_medium_method_gets_full_medium_profile_retrieval() -> None:
    question = (
        "Wie muss ein Dichtungsingenieur die Verträglichkeit eines unbekannten "
        "Hydraulikmediums wie Skydrol bewerten?"
    )
    plan = build_knowledge_answer_plan(
        question,
        route_name="general_sealing_knowledge",
    )

    assert plan is not None and plan.profile == "medium_overview"
    assert knowledge_retrieval_limit(question) == 12


def test_only_explicit_knowledge_turns_expand_retrieval() -> None:
    assert knowledge_retrieval_limit("Details zu PTFE", material_terms=("PTFE",)) == 12
    assert (
        knowledge_retrieval_limit(
            "PTFE bei 120 Grad und 8 bar auslegen", material_terms=("PTFE",)
        )
        == 5
    )


def test_case_profile_is_available_without_expanding_the_retrieval_budget() -> None:
    question = "RWDR 45 mm bei 1500 U/min, Mineralöl und 80 Grad technisch vorprüfen"
    assert build_knowledge_answer_plan(question) is None
    plan = build_knowledge_answer_plan(question, allow_case_subject_profile=True)
    assert plan is not None and plan.profile == "seal_type_overview"
    assert plan.subjects == ("RWDR",)
    assert knowledge_retrieval_limit(question) == 5


def test_material_subject_order_follows_the_user_question() -> None:
    forward = build_knowledge_answer_plan(
        "Vergleiche NBR mit PTFE", route_name="material_comparison"
    )
    reverse = build_knowledge_answer_plan(
        "Vergleiche PTFE mit NBR", route_name="material_comparison"
    )
    assert forward is not None and forward.subjects == ("NBR", "PTFE")
    assert reverse is not None and reverse.subjects == ("PTFE", "NBR")


def test_reviewed_expert_profiles_cover_core_subjects() -> None:
    catalog = independently_reviewed_test_catalog()
    expected = {
        "FK-PTFE-ENGINEERING-PROFILE": "material",
        "FK-NBR-UEBERBLICK": "material",
        "FK-ORING-ENGINEERING-PROFILE": "seal_type",
        "FK-RWDR-ENGINEERING-PROFILE": "seal_type",
        "FK-GLRD-ENGINEERING-PROFILE": "seal_type",
        "FK-MEDIUM-ENGINEERING-METHOD": "medium",
    }
    for card_id, subject_type in expected.items():
        card = catalog.by_id(card_id)
        assert card is not None and card.review_state == "reviewed"
        assert card.subject_type == subject_type
        assert all(claim.answer_facets for claim in card.reviewed_claims())


def test_inprocess_retrieval_returns_deep_rwdr_profile() -> None:
    import asyncio

    result = asyncio.run(
        InProcessRetriever(independently_reviewed_test_catalog()).retrieve(
            "Erklaere einen RWDR im Detail", tenant_id="test", k=12
        )
    )
    facets = {facet for fact in result.grounding_facts for facet in fact.answer_facets}
    assert len(result.grounding_facts) >= 7
    assert {
        "mechanism",
        "parameters",
        "failure_modes",
        "standards_validation",
    } <= facets
    assert all(fact.claim_id for fact in result.grounding_facts)
    assert len({fact.claim_id for fact in result.grounding_facts}) == len(
        result.grounding_facts
    )


def test_case_specific_rwdr_retrieval_is_facet_balanced_and_bounded() -> None:
    import asyncio

    result = asyncio.run(
        InProcessRetriever(independently_reviewed_test_catalog()).retrieve(
            "RWDR 45 mm bei 1500 U/min, Mineralöl und 80 Grad technisch vorprüfen",
            tenant_id="test",
            k=5,
        )
    )
    facets = {facet for fact in result.grounding_facts for facet in fact.answer_facets}
    assert len(result.grounding_facts) >= 5
    assert {"mechanism", "parameters", "selection_inputs"} <= facets
    assert "FK-RWDR-ENGINEERING-PROFILE" in {
        fact.card_id for fact in result.grounding_facts
    }
