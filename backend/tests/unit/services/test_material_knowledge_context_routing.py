from __future__ import annotations

from app.agent.api.dispatch import _contextualized_knowledge_message
from app.domain.pre_gate_classification import PreGateClassification
from app.services.knowledge_service import KnowledgeService
from app.services.pre_gate_classifier import PreGateClassifier


_GOVERNED_FALLBACK_TEXT = (
    "Ich kann diesen Schritt gerade nicht sicher in den geregelten Fallfluss geben"
)


def _knowledge_answer(message: str, history: list[dict[str, str]]) -> str:
    route = PreGateClassifier().classify(message)
    assert route.classification in {
        PreGateClassification.KNOWLEDGE_QUERY,
        PreGateClassification.DEEP_DIVE,
    }
    assert route.escalate_to_graph is False

    resolved = _contextualized_knowledge_message(
        message,
        recent_history=tuple(history),
    )
    response = KnowledgeService().answer(
        resolved,
        source_classification=route.classification,
    )
    assert response.no_case_created is True
    assert _GOVERNED_FALLBACK_TEXT not in response.content

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response.content})
    return response.content


def test_material_knowledge_sequence_stays_in_knowledge_and_resolves_comparison() -> (
    None
):
    classifier = PreGateClassifier()
    greeting = classifier.classify("Hallo, was geht ab")
    assert greeting.classification is PreGateClassification.GREETING
    assert greeting.escalate_to_graph is False

    history: list[dict[str, str]] = []
    ptfe = _knowledge_answer(
        "ich brauche informationen zu PTFE. was kannst du mir darüber erzählen.",
        history,
    )
    assert "PTFE" in ptfe
    assert "Dichtungstechnik" in ptfe

    reformulated_ptfe = _knowledge_answer(
        "bitte gebe mir informationen über PTFE", history
    )
    assert "PTFE" in reformulated_ptfe
    assert "Dichtungstechnik" in reformulated_ptfe

    nbr = _knowledge_answer("bitte jetzt zu NBR", history)
    assert "NBR" in nbr
    assert "Acrylnitril" in nbr
    assert "Dichtungstechnik" in nbr

    resolved = _contextualized_knowledge_message(
        "bitte vergleiche die beiden",
        recent_history=tuple(history),
    )
    assert resolved.startswith("Vergleiche PTFE mit NBR.")

    comparison = _knowledge_answer("bitte vergleiche die beiden", history)
    assert "PTFE" in comparison
    assert "NBR" in comparison
    assert "Fluorpolymer" in comparison
    assert "Elastomer" in comparison
    assert "Medium" in comparison
    assert "Temperatur" in comparison
    assert "Druck" in comparison
    assert "Werkstoffvergleich" in comparison[:500]
    assert "welches medium soll" not in comparison[:500].casefold()
    assert "dichtungssituation" not in comparison[:500].casefold()


def test_contextual_better_for_application_bridges_without_case_facts() -> None:
    history: list[dict[str, str]] = []
    _knowledge_answer("ich brauche informationen über PTFE", history)
    _knowledge_answer("bitte jetzt zu NBR", history)

    resolved = _contextualized_knowledge_message(
        "welches ist besser für meine Anwendung?",
        recent_history=tuple(history),
    )
    assert resolved.startswith("Vergleiche PTFE mit NBR.")

    answer = _knowledge_answer("welches ist besser für meine Anwendung?", history)
    assert "PTFE" in answer
    assert "NBR" in answer
    assert "Medium" in answer
    assert "Hersteller" in answer


def test_also_about_peek_is_explanation_not_implicit_comparison() -> None:
    history: list[dict[str, str]] = []
    _knowledge_answer(
        "ich brauche weitergehende informationen zu PTFE. was kannst du mir darüber erzählen",
        history,
    )

    resolved_peek = _contextualized_knowledge_message(
        "und auch über PEEK",
        recent_history=tuple(history),
    )
    assert resolved_peek == "und auch über PEEK"

    peek = _knowledge_answer("und auch über PEEK", history)
    assert "PEEK" in peek
    assert "PTFE vs PEEK" not in peek[:500]
    assert "Werkstoffvergleich" not in peek[:500]

    resolved_comparison = _contextualized_knowledge_message(
        "bitte vergleiche beide materialien",
        recent_history=tuple(history),
    )
    assert resolved_comparison.startswith("Vergleiche PTFE mit PEEK.")


def test_concrete_case_data_remains_governed_intake() -> None:
    result = PreGateClassifier().classify(
        "Ich habe Hydrauliköl, 90 °C, rotierende Welle, 8 bar"
    )

    assert result.classification is PreGateClassification.DOMAIN_INQUIRY
    assert result.escalate_to_graph is True
