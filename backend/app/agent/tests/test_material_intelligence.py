from __future__ import annotations

from app.agent.services.material_intelligence import (
    build_material_intelligence_projection,
)


def _labels(result: dict) -> list[str]:
    return [item["label"] for item in result["candidate_materials"]]


def _joined(result: dict) -> str:
    parts: list[str] = []
    for item in result["candidate_materials"]:
        parts.extend(item["why_considered"])
        parts.extend(item["limits"])
        parts.extend(item["blocking_unknowns"])
        parts.extend(item["required_checks"])
    parts.extend(result["missing_field_hints"])
    parts.extend(result["rfq_relevance_notes"])
    return " ".join(parts).casefold()


def test_salzwasser_rwdr_material_window_is_read_only_and_on_topic() -> None:
    result = build_material_intelligence_projection(
        profile={
            "medium": "Salzwasser",
            "seal_type": "Radialwellendichtring",
            "motion_type": "rotierend",
            "shaft_diameter_mm": 80,
            "speed_rpm": 4000,
        },
        medium_classification={
            "canonical_label": "Salzwasser",
            "family": "waessrig_salzhaltig",
        },
        seal_application_profile={"seal_type": "rwdr"},
    )

    assert result["capability_id"] == "material_seal_type_context"
    assert result["safety"] == {
        "mutates_case_state": False,
        "creates_engineering_truth": False,
        "final_approval_claim_allowed": False,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "export_allowed": False,
    }
    assert "EPDM" in _labels(result)
    assert "PTFE" in _labels(result)
    assert "Druck oder Druckdifferenz" in result["missing_field_hints"]
    assert "Temperatur" in result["missing_field_hints"]
    joined = _joined(result)
    assert "salzhaltiges wasser" in joined or "salzwasser" in joined
    assert "welle" in joined
    assert "feder" in joined


def test_hydraulic_oil_prioritizes_oil_material_families() -> None:
    result = build_material_intelligence_projection(
        profile={
            "medium": "Hydraulikoel HLP 46",
            "temperature_c": 60,
            "pressure_bar": 120,
            "seal_type": "Hydraulikdichtung",
            "motion_type": "linear",
        },
        medium_classification={
            "canonical_label": "Hydraulikoel",
            "family": "hydraulikoel",
        },
    )

    labels = _labels(result)
    assert labels[:4] == ["NBR", "HNBR", "FKM", "PU"]
    epdm = next(item for item in result["candidate_materials"] if item["label"] == "EPDM")
    assert epdm["status"] == "excluded_by_known_constraint"
    assert "Hydraulikoel" == result["input_summary"]["medium"]


def test_steam_keeps_nbr_out_of_the_main_window() -> None:
    result = build_material_intelligence_projection(
        profile={
            "medium": "Dampf",
            "temperature_c": 150,
            "pressure_bar": 5,
            "seal_type": "Flachdichtung",
            "motion_type": "statisch",
        },
        medium_classification={"canonical_label": "Dampf", "family": "dampf"},
    )

    labels = _labels(result)
    assert labels[:3] == ["EPDM", "PTFE", "FFKM"]
    nbr = next(item for item in result["candidate_materials"] if item["label"] == "NBR")
    assert nbr["status"] == "excluded_by_known_constraint"


def test_known_material_is_carried_as_candidate_without_release_claim() -> None:
    result = build_material_intelligence_projection(
        profile={
            "medium": "Oel",
            "material": "FKM",
            "temperature_c": 90,
            "pressure_bar": 3,
            "seal_type": "RWDR",
        },
        medium_classification={"canonical_label": "Oel", "family": "oel"},
    )

    assert _labels(result)[0] == "FKM"
    assert result["candidate_materials"][0]["status"] == "candidate_to_check"
    joined = _joined(result)
    forbidden = ("geeignet", "freigegeben", "garantiert", "rfq-ready")
    assert not any(word in joined for word in forbidden)


def test_material_alternatives_are_generic_not_pair_specific() -> None:
    result = build_material_intelligence_projection(
        profile={
            "medium": "Wasser",
            "temperature_c": 40,
            "pressure_bar": 2,
            "seal_type": "O-Ring",
        },
        medium_classification={"canonical_label": "Wasser", "family": "wasser"},
    )

    assert result["alternatives"]
    pairs = {
        (item["from_material"], item["to_material"])
        for item in result["alternatives"]
    }
    assert ("EPDM", "PTFE") in pairs
    assert all(item["missing_for_decision"] is not None for item in result["alternatives"])
