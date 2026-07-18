from __future__ import annotations

import json
from pathlib import Path

import pytest

from sealai_v2.core.material_rule_coverage import (
    COVERAGE_AUTHORITY,
    REQUIRED_MATERIAL_SUBJECTS,
    REQUIRED_SERVICE_SUBJECTS,
    MaterialRuleCoverageValidationError,
    canonicalize_coverage_report,
    coverage_content_sha256,
    parse_coverage_report,
)


REPORT_PATH = (
    Path(__file__).parents[3] / "docs" / "ssot" / "material-rule-coverage-v1.json"
)
GOLDEN_CONTENT_SHA256 = (
    "39306790bfcab244f4ba77c2a189bd4cc44c45f4d91328a635b5ea824258ba5c"
)


def _raw() -> str:
    return REPORT_PATH.read_text(encoding="utf-8")


def test_initial_coverage_report_is_complete_gap_only_and_nonpositive() -> None:
    report = parse_coverage_report(_raw())
    assert report.authority == COVERAGE_AUTHORITY
    assert report.positive_statement_allowed is False
    assert len(report.gaps) == len(REQUIRED_MATERIAL_SUBJECTS) + len(
        REQUIRED_SERVICE_SUBJECTS
    )
    assert all(not item.rule_refs for item in report.gaps)
    assert all(not item.review_snapshot_ids for item in report.gaps)
    assert canonicalize_coverage_report(report)
    assert coverage_content_sha256(report) == GOLDEN_CONTENT_SHA256


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(positive_statement_allowed=True),
        lambda value: value.update(authority="REVIEWED"),
        lambda value: value["gaps"].pop(),
        lambda value: value["gaps"][0].update(rule_refs=["MR-FORGED"]),
        lambda value: value["gaps"][0].update(review_snapshot_ids=["mrv_forged"]),
        lambda value: value["gaps"][0].update(status="reviewed"),
        lambda value: value["gaps"][0].update(extra="unknown"),
    ],
)
def test_coverage_report_rejects_claimed_or_incomplete_coverage(mutate) -> None:
    value = json.loads(_raw())
    mutate(value)
    with pytest.raises(MaterialRuleCoverageValidationError):
        parse_coverage_report(json.dumps(value))


def test_coverage_report_rejects_duplicate_properties_and_floats() -> None:
    with pytest.raises(MaterialRuleCoverageValidationError, match="duplicate"):
        parse_coverage_report('{"authority":"a","authority":"b"}')
    value = json.loads(_raw())
    value["coverage_schema_version"] = 1.0
    with pytest.raises(MaterialRuleCoverageValidationError, match="floats"):
        parse_coverage_report(json.dumps(value))


def test_coverage_report_rejects_duplicate_subject_with_different_label() -> None:
    value = json.loads(_raw())
    duplicate = dict(value["gaps"][0])
    duplicate["label"] = "Duplicate label"
    value["gaps"].append(duplicate)
    value["gaps"].sort(key=lambda item: (item["subject_id"], item["label"]))
    with pytest.raises(MaterialRuleCoverageValidationError, match="exactly once"):
        parse_coverage_report(json.dumps(value))
