from __future__ import annotations

from typing import get_args, get_type_hints

from app.agent.evidence import EvidenceQuery, ExplorationQuery


def test_evidence_query_is_instantiable_with_defaults() -> None:
    query = EvidenceQuery(topic="PTFE fuer Dampf", detected_sts_codes=["STS-MAT-PTFE-A1"])

    assert query.topic == "PTFE fuer Dampf"
    assert query.detected_sts_codes == ["STS-MAT-PTFE-A1"]
    assert query.language == "de"
    assert query.max_results == 5
    assert query.query_intent == "material_suitability"


def test_exploration_query_is_instantiable_with_defaults() -> None:
    query = ExplorationQuery(topic="FKM vs PTFE", detected_parameters=["temperature_c"])

    assert query.topic == "FKM vs PTFE"
    assert query.detected_parameters == ["temperature_c"]
    assert query.language == "de"
    assert query.max_results == 3
    assert query.query_intent == "general_orientation"


def test_exploration_query_gets_distinct_default_comparison_candidates() -> None:
    first = ExplorationQuery(topic="FKM")
    second = ExplorationQuery(topic="PTFE")

    first.comparison_candidates.append("PTFE")

    assert first.comparison_candidates == ["PTFE"]
    assert second.comparison_candidates == []


def test_detected_fields_are_held_verbatim() -> None:
    evidence = EvidenceQuery(
        topic="Dampfleckage",
        detected_sts_codes=["STS-MED-STEAM-A1", "STS-MAT-PTFE-A1"],
        query_intent="failure_mode",
    )
    exploration = ExplorationQuery(
        topic="Werkstoffvergleich",
        detected_parameters=["medium", "temperature_c"],
        query_intent="material_comparison",
        comparison_candidates=["PTFE", "FKM"],
    )

    assert evidence.detected_sts_codes == ["STS-MED-STEAM-A1", "STS-MAT-PTFE-A1"]
    assert exploration.detected_parameters == ["medium", "temperature_c"]
    assert exploration.comparison_candidates == ["PTFE", "FKM"]


def test_query_intent_literals_match_allowed_values() -> None:
    evidence_hints = get_type_hints(EvidenceQuery)
    exploration_hints = get_type_hints(ExplorationQuery)

    assert set(get_args(evidence_hints["query_intent"])) == {
        "material_suitability",
        "failure_mode",
        "norm_reference",
        "calculation_basis",
    }
    assert set(get_args(exploration_hints["query_intent"])) == {
        "material_suitability",
        "material_comparison",
        "material_detail",
        "norm_explanation",
        "general_orientation",
    }
