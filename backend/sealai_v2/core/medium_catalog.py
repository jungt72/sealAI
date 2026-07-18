"""MED-NORM-01 closed media catalog and structured classification contracts.

This module is deliberately runtime-inert.  It contains no built-in media
facts, performs no token splitting, and cannot turn an LLM candidate into a
canonical identity.  Canonical assignments are bound to one exact immutable
catalog snapshot and are produced only by exact catalog lookup or an explicit
user-confirmation provenance record.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any, Callable, NoReturn

from sealai_v2.core.contracts import (
    EvaluationState,
    InputResolutionState,
    MaterialConstraintBlocker,
    MaterialConstraintBlockerKind,
    MaterialConstraintMatch,
    MaterialConstraintResult,
    MaterialConstraintVerdict,
    MediumCardinality,
    RelationState,
    material_constraint_match_sort_key,
)


MEDIA_CATALOG_SCHEMA_VERSION = 1
CANONICALIZATION_VERSION = 1
MED_NORM_CONTRACT_VERSION = "MED-NORM-01.v1"

CONTENT_HASH_DOMAIN = b"sealai.medium-catalog.content.v1\x00"
SNAPSHOT_ID_DOMAIN = b"sealai.medium-catalog.snapshot.v1\x00"
ENTRY_HASH_DOMAIN = b"sealai.medium-catalog.entry.v1\x00"
IDENTITY_ASSERTION_HASH_DOMAIN = b"sealai.medium-catalog.identity-assertion.v1\x00"
MEDIA_ID_DOMAIN = b"sealai.medium-catalog.media-id.v1\x00"
VALIDATION_HASH_DOMAIN = b"sealai.medium-catalog.validation.v1\x00"
AUDIT_HASH_DOMAIN = b"sealai.medium-catalog.audit.v1\x00"

_CATALOG_ID_RE = re.compile(r"^mcf_[0-9a-f]{32}$", re.ASCII)
_SNAPSHOT_ID_RE = re.compile(r"^mcs_[0-9a-f]{64}$", re.ASCII)
_MEDIA_ID_RE = re.compile(r"^med_[0-9a-f]{64}$", re.ASCII)
_REVIEW_SNAPSHOT_ID_RE = re.compile(r"^mrv_[0-9a-f]{64}$", re.ASCII)
_CLAIM_REF_RE = re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII)
_COMPONENT_REF_RE = re.compile(r"^mcmp_[0-9a-f]{32}$", re.ASCII)
_CONFIRMATION_REF_RE = re.compile(r"^mconf_[0-9a-f]{32}$", re.ASCII)
_HMAC_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", re.ASCII)
_DOMAIN_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "media_catalog_schema_version",
        "canonicalization_version",
        "med_norm_contract_version",
        "domain_pack_id",
        "entries",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "media_id",
        "canonical_name",
        "identity_kind",
        "aliases",
        "evidence_review_snapshot_id",
        "evidence_review_content_sha256",
        "claim_refs",
    }
)


class MediumCatalogErrorCode(str, Enum):
    INVALID_JSON = "MED_NORM_INVALID_JSON"
    DUPLICATE_PROPERTY = "MED_NORM_DUPLICATE_PROPERTY"
    UNKNOWN_FIELD = "MED_NORM_UNKNOWN_FIELD"
    INVALID_TYPE = "MED_NORM_INVALID_TYPE"
    INVALID_ID = "MED_NORM_INVALID_ID"
    INVALID_UNICODE = "MED_NORM_INVALID_UNICODE"
    NON_NFC = "MED_NORM_NON_NFC"
    FLOAT_FORBIDDEN = "MED_NORM_FLOAT_FORBIDDEN"
    UNKNOWN_SCHEMA = "MED_NORM_UNKNOWN_SCHEMA"
    INVALID_CONSTANT = "MED_NORM_INVALID_CONSTANT"
    DUPLICATE_REF = "MED_NORM_DUPLICATE_REF"
    DANGLING_REF = "MED_NORM_DANGLING_REF"
    NON_CANONICAL_ORDER = "MED_NORM_NON_CANONICAL_ORDER"
    RELATION_INCOMPLETE = "MED_NORM_RELATION_INCOMPLETE"
    HASH_MISMATCH = "MED_NORM_HASH_MISMATCH"
    SNAPSHOT_ID_MISMATCH = "MED_NORM_SNAPSHOT_ID_MISMATCH"
    DB_INTEGRITY = "MED_NORM_DB_INTEGRITY"


class MediumCatalogValidationError(ValueError):
    def __init__(
        self, code: MediumCatalogErrorCode, message: str, *, path: str = "$"
    ) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value} at {path}: {message}")


class MediumCatalogIntegrityError(RuntimeError):
    quarantine_candidate = True

    def __init__(self, code: MediumCatalogErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(code: MediumCatalogErrorCode, message: str, *, path: str = "$") -> NoReturn:
    raise MediumCatalogValidationError(code, message, path=path)


def _exact_fields(
    value: dict[str, Any], expected: frozenset[str], *, path: str
) -> None:
    actual = frozenset(value)
    if actual != expected:
        _fail(
            MediumCatalogErrorCode.UNKNOWN_FIELD,
            f"unknown={sorted(actual - expected)} missing={sorted(expected - actual)}",
            path=path,
        )


def _unicode(value: str, *, path: str) -> None:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _fail(
            MediumCatalogErrorCode.INVALID_UNICODE,
            "invalid Unicode scalar",
            path=path,
        )
    if unicodedata.normalize("NFC", value) != value:
        _fail(
            MediumCatalogErrorCode.NON_NFC,
            "string must already be NFC",
            path=path,
        )


def _text(value: Any, *, path: str, maximum: int = 256) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        _fail(
            MediumCatalogErrorCode.INVALID_TYPE,
            "expected non-whitespace string",
            path=path,
        )
    _unicode(value, path=path)
    if len(value) > maximum or len(value.encode("utf-8")) > maximum * 4:
        _fail(
            MediumCatalogErrorCode.INVALID_TYPE,
            "string exceeds the closed catalog limit",
            path=path,
        )
    return value


def _identifier(
    value: Any, pattern: re.Pattern[str], *, path: str, message: str
) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _fail(MediumCatalogErrorCode.INVALID_ID, message, path=path)
    return value


def _version(value: Any, expected: int, *, path: str) -> int:
    if type(value) is not int:
        _fail(MediumCatalogErrorCode.INVALID_TYPE, "expected integer", path=path)
    if value != expected:
        _fail(
            MediumCatalogErrorCode.UNKNOWN_SCHEMA,
            f"only version {expected} is supported",
            path=path,
        )
    return value


def _canonical_json(value: Any) -> bytes:
    def visit(item: Any, path: str) -> None:
        if type(item) is str:
            _unicode(item, path=path)
            return
        if item is None or type(item) in {bool, int}:
            return
        if type(item) is float:
            _fail(
                MediumCatalogErrorCode.FLOAT_FORBIDDEN,
                "floating-point values are forbidden",
                path=path,
            )
        if type(item) is list:
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or not key.isascii():
                    _fail(
                        MediumCatalogErrorCode.INVALID_TYPE,
                        "object keys must be ASCII strings",
                        path=path,
                    )
                visit(child, f"{path}.{key}")
            return
        _fail(
            MediumCatalogErrorCode.INVALID_TYPE,
            "value is outside the exact JSON domain",
            path=path,
        )

    visit(value, "$")
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_float(_value: str) -> NoReturn:
    _fail(MediumCatalogErrorCode.FLOAT_FORBIDDEN, "floats are forbidden")


def _reject_constant(_value: str) -> NoReturn:
    _fail(MediumCatalogErrorCode.FLOAT_FORBIDDEN, "non-finite values are forbidden")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(
                MediumCatalogErrorCode.DUPLICATE_PROPERTY,
                f"duplicate property {key!r}",
            )
        result[key] = value
    return result


def parse_json_without_duplicates(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        if raw.startswith(b"\xef\xbb\xbf"):
            _fail(MediumCatalogErrorCode.INVALID_JSON, "BOM is forbidden")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail(MediumCatalogErrorCode.INVALID_UNICODE, "invalid UTF-8")
    elif isinstance(raw, str):
        text = raw
        if text.startswith("\ufeff"):
            _fail(MediumCatalogErrorCode.INVALID_JSON, "BOM is forbidden")
    else:
        _fail(MediumCatalogErrorCode.INVALID_TYPE, "input must be str or bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except MediumCatalogValidationError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MediumCatalogValidationError(
            MediumCatalogErrorCode.INVALID_JSON, "malformed JSON"
        ) from exc
    if type(value) is not dict:
        _fail(MediumCatalogErrorCode.INVALID_TYPE, "root must be an object")
    _canonical_json(value)
    return value


class MediumIdentityKind(str, Enum):
    CHEMICAL_SUBSTANCE = "chemical_substance"
    DEFINED_MIXTURE = "defined_mixture"
    FLUID_CLASS = "fluid_class"
    TRADE_NAME = "trade_name"
    PROCESS_MEDIUM = "process_medium"
    ADDITIVE_SYSTEM = "additive_system"


class MediumRelationshipKind(str, Enum):
    CO_CONTACT = "co_contact"
    MIXTURE = "mixture"
    SEQUENTIAL_CONTACT = "sequential_contact"
    ALTERNATIVE = "alternative"


class MediumClassificationAuthority(str, Enum):
    CATALOG_EVIDENCE = "catalog_evidence"
    USER_CONFIRMATION = "user_confirmation"


def derive_media_id(canonical_name: str, identity_kind: MediumIdentityKind) -> str:
    _text(canonical_name, path="$.canonical_name")
    if type(identity_kind) is not MediumIdentityKind:
        _fail(
            MediumCatalogErrorCode.INVALID_TYPE,
            "invalid identity_kind",
            path="$.identity_kind",
        )
    payload = {
        "canonical_name": canonical_name,
        "identity_kind": identity_kind.value,
    }
    return (
        f"med_{hashlib.sha256(MEDIA_ID_DOMAIN + _canonical_json(payload)).hexdigest()}"
    )


@dataclass(frozen=True, slots=True)
class MediumCatalogEntryV1:
    media_id: str
    canonical_name: str
    identity_kind: MediumIdentityKind
    aliases: tuple[str, ...]
    evidence_review_snapshot_id: str
    evidence_review_content_sha256: str
    claim_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(
            self.media_id,
            _MEDIA_ID_RE,
            path="$.entry.media_id",
            message="media_id must match med_<64 lowercase hex>",
        )
        _text(self.canonical_name, path="$.entry.canonical_name")
        if type(self.identity_kind) is not MediumIdentityKind:
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "invalid identity_kind",
                path="$.entry.identity_kind",
            )
        if self.media_id != derive_media_id(self.canonical_name, self.identity_kind):
            _fail(
                MediumCatalogErrorCode.INVALID_ID,
                "media_id must be derived from canonical identity",
                path="$.entry.media_id",
            )
        if type(self.aliases) is not tuple:
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "aliases must be a tuple",
                path="$.entry.aliases",
            )
        for index, alias in enumerate(self.aliases):
            _text(alias, path=f"$.entry.aliases[{index}]")
        expected_aliases = tuple(
            sorted(set(self.aliases), key=lambda value: value.encode("utf-8"))
        )
        if self.aliases != expected_aliases or self.canonical_name in self.aliases:
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "aliases must be unique, ordered, and exclude canonical_name",
                path="$.entry.aliases",
            )
        _identifier(
            self.evidence_review_snapshot_id,
            _REVIEW_SNAPSHOT_ID_RE,
            path="$.entry.evidence_review_snapshot_id",
            message="invalid evidence review snapshot ID",
        )
        _identifier(
            self.evidence_review_content_sha256,
            _SHA256_RE,
            path="$.entry.evidence_review_content_sha256",
            message="invalid evidence review content hash",
        )
        if type(self.claim_refs) is not tuple or not self.claim_refs:
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "claim_refs must be a non-empty tuple",
                path="$.entry.claim_refs",
            )
        for index, claim_ref in enumerate(self.claim_refs):
            _identifier(
                claim_ref,
                _CLAIM_REF_RE,
                path=f"$.entry.claim_refs[{index}]",
                message="invalid claim_ref",
            )
        if self.claim_refs != tuple(sorted(set(self.claim_refs))):
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "claim_refs must be unique and ordered",
                path="$.entry.claim_refs",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "aliases": list(self.aliases),
            "canonical_name": self.canonical_name,
            "claim_refs": list(self.claim_refs),
            "evidence_review_content_sha256": self.evidence_review_content_sha256,
            "evidence_review_snapshot_id": self.evidence_review_snapshot_id,
            "identity_kind": self.identity_kind.value,
            "media_id": self.media_id,
        }

    @property
    def entry_sha256(self) -> str:
        return hashlib.sha256(
            ENTRY_HASH_DOMAIN + _canonical_json(self.to_dict())
        ).hexdigest()

    @property
    def identity_assertion_ref(self) -> str:
        """Bind reviewed Evidence to the exact identity and alias assertion."""

        identity = {
            "aliases": list(self.aliases),
            "canonical_name": self.canonical_name,
            "identity_kind": self.identity_kind.value,
            "media_id": self.media_id,
        }
        digest = hashlib.sha256(
            IDENTITY_ASSERTION_HASH_DOMAIN + _canonical_json(identity)
        ).hexdigest()
        return f"med-norm-identity-sha256:{digest}"


@dataclass(frozen=True, slots=True)
class MediumCatalogPayloadV1:
    domain_pack_id: str
    entries: tuple[MediumCatalogEntryV1, ...]
    media_catalog_schema_version: int = MEDIA_CATALOG_SCHEMA_VERSION
    canonicalization_version: int = CANONICALIZATION_VERSION
    med_norm_contract_version: str = MED_NORM_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.media_catalog_schema_version) is not int
            or self.media_catalog_schema_version != MEDIA_CATALOG_SCHEMA_VERSION
            or type(self.canonicalization_version) is not int
            or self.canonicalization_version != CANONICALIZATION_VERSION
            or self.med_norm_contract_version != MED_NORM_CONTRACT_VERSION
        ):
            _fail(MediumCatalogErrorCode.UNKNOWN_SCHEMA, "unsupported catalog contract")
        _identifier(
            self.domain_pack_id,
            _DOMAIN_PACK_ID_RE,
            path="$.domain_pack_id",
            message="invalid domain_pack_id",
        )
        if type(self.entries) is not tuple or any(
            type(entry) is not MediumCatalogEntryV1 for entry in self.entries
        ):
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "entries must be a typed tuple",
                path="$.entries",
            )
        media_ids = tuple(entry.media_id for entry in self.entries)
        if media_ids != tuple(sorted(set(media_ids))):
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "entries must have unique ordered media IDs",
                path="$.entries",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": self.canonicalization_version,
            "domain_pack_id": self.domain_pack_id,
            "entries": [entry.to_dict() for entry in self.entries],
            "med_norm_contract_version": self.med_norm_contract_version,
            "media_catalog_schema_version": self.media_catalog_schema_version,
        }

    def entry(self, media_id: str) -> MediumCatalogEntryV1 | None:
        return next((item for item in self.entries if item.media_id == media_id), None)


def parse_catalog_payload(raw: str | bytes) -> MediumCatalogPayloadV1:
    value = parse_json_without_duplicates(raw)
    _exact_fields(value, _TOP_LEVEL_FIELDS, path="$")
    _version(
        value["media_catalog_schema_version"],
        MEDIA_CATALOG_SCHEMA_VERSION,
        path="$.media_catalog_schema_version",
    )
    _version(
        value["canonicalization_version"],
        CANONICALIZATION_VERSION,
        path="$.canonicalization_version",
    )
    if value["med_norm_contract_version"] != MED_NORM_CONTRACT_VERSION:
        _fail(
            MediumCatalogErrorCode.UNKNOWN_SCHEMA,
            "unsupported MED-NORM contract",
            path="$.med_norm_contract_version",
        )
    if type(value["entries"]) is not list:
        _fail(
            MediumCatalogErrorCode.INVALID_TYPE,
            "entries must be an array",
            path="$.entries",
        )
    entries: list[MediumCatalogEntryV1] = []
    for index, item in enumerate(value["entries"]):
        path = f"$.entries[{index}]"
        if type(item) is not dict:
            _fail(MediumCatalogErrorCode.INVALID_TYPE, "expected object", path=path)
        _exact_fields(item, _ENTRY_FIELDS, path=path)
        if type(item["aliases"]) is not list or type(item["claim_refs"]) is not list:
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "aliases and claim_refs must be arrays",
                path=path,
            )
        try:
            identity_kind = MediumIdentityKind(item["identity_kind"])
        except (TypeError, ValueError):
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "unknown identity_kind",
                path=f"{path}.identity_kind",
            )
        entries.append(
            MediumCatalogEntryV1(
                media_id=item["media_id"],
                canonical_name=item["canonical_name"],
                identity_kind=identity_kind,
                aliases=tuple(item["aliases"]),
                evidence_review_snapshot_id=item["evidence_review_snapshot_id"],
                evidence_review_content_sha256=item["evidence_review_content_sha256"],
                claim_refs=tuple(item["claim_refs"]),
            )
        )
    return MediumCatalogPayloadV1(
        domain_pack_id=value["domain_pack_id"], entries=tuple(entries)
    )


@dataclass(frozen=True, slots=True)
class MediumCatalogSnapshotV1:
    catalog_id: str
    payload: MediumCatalogPayloadV1
    canonical_bytes: bytes
    content_sha256: str
    snapshot_id: str

    @classmethod
    def from_json(cls, catalog_id: str, raw: str | bytes) -> "MediumCatalogSnapshotV1":
        _identifier(
            catalog_id,
            _CATALOG_ID_RE,
            path="$.catalog_id",
            message="catalog_id must match mcf_<32 lowercase hex>",
        )
        payload = parse_catalog_payload(raw)
        canonical = _canonical_json(payload.to_dict())
        content_hash = hashlib.sha256(CONTENT_HASH_DOMAIN + canonical).hexdigest()
        snapshot_hash = hashlib.sha256(
            SNAPSHOT_ID_DOMAIN
            + catalog_id.encode("ascii")
            + b"\x00"
            + content_hash.encode("ascii")
        ).hexdigest()
        return cls(
            catalog_id=catalog_id,
            payload=payload,
            canonical_bytes=canonical,
            content_sha256=content_hash,
            snapshot_id=f"mcs_{snapshot_hash}",
        )


@dataclass(frozen=True, slots=True)
class CatalogEvidenceProvenanceV1:
    catalog_snapshot_id: str
    catalog_content_sha256: str
    media_id: str
    entry_sha256: str
    evidence_review_snapshot_id: str
    evidence_review_content_sha256: str
    claim_refs: tuple[str, ...]
    authority: MediumClassificationAuthority = (
        MediumClassificationAuthority.CATALOG_EVIDENCE
    )

    def __post_init__(self) -> None:
        if self.authority is not MediumClassificationAuthority.CATALOG_EVIDENCE:
            _fail(
                MediumCatalogErrorCode.INVALID_CONSTANT,
                "catalog provenance authority is fixed",
            )
        for value, pattern, path in (
            (self.catalog_snapshot_id, _SNAPSHOT_ID_RE, "$.catalog_snapshot_id"),
            (self.catalog_content_sha256, _SHA256_RE, "$.catalog_content_sha256"),
            (self.media_id, _MEDIA_ID_RE, "$.media_id"),
            (self.entry_sha256, _SHA256_RE, "$.entry_sha256"),
            (
                self.evidence_review_snapshot_id,
                _REVIEW_SNAPSHOT_ID_RE,
                "$.evidence_review_snapshot_id",
            ),
            (
                self.evidence_review_content_sha256,
                _SHA256_RE,
                "$.evidence_review_content_sha256",
            ),
        ):
            _identifier(value, pattern, path=path, message="invalid provenance ID")
        if type(self.claim_refs) is not tuple or not self.claim_refs:
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "provenance claim_refs must be non-empty",
            )
        if self.claim_refs != tuple(sorted(set(self.claim_refs))):
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "provenance claim_refs must be unique and ordered",
            )
        for claim_ref in self.claim_refs:
            _identifier(
                claim_ref,
                _CLAIM_REF_RE,
                path="$.claim_refs",
                message="invalid claim_ref",
            )


@dataclass(frozen=True, slots=True)
class UserConfirmationProvenanceV1:
    catalog: CatalogEvidenceProvenanceV1
    confirmation_ref: str
    tenant_ref_hmac: str
    subject_ref_hmac: str
    hmac_key_id: str
    authority: MediumClassificationAuthority = (
        MediumClassificationAuthority.USER_CONFIRMATION
    )

    def __post_init__(self) -> None:
        if type(self.catalog) is not CatalogEvidenceProvenanceV1:
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "user confirmation requires exact catalog provenance",
            )
        if self.authority is not MediumClassificationAuthority.USER_CONFIRMATION:
            _fail(
                MediumCatalogErrorCode.INVALID_CONSTANT,
                "confirmation authority is fixed",
            )
        _identifier(
            self.confirmation_ref,
            _CONFIRMATION_REF_RE,
            path="$.confirmation_ref",
            message="invalid confirmation_ref",
        )
        for field, value in (
            ("tenant_ref_hmac", self.tenant_ref_hmac),
            ("subject_ref_hmac", self.subject_ref_hmac),
        ):
            _identifier(value, _HMAC_RE, path=f"$.{field}", message="invalid HMAC")
        _identifier(
            self.hmac_key_id,
            _STABLE_ID_RE,
            path="$.hmac_key_id",
            message="invalid HMAC key ID",
        )


ClassificationProvenanceV1 = CatalogEvidenceProvenanceV1 | UserConfirmationProvenanceV1


@dataclass(frozen=True, slots=True)
class CanonicalMediumComponentV1:
    component_ref: str
    media_id: str
    provenance: ClassificationProvenanceV1

    def __post_init__(self) -> None:
        _identifier(
            self.component_ref,
            _COMPONENT_REF_RE,
            path="$.component_ref",
            message="invalid component_ref",
        )
        _identifier(
            self.media_id,
            _MEDIA_ID_RE,
            path="$.media_id",
            message="invalid media_id",
        )
        if type(self.provenance) not in {
            CatalogEvidenceProvenanceV1,
            UserConfirmationProvenanceV1,
        }:
            _fail(
                MediumCatalogErrorCode.INVALID_TYPE,
                "component requires catalog or user-confirmation provenance",
            )
        catalog = (
            self.provenance.catalog
            if isinstance(self.provenance, UserConfirmationProvenanceV1)
            else self.provenance
        )
        if catalog.media_id != self.media_id:
            _fail(
                MediumCatalogErrorCode.DANGLING_REF,
                "component media_id differs from provenance",
            )


@dataclass(frozen=True, slots=True)
class MediumRelationshipV1:
    kind: MediumRelationshipKind
    left_component_ref: str
    right_component_ref: str

    def __post_init__(self) -> None:
        if type(self.kind) is not MediumRelationshipKind:
            _fail(MediumCatalogErrorCode.INVALID_TYPE, "invalid relationship kind")
        for field, value in (
            ("left_component_ref", self.left_component_ref),
            ("right_component_ref", self.right_component_ref),
        ):
            _identifier(
                value,
                _COMPONENT_REF_RE,
                path=f"$.{field}",
                message="invalid component_ref",
            )
        if self.left_component_ref == self.right_component_ref:
            _fail(MediumCatalogErrorCode.INVALID_ID, "self relationship is forbidden")
        if (
            self.kind is not MediumRelationshipKind.SEQUENTIAL_CONTACT
            and self.left_component_ref > self.right_component_ref
        ):
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "symmetric relationship endpoints must be ordered",
            )

    def key(self) -> tuple[str, str, str]:
        return (self.kind.value, self.left_component_ref, self.right_component_ref)


@dataclass(frozen=True, slots=True)
class NormalizedMediumInputV1:
    medium_state: InputResolutionState
    medium_cardinality: MediumCardinality
    relation_state: RelationState
    components: tuple[CanonicalMediumComponentV1, ...] = ()
    relationships: tuple[MediumRelationshipV1, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.medium_state, InputResolutionState):
            raise TypeError("medium_state must be InputResolutionState")
        if not isinstance(self.medium_cardinality, MediumCardinality):
            raise TypeError("medium_cardinality must be MediumCardinality")
        if not isinstance(self.relation_state, RelationState):
            raise TypeError("relation_state must be RelationState")
        if type(self.components) is not tuple or any(
            type(item) is not CanonicalMediumComponentV1 for item in self.components
        ):
            raise TypeError("components must be a typed tuple")
        if type(self.relationships) is not tuple or any(
            type(item) is not MediumRelationshipV1 for item in self.relationships
        ):
            raise TypeError("relationships must be a typed tuple")
        component_refs = tuple(item.component_ref for item in self.components)
        if component_refs != tuple(sorted(set(component_refs))):
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "components must be unique and ordered",
            )
        relation_keys = tuple(item.key() for item in self.relationships)
        if relation_keys != tuple(sorted(set(relation_keys))):
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "relationships must be unique and ordered",
            )
        refs = set(component_refs)
        if any(
            item.left_component_ref not in refs or item.right_component_ref not in refs
            for item in self.relationships
        ):
            _fail(
                MediumCatalogErrorCode.DANGLING_REF,
                "relationship references an absent component",
            )
        closed = {
            (
                InputResolutionState.MISSING,
                MediumCardinality.NONE,
                RelationState.UNDETERMINED,
            ),
            (
                InputResolutionState.UNKNOWN,
                MediumCardinality.UNKNOWN,
                RelationState.UNDETERMINED,
            ),
            (
                InputResolutionState.AMBIGUOUS,
                MediumCardinality.UNKNOWN,
                RelationState.UNDETERMINED,
            ),
            (
                InputResolutionState.KNOWN,
                MediumCardinality.SINGLE,
                RelationState.NOT_APPLICABLE,
            ),
            (
                InputResolutionState.KNOWN,
                MediumCardinality.MULTIPLE,
                RelationState.UNRESOLVED,
            ),
            (
                InputResolutionState.KNOWN,
                MediumCardinality.MULTIPLE,
                RelationState.RESOLVED,
            ),
        }
        state = (self.medium_state, self.medium_cardinality, self.relation_state)
        if state not in closed:
            _fail(MediumCatalogErrorCode.INVALID_CONSTANT, "invalid state combination")
        if self.medium_state is not InputResolutionState.KNOWN:
            if self.components or self.relationships:
                _fail(
                    MediumCatalogErrorCode.INVALID_CONSTANT,
                    "unresolved input cannot carry canonical components",
                )
            return
        expected_count = 1 if self.medium_cardinality is MediumCardinality.SINGLE else 2
        if len(self.components) < expected_count:
            _fail(
                MediumCatalogErrorCode.INVALID_CONSTANT,
                "known cardinality does not match component count",
            )
        if self.medium_cardinality is MediumCardinality.SINGLE:
            if len(self.components) != 1 or self.relationships:
                _fail(
                    MediumCatalogErrorCode.INVALID_CONSTANT,
                    "single medium requires one component and no relationships",
                )
            return
        if self.relation_state is RelationState.UNRESOLVED:
            if self.relationships:
                _fail(
                    MediumCatalogErrorCode.INVALID_CONSTANT,
                    "unresolved relation cannot carry asserted relationships",
                )
            return
        pairs = {
            frozenset((item.left_component_ref, item.right_component_ref))
            for item in self.relationships
        }
        expected_pairs = {
            frozenset((left, right))
            for index, left in enumerate(component_refs)
            for right in component_refs[index + 1 :]
        }
        if pairs != expected_pairs or len(self.relationships) != len(expected_pairs):
            _fail(
                MediumCatalogErrorCode.RELATION_INCOMPLETE,
                "resolved multiple media require exactly one relationship per pair",
            )

    @property
    def evaluable(self) -> bool:
        return self.medium_state is InputResolutionState.KNOWN and (
            self.medium_cardinality is MediumCardinality.SINGLE
            or self.relation_state is RelationState.RESOLVED
        )


@dataclass(frozen=True, slots=True)
class MediumClassificationCandidateV1:
    candidate_media_ids: tuple[str, ...]
    source: str = "llm_candidate"
    authoritative: bool = False

    def __post_init__(self) -> None:
        if self.source != "llm_candidate" or self.authoritative is not False:
            _fail(
                MediumCatalogErrorCode.INVALID_CONSTANT,
                "LLM candidates are permanently non-authoritative",
            )
        if self.candidate_media_ids != tuple(sorted(set(self.candidate_media_ids))):
            _fail(
                MediumCatalogErrorCode.NON_CANONICAL_ORDER,
                "candidate IDs must be unique and ordered",
            )
        for media_id in self.candidate_media_ids:
            _identifier(
                media_id,
                _MEDIA_ID_RE,
                path="$.candidate_media_ids",
                message="invalid media_id",
            )


def _catalog_provenance(
    snapshot: MediumCatalogSnapshotV1, entry: MediumCatalogEntryV1
) -> CatalogEvidenceProvenanceV1:
    return CatalogEvidenceProvenanceV1(
        catalog_snapshot_id=snapshot.snapshot_id,
        catalog_content_sha256=snapshot.content_sha256,
        media_id=entry.media_id,
        entry_sha256=entry.entry_sha256,
        evidence_review_snapshot_id=entry.evidence_review_snapshot_id,
        evidence_review_content_sha256=entry.evidence_review_content_sha256,
        claim_refs=entry.claim_refs,
    )


def derive_component_ref(
    catalog_snapshot_id: str, media_id: str, *, occurrence: int = 0
) -> str:
    _identifier(
        catalog_snapshot_id,
        _SNAPSHOT_ID_RE,
        path="$.catalog_snapshot_id",
        message="invalid catalog snapshot ID",
    )
    _identifier(
        media_id,
        _MEDIA_ID_RE,
        path="$.media_id",
        message="invalid media_id",
    )
    if type(occurrence) is not int or occurrence < 0:
        raise ValueError("occurrence must be a non-negative integer")
    digest = hashlib.sha256(
        b"sealai.medium-component.v1\x00"
        + catalog_snapshot_id.encode("ascii")
        + b"\x00"
        + media_id.encode("ascii")
        + b"\x00"
        + str(occurrence).encode("ascii")
    ).hexdigest()
    return f"mcmp_{digest[:32]}"


def resolve_exact_catalog_values(
    observed_values: tuple[str, ...],
    *,
    snapshot: MediumCatalogSnapshotV1,
    component_refs: tuple[str, ...] = (),
    relationships: tuple[MediumRelationshipV1, ...] = (),
) -> NormalizedMediumInputV1:
    """Resolve whole values only; punctuation and conjunctions are never split."""

    if type(observed_values) is not tuple:
        raise TypeError("observed_values must be a tuple")
    if not observed_values:
        if component_refs or relationships:
            raise ValueError("missing input cannot carry components or relationships")
        return NormalizedMediumInputV1(
            InputResolutionState.MISSING,
            MediumCardinality.NONE,
            RelationState.UNDETERMINED,
        )
    if component_refs and len(component_refs) != len(observed_values):
        raise ValueError("component_refs must align with observed values")
    matched_entries: list[MediumCatalogEntryV1] = []
    ambiguous = False
    for index, observed in enumerate(observed_values):
        _text(observed, path=f"$.observed_values[{index}]")
        matches = [
            entry
            for entry in snapshot.payload.entries
            if observed == entry.canonical_name or observed in entry.aliases
        ]
        if not matches:
            return NormalizedMediumInputV1(
                InputResolutionState.UNKNOWN,
                MediumCardinality.UNKNOWN,
                RelationState.UNDETERMINED,
            )
        if len(matches) > 1:
            ambiguous = True
            continue
        matched_entries.append(matches[0])
    if ambiguous:
        return NormalizedMediumInputV1(
            InputResolutionState.AMBIGUOUS,
            MediumCardinality.UNKNOWN,
            RelationState.UNDETERMINED,
        )
    if component_refs:
        refs = component_refs
    else:
        occurrences: dict[str, int] = {}
        generated: list[str] = []
        for entry in matched_entries:
            occurrence = occurrences.get(entry.media_id, 0)
            generated.append(
                derive_component_ref(
                    snapshot.snapshot_id, entry.media_id, occurrence=occurrence
                )
            )
            occurrences[entry.media_id] = occurrence + 1
        refs = tuple(generated)
    components: list[CanonicalMediumComponentV1] = []
    for index, entry in enumerate(matched_entries):
        components.append(
            CanonicalMediumComponentV1(
                component_ref=refs[index],
                media_id=entry.media_id,
                provenance=_catalog_provenance(snapshot, entry),
            )
        )
    ordered_components = tuple(sorted(components, key=lambda item: item.component_ref))
    if len(ordered_components) == 1:
        if relationships:
            raise ValueError("single medium cannot carry relationships")
        return NormalizedMediumInputV1(
            InputResolutionState.KNOWN,
            MediumCardinality.SINGLE,
            RelationState.NOT_APPLICABLE,
            ordered_components,
        )
    relation_state = (
        RelationState.RESOLVED if relationships else RelationState.UNRESOLVED
    )
    return NormalizedMediumInputV1(
        InputResolutionState.KNOWN,
        MediumCardinality.MULTIPLE,
        relation_state,
        ordered_components,
        tuple(sorted(relationships, key=lambda item: item.key())),
    )


@dataclass(frozen=True, slots=True)
class AttributedMaterialMatchV1:
    component_ref: str
    media_id: str
    match: MaterialConstraintMatch

    def __post_init__(self) -> None:
        _identifier(
            self.component_ref,
            _COMPONENT_REF_RE,
            path="$.component_ref",
            message="invalid component_ref",
        )
        _identifier(
            self.media_id,
            _MEDIA_ID_RE,
            path="$.media_id",
            message="invalid media_id",
        )
        if type(self.match) is not MaterialConstraintMatch:
            raise TypeError("attributed match requires MaterialConstraintMatch")

    @property
    def decisive_ref(self) -> str:
        return f"{self.component_ref}:{self.match.rule_ref}"


def _attributed_sort_key(
    item: AttributedMaterialMatchV1,
) -> tuple[int, str, str, str, str, str]:
    base = material_constraint_match_sort_key(item.match)
    return (base[0], item.component_ref, item.media_id, *base[1:])


@dataclass(frozen=True, slots=True)
class NormalizedMaterialEvaluationV1:
    medium_input: NormalizedMediumInputV1
    evaluation_state: EvaluationState
    component_results: tuple[tuple[str, str, MaterialConstraintResult], ...] = ()
    verdict: MaterialConstraintVerdict | None = None
    matches: tuple[AttributedMaterialMatchV1, ...] = ()
    decisive_ref: str | None = None
    blockers: tuple[MaterialConstraintBlocker, ...] = ()

    def __post_init__(self) -> None:
        if type(self.medium_input) is not NormalizedMediumInputV1:
            raise TypeError("medium_input must be NormalizedMediumInputV1")
        if not isinstance(self.evaluation_state, EvaluationState):
            raise TypeError("evaluation_state must be EvaluationState")
        if type(self.component_results) is not tuple:
            raise TypeError("component_results must be a tuple")
        normalized_results: list[tuple[str, str, MaterialConstraintResult]] = []
        for item in self.component_results:
            if (
                type(item) is not tuple
                or len(item) != 3
                or type(item[2]) is not MaterialConstraintResult
            ):
                raise TypeError("component result must be (ref, media_id, result)")
            component_ref, media_id, result = item
            _identifier(
                component_ref,
                _COMPONENT_REF_RE,
                path="$.component_results.component_ref",
                message="invalid component_ref",
            )
            _identifier(
                media_id,
                _MEDIA_ID_RE,
                path="$.component_results.media_id",
                message="invalid media_id",
            )
            if (
                result.medium_state is not InputResolutionState.KNOWN
                or result.medium_cardinality is not MediumCardinality.SINGLE
                or result.relation_state is not RelationState.NOT_APPLICABLE
            ):
                raise ValueError("component result must represent one canonical medium")
            normalized_results.append((component_ref, media_id, result))
        expected_results = tuple(
            sorted(normalized_results, key=lambda item: (item[0], item[1]))
        )
        if self.component_results != expected_results or len(
            {item[0] for item in self.component_results}
        ) != len(self.component_results):
            raise ValueError("component results must be unique and ordered")
        expected_components = tuple(
            (item.component_ref, item.media_id) for item in self.medium_input.components
        )
        actual_components = tuple((item[0], item[1]) for item in self.component_results)
        if self.medium_input.evaluable and actual_components != expected_components:
            raise ValueError("component results must cover every canonical component")
        if not self.medium_input.evaluable and self.component_results:
            raise ValueError("unevaluable medium input cannot carry component results")
        if type(self.matches) is not tuple or any(
            type(item) is not AttributedMaterialMatchV1 for item in self.matches
        ):
            raise TypeError("matches must be attributed material matches")
        if type(self.blockers) is not tuple or any(
            not isinstance(item, MaterialConstraintBlocker) for item in self.blockers
        ):
            raise TypeError("blockers must be MaterialConstraintBlocker values")
        if self.positive_statement_allowed is not False:
            raise ValueError("positive material statements are forbidden")
        component_states = tuple(
            item[2].evaluation_state for item in self.component_results
        )
        if self.evaluation_state is EvaluationState.EVALUATED:
            if (
                self.verdict is None
                or not self.matches
                or self.decisive_ref is None
                or self.blockers
            ):
                raise ValueError("evaluated normalized result is incomplete")
            if any(
                state is not EvaluationState.EVALUATED for state in component_states
            ):
                raise ValueError(
                    "evaluated aggregate requires every component evaluated"
                )
            ordered = tuple(sorted(self.matches, key=_attributed_sort_key))
            if self.matches != ordered or self.verdict is not ordered[0].match.verdict:
                raise ValueError("normalized result must use canonical precedence")
            if self.decisive_ref != ordered[0].decisive_ref:
                raise ValueError("decisive_ref must identify the strongest attribution")
            expected_matches = tuple(
                sorted(
                    (
                        AttributedMaterialMatchV1(component_ref, media_id, match)
                        for component_ref, media_id, result in self.component_results
                        for match in result.matches
                    ),
                    key=_attributed_sort_key,
                )
            )
            if self.matches != expected_matches:
                raise ValueError("normalized result must retain every attributed match")
            return
        if self.verdict is not None or self.matches or self.decisive_ref is not None:
            raise ValueError("non-evaluated normalized result cannot carry a verdict")
        if self.evaluation_state is EvaluationState.NO_RULE_DATA and (
            not component_states
            or EvaluationState.NO_RULE_DATA not in component_states
            or EvaluationState.BLOCKED in component_states
            or self.blockers
        ):
            raise ValueError("no_rule_data aggregate has inconsistent components")
        if (
            self.evaluation_state is EvaluationState.BLOCKED
            and self.medium_input.evaluable
            and EvaluationState.BLOCKED not in component_states
        ):
            raise ValueError("blocked aggregate requires a blocked component")

    @property
    def positive_statement_allowed(self) -> bool:
        return False

    @property
    def conditions(self) -> tuple[AttributedMaterialMatchV1, ...]:
        return tuple(
            item
            for item in self.matches
            if item.match.verdict is MaterialConstraintVerdict.BEDINGT
        )


def evaluate_normalized_media(
    medium_input: NormalizedMediumInputV1,
    *,
    evaluate_component: Callable[
        [CanonicalMediumComponentV1], MaterialConstraintResult
    ],
) -> NormalizedMaterialEvaluationV1:
    """Evaluate every canonical component separately and aggregate fail-closed."""

    if not medium_input.evaluable:
        blocker = MaterialConstraintBlocker(
            MaterialConstraintBlockerKind.MEDIUM_RELATION,
            (
                f"medium-input:{medium_input.medium_state.value}"
                if medium_input.medium_state is not InputResolutionState.KNOWN
                else f"medium-relation:{medium_input.relation_state.value}"
            ),
        )
        return NormalizedMaterialEvaluationV1(
            medium_input,
            EvaluationState.BLOCKED,
            blockers=(blocker,),
        )
    results: list[tuple[str, str, MaterialConstraintResult]] = []
    attributed: list[AttributedMaterialMatchV1] = []
    for component in medium_input.components:
        result = evaluate_component(component)
        if not isinstance(result, MaterialConstraintResult):
            raise TypeError("component evaluator must return MaterialConstraintResult")
        if (
            result.medium_state is not InputResolutionState.KNOWN
            or result.medium_cardinality is not MediumCardinality.SINGLE
            or result.relation_state is not RelationState.NOT_APPLICABLE
        ):
            raise ValueError("component result does not represent one canonical medium")
        results.append((component.component_ref, component.media_id, result))
        attributed.extend(
            AttributedMaterialMatchV1(
                component.component_ref, component.media_id, match
            )
            for match in result.matches
        )
    ordered_results = tuple(sorted(results, key=lambda item: (item[0], item[1])))
    if any(item[2].evaluation_state is EvaluationState.BLOCKED for item in results):
        return NormalizedMaterialEvaluationV1(
            medium_input,
            EvaluationState.BLOCKED,
            component_results=ordered_results,
            blockers=(
                MaterialConstraintBlocker(
                    MaterialConstraintBlockerKind.MEDIUM_RELATION,
                    "medium-component:evaluation-blocked",
                ),
            ),
        )
    if any(
        item[2].evaluation_state is EvaluationState.NO_RULE_DATA for item in results
    ):
        return NormalizedMaterialEvaluationV1(
            medium_input,
            EvaluationState.NO_RULE_DATA,
            component_results=ordered_results,
        )
    ordered_matches = tuple(sorted(attributed, key=_attributed_sort_key))
    if not ordered_matches:
        return NormalizedMaterialEvaluationV1(
            medium_input,
            EvaluationState.NO_RULE_DATA,
            component_results=ordered_results,
        )
    return NormalizedMaterialEvaluationV1(
        medium_input,
        EvaluationState.EVALUATED,
        component_results=ordered_results,
        verdict=ordered_matches[0].match.verdict,
        matches=ordered_matches,
        decisive_ref=ordered_matches[0].decisive_ref,
    )


def compute_validation_sha256(snapshot: MediumCatalogSnapshotV1) -> str:
    payload = {
        "content_sha256": snapshot.content_sha256,
        "contract_version": MED_NORM_CONTRACT_VERSION,
        "snapshot_id": snapshot.snapshot_id,
        "state": "valid",
    }
    return hashlib.sha256(VALIDATION_HASH_DOMAIN + _canonical_json(payload)).hexdigest()


def compute_audit_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(AUDIT_HASH_DOMAIN + _canonical_json(payload)).hexdigest()


__all__ = [
    "CANONICALIZATION_VERSION",
    "MEDIA_CATALOG_SCHEMA_VERSION",
    "MED_NORM_CONTRACT_VERSION",
    "AttributedMaterialMatchV1",
    "CanonicalMediumComponentV1",
    "CatalogEvidenceProvenanceV1",
    "MediumCatalogEntryV1",
    "MediumCatalogErrorCode",
    "MediumCatalogIntegrityError",
    "MediumCatalogPayloadV1",
    "MediumCatalogSnapshotV1",
    "MediumCatalogValidationError",
    "MediumClassificationAuthority",
    "MediumClassificationCandidateV1",
    "MediumIdentityKind",
    "MediumRelationshipKind",
    "MediumRelationshipV1",
    "NormalizedMaterialEvaluationV1",
    "NormalizedMediumInputV1",
    "UserConfirmationProvenanceV1",
    "compute_audit_sha256",
    "compute_validation_sha256",
    "derive_component_ref",
    "derive_media_id",
    "evaluate_normalized_media",
    "parse_catalog_payload",
    "parse_json_without_duplicates",
    "resolve_exact_catalog_values",
]
