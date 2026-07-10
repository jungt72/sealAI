"""Versioned, provenance-aware case state: the technical truth of one case."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum

from sealai_v2.core.contracts import RememberedFact


class CaseFieldStatus(str, Enum):
    STATED = "stated"
    CONFIRMED = "confirmed"
    DOCUMENT_EXTRACTED = "document_extracted"
    DERIVED = "derived"
    CONFLICT = "conflict"
    REQUIRED_MISSING = "required_missing"


@dataclass(frozen=True)
class CaseFieldSource:
    kind: str
    reference: str = ""
    document_id: str = ""
    document_version: str = ""
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class CaseField:
    key: str
    value: str | None
    unit: str = ""
    status: CaseFieldStatus = CaseFieldStatus.STATED
    source: CaseFieldSource = field(
        default_factory=lambda: CaseFieldSource(kind="conversation_distilled")
    )
    observed_at: str = ""
    as_of_turn: int = 0
    confidence: float | None = None


@dataclass(frozen=True)
class CaseConflict:
    field_key: str
    candidate_values: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class CaseStateV2:
    case_id: str
    revision: int = 0
    fields: tuple[CaseField, ...] = ()
    open_conflicts: tuple[CaseConflict, ...] = ()
    required_missing: tuple[str, ...] = ()
    schema_version: int = 2

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id is required")
        if self.revision < 0:
            raise ValueError("case revision cannot be negative")
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("case-state field keys must be unique")

    @classmethod
    def from_remembered_facts(
        cls,
        *,
        case_id: str,
        revision: int,
        facts: tuple[RememberedFact, ...],
    ) -> "CaseStateV2":
        fields = tuple(
            CaseField(
                key=fact.feld,
                value=fact.wert,
                unit=fact.unit,
                status=_status(fact),
                source=CaseFieldSource(
                    kind=_source_kind(fact.provenance),
                    reference=fact.source_ref,
                    document_id=fact.document_id,
                    document_version=fact.document_version,
                    page=fact.page,
                    bbox=fact.bbox,
                ),
                observed_at=fact.observed_at,
                as_of_turn=fact.as_of_turn,
                confidence=fact.confidence,
            )
            for fact in facts
        )
        return cls(case_id=case_id, revision=revision, fields=fields)

    def field(self, key: str) -> CaseField | None:
        return next((field for field in self.fields if field.key == key), None)

    def to_remembered_facts(self) -> tuple[RememberedFact, ...]:
        return tuple(
            RememberedFact(
                feld=field.key,
                wert=field.value or "",
                provenance=_legacy_provenance(field),
                as_of_turn=field.as_of_turn,
                unit=field.unit,
                status=field.status.value,
                source_ref=field.source.reference,
                observed_at=field.observed_at,
                document_id=field.source.document_id,
                document_version=field.source.document_version,
                page=field.source.page,
                bbox=field.source.bbox,
                confidence=field.confidence,
            )
            for field in self.fields
            if field.value is not None
        )

    def to_prompt_context(self) -> list[dict[str, str]]:
        """Minimal compatibility projection; metadata never leaks into the prompt implicitly."""
        return [
            {"feld": field.key, "wert": field.value}
            for field in self.fields
            if field.value is not None
        ]

    def canonical_dict(self) -> dict:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.canonical_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_kind(provenance: str) -> str:
    if provenance in {"user-edited", "user-form", "user-confirmed"}:
        return "user"
    if provenance.startswith("document"):
        return "document"
    if provenance == "kernel_computed":
        return "kernel"
    return "conversation_distilled"


def _status(fact: RememberedFact) -> CaseFieldStatus:
    try:
        return CaseFieldStatus(fact.status)
    except ValueError:
        source = _source_kind(fact.provenance)
        if source == "user":
            return CaseFieldStatus.CONFIRMED
        if source == "document":
            return CaseFieldStatus.DOCUMENT_EXTRACTED
        if source == "kernel":
            return CaseFieldStatus.DERIVED
        return CaseFieldStatus.STATED


def _legacy_provenance(field: CaseField) -> str:
    if field.source.kind == "user":
        return "user-confirmed"
    if field.source.kind == "document":
        return "document-extracted"
    if field.source.kind == "kernel":
        return "kernel_computed"
    return "distilled-from-conversation"
