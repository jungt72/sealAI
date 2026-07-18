"""MAT-EVID-01C.v2 factual review for exact MAT-EVID-01A.v2 snapshots.

The lifecycle semantics and source-review vocabulary remain the accepted 01C
contract.  Version 2 adds only exact support for the two closed 01A.v2 claim
scope variants and uses independent review canonicalization/hash domains.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from sealai_v2.core.material_evidence_review import (
    ClaimRelationKind,
    ClaimRelationV1,
    EvidenceClaimType,
    EvidenceDocumentType,
    EvidenceReviewErrorCode,
    EvidenceReviewIntegrityError,
    EvidenceReviewValidationError,
    EvidenceRightsState,
    MAX_APPROVABLE_CLAIM_TEXT_BYTES,
    MAX_APPROVABLE_CLAIM_TEXT_CHARS,
    MAX_SCOPE_VALUE_BYTES,
    MAX_SCOPE_VALUE_CHARS,
    NO_RUNTIME_AUTHORITY,
    ReviewedSourceMetadataV1,
    _bounded_text,
    _canonical_json,
    _dict,
    _enum,
    _fail,
    _id,
    _list,
    _parse_excerpt,
    _parse_locator,
    _require_exact,
    _text,
)
from sealai_v2.core.material_evidence_v2 import (
    EVIDENCE_MANIFEST_SCHEMA_VERSION_V2,
    MAT_EVID_CONTRACT_VERSION_V2,
    EvidenceClaimScopeV2,
    EvidenceManifestSnapshotV2,
    MaterialEvidenceV2ErrorCode,
    MaterialEvidenceV2ValidationError,
    MaterialRelationClaimScopeV2,
    MediaIdentityClaimScopeV2,
    parse_json_v2,
)


REVIEW_SCHEMA_VERSION_V2 = 2
REVIEW_CANONICALIZATION_VERSION_V2 = 2
MAT_EVID_REVIEW_CONTRACT_VERSION_V2 = "MAT-EVID-01C.v2"

CONTENT_DOMAIN_V2 = b"sealai.material-evidence-review.content.v2\x00"
SNAPSHOT_DOMAIN_V2 = b"sealai.material-evidence-review.snapshot.v2\x00"
VALIDATION_DOMAIN_V2 = b"sealai.material-evidence-review.validation.v2\x00"
AUDIT_DOMAIN_V2 = b"sealai.material-evidence-review.audit.v2\x00"
LIFECYCLE_DOMAIN_V2 = b"sealai.material-evidence-review.lifecycle.v2\x00"

_REVIEW_ID_RE = re.compile(r"^mer_[0-9a-f]{32}$", re.ASCII)
_REVIEW_SNAPSHOT_ID_RE = re.compile(r"^mrv_[0-9a-f]{64}$", re.ASCII)
_EVIDENCE_SNAPSHOT_ID_RE = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_CLAIM_REF_RE = re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

ReviewedSourceMetadataV2 = ReviewedSourceMetadataV1
ClaimRelationV2 = ClaimRelationV1


@dataclass(frozen=True, slots=True)
class ReviewedClaimMetadataV2:
    claim_ref: str
    claim_type: EvidenceClaimType
    scope: EvidenceClaimScopeV2
    required_source_types: tuple[EvidenceDocumentType, ...]

    def __post_init__(self) -> None:
        _id(
            self.claim_ref,
            _CLAIM_REF_RE,
            "invalid claim_ref",
            path="$.claim.claim_ref",
        )
        if type(self.claim_type) is not EvidenceClaimType:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid claim_type",
                path="$.claim.claim_type",
            )
        if type(self.scope) not in {
            MaterialRelationClaimScopeV2,
            MediaIdentityClaimScopeV2,
        }:
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "invalid v2 claim scope",
                path="$.claim.scope",
            )
        if (
            type(self.scope) is MediaIdentityClaimScopeV2
            and self.claim_type is not EvidenceClaimType.OTHER_TECHNICAL
        ):
            _fail(
                EvidenceReviewErrorCode.CLAIM_SCOPE_MISMATCH,
                "media_identity scope requires other_technical claim type",
                path="$.claim.claim_type",
            )
        if (
            type(self.scope) is MaterialRelationClaimScopeV2
            and self.claim_type is EvidenceClaimType.OTHER_TECHNICAL
        ):
            _fail(
                EvidenceReviewErrorCode.CLAIM_SCOPE_MISMATCH,
                "other_technical is reserved for media_identity scope in v2",
                path="$.claim.claim_type",
            )
        scope_values = (
            self.scope.materials + self.scope.media + self.scope.conditions
            if type(self.scope) is MaterialRelationClaimScopeV2
            else (self.scope.media_ref, self.scope.identity_assertion_ref)
        )
        for index, value in enumerate(scope_values):
            _bounded_text(
                value,
                path=f"$.claim.scope.values[{index}]",
                max_chars=MAX_SCOPE_VALUE_CHARS,
                max_bytes=MAX_SCOPE_VALUE_BYTES,
            )
        if (
            type(self.required_source_types) is not tuple
            or not self.required_source_types
            or any(
                type(item) is not EvidenceDocumentType
                for item in self.required_source_types
            )
        ):
            _fail(
                EvidenceReviewErrorCode.INVALID_TYPE,
                "required_source_types must be a non-empty typed tuple",
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
class EvidenceReviewPayloadV2:
    evidence_snapshot_id: str
    evidence_content_sha256: str
    sources: tuple[ReviewedSourceMetadataV2, ...]
    claims: tuple[ReviewedClaimMetadataV2, ...]
    claim_relations: tuple[ClaimRelationV2, ...]
    evidence_manifest_schema_version: int = EVIDENCE_MANIFEST_SCHEMA_VERSION_V2
    evidence_contract_version: str = MAT_EVID_CONTRACT_VERSION_V2
    review_schema_version: int = REVIEW_SCHEMA_VERSION_V2
    canonicalization_version: int = REVIEW_CANONICALIZATION_VERSION_V2
    mat_evid_review_contract_version: str = MAT_EVID_REVIEW_CONTRACT_VERSION_V2

    def __post_init__(self) -> None:
        _id(
            self.evidence_snapshot_id,
            _EVIDENCE_SNAPSHOT_ID_RE,
            "invalid evidence snapshot ID",
            path="$.evidence_snapshot_id",
        )
        _id(
            self.evidence_content_sha256,
            _SHA256_RE,
            "invalid evidence hash",
            path="$.evidence_content_sha256",
        )
        if (
            type(self.review_schema_version) is not int
            or self.review_schema_version != REVIEW_SCHEMA_VERSION_V2
            or type(self.canonicalization_version) is not int
            or self.canonicalization_version != REVIEW_CANONICALIZATION_VERSION_V2
            or self.mat_evid_review_contract_version
            != MAT_EVID_REVIEW_CONTRACT_VERSION_V2
            or type(self.evidence_manifest_schema_version) is not int
            or self.evidence_manifest_schema_version
            != EVIDENCE_MANIFEST_SCHEMA_VERSION_V2
            or self.evidence_contract_version != MAT_EVID_CONTRACT_VERSION_V2
        ):
            _fail(
                EvidenceReviewErrorCode.UNKNOWN_SCHEMA,
                "01C v2 requires exact MAT-EVID-01A.v2",
            )
        for name, values, item_type in (
            ("sources", self.sources, ReviewedSourceMetadataV1),
            ("claims", self.claims, ReviewedClaimMetadataV2),
        ):
            if (
                type(values) is not tuple
                or not values
                or any(type(item) is not item_type for item in values)
            ):
                _fail(
                    EvidenceReviewErrorCode.INVALID_TYPE,
                    f"{name} must be a non-empty typed tuple",
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

    def validate_against_evidence(self, evidence: EvidenceManifestSnapshotV2) -> None:
        if type(evidence) is not EvidenceManifestSnapshotV2:
            _fail(
                EvidenceReviewErrorCode.UNKNOWN_SCHEMA,
                "01C v2 requires an exact 01A.v2 snapshot",
            )
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
                    "review source identity differs from 01A.v2",
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
                    "review scope differs from 01A.v2",
                    path=f"$.claims[{claim_ref}].scope",
                )
            actual_types = {
                source_types[source_ref] for source_ref in claim.source_refs
            }
            required_types = set(review.required_source_types)
            if not required_types.issubset(actual_types):
                _fail(
                    EvidenceReviewErrorCode.SOURCE_TYPE_MISMATCH,
                    "claim lacks required source types",
                    path=f"$.claims[{claim_ref}].required_source_types",
                )

    def validate_for_approval(self, evidence: EvidenceManifestSnapshotV2) -> None:
        self.validate_against_evidence(evidence)
        for index, claim in enumerate(evidence.payload.claims):
            _bounded_text(
                claim.claim_text,
                path=f"$.evidence.claims[{index}].claim_text",
                max_chars=MAX_APPROVABLE_CLAIM_TEXT_CHARS,
                max_bytes=MAX_APPROVABLE_CLAIM_TEXT_BYTES,
            )
        if any(
            source.rights_state
            in {EvidenceRightsState.UNKNOWN, EvidenceRightsState.RESTRICTED}
            for source in self.sources
        ):
            _fail(EvidenceReviewErrorCode.RIGHTS_BLOCKED, "source rights block review")
        if self.claim_relations:
            _fail(
                EvidenceReviewErrorCode.CONFLICT_BLOCKED,
                "relations require a corrected immutable snapshot",
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


def _parse_scope_v2(value: Any, *, path: str) -> EvidenceClaimScopeV2:
    obj = _dict(value, path=path)
    discriminator = obj.get("scope_type")
    if discriminator == "material_relation":
        _require_exact(
            obj,
            frozenset({"scope_type", "materials", "media", "conditions"}),
            path=path,
        )
        return MaterialRelationClaimScopeV2(
            materials=_ordered_strings_v2(obj["materials"], path=f"{path}.materials"),
            media=_ordered_strings_v2(obj["media"], path=f"{path}.media"),
            conditions=_ordered_strings_v2(
                obj["conditions"], path=f"{path}.conditions", allow_empty=True
            ),
        )
    if discriminator == "media_identity":
        _require_exact(
            obj,
            frozenset({"scope_type", "media_ref", "identity_assertion_ref"}),
            path=path,
        )
        return MediaIdentityClaimScopeV2(
            media_ref=_text(obj["media_ref"], path=f"{path}.media_ref"),
            identity_assertion_ref=_text(
                obj["identity_assertion_ref"],
                path=f"{path}.identity_assertion_ref",
            ),
        )
    _fail(
        EvidenceReviewErrorCode.UNKNOWN_SCHEMA,
        "unknown v2 scope discriminator",
        path=f"{path}.scope_type",
    )


def _ordered_strings_v2(
    value: Any, *, path: str, allow_empty: bool = False
) -> tuple[str, ...]:
    items = tuple(
        _text(item, path=f"{path}[{index}]")
        for index, item in enumerate(_list(value, path=path))
    )
    if not allow_empty and not items:
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


def parse_review_payload_v2(raw: str | bytes) -> EvidenceReviewPayloadV2:
    try:
        obj = parse_json_v2(raw)
    except MaterialEvidenceV2ValidationError as exc:
        code = {
            MaterialEvidenceV2ErrorCode.DUPLICATE_PROPERTY: (
                EvidenceReviewErrorCode.DUPLICATE_PROPERTY
            ),
            MaterialEvidenceV2ErrorCode.NON_NFC: EvidenceReviewErrorCode.NON_NFC,
            MaterialEvidenceV2ErrorCode.INVALID_UNICODE: (
                EvidenceReviewErrorCode.INVALID_UNICODE
            ),
        }.get(exc.code, EvidenceReviewErrorCode.INVALID_JSON)
        raise EvidenceReviewValidationError(code, "invalid strict JSON") from exc
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
        obj["review_schema_version"] != REVIEW_SCHEMA_VERSION_V2
        or obj["canonicalization_version"] != REVIEW_CANONICALIZATION_VERSION_V2
        or obj["mat_evid_review_contract_version"]
        != MAT_EVID_REVIEW_CONTRACT_VERSION_V2
        or obj["evidence_manifest_schema_version"]
        != EVIDENCE_MANIFEST_SCHEMA_VERSION_V2
        or obj["evidence_contract_version"] != MAT_EVID_CONTRACT_VERSION_V2
    ):
        _fail(EvidenceReviewErrorCode.UNKNOWN_SCHEMA, "unknown 01C v2 contract")
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
    sources: list[ReviewedSourceMetadataV2] = []
    for index, item in enumerate(_list(obj["sources"], path="$.sources")):
        path = f"$.sources[{index}]"
        value = _dict(item, path=path)
        _require_exact(value, source_fields, path=path)
        sources.append(
            ReviewedSourceMetadataV1(
                source_ref=_text(value["source_ref"], path=f"{path}.source_ref"),
                document_id=_text(value["document_id"], path=f"{path}.document_id"),
                document_title=_text(
                    value["document_title"], path=f"{path}.document_title"
                ),
                publisher=_text(value["publisher"], path=f"{path}.publisher"),
                document_type=_enum(
                    EvidenceDocumentType,
                    value["document_type"],
                    path=f"{path}.document_type",
                ),
                document_revision=_text(
                    value["document_revision"], path=f"{path}.document_revision"
                ),
                publication_edition=_text(
                    value["publication_edition"], path=f"{path}.publication_edition"
                ),
                content_sha256=_text(
                    value["content_sha256"], path=f"{path}.content_sha256"
                ),
                locator=_parse_locator(value["locator"], path=f"{path}.locator"),
                rights_state=_enum(
                    EvidenceRightsState,
                    value["rights_state"],
                    path=f"{path}.rights_state",
                ),
                rights_basis=_text(value["rights_basis"], path=f"{path}.rights_basis"),
                excerpt=_parse_excerpt(value["excerpt"], path=f"{path}.excerpt"),
            )
        )
    claim_fields = frozenset(
        {"claim_ref", "claim_type", "scope", "required_source_types"}
    )
    claims: list[ReviewedClaimMetadataV2] = []
    for index, item in enumerate(_list(obj["claims"], path="$.claims")):
        path = f"$.claims[{index}]"
        value = _dict(item, path=path)
        _require_exact(value, claim_fields, path=path)
        required = tuple(
            _enum(
                EvidenceDocumentType,
                entry,
                path=f"{path}.required_source_types",
            )
            for entry in _list(
                value["required_source_types"],
                path=f"{path}.required_source_types",
            )
        )
        claims.append(
            ReviewedClaimMetadataV2(
                claim_ref=_text(value["claim_ref"], path=f"{path}.claim_ref"),
                claim_type=_enum(
                    EvidenceClaimType,
                    value["claim_type"],
                    path=f"{path}.claim_type",
                ),
                scope=_parse_scope_v2(value["scope"], path=f"{path}.scope"),
                required_source_types=required,
            )
        )
    relations: list[ClaimRelationV2] = []
    for index, item in enumerate(
        _list(obj["claim_relations"], path="$.claim_relations")
    ):
        path = f"$.claim_relations[{index}]"
        value = _dict(item, path=path)
        _require_exact(
            value,
            frozenset({"kind", "subject_claim_ref", "object_claim_ref"}),
            path=path,
        )
        relations.append(
            ClaimRelationV1(
                kind=_enum(ClaimRelationKind, value["kind"], path=f"{path}.kind"),
                subject_claim_ref=_text(
                    value["subject_claim_ref"], path=f"{path}.subject_claim_ref"
                ),
                object_claim_ref=_text(
                    value["object_claim_ref"], path=f"{path}.object_claim_ref"
                ),
            )
        )
    return EvidenceReviewPayloadV2(
        evidence_snapshot_id=_text(
            obj["evidence_snapshot_id"], path="$.evidence_snapshot_id"
        ),
        evidence_content_sha256=_text(
            obj["evidence_content_sha256"], path="$.evidence_content_sha256"
        ),
        sources=tuple(sources),
        claims=tuple(claims),
        claim_relations=tuple(relations),
        evidence_manifest_schema_version=obj["evidence_manifest_schema_version"],
        evidence_contract_version=_text(
            obj["evidence_contract_version"], path="$.evidence_contract_version"
        ),
        review_schema_version=obj["review_schema_version"],
        canonicalization_version=obj["canonicalization_version"],
        mat_evid_review_contract_version=_text(
            obj["mat_evid_review_contract_version"],
            path="$.mat_evid_review_contract_version",
        ),
    )


def canonicalize_review_payload_v2(payload: EvidenceReviewPayloadV2) -> bytes:
    if type(payload) is not EvidenceReviewPayloadV2:
        raise TypeError("payload must be EvidenceReviewPayloadV2")
    return _canonical_json(payload.to_dict())


def compute_review_content_sha256_v2(canonical_bytes: bytes) -> str:
    if type(canonical_bytes) is not bytes:
        raise TypeError("canonical_bytes must be bytes")
    return hashlib.sha256(CONTENT_DOMAIN_V2 + canonical_bytes).hexdigest()


def validate_review_id_v2(value: str) -> str:
    return _id(
        value, _REVIEW_ID_RE, "expected mer_<32 lowercase hex>", path="$.review_id"
    )


def validate_review_snapshot_id_v2(value: str) -> str:
    return _id(
        value,
        _REVIEW_SNAPSHOT_ID_RE,
        "expected mrv_<64 lowercase hex>",
        path="$.review_snapshot_id",
    )


def derive_review_snapshot_id_v2(review_id: str, content_sha256: str) -> str:
    validate_review_id_v2(review_id)
    _id(content_sha256, _SHA256_RE, "invalid hash", path="$.content_sha256")
    return (
        "mrv_"
        + hashlib.sha256(
            SNAPSHOT_DOMAIN_V2
            + review_id.encode("ascii")
            + b"\x00"
            + content_sha256.encode("ascii")
        ).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class EvidenceReviewSnapshotV2:
    review_id: str
    review_snapshot_id: str
    content_sha256: str
    canonical_bytes: bytes
    payload: EvidenceReviewPayloadV2

    def __post_init__(self) -> None:
        validate_review_id_v2(self.review_id)
        validate_review_snapshot_id_v2(self.review_snapshot_id)
        if type(self.payload) is not EvidenceReviewPayloadV2:
            raise TypeError("payload must be EvidenceReviewPayloadV2")
        expected_bytes = canonicalize_review_payload_v2(self.payload)
        if self.canonical_bytes != expected_bytes:
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.HASH_MISMATCH,
                "v2 review canonical bytes differ from payload",
            )
        expected_hash = compute_review_content_sha256_v2(expected_bytes)
        if self.content_sha256 != expected_hash:
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.HASH_MISMATCH,
                "v2 review content hash differs",
            )
        if self.review_snapshot_id != derive_review_snapshot_id_v2(
            self.review_id, expected_hash
        ):
            raise EvidenceReviewIntegrityError(
                EvidenceReviewErrorCode.SNAPSHOT_ID_MISMATCH,
                "v2 review snapshot ID differs",
            )

    @classmethod
    def create(
        cls, review_id: str, payload: EvidenceReviewPayloadV2
    ) -> EvidenceReviewSnapshotV2:
        canonical_bytes = canonicalize_review_payload_v2(payload)
        content_sha256 = compute_review_content_sha256_v2(canonical_bytes)
        return cls(
            review_id=review_id,
            review_snapshot_id=derive_review_snapshot_id_v2(review_id, content_sha256),
            content_sha256=content_sha256,
            canonical_bytes=canonical_bytes,
            payload=payload,
        )

    @classmethod
    def from_json(cls, review_id: str, raw: str | bytes) -> EvidenceReviewSnapshotV2:
        return cls.create(review_id, parse_review_payload_v2(raw))

    @property
    def runtime_authority(self) -> str:
        return NO_RUNTIME_AUTHORITY

    @property
    def positive_statement_allowed(self) -> bool:
        return False


def compute_review_validation_sha256_v2(snapshot: EvidenceReviewSnapshotV2) -> str:
    return hashlib.sha256(
        VALIDATION_DOMAIN_V2
        + snapshot.review_snapshot_id.encode("ascii")
        + b"\x00"
        + snapshot.content_sha256.encode("ascii")
    ).hexdigest()


def compute_review_audit_sha256_v2(payload: dict[str, Any]) -> str:
    return hashlib.sha256(AUDIT_DOMAIN_V2 + _canonical_json(payload)).hexdigest()


def compute_review_lifecycle_sha256_v2(payload: dict[str, Any]) -> str:
    if type(payload) is not dict:
        raise TypeError("lifecycle payload must be a dict")
    return hashlib.sha256(LIFECYCLE_DOMAIN_V2 + _canonical_json(payload)).hexdigest()


__all__ = [
    "AUDIT_DOMAIN_V2",
    "CONTENT_DOMAIN_V2",
    "MAT_EVID_REVIEW_CONTRACT_VERSION_V2",
    "REVIEW_CANONICALIZATION_VERSION_V2",
    "REVIEW_SCHEMA_VERSION_V2",
    "SNAPSHOT_DOMAIN_V2",
    "VALIDATION_DOMAIN_V2",
    "ClaimRelationV2",
    "EvidenceReviewPayloadV2",
    "EvidenceReviewSnapshotV2",
    "ReviewedClaimMetadataV2",
    "ReviewedSourceMetadataV2",
    "canonicalize_review_payload_v2",
    "compute_review_audit_sha256_v2",
    "compute_review_lifecycle_sha256_v2",
    "compute_review_content_sha256_v2",
    "compute_review_validation_sha256_v2",
    "derive_review_snapshot_id_v2",
    "parse_review_payload_v2",
    "validate_review_id_v2",
    "validate_review_snapshot_id_v2",
]
