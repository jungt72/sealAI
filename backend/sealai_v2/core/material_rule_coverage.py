"""Strict gap-only coverage inventory for the initial material rule package."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any


COVERAGE_SCHEMA_VERSION = 1
COVERAGE_CONTRACT_VERSION = "MAT-RULES-COVERAGE.v1"
COVERAGE_AUTHORITY = "NONE_EVIDENCE_GAPS_ONLY"
CONTENT_HASH_DOMAIN = b"sealai.material-rules.coverage.v1\x00"


class CoverageSubjectKind(str, Enum):
    MATERIAL_FAMILY = "material_family"
    SERVICE_GROUP = "service_group"


class CoverageStatus(str, Enum):
    EVIDENCE_GAP = "evidence_gap"


REQUIRED_MATERIAL_SUBJECTS = frozenset(
    {
        "material:acm",
        "material:aem",
        "material:cr",
        "material:epdm-crosslink-specific",
        "material:fepm",
        "material:fkm-subtype-specific",
        "material:filled-ptfe",
        "material:fvmq",
        "material:graphite",
        "material:hnbr",
        "material:iir",
        "material:nbr",
        "material:modified-ptfe",
        "material:peek",
        "material:polyester-pu",
        "material:polyether-pu",
        "material:sbr",
        "material:sheet-fiber",
        "material:virgin-ptfe",
        "material:vmq",
    }
)

REQUIRED_SERVICE_SUBJECTS = frozenset(
    {
        "service:adblue-urea-solution",
        "service:autoclave-sterilization",
        "service:biofuels",
        "service:cip",
        "service:eto-sterilization",
        "service:food-contact",
        "service:fuels",
        "service:gamma-sterilization",
        "service:glycol-brake-fluid",
        "service:hfa",
        "service:hfb",
        "service:hfc",
        "service:hfd",
        "service:hot-caustic",
        "service:hot-water",
        "service:hydrogen",
        "service:mineral-oil-brake-fluid",
        "service:mineral-oils-additized",
        "service:offshore",
        "service:oxygen",
        "service:peracetic-acid",
        "service:pharma",
        "service:potable-water",
        "service:r1234yf",
        "service:r134a",
        "service:r717",
        "service:r744",
        "service:rgd-aed",
        "service:seawater",
        "service:silicone-brake-fluid",
        "service:sip",
        "service:steam",
        "service:water",
    }
)

_SUBJECT_ID_RE = re.compile(r"^(?:material|service):[a-z0-9]+(?:-[a-z0-9]+)*$")


class MaterialRuleCoverageValidationError(ValueError):
    pass


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaterialRuleCoverageValidationError(f"duplicate property {key}")
        result[key] = value
    return result


def _strict_json(raw: str | bytes) -> dict[str, Any]:
    if type(raw) is bytes:
        try:
            raw = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise MaterialRuleCoverageValidationError("invalid UTF-8") from exc
    if type(raw) is not str:
        raise TypeError("coverage payload must be str or bytes")
    if unicodedata.normalize("NFC", raw) != raw:
        raise MaterialRuleCoverageValidationError("coverage payload must be NFC")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs_without_duplicates,
            parse_float=lambda _value: (_ for _ in ()).throw(
                MaterialRuleCoverageValidationError("floats are forbidden")
            ),
            parse_constant=lambda _value: (_ for _ in ()).throw(
                MaterialRuleCoverageValidationError("non-finite numbers are forbidden")
            ),
        )
    except MaterialRuleCoverageValidationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MaterialRuleCoverageValidationError("invalid strict JSON") from exc
    if type(value) is not dict:
        raise MaterialRuleCoverageValidationError("coverage payload must be an object")
    return value


def _exact_fields(value: dict[str, Any], expected: frozenset[str], path: str) -> None:
    if frozenset(value) != expected:
        raise MaterialRuleCoverageValidationError(
            f"{path} has unknown or missing fields"
        )


def _text(value: Any, *, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
    ):
        raise MaterialRuleCoverageValidationError(f"{field} must be trimmed NFC text")
    return value


@dataclass(frozen=True, slots=True, order=True)
class CoverageGapV1:
    subject_id: str
    label: str
    kind: CoverageSubjectKind
    status: CoverageStatus = CoverageStatus.EVIDENCE_GAP
    rule_refs: tuple[str, ...] = ()
    review_snapshot_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.subject_id) is not str or not _SUBJECT_ID_RE.fullmatch(
            self.subject_id
        ):
            raise MaterialRuleCoverageValidationError("invalid coverage subject_id")
        _text(self.label, field="label")
        if type(self.kind) is not CoverageSubjectKind:
            raise TypeError("kind must be CoverageSubjectKind")
        if type(self.status) is not CoverageStatus:
            raise TypeError("status must be CoverageStatus")
        expected_prefix = (
            "material:"
            if self.kind is CoverageSubjectKind.MATERIAL_FAMILY
            else "service:"
        )
        if not self.subject_id.startswith(expected_prefix):
            raise MaterialRuleCoverageValidationError("subject kind and ID differ")
        if self.rule_refs or self.review_snapshot_ids:
            raise MaterialRuleCoverageValidationError(
                "evidence gaps cannot claim rule or review references"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "label": self.label,
            "review_snapshot_ids": [],
            "rule_refs": [],
            "status": self.status.value,
            "subject_id": self.subject_id,
        }


@dataclass(frozen=True, slots=True)
class MaterialRuleCoverageReportV1:
    gaps: tuple[CoverageGapV1, ...]
    coverage_schema_version: int = COVERAGE_SCHEMA_VERSION
    coverage_contract_version: str = COVERAGE_CONTRACT_VERSION
    authority: str = COVERAGE_AUTHORITY

    def __post_init__(self) -> None:
        if (
            type(self.coverage_schema_version) is not int
            or self.coverage_schema_version != 1
        ):
            raise MaterialRuleCoverageValidationError("unsupported coverage schema")
        if self.coverage_contract_version != COVERAGE_CONTRACT_VERSION:
            raise MaterialRuleCoverageValidationError("unsupported coverage contract")
        if self.authority != COVERAGE_AUTHORITY:
            raise MaterialRuleCoverageValidationError(
                "coverage authority must remain NONE"
            )
        if (
            type(self.gaps) is not tuple
            or any(type(item) is not CoverageGapV1 for item in self.gaps)
            or self.gaps != tuple(sorted(set(self.gaps)))
        ):
            raise MaterialRuleCoverageValidationError(
                "coverage gaps must be unique and ordered"
            )
        material = {
            item.subject_id
            for item in self.gaps
            if item.kind is CoverageSubjectKind.MATERIAL_FAMILY
        }
        service = {
            item.subject_id
            for item in self.gaps
            if item.kind is CoverageSubjectKind.SERVICE_GROUP
        }
        subject_ids = tuple(item.subject_id for item in self.gaps)
        if (
            material != REQUIRED_MATERIAL_SUBJECTS
            or service != REQUIRED_SERVICE_SUBJECTS
            or len(subject_ids) != len(set(subject_ids))
            or len(subject_ids)
            != len(REQUIRED_MATERIAL_SUBJECTS) + len(REQUIRED_SERVICE_SUBJECTS)
        ):
            raise MaterialRuleCoverageValidationError(
                "coverage report must contain every required subject exactly once"
            )

    @property
    def positive_statement_allowed(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "coverage_contract_version": self.coverage_contract_version,
            "coverage_schema_version": self.coverage_schema_version,
            "gaps": [item.to_dict() for item in self.gaps],
            "positive_statement_allowed": False,
        }


def parse_coverage_report(raw: str | bytes) -> MaterialRuleCoverageReportV1:
    value = _strict_json(raw)
    _exact_fields(
        value,
        frozenset(
            {
                "authority",
                "coverage_contract_version",
                "coverage_schema_version",
                "gaps",
                "positive_statement_allowed",
            }
        ),
        "$",
    )
    if type(value["coverage_schema_version"]) is not int:
        raise MaterialRuleCoverageValidationError("schema version must be int")
    if value["positive_statement_allowed"] is not False:
        raise MaterialRuleCoverageValidationError("positive statements are forbidden")
    raw_gaps = value["gaps"]
    if type(raw_gaps) is not list:
        raise MaterialRuleCoverageValidationError("gaps must be an array")
    gaps: list[CoverageGapV1] = []
    for index, raw_gap in enumerate(raw_gaps):
        if type(raw_gap) is not dict:
            raise MaterialRuleCoverageValidationError(f"gap {index} must be an object")
        _exact_fields(
            raw_gap,
            frozenset(
                {
                    "kind",
                    "label",
                    "review_snapshot_ids",
                    "rule_refs",
                    "status",
                    "subject_id",
                }
            ),
            f"$.gaps[{index}]",
        )
        if raw_gap["rule_refs"] != [] or raw_gap["review_snapshot_ids"] != []:
            raise MaterialRuleCoverageValidationError("gap references must be empty")
        try:
            kind = CoverageSubjectKind(raw_gap["kind"])
            status = CoverageStatus(raw_gap["status"])
        except (TypeError, ValueError) as exc:
            raise MaterialRuleCoverageValidationError(
                "unknown coverage constant"
            ) from exc
        gaps.append(
            CoverageGapV1(
                subject_id=_text(raw_gap["subject_id"], field="subject_id"),
                label=_text(raw_gap["label"], field="label"),
                kind=kind,
                status=status,
            )
        )
    return MaterialRuleCoverageReportV1(
        tuple(gaps),
        coverage_schema_version=value["coverage_schema_version"],
        coverage_contract_version=_text(
            value["coverage_contract_version"], field="coverage_contract_version"
        ),
        authority=_text(value["authority"], field="authority"),
    )


def canonicalize_coverage_report(report: MaterialRuleCoverageReportV1) -> bytes:
    if type(report) is not MaterialRuleCoverageReportV1:
        raise TypeError("report must be MaterialRuleCoverageReportV1")
    return json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def coverage_content_sha256(report: MaterialRuleCoverageReportV1) -> str:
    return hashlib.sha256(
        CONTENT_HASH_DOMAIN + canonicalize_coverage_report(report)
    ).hexdigest()


__all__ = [
    "COVERAGE_AUTHORITY",
    "COVERAGE_CONTRACT_VERSION",
    "COVERAGE_SCHEMA_VERSION",
    "CoverageGapV1",
    "CoverageStatus",
    "CoverageSubjectKind",
    "MaterialRuleCoverageReportV1",
    "MaterialRuleCoverageValidationError",
    "REQUIRED_MATERIAL_SUBJECTS",
    "REQUIRED_SERVICE_SUBJECTS",
    "canonicalize_coverage_report",
    "coverage_content_sha256",
    "parse_coverage_report",
]
