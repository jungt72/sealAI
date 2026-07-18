from __future__ import annotations

import asyncio

from sealai_v2.core.output_guard import fail_closed_answer
from sealai_v2.core.response_contract import build_guard_contract
from sealai_v2.knowledge.retrieval import InProcessRetriever
from sealai_v2.tests.reviewed_catalog import independently_reviewed_test_catalog


_INCIDENT_QUESTIONS = (
    "Hallo und guten Morgen, bitte gebe mir Details zu NBR",
    "Details ueber NBR",
    "Koenntest du NBR allgemein einordnen?",
)


def test_incident_phrasings_retrieve_a_balanced_reviewed_nbr_overview():
    retriever = InProcessRetriever(independently_reviewed_test_catalog())
    for question in _INCIDENT_QUESTIONS:
        result = asyncio.run(retriever.retrieve(question, tenant_id="ux-regression"))
        overview = [
            fact
            for fact in result.grounding_facts
            if fact.card_id == "FK-NBR-UEBERBLICK"
        ]
        assert len(overview) == 5, question
        assert [fact.claim_kind for fact in overview] == [
            "definition",
            "family_tendency",
            "family_tendency",
            "safety_caution",
            "qualification_required",
        ]


def test_general_fail_closed_answer_remains_a_useful_overview():
    result = asyncio.run(
        InProcessRetriever(independently_reviewed_test_catalog()).retrieve(
            "Details ueber NBR", tenant_id="ux-regression"
        )
    )
    overview = tuple(
        fact for fact in result.grounding_facts if fact.card_id == "FK-NBR-UEBERBLICK"
    )
    contract = build_guard_contract(grounding_facts=overview, calc=None)
    assert contract is not None

    answer = fail_closed_answer(contract.to_dict())
    assert answer.index("Familie ungesättigter Copolymere") < answer.index(
        "wesentliche Familiengrenze"
    )
    assert "Typische Stärken" in answer
    assert "keine Eignungsfreigabe" in answer
