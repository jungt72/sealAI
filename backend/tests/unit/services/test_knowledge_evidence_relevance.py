from __future__ import annotations

import re

from app.agent.communication.knowledge_context_builder import KnowledgeContextBuilder
from app.services.knowledge import FactCardStore
from app.services.knowledge_service import KnowledgeService


class _FactcardStore:
    _sources = {
        "src-alkali": {
            "title": "Irrelevant PTFE compatibility chart",
            "url": "https://example.invalid/alkali",
            "rank": 1,
        }
    }

    def __init__(self, cards: list[dict[str, object]]) -> None:
        self._cards = cards

    def match_query_to_cards(self, query_lower: str) -> list[dict[str, object]]:
        return list(self._cards)


def _combined_answer_and_evidence(response) -> str:
    view = response.knowledge_answer_view
    return "\n".join(
        [
            response.content,
            *(evidence.content for evidence in view.knowledge_evidence),
        ]
    ).casefold()


def _irrelevant_alkali_card() -> dict[str, object]:
    return {
        "id": "PTFE-F-018",
        "topic": "chemical_resistance",
        "property": "TEADIT_molten_alkali_metals_rating",
        "value": "Not recommended (C)",
        "conditions": "PTFE sealing products rated C for molten alkali metals",
        "source": "src-alkali",
    }


def test_pfas_no_case_knowledge_is_relevant_and_currentness_limited() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
        "Was bedeutet PFAS für Dichtungen?"
    )
    view = response.knowledge_answer_view
    text = _combined_answer_and_evidence(response)

    assert response.no_case_created is True
    assert view.answer_available is True
    assert view.knowledge_evidence
    assert {item.source_type for item in view.knowledge_evidence} <= {
        "deterministic",
        "fact_card",
        "rag",
        "fallback",
        "unknown",
    }
    assert "pfas" in text
    assert any(term in text for term in ("fkm", "ffkm", "ptfe", "fluor"))
    assert "reach" in text
    assert "echa" in text
    assert "lieferanten" in text or "dokument" in text
    assert "keine verbindliche rechtliche bewertung" in text
    assert "rechtsberatung" not in text
    assert not re.search(r"\b20\d{2}\b", text)
    assert "verbot ab" not in text


def test_saltwater_no_case_knowledge_is_relevant_and_bounded() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
        "Was ist bei Salzwasser und Dichtungen kritisch?"
    )
    text = _combined_answer_and_evidence(response)

    assert "salzwasser" in text
    assert "chlorid" in text
    assert "korrosion" in text
    assert "feder" in text or "welle" in text
    assert "ablager" in text or "kristall" in text
    assert "benetzung" in text
    assert "molten alkali" not in text
    assert "alkali metals" not in text
    assert "alkalimetall" not in text
    assert "salzrueckstaende" not in text
    assert "spuelung" not in text


def test_saltwater_deterministic_answer_wins_over_irrelevant_factcard() -> None:
    response = KnowledgeService(
        factcard_store=_FactcardStore([_irrelevant_alkali_card()])
    ).answer("Was ist bei Salzwasser und Dichtungen kritisch?")
    text = _combined_answer_and_evidence(response)

    assert response.knowledge_answer_view.knowledge_evidence[0].source_type == "deterministic"
    assert "chlorid" in text
    assert "korrosion" in text
    assert "molten alkali" not in text
    assert "teadit_molten_alkali_metals_rating" not in text


def test_factcard_matching_ignores_generic_saltwater_question_tokens() -> None:
    cards = FactCardStore.get_instance().match_query_to_cards(
        "Was ist bei Salzwasser und Dichtungen kritisch?".lower()
    )
    rendered = "\n".join(
        " ".join(str(card.get(field) or "") for field in ("topic", "property", "value", "conditions"))
        for card in cards
    ).casefold()

    assert "molten alkali" not in rendered
    assert "teadit_molten_alkali_metals_rating" not in rendered


def test_composer_bypass_still_has_useful_deterministic_evidence() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
        "Was bedeutet PFAS für Dichtungen?"
    )
    context = KnowledgeContextBuilder().build(
        user_message="Was bedeutet PFAS für Dichtungen?",
        deterministic_answer=response.content,
        knowledge_response=response,
    )

    assert response.answer_markdown is None
    assert response.content == response.knowledge_answer_view.answer
    assert context.regulatory_currentness_required is True
    assert context.evidence_items
    assert context.evidence_items[0].source_type == "deterministic"
    assert "PFAS" in context.evidence_items[0].content


def test_generic_material_comparison_nbr_ptfe_is_structured_and_bounded() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([_irrelevant_alkali_card()])).answer(
        "bitte vergleiche NBR und PTFE fuer mich"
    )
    view = response.knowledge_answer_view
    text = _combined_answer_and_evidence(response)

    assert view.answer_available is True
    assert view.knowledge_evidence
    assert view.knowledge_evidence[0].source_type == "deterministic"
    assert "werkstoffvergleich: nbr vs ptfe" in text
    assert "nitrilkautschuk" in text
    assert "fluorpolymer" in text
    assert "elastomer" in text
    assert "kein elastomer" in text
    assert "mineral" in text or "öl" in text
    assert "können" in text
    assert "für" in text
    assert "fuer" not in text
    assert "koennen" not in text
    assert "staerken" not in text
    assert "°c" in text
    assert "kriechen" in text or "kaltfluss" in text
    assert "keine konkrete materialfreigabe" in text
    assert "hersteller" in text
    assert "molten alkali" not in text


def test_generic_material_comparison_fkm_epdm_is_not_factcard_only() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
        "Vergleiche FKM und EPDM fuer Dichtungen."
    )
    text = _combined_answer_and_evidence(response)

    assert "werkstoffvergleich: fkm vs epdm" in text
    assert "fluorelastomer" in text
    assert "ethylen-propylen" in text
    assert "wasser" in text
    assert "öl" in text
    assert "für" in text
    assert "fuer" not in text
    assert "keine konkrete materialfreigabe" in text


def test_material_comparison_supported_pairs_have_structured_answer() -> None:
    from app.services.knowledge.material_comparison import supported_material_ids

    materials = supported_material_ids()
    assert len(materials) >= 6

    for left in materials:
        for right in materials:
            if left == right:
                continue
            response = KnowledgeService(factcard_store=_FactcardStore([])).answer(
                f"Vergleiche {left} und {right} fuer Dichtungen."
            )
            text = _combined_answer_and_evidence(response)
            assert response.knowledge_answer_view.knowledge_evidence[0].source_type == "deterministic"
            assert f"werkstoffvergleich: {left.casefold()} vs {right.casefold()}" in text
            assert "direkter vergleich" in text
            assert "keine konkrete materialfreigabe" in text


def test_non_comparison_material_question_can_still_use_existing_knowledge_path() -> None:
    response = KnowledgeService(factcard_store=_FactcardStore([])).answer("Was ist FKM?")

    assert "werkstoffvergleich" not in response.content.casefold()
