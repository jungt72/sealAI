from __future__ import annotations

import pytest

from app.agent.runtime.output_guard import check_fast_path_output
from app.mcp.calculations.chemical_resistance import get_compatible_materials, lookup
from app.mcp.calculations.compliance import ComplianceFlag, check_compliance


FORBIDDEN_USER_VISIBLE_FRAGMENTS = (
    "fda-konform",
    "konform",
    "zugelassen",
    "zertifiziert",
    "freigegeben",
    "validiert",
    "geeignet",
    "empfohlen",
    "compliant",
)


def _assert_no_overclaim(text: str) -> None:
    lowered = text.lower()
    violations = [
        fragment for fragment in FORBIDDEN_USER_VISIBLE_FRAGMENTS if fragment in lowered
    ]
    assert violations == []
    assert "Herstellerprüfung erforderlich".lower() in lowered or "prüfen" in lowered


def test_fda_compliance_reasons_are_review_oriented_not_approval_claims() -> None:
    result = check_compliance("PTFE", flags=[ComplianceFlag.FDA])
    fda = next(flag for flag in result.flag_results if flag.flag == ComplianceFlag.FDA)

    assert fda.passed is True
    for reason in fda.reasons:
        _assert_no_overclaim(reason)


def test_atex_compliance_reasons_are_review_oriented_not_certification_claims() -> None:
    result = check_compliance("PTFE", medium="ethanol", flags=[ComplianceFlag.ATEX])
    atex = next(
        flag for flag in result.flag_results if flag.flag == ComplianceFlag.ATEX
    )

    assert atex.passed is True
    assert atex.severity == "warning"
    for reason in atex.reasons:
        _assert_no_overclaim(reason)


def test_food_hygiene_compliance_reasons_do_not_claim_release() -> None:
    result = check_compliance("NBR", flags=[ComplianceFlag.EHEDG])
    ehedg = next(
        flag for flag in result.flag_results if flag.flag == ComplianceFlag.EHEDG
    )

    assert ehedg.passed is False
    for reason in ehedg.reasons:
        _assert_no_overclaim(reason)


@pytest.mark.parametrize(
    ("medium", "material"),
    [
        ("ethanol", "PTFE"),
        ("ethanol", "FKM"),
        ("steam", "FKM"),
    ],
)
def test_chemical_resistance_results_do_not_render_final_suitability_claims(
    medium: str,
    material: str,
) -> None:
    result = lookup(medium, material)

    _assert_no_overclaim(result.note)
    _assert_no_overclaim(result.recommendation)


def test_compatible_materials_are_still_ranked_without_recommendation_language() -> (
    None
):
    results = get_compatible_materials("Dampf")

    assert [item.rating for item in results] == sorted(item.rating for item in results)
    assert results
    for item in results:
        _assert_no_overclaim(item.note)
        _assert_no_overclaim(item.recommendation)


@pytest.mark.parametrize(
    "claim",
    [
        "Das Material ist FDA-Konformität bestätigt.",
        "Die Lösung ist konform nach EU 1935/2004.",
        "Das Bauteil ist gemäß FDA zugelassen.",
        "PTFE ist chemisch beständig gegen Ethanol.",
        "Diese Dichtung ist ATEX freigegeben.",
    ],
)
def test_output_guard_blocks_broader_compliance_and_chemical_overclaims(
    claim: str,
) -> None:
    safe, category = check_fast_path_output(claim)

    assert safe is False
    assert category in {"compliance_overclaim", "suitability"}
