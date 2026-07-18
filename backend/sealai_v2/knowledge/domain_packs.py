"""Versioned, declarative domain-pack loader for the adaptive interview.

The JSON catalog contains metadata and simple dependencies only.  Evaluation,
scope checks, conflict handling, and calculator use remain typed Python.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sealai_v2.core.interview.contracts import (
    DomainPack,
    NeedDefinition,
    QuestionDefinition,
)

_PACK_DIR = Path(__file__).resolve().parent / "domain_packs"


class DomainPackValidationError(ValueError):
    pass


def _unique(values: list[str], *, label: str) -> None:
    if len(values) != len(set(values)):
        raise DomainPackValidationError(f"duplicate {label}")


def _strict_bool(raw: dict, key: str, *, default: bool = False) -> bool:
    value = raw.get(key, default)
    if type(value) is not bool:
        raise DomainPackValidationError(f"{key} must be a JSON boolean")
    return value


def _parse(raw: dict) -> DomainPack:
    needs = tuple(
        NeedDefinition(
            need_id=item["need_id"],
            field_keys=tuple(item.get("field_keys", ())),
            active=_strict_bool(item, "active"),
            required=_strict_bool(item, "required"),
            criticality=item.get("criticality", "quality"),
            question_id=item.get("question_id"),
            dependency_refs=tuple(item.get("dependency_refs", ())),
            rule_refs=tuple(item.get("rule_refs", ())),
            curated_order=int(item.get("curated_order", 1000)),
            dependency_depth=int(item.get("dependency_depth", 0)),
            downstream_unlock_count=int(item.get("downstream_unlock_count", 0)),
            min_present=int(item.get("min_present", 1)),
            derived_calc_id=item.get("derived_calc_id"),
            conflict_sensitive=_strict_bool(item, "conflict_sensitive"),
        )
        for item in raw["needs"]
    )
    questions = tuple(
        QuestionDefinition(
            question_id=item["question_id"],
            primary_need_id=item["primary_need_id"],
            related_need_ids=tuple(item.get("related_need_ids", ())),
            canonical_text_de=item["canonical_text_de"].strip(),
            question_type=item["question_type"],
            answer_schema=dict(item.get("answer_schema", {})),
            allowed_unknown=_strict_bool(item, "allowed_unknown"),
            allowed_unobtainable=_strict_bool(item, "allowed_unobtainable"),
            criticality=item["criticality"],
            dependency_refs=tuple(item.get("dependency_refs", ())),
            rule_refs=tuple(item.get("rule_refs", ())),
            curated_order=int(item["curated_order"]),
            legacy_aliases=tuple(item.get("legacy_aliases", ())),
        )
        for item in raw["questions"]
    )
    _unique([item.need_id for item in needs], label="need_id")
    _unique([item.question_id for item in questions], label="question_id")
    need_ids = {item.need_id for item in needs}
    question_ids = {item.question_id for item in questions}
    for need in needs:
        if need.question_id and need.question_id not in question_ids:
            raise DomainPackValidationError(
                f"need {need.need_id} references unknown question {need.question_id}"
            )
        unknown_dependencies = set(need.dependency_refs) - need_ids
        if unknown_dependencies:
            raise DomainPackValidationError(
                f"need {need.need_id} has unknown dependencies {sorted(unknown_dependencies)}"
            )
        if (
            need.active
            and need.required
            and not (need.question_id or need.derived_calc_id)
        ):
            raise DomainPackValidationError(
                f"required need {need.need_id} is neither askable nor derived"
            )
    for question in questions:
        if question.primary_need_id not in need_ids:
            raise DomainPackValidationError(
                f"question {question.question_id} references unknown primary need"
            )
        unknown_related = set(question.related_need_ids) - need_ids
        if unknown_related:
            raise DomainPackValidationError(
                f"question {question.question_id} has unknown related needs"
            )
    return DomainPack(
        pack_id=raw["pack_id"],
        version=raw["version"],
        question_catalog_version=raw["question_catalog_version"],
        case_schema_version=int(raw["case_schema_version"]),
        policy_version=raw["policy_version"],
        stop_profile=raw["stop_profile"],
        supported_seal_types=tuple(raw["scope"]["supported_seal_types"]),
        unsupported_primary_types=tuple(raw["scope"]["unsupported_primary_types"]),
        rwdr_signal_fields=tuple(raw["scope"]["rwdr_signal_fields"]),
        needs=needs,
        questions=questions,
        calculator_version_refs=tuple(raw.get("calculator_version_refs", ())),
    )


@lru_cache(maxsize=1)
def load_rwdr_v1_pack() -> DomainPack:
    raw = json.loads((_PACK_DIR / "rwdr.v1.json").read_text(encoding="utf-8"))
    pack = _parse(raw)
    if pack.pack_id != "rwdr.v1":
        raise DomainPackValidationError("rwdr.v1.json carries a different pack_id")
    return pack
