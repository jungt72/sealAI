"""MAT-EVID-01C factual evidence-review contract.

The contract is a separate, content-addressed companion to one immutable
MAT-EVID-01A snapshot.  It adds source metadata, rights/locator handling and a
human review lifecycle without changing 01A, 01B, any verdict, or runtime
authority.  Lifecycle events are deliberately excluded from the dossier hash.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any, NoReturn

from sealai_v2.core.material_evidence import (
    EvidenceClaimScopeV1,
    EvidenceManifestSnapshotV1,
    MaterialEvidenceErrorCode,
    MaterialEvidenceValidationError,
    parse_json_without_duplicates,
)


REVIEW_SCHEMA_VERSION = 1
CANONICALIZATION_VERSION = 1
MAT_EVID_REVIEW_CONTRACT_VERSION = "MAT-EVID-01C.v1"
HUMAN_ROLE = "verified_human"
CREATE_ROLE = "material_evidence:create"
REVIEW_ROLE = "material_evidence:review"
APPROVE_ROLE = "material_evidence:approve"
NO_RUNTIME_AUTHORITY = "FACTUAL_REVIEW_ONLY"
ZERO_EVENT_HASH = "0" * 64

CONTENT_DOMAIN = b"sealai.material-evidence-review.content.v1\x00"
SNAPSHOT_DOMAIN = b"sealai.material-evidence-review.snapshot.v1\x00"
VALIDATION_DOMAIN = b"sealai.material-evidence-review.validation.v1\x00"
AUDIT_DOMAIN = b"sealai.material-evidence-review.audit.v1\x00"
LIFECYCLE_DOMAIN = b"sealai.material-evidence-review.lifecycle.v1\x00"

_REVIEW_ID_RE = re.compile(r"^mer_[0-9a-f]{32}$", re.ASCII)
_REVIEW_SNAPSHOT_ID_RE = re.compile(r"^mrv_[0-9a-f]{64}$", re.ASCII)
_EVIDENCE_SNAPSHOT_ID_RE = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_SOURCE_REF_RE = re.compile(r"^msr_[0-9a-f]{64}$", re.ASCII)
_CLAIM_REF_RE = re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class EvidenceReviewErrorCode(str, Enum):
    INVALID_JSON = "MAT_EVID_REVIEW_INVALID_JSON"
    DUPLICATE_PROPERTY = "MAT_EVID_REVIEW_DUPLICATE_PROPERTY"
    UNKNOWN_FIELD = "MAT_EVID_REVIEW_UNKNOWN_FIELD"
    INVALID_TYPE = "MAT_EVID_REVIEW_INVALID_TYPE"
    INVALID_ID = "MAT_EVID_REVIEW_INVALID_ID"
    INVALID_UNICODE = "MAT_EVID_REVIEW_INVALID_UNICODE"
    NON_NFC = "MAT_EVID_REVIEW_NON_NFC"
    UNKNOWN_SCHEMA = "MAT_EVID_REVIEW_UNKNOWN_SCHEMA"
    DUPLICATE_REF = "MAT_EVID_REVIEW_DUPLICATE_REF"
    DANGLING_REF = "MAT_EVID_REVIEW_DANGLING_REF"
    INCOMPLETE_COVERAGE = "MAT_EVID_REVIEW_INCOMPLETE_COVERAGE"
    NON_CANONICAL_ORDER = "MAT_EVID_REVIEW_NON_CANONICAL_ORDER"
    SOURCE_IDENTITY_MISMATCH = "MAT_EVID_REVIEW_SOURCE_IDENTITY_MISMATCH"
    CLAIM_SCOPE_MISMATCH = "MAT_EVID_REVIEW_CLAIM_SCOPE_MISMATCH"
    RIGHTS_BLOCKED = "MAT_EVID_REVIEW_RIGHTS_BLOCKED"
    SOURCE_TYPE_MISMATCH = "MAT_EVID_REVIEW_SOURCE_TYPE_MISMATCH"
    CONFLICT_BLOCKED = "MAT_EVID_REVIEW_CONFLICT_BLOCKED"
    HASH_MISMATCH = "MAT_EVID_REVIEW_HASH_MISMATCH"
    SNAPSHOT_ID_MISMATCH = "MAT_EVID_REVIEW_SNAPSHOT_ID_MISMATCH"
    ROLE_REQUIRED = "MAT_EVID_REVIEW_ROLE_REQUIRED"
    SELF_REVIEW = "MAT_EVID_REVIEW_SELF_REVIEW"
    SELF_APPROVAL = "MAT_EVID_REVIEW_SELF_APPROVAL"
    INVALID_TRANSITION = "MAT_EVID_REVIEW_INVALID_TRANSITION"
    TENANT_MISMATCH = "MAT_EVID_REVIEW_TENANT_MISMATCH"
    DB_INTEGRITY = "MAT_EVID_REVIEW_DB_INTEGRITY"


class EvidenceReviewValidationError(ValueError):
    def __init__(
        self, code: EvidenceReviewErrorCode, message: str, *, path: str = "$"
    ) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value} at {path}: {message}")


class EvidenceReviewIntegrityError(RuntimeError):
    quarantine_candidate = True

    def __init__(self, code: EvidenceReviewErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: EvidenceReviewErrorCode, message: str, *, path: str = "$") -> NoReturn:
    raise EvidenceReviewValidationError(code, message, path=path)


def _require_exact(obj: dict[str, Any], expected: frozenset[str], *, path: str) -> None:
    actual = frozenset(obj)
    if actual != expected:
        _fail(
            EvidenceReviewErrorCode.UNKNOWN_FIELD,
            f"unknown={sorted(actual - expected)} missing={sorted(expected - actual)}",
            path=path,
        )


def _dict(value: Any, *, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(EvidenceReviewErrorCode.INVALID_TYPE, "expected object", path=path)
    return value


def _list(value: Any, *, path: str) -> list[Any]:
    if type(value) is not list:
        _fail(EvidenceReviewErrorCode.INVALID_TYPE, "expected array", path=path)
    return value


def _text(value: Any, *, path: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        _fail(
            EvidenceReviewErrorCode.INVALID_TYPE,
            "expected non-whitespace string",
            path=path,
        )
    _unicode(value, path=path)
    return value


def _unicode(value: str, *, path: str) -> None:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _fail(
            EvidenceReviewErrorCode.INVALID_UNICODE,
            "invalid Unicode scalar",
            path=path,
        )
    if unicodedata.normalize("NFC", value) != value:
        _fail(EvidenceReviewErrorCode.NON_NFC, "string must be NFC", path=path)


def _id(value: Any, pattern: re.Pattern[str], message: str, *, path: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _fail(EvidenceReviewErrorCode.INVALID_ID, message, path=path)
    return value


def _enum(enum_type: type[Enum], value: Any, *, path: str):
    if type(value) is not str:
        _fail(EvidenceReviewErrorCode.INVALID_TYPE, "expected string", path=path)
    try:
        return enum_type(value)
    except ValueError:
        _fail(
            EvidenceReviewErrorCode.INVALID_TYPE,
            f"unknown {enum_type.__name__}",
            path=path,
        )


def _canonical_json(value: dict[str, Any]) -> bytes:
    def validate(item: Any, path: str) -> None:
        if item is None or type(item) in {bool, int, str}:
            if type(item) is str:
                _unicode(item, path=path)
            return
        if type(item) is list:
            for index, child in enumerate(item):
                validate(child, f"{path}[{index}]")
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or not key.isascii():
                    _fail(
                        EvidenceReviewErrorCode.INVALID_TYPE,
                        "object keys must be ASCII strings",
                        path=path,
                    )
                validate(child, f"{path}.{key}")
            return
        _fail(
            EvidenceReviewErrorCode.INVALID_TYPE,
            "value is outside the exact JSON domain",
            path=path,
        )

    validate(value, "$")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _ordered_strings(value: Any, *, path: str) -> tuple[str, ...]:
    items = tuple(
        _text(item, path=f"{path}[{index}]")
        for index, item in enumerate(_list(value, path=path))
    )
    if not items:
        _fail(
            EvidenceReviewErrorCode.INVALID_TYPE, "array must not be empty", path=path
        )
    expected = tuple(sorted(set(items), key=lambda item: item.encode("utf-8")))
    if items != expected:
        _fail(
            EvidenceReviewErrorCode.NON_CANONICAL_ORDER,
            "array must be unique and ordered",
            path=path,
        )
    return items


def _ordered_strings_allow_empty(value: Any, *, path: str) -> tuple[str, ...]:
    items = tuple(
        _text(item, path=f"{path}[{index}]")
        for index, item in enumerate(_list(value, path=path))
    )
    expected = tuple(sorted(set(items), key=lambda item: item.encode("utf-8")))
    if items != expected:
        _fail(
            EvidenceReviewErrorCode.NON_CANONICAL_ORDER,
            "array must be unique and ordered",
            path=path,
        )
    return items


class EvidenceDocumentType(str, Enum):
    MANUFACTURER_DATASHEET = "manufacturer_datasheet"
    PEER_REVIEWED_PUBLICATION = "peer_reviewed_publication"
    STANDARD_METADATA = "standard_metadata"
    REGULATORY_DOCUMENT = "regulatory_document"
    TECHNICAL_REPORT = "technical_report"
    INTERNAL_EXPERT_ATTESTATION = "internal_expert_attestation"


class EvidenceClaimType(str, Enum):
    INCOMPATIBILITY = "incompatibility"
    CONDITIONAL_COMPATIBILITY = "conditional_compatibility"
    TEMPERATURE_LIMIT = "temperature_limit"
    APPLICATION_LIMIT = "application_limit"
    REGULATORY_CONSTRAINT = "regulatory_constraint"
    OTHER_TECHNICAL = "other_technical"


class EvidenceRightsState(str, Enum):
    PERMITTED = "permitted"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    UNKNOWN = "unknown"
    RESTRICTED = "restricted"


class ClaimRelationKind(str, Enum):
    CONFLICTS = "conflicts"
    SUPERSEDES = "supersedes"


class FactualReviewState(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    REVOKED = "revoked"
    QUARANTINED = "quarantined"


class FactualApprovalState(str, Enum):
    NOT_APPROVED = "not_approved"
    APPROVED = "approved"
    REVOKED = "revoked"
    QUARANTINED = "quarantined"


class ReviewEventType(str, Enum):
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    APPROVED = "approved"
    REVOKED = "revoked"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class ExactLocatorV1:
    value: str

    def __post_init__(self) -> None:
        _text(self.value, path="$.source.locator.value")

    def to_dict(self) -> dict[str, str]:
        return {"state": "exact", "value": self.value}


@dataclass(frozen=True, slots=True)
class UnavailableLocatorV1:
    reason: str

    def __post_init__(self) -> None:
        _text(self.reason, path="$.source.locator.reason")

    def to_dict(self) -> dict[str, str]:
        return {"reason": self.reason, "state": "unavailable"}


SourceLocatorV1 = ExactLocatorV1 | UnavailableLocatorV1


@dataclass(frozen=True, slots=True)
class OmittedExcerptV1:
    def to_dict(self) -> dict[str, str]:
        return {"state": "omitted"}


@dataclass(frozen=True, slots=True)
class IncludedExcerptV1:
    text: str
    rights_basis: str

    def __post_init__(self) -> None:
        _text(self.text, path="$.source.excerpt.text")
        _text(self.rights_basis, path="$.source.excerpt.rights_basis")
        if len(self.text) > 280 or len(self.text.encode("utf-8")) > 1024:
            _fail(
                EvidenceReviewErrorCode.RIGHTS_BLOCKED,
                "excerpt exceeds the short-excerpt limit",
                path="$.source.excerpt.text",
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "rights_basis": self.rights_basis,
            "state": "included",
            "text": self.text,
        }


SourceExcerptV1 = OmittedExcerptV1 | IncludedExcerptV1


@dataclass(frozen=True, slots=True)
class ReviewedSourceMetadataV1:
    source_ref: str
    document_id: str
    document_title: str
    publisher: str
    document_type: EvidenceDocumentType
    document_revision: str
    publication_edition: str
    content_sha256: str
    locator: SourceLocatorV1
    rights_state: EvidenceRightsState
    rights_basis: str
    excerpt: SourceExcerptV1

    def __post_init__(self) -> None:
        _id(
            self.source_ref,
            _SOURCE_REF_RE,
            "invalid source_ref",
            path="$.source.source_ref",
        )
        for field, value in (
            ("document_id", self.document_id),
            ("document_title", self.document_title),
            ("publisher", self.publisher),
            ("document_revision", self.document_revision),
            ("publication_edition", self.publication_edition),
            ("rights_basis", self.rights_basis),
        ):
            _text(value, path=f"$.source.{field}")
        if type(self.document_type) is not EvidenceDocumentType:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid document_type",
                path="$.source.document_type",
            )
        _id(
            self.content_sha256,
            _SHA256_RE,
            "invalid SHA-256",
            path="$.source.content_sha256",
        )
        if type(self.locator) not in {ExactLocatorV1, UnavailableLocatorV1}:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid locator",
                path="$.source.locator",
            )
        if type(self.rights_state) is not EvidenceRightsState:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid rights_state",
                path="$.source.rights_state",
            )
        if type(self.excerpt) not in {OmittedExcerptV1, IncludedExcerptV1}:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid excerpt",
                path="$.source.excerpt",
            )
        if isinstance(self.excerpt, IncludedExcerptV1) and self.rights_state in {
            EvidenceRightsState.UNKNOWN,
            EvidenceRightsState.RESTRICTED,
        }:
            _fail(
                EvidenceReviewErrorCode.RIGHTS_BLOCKED,
                "excerpt requires permitted, licensed, or public-domain rights",
                path="$.source.excerpt",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_sha256": self.content_sha256,
            "document_id": self.document_id,
            "document_revision": self.document_revision,
            "document_title": self.document_title,
            "document_type": self.document_type.value,
            "excerpt": self.excerpt.to_dict(),
            "locator": self.locator.to_dict(),
            "publication_edition": self.publication_edition,
            "publisher": self.publisher,
            "rights_basis": self.rights_basis,
            "rights_state": self.rights_state.value,
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class ReviewedClaimMetadataV1:
    claim_ref: str
    claim_type: EvidenceClaimType
    scope: EvidenceClaimScopeV1
    required_source_types: tuple[EvidenceDocumentType, ...]

    def __post_init__(self) -> None:
        _id(
            self.claim_ref, _CLAIM_REF_RE, "invalid claim_ref", path="$.claim.claim_ref"
        )
        if type(self.claim_type) is not EvidenceClaimType:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid claim_type",
                path="$.claim.claim_type",
            )
        if type(self.scope) is not EvidenceClaimScopeV1:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid scope",
                path="$.claim.scope",
            )
        if (
            type(self.required_source_types) is not tuple
            or not self.required_source_types
        ):
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "required_source_types must be non-empty",
                path="$.claim.required_source_types",
            )
        if any(
            type(item) is not EvidenceDocumentType
            for item in self.required_source_types
        ):
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid required source type",
                path="$.claim.required_source_types",
            )
        expected = tuple(
            sorted(set(self.required_source_types), key=lambda item: item.value)
        )
        if self.required_source_types != expected:
            _fail(
                EvidenceReviewErrorCode.NON_CANONICAL_ORDER,
                "required source types must be unique and ordered",
                path="$.claim.required_source_types",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_ref": self.claim_ref,
            "claim_type": self.claim_type.value,
            "required_source_types": [
                item.value for item in self.required_source_types
            ],
            "scope": self.scope.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ClaimRelationV1:
    kind: ClaimRelationKind
    subject_claim_ref: str
    object_claim_ref: str

    def __post_init__(self) -> None:
        if type(self.kind) is not ClaimRelationKind:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid relation kind",
                path="$.relation.kind",
            )
        for field, value in (
            ("subject_claim_ref", self.subject_claim_ref),
            ("object_claim_ref", self.object_claim_ref),
        ):
            _id(value, _CLAIM_REF_RE, "invalid claim_ref", path=f"$.relation.{field}")
        if self.subject_claim_ref == self.object_claim_ref:
            _fail(
                EvidenceReviewErrorCode.INVALID_ID,
                "self relation is forbidden",
                path="$.relation",
            )
        if (
            self.kind is ClaimRelationKind.CONFLICTS
            and self.subject_claim_ref > self.object_claim_ref
        ):
            _fail(
                EvidenceReviewErrorCode.NON_CANONICAL_ORDER,
                "conflict endpoints must be ordered",
                path="$.relation",
            )

    def key(self) -> tuple[str, str, str]:
        return (self.kind.value, self.subject_claim_ref, self.object_claim_ref)

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "object_claim_ref": self.object_claim_ref,
            "subject_claim_ref": self.subject_claim_ref,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReviewPayloadV1:
    evidence_snapshot_id: str
    evidence_content_sha256: str
    evidence_manifest_schema_version: int
    evidence_contract_version: str
    sources: tuple[ReviewedSourceMetadataV1, ...]
    claims: tuple[ReviewedClaimMetadataV1, ...]
    claim_relations: tuple[ClaimRelationV1, ...]
    review_schema_version: int = REVIEW_SCHEMA_VERSION
    canonicalization_version: int = CANONICALIZATION_VERSION
    mat_evid_review_contract_version: str = MAT_EVID_REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.review_schema_version) is not int
            or self.review_schema_version != REVIEW_SCHEMA_VERSION
            or type(self.canonicalization_version) is not int
            or self.canonicalization_version != CANONICALIZATION_VERSION
        ):
            _fail(
                EvidenceReviewErrorCode.UNKNOWN_SCHEMA,
                "unsupported schema/canonicalization version",
            )
        if self.mat_evid_review_contract_version != MAT_EVID_REVIEW_CONTRACT_VERSION:
            _fail(EvidenceReviewErrorCode.UNKNOWN_SCHEMA, "unsupported review contract")
        _id(
            self.evidence_snapshot_id,
            _EVIDENCE_SNAPSHOT_ID_RE,
            "invalid evidence snapshot",
            path="$.evidence_snapshot_id",
        )
        _id(
            self.evidence_content_sha256,
            _SHA256_RE,
            "invalid evidence hash",
            path="$.evidence_content_sha256",
        )
        if (
            type(self.evidence_manifest_schema_version) is not int
            or self.evidence_manifest_schema_version != 1
            or self.evidence_contract_version != "MAT-EVID-01A.v1"
        ):
            _fail(
                EvidenceReviewErrorCode.UNKNOWN_SCHEMA,
                "01C v1 requires exact MAT-EVID-01A.v1",
            )
        for name, values, item_type in (
            ("sources", self.sources, ReviewedSourceMetadataV1),
            ("claims", self.claims, ReviewedClaimMetadataV1),
        ):
            if (
                type(values) is not tuple
                or not values
                or any(type(item) is not item_type for item in values)
            ):
                _fail(
                    EvidenceReviewErrorCode.INVALID_TYPE,
                    f"{name} must be non-empty typed tuple",
                    path=f"$.{name}",
                )
        if type(self.claim_relations) is not tuple or any(
            type(item) is not ClaimRelationV1 for item in self.claim_relations
        ):
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "claim_relations must be a typed tuple",
                path="$.claim_relations",
            )
        source_refs = tuple(item.source_ref for item in self.sources)
        claim_refs = tuple(item.claim_ref for item in self.claims)
        relation_keys = tuple(item.key() for item in self.claim_relations)
        if source_refs != tuple(sorted(set(source_refs))):
            _fail(
                EvidenceReviewErrorCode.NON_CANONICAL_ORDER,
                "sources must be unique and ordered",
                path="$.sources",
            )
        if claim_refs != tuple(sorted(set(claim_refs))):
            _fail(
                EvidenceReviewErrorCode.NON_CANONICAL_ORDER,
                "claims must be unique and ordered",
                path="$.claims",
            )
        if relation_keys != tuple(sorted(set(relation_keys))):
            _fail(
                EvidenceReviewErrorCode.NON_CANONICAL_ORDER,
                "relations must be unique and ordered",
                path="$.claim_relations",
            )
        claim_set = set(claim_refs)
        if any(
            relation.subject_claim_ref not in claim_set
            or relation.object_claim_ref not in claim_set
            for relation in self.claim_relations
        ):
            _fail(
                EvidenceReviewErrorCode.DANGLING_REF,
                "relation references absent claim",
                path="$.claim_relations",
            )
        requirements: dict[EvidenceClaimType, tuple[EvidenceDocumentType, ...]] = {}
        for claim in self.claims:
            previous = requirements.setdefault(
                claim.claim_type, claim.required_source_types
            )
            if previous != claim.required_source_types:
                _fail(
                    EvidenceReviewErrorCode.SOURCE_TYPE_MISMATCH,
                    "same claim type has inconsistent source requirements",
                    path="$.claims",
                )
        self._reject_supersession_cycles()

    def _reject_supersession_cycles(self) -> None:
        edges: dict[str, set[str]] = {}
        for relation in self.claim_relations:
            if relation.kind is ClaimRelationKind.SUPERSEDES:
                edges.setdefault(relation.subject_claim_ref, set()).add(
                    relation.object_claim_ref
                )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                _fail(
                    EvidenceReviewErrorCode.CONFLICT_BLOCKED,
                    "supersession cycle",
                    path="$.claim_relations",
                )
            if node in visited:
                return
            visiting.add(node)
            for target in edges.get(node, set()):
                visit(target)
            visiting.remove(node)
            visited.add(node)

        for node in sorted(edges):
            visit(node)

    def validate_against_evidence(self, evidence: EvidenceManifestSnapshotV1) -> None:
        if (
            self.evidence_snapshot_id != evidence.snapshot_id
            or self.evidence_content_sha256 != evidence.content_sha256
        ):
            _fail(
                EvidenceReviewErrorCode.HASH_MISMATCH,
                "review is not pinned to the exact evidence snapshot",
            )
        if (
            self.evidence_manifest_schema_version
            != evidence.payload.evidence_manifest_schema_version
            or self.evidence_contract_version
            != evidence.payload.mat_evid_contract_version
        ):
            _fail(EvidenceReviewErrorCode.UNKNOWN_SCHEMA, "evidence version drift")
        reviewed_sources = {source.source_ref: source for source in self.sources}
        evidence_sources = {
            source.source_ref: source for source in evidence.payload.sources
        }
        if set(reviewed_sources) != set(evidence_sources):
            _fail(
                EvidenceReviewErrorCode.INCOMPLETE_COVERAGE,
                "review must cover every and only every source",
                path="$.sources",
            )
        for source_ref, review in reviewed_sources.items():
            source = evidence_sources[source_ref]
            if (
                review.document_id,
                review.document_revision,
                review.publication_edition,
                review.content_sha256,
            ) != (
                source.document_id,
                source.document_revision,
                source.publication_edition,
                source.content_sha256,
            ):
                _fail(
                    EvidenceReviewErrorCode.SOURCE_IDENTITY_MISMATCH,
                    "review source identity differs from 01A",
                    path=f"$.sources[{source_ref}]",
                )
        reviewed_claims = {claim.claim_ref: claim for claim in self.claims}
        evidence_claims = {claim.claim_ref: claim for claim in evidence.payload.claims}
        if set(reviewed_claims) != set(evidence_claims):
            _fail(
                EvidenceReviewErrorCode.INCOMPLETE_COVERAGE,
                "review must cover every and only every claim",
                path="$.claims",
            )
        source_types = {
            source.source_ref: source.document_type for source in self.sources
        }
        for claim_ref, review in reviewed_claims.items():
            claim = evidence_claims[claim_ref]
            if review.scope != claim.scope:
                _fail(
                    EvidenceReviewErrorCode.CLAIM_SCOPE_MISMATCH,
                    "review scope differs from 01A",
                    path=f"$.claims[{claim_ref}].scope",
                )
            actual_types = {
                source_types[source_ref] for source_ref in claim.source_refs
            }
            required_types = set(review.required_source_types)
            if not required_types.issubset(actual_types):
                missing_types = sorted(
                    item.value for item in required_types - actual_types
                )
                _fail(
                    EvidenceReviewErrorCode.SOURCE_TYPE_MISMATCH,
                    f"claim lacks required source types {missing_types}",
                    path=f"$.claims[{claim_ref}].required_source_types",
                )

    def validate_for_approval(self, evidence: EvidenceManifestSnapshotV1) -> None:
        self.validate_against_evidence(evidence)
        blocked = [
            source.source_ref
            for source in self.sources
            if source.rights_state
            in {EvidenceRightsState.UNKNOWN, EvidenceRightsState.RESTRICTED}
        ]
        if blocked:
            _fail(
                EvidenceReviewErrorCode.RIGHTS_BLOCKED,
                f"rights block sources {blocked}",
            )
        if self.claim_relations:
            _fail(
                EvidenceReviewErrorCode.CONFLICT_BLOCKED,
                "conflict/supersession requires a corrected evidence snapshot",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": self.canonicalization_version,
            "claim_relations": [item.to_dict() for item in self.claim_relations],
            "claims": [item.to_dict() for item in self.claims],
            "evidence_content_sha256": self.evidence_content_sha256,
            "evidence_contract_version": self.evidence_contract_version,
            "evidence_manifest_schema_version": self.evidence_manifest_schema_version,
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "mat_evid_review_contract_version": self.mat_evid_review_contract_version,
            "review_schema_version": self.review_schema_version,
            "sources": [item.to_dict() for item in self.sources],
        }


def _parse_locator(value: Any, *, path: str) -> SourceLocatorV1:
    obj = _dict(value, path=path)
    state = obj.get("state")
    if state == "exact":
        _require_exact(obj, frozenset({"state", "value"}), path=path)
        return ExactLocatorV1(_text(obj["value"], path=f"{path}.value"))
    if state == "unavailable":
        _require_exact(obj, frozenset({"state", "reason"}), path=path)
        return UnavailableLocatorV1(_text(obj["reason"], path=f"{path}.reason"))
    _fail(EvidenceReviewErrorCode.INVALID_TYPE, "unknown locator state", path=path)


def _parse_excerpt(value: Any, *, path: str) -> SourceExcerptV1:
    obj = _dict(value, path=path)
    state = obj.get("state")
    if state == "omitted":
        _require_exact(obj, frozenset({"state"}), path=path)
        return OmittedExcerptV1()
    if state == "included":
        _require_exact(obj, frozenset({"state", "text", "rights_basis"}), path=path)
        return IncludedExcerptV1(
            text=_text(obj["text"], path=f"{path}.text"),
            rights_basis=_text(obj["rights_basis"], path=f"{path}.rights_basis"),
        )
    _fail(EvidenceReviewErrorCode.INVALID_TYPE, "unknown excerpt state", path=path)


def _parse_scope(value: Any, *, path: str) -> EvidenceClaimScopeV1:
    obj = _dict(value, path=path)
    _require_exact(obj, frozenset({"materials", "media", "conditions"}), path=path)
    return EvidenceClaimScopeV1(
        materials=tuple(_ordered_strings(obj["materials"], path=f"{path}.materials")),
        media=tuple(_ordered_strings(obj["media"], path=f"{path}.media")),
        conditions=_ordered_strings_allow_empty(
            obj["conditions"], path=f"{path}.conditions"
        ),
    )


def parse_review_payload(raw: str | bytes) -> EvidenceReviewPayloadV1:
    try:
        obj = parse_json_without_duplicates(raw)
    except MaterialEvidenceValidationError as exc:
        code = {
            MaterialEvidenceErrorCode.DUPLICATE_PROPERTY: (
                EvidenceReviewErrorCode.DUPLICATE_PROPERTY
            ),
            MaterialEvidenceErrorCode.NON_NFC: EvidenceReviewErrorCode.NON_NFC,
            MaterialEvidenceErrorCode.INVALID_UNICODE: (
                EvidenceReviewErrorCode.INVALID_UNICODE
            ),
        }.get(exc.code, EvidenceReviewErrorCode.INVALID_JSON)
        raise EvidenceReviewValidationError(code, "invalid strict JSON") from exc
    except Exception as exc:
        if isinstance(exc, EvidenceReviewValidationError):
            raise
        raise EvidenceReviewValidationError(
            EvidenceReviewErrorCode.INVALID_JSON, "invalid JSON"
        ) from exc
    _require_exact(
        obj,
        frozenset(
            {
                "review_schema_version",
                "canonicalization_version",
                "mat_evid_review_contract_version",
                "evidence_snapshot_id",
                "evidence_content_sha256",
                "evidence_manifest_schema_version",
                "evidence_contract_version",
                "sources",
                "claims",
                "claim_relations",
            }
        ),
        path="$",
    )
    if (
        type(obj["review_schema_version"]) is not int
        or obj["review_schema_version"] != REVIEW_SCHEMA_VERSION
        or type(obj["canonicalization_version"]) is not int
        or obj["canonicalization_version"] != CANONICALIZATION_VERSION
        or obj["mat_evid_review_contract_version"] != MAT_EVID_REVIEW_CONTRACT_VERSION
        or type(obj["evidence_manifest_schema_version"]) is not int
    ):
        _fail(EvidenceReviewErrorCode.UNKNOWN_SCHEMA, "unknown 01C contract")
    sources: list[ReviewedSourceMetadataV1] = []
    source_fields = frozenset(
        {
            "source_ref",
            "document_id",
            "document_title",
            "publisher",
            "document_type",
            "document_revision",
            "publication_edition",
            "content_sha256",
            "locator",
            "rights_state",
            "rights_basis",
            "excerpt",
        }
    )
    for index, item in enumerate(_list(obj["sources"], path="$.sources")):
        value = _dict(item, path=f"$.sources[{index}]")
        _require_exact(value, source_fields, path=f"$.sources[{index}]")
        sources.append(
            ReviewedSourceMetadataV1(
                source_ref=_text(
                    value["source_ref"], path=f"$.sources[{index}].source_ref"
                ),
                document_id=_text(
                    value["document_id"], path=f"$.sources[{index}].document_id"
                ),
                document_title=_text(
                    value["document_title"], path=f"$.sources[{index}].document_title"
                ),
                publisher=_text(
                    value["publisher"], path=f"$.sources[{index}].publisher"
                ),
                document_type=_enum(
                    EvidenceDocumentType,
                    value["document_type"],
                    path=f"$.sources[{index}].document_type",
                ),
                document_revision=_text(
                    value["document_revision"],
                    path=f"$.sources[{index}].document_revision",
                ),
                publication_edition=_text(
                    value["publication_edition"],
                    path=f"$.sources[{index}].publication_edition",
                ),
                content_sha256=_text(
                    value["content_sha256"], path=f"$.sources[{index}].content_sha256"
                ),
                locator=_parse_locator(
                    value["locator"], path=f"$.sources[{index}].locator"
                ),
                rights_state=_enum(
                    EvidenceRightsState,
                    value["rights_state"],
                    path=f"$.sources[{index}].rights_state",
                ),
                rights_basis=_text(
                    value["rights_basis"], path=f"$.sources[{index}].rights_basis"
                ),
                excerpt=_parse_excerpt(
                    value["excerpt"], path=f"$.sources[{index}].excerpt"
                ),
            )
        )
    claims: list[ReviewedClaimMetadataV1] = []
    claim_fields = frozenset(
        {"claim_ref", "claim_type", "scope", "required_source_types"}
    )
    for index, item in enumerate(_list(obj["claims"], path="$.claims")):
        value = _dict(item, path=f"$.claims[{index}]")
        _require_exact(value, claim_fields, path=f"$.claims[{index}]")
        required = tuple(
            sorted(
                (
                    _enum(
                        EvidenceDocumentType,
                        entry,
                        path=f"$.claims[{index}].required_source_types",
                    )
                    for entry in _list(
                        value["required_source_types"],
                        path=f"$.claims[{index}].required_source_types",
                    )
                ),
                key=lambda entry: entry.value,
            )
        )
        claims.append(
            ReviewedClaimMetadataV1(
                claim_ref=_text(
                    value["claim_ref"], path=f"$.claims[{index}].claim_ref"
                ),
                claim_type=_enum(
                    EvidenceClaimType,
                    value["claim_type"],
                    path=f"$.claims[{index}].claim_type",
                ),
                scope=_parse_scope(value["scope"], path=f"$.claims[{index}].scope"),
                required_source_types=required,
            )
        )
    relations: list[ClaimRelationV1] = []
    for index, item in enumerate(
        _list(obj["claim_relations"], path="$.claim_relations")
    ):
        value = _dict(item, path=f"$.claim_relations[{index}]")
        _require_exact(
            value,
            frozenset({"kind", "subject_claim_ref", "object_claim_ref"}),
            path=f"$.claim_relations[{index}]",
        )
        relations.append(
            ClaimRelationV1(
                kind=_enum(
                    ClaimRelationKind,
                    value["kind"],
                    path=f"$.claim_relations[{index}].kind",
                ),
                subject_claim_ref=_text(
                    value["subject_claim_ref"],
                    path=f"$.claim_relations[{index}].subject_claim_ref",
                ),
                object_claim_ref=_text(
                    value["object_claim_ref"],
                    path=f"$.claim_relations[{index}].object_claim_ref",
                ),
            )
        )
    return EvidenceReviewPayloadV1(
        evidence_snapshot_id=_text(
            obj["evidence_snapshot_id"], path="$.evidence_snapshot_id"
        ),
        evidence_content_sha256=_text(
            obj["evidence_content_sha256"], path="$.evidence_content_sha256"
        ),
        evidence_manifest_schema_version=obj["evidence_manifest_schema_version"],
        evidence_contract_version=_text(
            obj["evidence_contract_version"], path="$.evidence_contract_version"
        ),
        sources=tuple(sorted(sources, key=lambda item: item.source_ref)),
        claims=tuple(sorted(claims, key=lambda item: item.claim_ref)),
        claim_relations=tuple(sorted(relations, key=lambda item: item.key())),
        review_schema_version=obj["review_schema_version"],
        canonicalization_version=obj["canonicalization_version"],
        mat_evid_review_contract_version=_text(
            obj["mat_evid_review_contract_version"],
            path="$.mat_evid_review_contract_version",
        ),
    )


def canonicalize_review_payload(payload: EvidenceReviewPayloadV1) -> bytes:
    if type(payload) is not EvidenceReviewPayloadV1:
        raise TypeError("payload must be EvidenceReviewPayloadV1")
    return _canonical_json(payload.to_dict())


def compute_review_content_sha256(canonical_bytes: bytes) -> str:
    if type(canonical_bytes) is not bytes:
        raise TypeError("canonical_bytes must be bytes")
    return hashlib.sha256(CONTENT_DOMAIN + canonical_bytes).hexdigest()


def validate_review_id(value: str) -> str:
    return _id(
        value, _REVIEW_ID_RE, "expected mer_<32 lowercase hex>", path="$.review_id"
    )


def validate_review_snapshot_id(value: str) -> str:
    return _id(
        value,
        _REVIEW_SNAPSHOT_ID_RE,
        "expected mrv_<64 lowercase hex>",
        path="$.review_snapshot_id",
    )


def derive_review_snapshot_id(review_id: str, content_sha256: str) -> str:
    validate_review_id(review_id)
    _id(content_sha256, _SHA256_RE, "invalid SHA-256", path="$.content_sha256")
    digest = hashlib.sha256(
        SNAPSHOT_DOMAIN
        + review_id.encode("ascii")
        + b"\x00"
        + content_sha256.encode("ascii")
    ).hexdigest()
    return f"mrv_{digest}"


@dataclass(frozen=True, slots=True)
class EvidenceReviewSnapshotV1:
    review_id: str
    review_snapshot_id: str
    content_sha256: str
    canonical_bytes: bytes
    payload: EvidenceReviewPayloadV1

    def __post_init__(self) -> None:
        validate_review_id(self.review_id)
        validate_review_snapshot_id(self.review_snapshot_id)
        expected_bytes = canonicalize_review_payload(self.payload)
        if self.canonical_bytes != expected_bytes:
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.HASH_MISMATCH,
                "canonical bytes differ from payload",
            )
        expected_hash = compute_review_content_sha256(expected_bytes)
        if self.content_sha256 != expected_hash:
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.HASH_MISMATCH,
                "content hash differs from canonical bytes",
            )
        if self.review_snapshot_id != derive_review_snapshot_id(
            self.review_id, expected_hash
        ):
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.SNAPSHOT_ID_MISMATCH,
                "snapshot identity differs from review and content",
            )

    @classmethod
    def from_json(cls, review_id: str, raw: str | bytes) -> EvidenceReviewSnapshotV1:
        payload = parse_review_payload(raw)
        canonical = canonicalize_review_payload(payload)
        content_hash = compute_review_content_sha256(canonical)
        return cls(
            review_id,
            derive_review_snapshot_id(review_id, content_hash),
            content_hash,
            canonical,
            payload,
        )


@dataclass(frozen=True, slots=True)
class EvidenceReviewProjection:
    review_state: FactualReviewState = FactualReviewState.DRAFT
    approval_state: FactualApprovalState = FactualApprovalState.NOT_APPROVED
    reviewer_subject: str = "UNASSIGNED"
    approver_subject: str = "UNASSIGNED"
    last_sequence: int = 0
    last_event_sha256: str = ZERO_EVENT_HASH

    @property
    def runtime_authority(self) -> str:
        return NO_RUNTIME_AUTHORITY

    @property
    def positive_statement_allowed(self) -> bool:
        return False


def transition_review_projection(
    projection: EvidenceReviewProjection,
    *,
    event_type: ReviewEventType,
    actor_subject: str,
    creator_subject: str,
) -> EvidenceReviewProjection:
    _text(actor_subject, path="$.actor_subject")
    if event_type is ReviewEventType.REVIEWED:
        if (
            projection.review_state is not FactualReviewState.DRAFT
            or actor_subject == creator_subject
        ):
            code = (
                EvidenceReviewErrorCode.SELF_REVIEW
                if actor_subject == creator_subject
                else EvidenceReviewErrorCode.INVALID_TRANSITION
            )
            _fail(code, "review requires an independent reviewer in draft state")
        return EvidenceReviewProjection(
            FactualReviewState.REVIEWED,
            FactualApprovalState.NOT_APPROVED,
            actor_subject,
            "UNASSIGNED",
            projection.last_sequence,
            projection.last_event_sha256,
        )
    if event_type is ReviewEventType.REJECTED:
        if (
            projection.review_state is not FactualReviewState.DRAFT
            or actor_subject == creator_subject
        ):
            _fail(
                EvidenceReviewErrorCode.INVALID_TRANSITION,
                "rejection requires an independent reviewer in draft state",
            )
        return EvidenceReviewProjection(
            FactualReviewState.REJECTED,
            FactualApprovalState.NOT_APPROVED,
            actor_subject,
            "UNASSIGNED",
            projection.last_sequence,
            projection.last_event_sha256,
        )
    if event_type is ReviewEventType.APPROVED:
        if (
            projection.review_state is not FactualReviewState.REVIEWED
            or projection.approval_state is not FactualApprovalState.NOT_APPROVED
        ):
            _fail(
                EvidenceReviewErrorCode.INVALID_TRANSITION,
                "approval requires reviewed/not-approved state",
            )
        if actor_subject in {creator_subject, projection.reviewer_subject}:
            _fail(
                EvidenceReviewErrorCode.SELF_APPROVAL,
                "approver must differ from creator and reviewer",
            )
        return EvidenceReviewProjection(
            projection.review_state,
            FactualApprovalState.APPROVED,
            projection.reviewer_subject,
            actor_subject,
            projection.last_sequence,
            projection.last_event_sha256,
        )
    if event_type is ReviewEventType.REVOKED:
        if projection.approval_state is not FactualApprovalState.APPROVED:
            _fail(
                EvidenceReviewErrorCode.INVALID_TRANSITION,
                "only approved evidence may be revoked",
            )
        if actor_subject in {creator_subject, projection.reviewer_subject}:
            _fail(
                EvidenceReviewErrorCode.SELF_APPROVAL,
                "revoker must differ from creator and reviewer",
            )
        return EvidenceReviewProjection(
            FactualReviewState.REVOKED,
            FactualApprovalState.REVOKED,
            projection.reviewer_subject,
            projection.approver_subject,
            projection.last_sequence,
            projection.last_event_sha256,
        )
    if event_type is ReviewEventType.QUARANTINED:
        if projection.review_state in {
            FactualReviewState.REJECTED,
            FactualReviewState.REVOKED,
            FactualReviewState.QUARANTINED,
        }:
            _fail(EvidenceReviewErrorCode.INVALID_TRANSITION, "terminal review state")
        if actor_subject in {creator_subject, projection.reviewer_subject}:
            _fail(
                EvidenceReviewErrorCode.SELF_APPROVAL,
                "quarantine approver must differ from creator and reviewer",
            )
        return EvidenceReviewProjection(
            FactualReviewState.QUARANTINED,
            FactualApprovalState.QUARANTINED,
            projection.reviewer_subject,
            projection.approver_subject,
            projection.last_sequence,
            projection.last_event_sha256,
        )
    _fail(EvidenceReviewErrorCode.INVALID_TRANSITION, "unknown event")


def compute_validation_sha256(snapshot: EvidenceReviewSnapshotV1) -> str:
    return hashlib.sha256(
        VALIDATION_DOMAIN
        + snapshot.review_snapshot_id.encode("ascii")
        + b"\x00"
        + snapshot.content_sha256.encode("ascii")
    ).hexdigest()


def compute_audit_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(AUDIT_DOMAIN + _canonical_json(payload)).hexdigest()


def compute_lifecycle_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(LIFECYCLE_DOMAIN + _canonical_json(payload)).hexdigest()
