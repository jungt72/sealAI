from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.api.v1.endpoints.rfq import (
    RwdrAnalyzeRequest,
    RwdrConfirmationDecision,
    RwdrConfirmationsRequest,
    analyze_rwdr_inquiry,
    diff_rwdr_case_snapshots,
    evaluate_rwdr_case,
    export_rwdr_case_markdown,
    export_rwdr_case_pdf,
    generate_persisted_rwdr_case_brief,
    list_rwdr_case_snapshots,
    update_rwdr_confirmations,
)
from app.models.case_state_snapshot import CaseStateSnapshot
from app.services.auth.dependencies import RequestUser


FIXTURE_PATH = (
    Path(__file__).parents[3] / "tests" / "fixtures" / "rwdr_golden_cases.json"
)


def _golden_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _golden_cases(), ids=lambda item: item["fixture_id"])
async def test_rwdr_golden_case_end_to_end(case: dict[str, Any]) -> None:
    session = _GoldenRwdrFakeSession()
    created = await analyze_rwdr_inquiry(
        body=RwdrAnalyzeRequest(raw_inquiry=case["raw_inquiry_text"]),
        user=_user(),
        session=session,
    )
    case_id = created["case_id"]

    candidates = {item["field"] for item in created["evidence_fields"]}
    for expected in case["expected_candidate_fields"]:
        assert expected in candidates

    if case["confirmation_decisions"]:
        await update_rwdr_confirmations(
            case_id=case_id,
            body=RwdrConfirmationsRequest(
                decisions=[
                    RwdrConfirmationDecision(**decision)
                    for decision in case["confirmation_decisions"]
                ]
            ),
            user=_user(),
            session=session,
        )

    evaluation = await evaluate_rwdr_case(
        case_id=case_id, user=_user(), session=session
    )
    brief = await generate_persisted_rwdr_case_brief(
        case_id=case_id, user=_user(), session=session
    )
    markdown = await export_rwdr_case_markdown(
        case_id=case_id, user=_user(), session=session
    )
    pdf = await export_rwdr_case_pdf(case_id=case_id, user=_user(), session=session)
    snapshots = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )

    assert brief["status"] == case["expected_status"]
    assert pdf.media_type == "application/pdf"
    assert pdf.body.startswith(b"%PDF-")
    assert len(snapshots["snapshots"]) >= 5

    missing = set(brief["canonical_case"]["missing_critical_fields"])
    for expected in case["expected_missing_critical_fields"]:
        assert expected in missing
    if case["expected_status"] == "COMPLETE":
        assert not missing

    flags = set(brief["engineering_review_flags"])
    for expected in case["expected_review_flags"]:
        assert expected in flags

    computed = {
        item["field"]: item
        for item in brief["computed_values"]
        if isinstance(item, dict) and item.get("field")
    }
    for field, expected_value in case["expected_computed_values"].items():
        assert computed[field]["value"] == expected_value

    questions = "\n".join(
        str(item) for item in evaluation.get("manufacturer_questions", ())
    )
    for expected in case["expected_manufacturer_questions_contains"]:
        assert expected.casefold() in questions.casefold()

    section_ids = {section["id"] for section in brief["sections"]}
    for expected in case["expected_brief_sections"]:
        assert expected in section_ids

    serialized = json.dumps(brief, ensure_ascii=False) + "\n" + markdown["content"]
    forbidden = [
        "recommended material",
        "recommended product",
        "best manufacturer",
        "final solution",
        "empfohlenes Material",
        "empfohlenes Produkt",
        "geeignete Lösung",
        "passende Lösung",
        *case["forbidden_phrases"],
    ]
    for phrase in forbidden:
        assert phrase.casefold() not in serialized.casefold()

    assert "Technical RWDR RFQ Brief" in markdown["content"]
    for title in (
        "Bestätigte Angaben",
        "Nicht bestätigte Angaben",
        "Kritisch fehlende Angaben",
        "Berechnete Werte",
        "Engineering Review-Themen",
        "Herstellerfragen",
        "Quellenübersicht",
        "Disclaimer",
    ):
        assert title in markdown["content"]

    repeat = await generate_persisted_rwdr_case_brief(
        case_id=case_id, user=_user(), session=session
    )
    assert _deterministic_brief(repeat) == _deterministic_brief(brief)


@pytest.mark.asyncio
async def test_rwdr_golden_demo_case_revision_diff_shows_confirmation_and_computation() -> (
    None
):
    case = next(
        item
        for item in _golden_cases()
        if item["fixture_id"] == "simple_gearbox_replacement"
    )
    session = _GoldenRwdrFakeSession()
    created = await analyze_rwdr_inquiry(
        body=RwdrAnalyzeRequest(raw_inquiry=case["raw_inquiry_text"]),
        user=_user(),
        session=session,
    )
    case_id = created["case_id"]
    await update_rwdr_confirmations(
        case_id=case_id,
        body=RwdrConfirmationsRequest(
            decisions=[
                RwdrConfirmationDecision(**decision)
                for decision in case["confirmation_decisions"]
            ]
        ),
        user=_user(),
        session=session,
    )
    await generate_persisted_rwdr_case_brief(
        case_id=case_id, user=_user(), session=session
    )
    await export_rwdr_case_markdown(case_id=case_id, user=_user(), session=session)
    listed = await list_rwdr_case_snapshots(
        case_id=case_id, user=_user(), session=session
    )
    diff = await diff_rwdr_case_snapshots(
        case_id=case_id,
        from_revision=1,
        to_revision=listed["snapshots"][-1]["revision_number"],
        user=_user(),
        session=session,
    )

    field_diffs = {item["field"]: item for item in diff["evidence_field_diffs"]}
    assert (
        field_diffs["shaft_diameter_d1_mm"]["change_type"]
        == "confirmation_status_changed"
    )
    assert {
        item["field"]
        for item in diff["computed_values_diff"]["added"]
        if isinstance(item, dict)
    } >= {"circumferential_speed_mps"}


def _deterministic_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": brief["status"],
        "missing": brief["canonical_case"]["missing_critical_fields"],
        "flags": brief["engineering_review_flags"],
        "computed": brief["computed_values"],
        "sections": brief["sections"],
    }


class _ScalarResult:
    def __init__(
        self, row: object | None = None, rows: list[object] | None = None
    ) -> None:
        self.row = row
        self.rows = rows or ([] if row is None else [row])

    def scalar_one_or_none(self) -> object | None:
        return self.row

    def scalars(self) -> "_ScalarResult":
        return self

    def all(self) -> list[object]:
        return list(self.rows)


class _GoldenRwdrFakeSession:
    def __init__(self) -> None:
        self.rows: dict[str, object] = {}
        self.snapshots: list[CaseStateSnapshot] = []

    def add(self, row: object) -> None:
        if isinstance(row, CaseStateSnapshot):
            self.snapshots.append(row)
        else:
            self.rows[str(row.id)] = row

    async def commit(self) -> None:
        return None

    async def execute(self, _statement: object) -> _ScalarResult:
        row = next(iter(self.rows.values()), None)
        return _ScalarResult(row)


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="user-1",
        sub="user-1",
        roles=[],
        tenant_id="tenant-1",
    )
