"""MAT-EVID-01A.v2 typed, immutable evidence-manifest contract.

Version 2 is additive and intentionally separate from MAT-EVID-01A.v1.  It
supports exactly two homogeneous manifest purposes: material-rule evidence and
media-identity evidence.  It creates no facts, review state, runtime authority,
positive statement, activation, or deployment surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any, NoReturn, TypeAlias


EVIDENCE_MANIFEST_SCHEMA_VERSION_V2 = 2
CANONICALIZATION_VERSION_V2 = 2
MAT_EVID_CONTRACT_VERSION_V2 = "MAT-EVID-01A.v2"
HASH_ALGORITHM_V2 = "sha256-v2"

SOURCE_REF_DOMAIN_V2 = b"sealai.material-evidence.source.v2\x00"
CLAIM_REF_DOMAIN_V2 = b"sealai.material-evidence.claim.v2\x00"
CONTENT_HASH_DOMAIN_V2 = b"sealai.material-evidence.content.v2\x00"
SNAPSHOT_ID_DOMAIN_V2 = b"sealai.material-evidence.snapshot.v2\x00"
VALIDATION_HASH_DOMAIN_V2 = b"sealai.material-evidence.validation.v2\x00"
AUDIT_HASH_DOMAIN_V2 = b"sealai.material-evidence.audit.v2\x00"

_MANIFEST_ID_RE = re.compile(r"^mef_[0-9a-f]{32}$", re.ASCII)
_SNAPSHOT_ID_RE = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_RULESET_SNAPSHOT_ID_RE = re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII)
_SOURCE_REF_RE = re.compile(r"^msr_[0-9a-f]{64}$", re.ASCII)
_CLAIM_REF_RE = re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII)
_RULE_REF_RE = re.compile(r"^MR-[A-Z0-9][A-Z0-9._:-]{0,124}$", re.ASCII)
_DOMAIN_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", re.ASCII)
_MEDIA_REF_RE = re.compile(r"^med_[0-9a-f]{64}$", re.ASCII)
_IDENTITY_ASSERTION_REF_RE = re.compile(
    r"^med-norm-identity-sha256:[0-9a-f]{64}$", re.ASCII
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "evidence_manifest_schema_version",
        "canonicalization_version",
        "mat_evid_contract_version",
        "domain_pack_id",
        "target",
        "sources",
        "claims",
        "rule_claim_bindings",
    }
)
_SOURCE_FIELDS = frozenset(
    {
        "source_ref",
        "document_id",
        "document_revision",
        "publication_edition",
        "content_sha256",
    }
)
_CLAIM_FIELDS = frozenset({"claim_ref", "claim_text", "scope", "source_refs"})
_MATERIAL_TARGET_FIELDS = frozenset({"target_type", "ruleset_snapshot_id"})
_MEDIA_TARGET_FIELDS = frozenset({"target_type", "media_ref"})
_MATERIAL_SCOPE_FIELDS = frozenset({"scope_type", "materials", "media", "conditions"})
_MEDIA_SCOPE_FIELDS = frozenset({"scope_type", "media_ref", "identity_assertion_ref"})
_BINDING_FIELDS = frozenset({"rule_ref", "claim_ref"})


class EvidenceScopeTypeV2(str, Enum):
    MATERIAL_RELATION = "material_relation"
    MEDIA_IDENTITY = "media_identity"


class MaterialEvidenceV2ErrorCode(str, Enum):
    INVALID_JSON = "MAT_EVID_V2_INVALID_JSON"
    DUPLICATE_PROPERTY = "MAT_EVID_V2_DUPLICATE_PROPERTY"
    UNKNOWN_FIELD = "MAT_EVID_V2_UNKNOWN_FIELD"
    INVALID_TYPE = "MAT_EVID_V2_INVALID_TYPE"
    INVALID_ID = "MAT_EVID_V2_INVALID_ID"
    INVALID_UNICODE = "MAT_EVID_V2_INVALID_UNICODE"
    NON_NFC = "MAT_EVID_V2_NON_NFC"
    FLOAT_FORBIDDEN = "MAT_EVID_V2_FLOAT_FORBIDDEN"
    UNKNOWN_SCHEMA = "MAT_EVID_V2_UNKNOWN_SCHEMA"
    EMPTY_COLLECTION = "MAT_EVID_V2_EMPTY_COLLECTION"
    DUPLICATE_REF = "MAT_EVID_V2_DUPLICATE_REF"
    DANGLING_REF = "MAT_EVID_V2_DANGLING_REF"
    ORPHAN_REF = "MAT_EVID_V2_ORPHAN_REF"
    NON_CANONICAL_ORDER = "MAT_EVID_V2_NON_CANONICAL_ORDER"
    CROSS_FIELD_MISMATCH = "MAT_EVID_V2_CROSS_FIELD_MISMATCH"
    HASH_MISMATCH = "MAT_EVID_V2_HASH_MISMATCH"
    SNAPSHOT_ID_MISMATCH = "MAT_EVID_V2_SNAPSHOT_ID_MISMATCH"
    DB_INTEGRITY = "MAT_EVID_V2_DB_INTEGRITY"


class MaterialEvidenceV2ValidationError(ValueError):
    def __init__(
        self,
        code: MaterialEvidenceV2ErrorCode,
        message: str,
        *,
        path: str = "$",
    ) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value} at {path}: {message}")


class MaterialEvidenceV2IntegrityError(RuntimeError):
    quarantine_candidate = True

    def __init__(self, code: MaterialEvidenceV2ErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(
    code: MaterialEvidenceV2ErrorCode, message: str, *, path: str = "$"
) -> NoReturn:
    raise MaterialEvidenceV2ValidationError(code, message, path=path)


def _dict(value: Any, *, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(MaterialEvidenceV2ErrorCode.INVALID_TYPE, "expected object", path=path)
    return value


def _list(value: Any, *, path: str) -> list[Any]:
    if type(value) is not list:
        _fail(MaterialEvidenceV2ErrorCode.INVALID_TYPE, "expected array", path=path)
    return value


def _text(value: Any, *, path: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        _fail(
            MaterialEvidenceV2ErrorCode.INVALID_TYPE,
            "expected non-whitespace string",
            path=path,
        )
    _unicode(value, path=path)
    return value


def _exact(value: dict[str, Any], expected: frozenset[str], *, path: str) -> None:
    actual = frozenset(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown or missing:
        _fail(
            MaterialEvidenceV2ErrorCode.UNKNOWN_FIELD,
            f"unknown={unknown} missing={missing}",
            path=path,
        )


def _unicode(value: Any, *, path: str) -> None:
    if type(value) is str:
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            _fail(
                MaterialEvidenceV2ErrorCode.INVALID_UNICODE,
                "string contains a non-Unicode-scalar value",
                path=path,
            )
        if unicodedata.normalize("NFC", value) != value:
            _fail(MaterialEvidenceV2ErrorCode.NON_NFC, "string must be NFC", path=path)
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _unicode(item, path=f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not key.isascii():
                _fail(
                    MaterialEvidenceV2ErrorCode.INVALID_ID,
                    "property names must be ASCII strings",
                    path=path,
                )
            _unicode(item, path=f"{path}.{key}")


def _canonical_value(value: Any, *, path: str = "$") -> None:
    if type(value) is float:
        _fail(
            MaterialEvidenceV2ErrorCode.FLOAT_FORBIDDEN,
            "floating-point values are forbidden",
            path=path,
        )
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is str:
        _unicode(value, path=path)
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _canonical_value(item, path=f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not key.isascii():
                _fail(
                    MaterialEvidenceV2ErrorCode.INVALID_ID,
                    "object keys must be ASCII strings",
                    path=path,
                )
            _canonical_value(item, path=f"{path}.{key}")
        return
    _fail(
        MaterialEvidenceV2ErrorCode.INVALID_TYPE,
        "value is outside the exact JSON domain",
        path=path,
    )


def _duplicate_free_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail(
                MaterialEvidenceV2ErrorCode.DUPLICATE_PROPERTY,
                f"duplicate property {key!r}",
            )
        value[key] = item
    return value


def _reject_float(_value: str) -> NoReturn:
    _fail(
        MaterialEvidenceV2ErrorCode.FLOAT_FORBIDDEN,
        "floating-point values are forbidden",
    )


def parse_json_v2(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        if raw.startswith(b"\xef\xbb\xbf"):
            _fail(MaterialEvidenceV2ErrorCode.INVALID_JSON, "BOM is forbidden")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail(MaterialEvidenceV2ErrorCode.INVALID_UNICODE, "invalid UTF-8")
    elif isinstance(raw, str):
        text = raw
        if text.startswith("\ufeff"):
            _fail(MaterialEvidenceV2ErrorCode.INVALID_JSON, "BOM is forbidden")
    else:
        _fail(
            MaterialEvidenceV2ErrorCode.INVALID_TYPE,
            "manifest input must be str or bytes",
        )
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_free_object,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except MaterialEvidenceV2ValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, UnicodeEncodeError) as exc:
        raise MaterialEvidenceV2ValidationError(
            MaterialEvidenceV2ErrorCode.INVALID_JSON, "malformed JSON"
        ) from exc
    root = _dict(value, path="$")
    _unicode(root, path="$")
    return root


def _canonical_json_v2(value: dict[str, Any]) -> bytes:
    _canonical_value(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaterialEvidenceV2ValidationError(
            MaterialEvidenceV2ErrorCode.INVALID_TYPE, "not canonical JSON"
        ) from exc


def _identifier(
    value: Any, pattern: re.Pattern[str], *, path: str, message: str
) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _fail(MaterialEvidenceV2ErrorCode.INVALID_ID, message, path=path)
    return value


def _version(value: Any, expected: int, *, path: str) -> int:
    if type(value) is not int:
        _fail(MaterialEvidenceV2ErrorCode.INVALID_TYPE, "expected integer", path=path)
    if value != expected:
        _fail(
            MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
            f"only version {expected} is supported",
            path=path,
        )
    return value


def _canonical_strings(value: Any, *, path: str, nonempty: bool) -> tuple[str, ...]:
    raw = _list(value, path=path)
    items = tuple(_text(item, path=f"{path}[{i}]") for i, item in enumerate(raw))
    if nonempty and not items:
        _fail(
            MaterialEvidenceV2ErrorCode.EMPTY_COLLECTION,
            "array must not be empty",
            path=path,
        )
    expected = tuple(sorted(set(items), key=lambda item: item.encode("utf-8")))
    if items != expected:
        _fail(
            MaterialEvidenceV2ErrorCode.NON_CANONICAL_ORDER,
            "array must be unique and UTF-8-byte ordered",
            path=path,
        )
    return items


def _identity(domain: bytes, payload: dict[str, Any], prefix: str) -> str:
    return (
        f"{prefix}_{hashlib.sha256(domain + _canonical_json_v2(payload)).hexdigest()}"
    )


def validate_manifest_id_v2(value: str) -> str:
    return _identifier(
        value,
        _MANIFEST_ID_RE,
        path="$.manifest_id",
        message="expected mef_<32 lowercase hex>",
    )


def validate_snapshot_id_v2(value: str) -> str:
    return _identifier(
        value,
        _SNAPSHOT_ID_RE,
        path="$.snapshot_id",
        message="expected mes_<64 lowercase hex>",
    )


def validate_domain_pack_id_v2(value: str) -> str:
    return _identifier(
        value,
        _DOMAIN_PACK_ID_RE,
        path="$.domain_pack_id",
        message="invalid domain_pack_id",
    )


@dataclass(frozen=True, slots=True)
class MaterialRelationTargetV2:
    ruleset_snapshot_id: str
    target_type: EvidenceScopeTypeV2 = EvidenceScopeTypeV2.MATERIAL_RELATION

    def __post_init__(self) -> None:
        if self.target_type is not EvidenceScopeTypeV2.MATERIAL_RELATION:
            _fail(
                MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                "invalid material target discriminator",
                path="$.target.target_type",
            )
        _identifier(
            self.ruleset_snapshot_id,
            _RULESET_SNAPSHOT_ID_RE,
            path="$.target.ruleset_snapshot_id",
            message="invalid ruleset_snapshot_id",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "ruleset_snapshot_id": self.ruleset_snapshot_id,
            "target_type": self.target_type.value,
        }


@dataclass(frozen=True, slots=True)
class MediaIdentityTargetV2:
    media_ref: str
    target_type: EvidenceScopeTypeV2 = EvidenceScopeTypeV2.MEDIA_IDENTITY

    def __post_init__(self) -> None:
        if self.target_type is not EvidenceScopeTypeV2.MEDIA_IDENTITY:
            _fail(
                MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                "invalid media target discriminator",
                path="$.target.target_type",
            )
        _identifier(
            self.media_ref,
            _MEDIA_REF_RE,
            path="$.target.media_ref",
            message="invalid media_ref",
        )

    def to_dict(self) -> dict[str, str]:
        return {"media_ref": self.media_ref, "target_type": self.target_type.value}


EvidenceManifestTargetV2: TypeAlias = MaterialRelationTargetV2 | MediaIdentityTargetV2


@dataclass(frozen=True, slots=True)
class EvidenceSourceV2:
    source_ref: str
    document_id: str
    document_revision: str
    publication_edition: str
    content_sha256: str

    def __post_init__(self) -> None:
        for name, value in (
            ("document_id", self.document_id),
            ("document_revision", self.document_revision),
            ("publication_edition", self.publication_edition),
        ):
            _text(value, path=f"$.source.{name}")
        _identifier(
            self.content_sha256,
            _SHA256_RE,
            path="$.source.content_sha256",
            message="expected lowercase SHA-256",
        )
        if self.source_ref != derive_source_ref_v2(
            document_id=self.document_id,
            document_revision=self.document_revision,
            publication_edition=self.publication_edition,
            content_sha256=self.content_sha256,
        ):
            _fail(
                MaterialEvidenceV2ErrorCode.HASH_MISMATCH,
                "source_ref does not match v2 source identity",
                path="$.source.source_ref",
            )

    def identity_dict(self) -> dict[str, str]:
        return {
            "content_sha256": self.content_sha256,
            "document_id": self.document_id,
            "document_revision": self.document_revision,
            "publication_edition": self.publication_edition,
        }

    def to_dict(self) -> dict[str, str]:
        return {"source_ref": self.source_ref, **self.identity_dict()}


def derive_source_ref_v2(
    *,
    document_id: str,
    document_revision: str,
    publication_edition: str,
    content_sha256: str,
) -> str:
    for name, value in (
        ("document_id", document_id),
        ("document_revision", document_revision),
        ("publication_edition", publication_edition),
    ):
        _text(value, path=f"$.source.{name}")
    _identifier(
        content_sha256,
        _SHA256_RE,
        path="$.source.content_sha256",
        message="expected lowercase SHA-256",
    )
    return _identity(
        SOURCE_REF_DOMAIN_V2,
        {
            "content_sha256": content_sha256,
            "document_id": document_id,
            "document_revision": document_revision,
            "publication_edition": publication_edition,
        },
        "msr",
    )


@dataclass(frozen=True, slots=True)
class MaterialRelationClaimScopeV2:
    materials: tuple[str, ...]
    media: tuple[str, ...]
    conditions: tuple[str, ...]
    scope_type: EvidenceScopeTypeV2 = EvidenceScopeTypeV2.MATERIAL_RELATION

    def __post_init__(self) -> None:
        if self.scope_type is not EvidenceScopeTypeV2.MATERIAL_RELATION:
            _fail(
                MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                "invalid material scope discriminator",
                path="$.claim.scope.scope_type",
            )
        for name, values, nonempty in (
            ("materials", self.materials, True),
            ("media", self.media, True),
            ("conditions", self.conditions, False),
        ):
            if type(values) is not tuple or any(
                type(item) is not str for item in values
            ):
                _fail(
                    MaterialEvidenceV2ErrorCode.INVALID_TYPE,
                    f"{name} must be a tuple of strings",
                    path=f"$.claim.scope.{name}",
                )
            if nonempty and not values:
                _fail(
                    MaterialEvidenceV2ErrorCode.EMPTY_COLLECTION,
                    f"{name} must not be empty",
                    path=f"$.claim.scope.{name}",
                )
            for index, item in enumerate(values):
                _text(item, path=f"$.claim.scope.{name}[{index}]")
            expected = tuple(sorted(set(values), key=lambda item: item.encode("utf-8")))
            if values != expected:
                _fail(
                    MaterialEvidenceV2ErrorCode.NON_CANONICAL_ORDER,
                    f"{name} must be unique and ordered",
                    path=f"$.claim.scope.{name}",
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conditions": list(self.conditions),
            "materials": list(self.materials),
            "media": list(self.media),
            "scope_type": self.scope_type.value,
        }


@dataclass(frozen=True, slots=True)
class MediaIdentityClaimScopeV2:
    media_ref: str
    identity_assertion_ref: str
    scope_type: EvidenceScopeTypeV2 = EvidenceScopeTypeV2.MEDIA_IDENTITY

    def __post_init__(self) -> None:
        if self.scope_type is not EvidenceScopeTypeV2.MEDIA_IDENTITY:
            _fail(
                MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                "invalid media scope discriminator",
                path="$.claim.scope.scope_type",
            )
        _identifier(
            self.media_ref,
            _MEDIA_REF_RE,
            path="$.claim.scope.media_ref",
            message="invalid media_ref",
        )
        _identifier(
            self.identity_assertion_ref,
            _IDENTITY_ASSERTION_REF_RE,
            path="$.claim.scope.identity_assertion_ref",
            message="invalid identity_assertion_ref",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "identity_assertion_ref": self.identity_assertion_ref,
            "media_ref": self.media_ref,
            "scope_type": self.scope_type.value,
        }


EvidenceClaimScopeV2: TypeAlias = (
    MaterialRelationClaimScopeV2 | MediaIdentityClaimScopeV2
)


def derive_claim_ref_v2(*, claim_text: str, scope: EvidenceClaimScopeV2) -> str:
    _text(claim_text, path="$.claim.claim_text")
    if type(scope) not in {MaterialRelationClaimScopeV2, MediaIdentityClaimScopeV2}:
        _fail(
            MaterialEvidenceV2ErrorCode.INVALID_TYPE,
            "scope must be an exact v2 scope variant",
            path="$.claim.scope",
        )
    return _identity(
        CLAIM_REF_DOMAIN_V2,
        {"claim_text": claim_text, "scope": scope.to_dict()},
        "mec",
    )


@dataclass(frozen=True, slots=True)
class AtomicEvidenceClaimV2:
    claim_ref: str
    claim_text: str
    scope: EvidenceClaimScopeV2
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.scope) not in {
            MaterialRelationClaimScopeV2,
            MediaIdentityClaimScopeV2,
        }:
            _fail(
                MaterialEvidenceV2ErrorCode.INVALID_TYPE,
                "scope must be an exact v2 scope variant",
                path="$.claim.scope",
            )
        _text(self.claim_text, path="$.claim.claim_text")
        if type(self.source_refs) is not tuple or not self.source_refs:
            _fail(
                MaterialEvidenceV2ErrorCode.EMPTY_COLLECTION,
                "source_refs must be a non-empty tuple",
                path="$.claim.source_refs",
            )
        if any(
            type(item) is not str or not _SOURCE_REF_RE.fullmatch(item)
            for item in self.source_refs
        ):
            _fail(
                MaterialEvidenceV2ErrorCode.INVALID_ID,
                "invalid source_ref",
                path="$.claim.source_refs",
            )
        if self.source_refs != tuple(sorted(set(self.source_refs))):
            _fail(
                MaterialEvidenceV2ErrorCode.NON_CANONICAL_ORDER,
                "source_refs must be unique and ordered",
                path="$.claim.source_refs",
            )
        expected = derive_claim_ref_v2(claim_text=self.claim_text, scope=self.scope)
        if self.claim_ref != expected:
            _fail(
                MaterialEvidenceV2ErrorCode.HASH_MISMATCH,
                "claim_ref does not match v2 claim text and scope",
                path="$.claim.claim_ref",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_ref": self.claim_ref,
            "claim_text": self.claim_text,
            "scope": self.scope.to_dict(),
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True, slots=True)
class RuleClaimBindingV2:
    rule_ref: str
    claim_ref: str

    def __post_init__(self) -> None:
        _identifier(
            self.rule_ref,
            _RULE_REF_RE,
            path="$.binding.rule_ref",
            message="invalid MAT-GOV-03A rule_ref",
        )
        _identifier(
            self.claim_ref,
            _CLAIM_REF_RE,
            path="$.binding.claim_ref",
            message="invalid claim_ref",
        )

    def to_dict(self) -> dict[str, str]:
        return {"claim_ref": self.claim_ref, "rule_ref": self.rule_ref}


@dataclass(frozen=True, slots=True)
class EvidenceManifestPayloadV2:
    domain_pack_id: str
    target: EvidenceManifestTargetV2
    sources: tuple[EvidenceSourceV2, ...]
    claims: tuple[AtomicEvidenceClaimV2, ...]
    rule_claim_bindings: tuple[RuleClaimBindingV2, ...]
    evidence_manifest_schema_version: int = EVIDENCE_MANIFEST_SCHEMA_VERSION_V2
    canonicalization_version: int = CANONICALIZATION_VERSION_V2
    mat_evid_contract_version: str = MAT_EVID_CONTRACT_VERSION_V2

    def __post_init__(self) -> None:
        _version(
            self.evidence_manifest_schema_version,
            EVIDENCE_MANIFEST_SCHEMA_VERSION_V2,
            path="$.evidence_manifest_schema_version",
        )
        _version(
            self.canonicalization_version,
            CANONICALIZATION_VERSION_V2,
            path="$.canonicalization_version",
        )
        if self.mat_evid_contract_version != MAT_EVID_CONTRACT_VERSION_V2:
            _fail(
                MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
                "unsupported MAT-EVID v2 contract",
                path="$.mat_evid_contract_version",
            )
        validate_domain_pack_id_v2(self.domain_pack_id)
        if type(self.target) not in {MaterialRelationTargetV2, MediaIdentityTargetV2}:
            _fail(
                MaterialEvidenceV2ErrorCode.INVALID_TYPE,
                "target must be an exact v2 target variant",
                path="$.target",
            )
        for name, values, expected_type in (
            ("sources", self.sources, EvidenceSourceV2),
            ("claims", self.claims, AtomicEvidenceClaimV2),
        ):
            if (
                type(values) is not tuple
                or not values
                or any(type(item) is not expected_type for item in values)
            ):
                _fail(
                    MaterialEvidenceV2ErrorCode.EMPTY_COLLECTION,
                    f"{name} must be a non-empty typed tuple",
                    path=f"$.{name}",
                )
        if type(self.rule_claim_bindings) is not tuple or any(
            type(item) is not RuleClaimBindingV2 for item in self.rule_claim_bindings
        ):
            _fail(
                MaterialEvidenceV2ErrorCode.INVALID_TYPE,
                "rule_claim_bindings must be a typed tuple",
                path="$.rule_claim_bindings",
            )
        source_refs = tuple(item.source_ref for item in self.sources)
        claim_refs = tuple(item.claim_ref for item in self.claims)
        binding_keys = tuple(
            (item.rule_ref, item.claim_ref) for item in self.rule_claim_bindings
        )
        if source_refs != tuple(sorted(set(source_refs))):
            _fail(
                MaterialEvidenceV2ErrorCode.NON_CANONICAL_ORDER,
                "sources must be unique and ordered",
                path="$.sources",
            )
        if claim_refs != tuple(sorted(set(claim_refs))):
            _fail(
                MaterialEvidenceV2ErrorCode.NON_CANONICAL_ORDER,
                "claims must be unique and ordered",
                path="$.claims",
            )
        if binding_keys != tuple(sorted(set(binding_keys))):
            _fail(
                MaterialEvidenceV2ErrorCode.NON_CANONICAL_ORDER,
                "bindings must be unique and ordered",
                path="$.rule_claim_bindings",
            )
        source_set = set(source_refs)
        used_sources = {ref for claim in self.claims for ref in claim.source_refs}
        if not used_sources <= source_set:
            _fail(
                MaterialEvidenceV2ErrorCode.DANGLING_REF,
                "claim references an absent source",
                path="$.claims",
            )
        if source_set != used_sources:
            _fail(
                MaterialEvidenceV2ErrorCode.ORPHAN_REF,
                "every source must support a claim",
                path="$.sources",
            )
        if type(self.target) is MaterialRelationTargetV2:
            if any(
                type(claim.scope) is not MaterialRelationClaimScopeV2
                for claim in self.claims
            ):
                _fail(
                    MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                    "material target accepts only material_relation claims",
                    path="$.claims",
                )
            if not self.rule_claim_bindings:
                _fail(
                    MaterialEvidenceV2ErrorCode.EMPTY_COLLECTION,
                    "material target requires rule bindings",
                    path="$.rule_claim_bindings",
                )
            bound = {binding.claim_ref for binding in self.rule_claim_bindings}
            claim_set = set(claim_refs)
            if not bound <= claim_set:
                _fail(
                    MaterialEvidenceV2ErrorCode.DANGLING_REF,
                    "binding references an absent claim",
                    path="$.rule_claim_bindings",
                )
            if bound != claim_set:
                _fail(
                    MaterialEvidenceV2ErrorCode.ORPHAN_REF,
                    "every material claim must bind to a rule",
                    path="$.claims",
                )
            return
        if self.rule_claim_bindings:
            _fail(
                MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                "media_identity manifests cannot carry rule bindings",
                path="$.rule_claim_bindings",
            )
        target = self.target
        if any(
            type(claim.scope) is not MediaIdentityClaimScopeV2
            or claim.scope.media_ref != target.media_ref
            for claim in self.claims
        ):
            _fail(
                MaterialEvidenceV2ErrorCode.CROSS_FIELD_MISMATCH,
                "all media_identity claims must name the exact target media_ref",
                path="$.claims",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": self.canonicalization_version,
            "claims": [item.to_dict() for item in self.claims],
            "domain_pack_id": self.domain_pack_id,
            "evidence_manifest_schema_version": self.evidence_manifest_schema_version,
            "mat_evid_contract_version": self.mat_evid_contract_version,
            "rule_claim_bindings": [
                item.to_dict() for item in self.rule_claim_bindings
            ],
            "sources": [item.to_dict() for item in self.sources],
            "target": self.target.to_dict(),
        }


def _parse_target(value: Any, *, path: str) -> EvidenceManifestTargetV2:
    obj = _dict(value, path=path)
    discriminator = _text(obj.get("target_type"), path=f"{path}.target_type")
    if discriminator == EvidenceScopeTypeV2.MATERIAL_RELATION.value:
        _exact(obj, _MATERIAL_TARGET_FIELDS, path=path)
        return MaterialRelationTargetV2(
            ruleset_snapshot_id=_text(
                obj["ruleset_snapshot_id"], path=f"{path}.ruleset_snapshot_id"
            )
        )
    if discriminator == EvidenceScopeTypeV2.MEDIA_IDENTITY.value:
        _exact(obj, _MEDIA_TARGET_FIELDS, path=path)
        return MediaIdentityTargetV2(
            media_ref=_text(obj["media_ref"], path=f"{path}.media_ref")
        )
    _fail(
        MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
        "unknown target discriminator",
        path=f"{path}.target_type",
    )


def _parse_scope(value: Any, *, path: str) -> EvidenceClaimScopeV2:
    obj = _dict(value, path=path)
    discriminator = _text(obj.get("scope_type"), path=f"{path}.scope_type")
    if discriminator == EvidenceScopeTypeV2.MATERIAL_RELATION.value:
        _exact(obj, _MATERIAL_SCOPE_FIELDS, path=path)
        return MaterialRelationClaimScopeV2(
            materials=_canonical_strings(
                obj["materials"], path=f"{path}.materials", nonempty=True
            ),
            media=_canonical_strings(obj["media"], path=f"{path}.media", nonempty=True),
            conditions=_canonical_strings(
                obj["conditions"], path=f"{path}.conditions", nonempty=False
            ),
        )
    if discriminator == EvidenceScopeTypeV2.MEDIA_IDENTITY.value:
        _exact(obj, _MEDIA_SCOPE_FIELDS, path=path)
        return MediaIdentityClaimScopeV2(
            media_ref=_text(obj["media_ref"], path=f"{path}.media_ref"),
            identity_assertion_ref=_text(
                obj["identity_assertion_ref"],
                path=f"{path}.identity_assertion_ref",
            ),
        )
    _fail(
        MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
        "unknown scope discriminator",
        path=f"{path}.scope_type",
    )


def _parse_source(value: Any, *, path: str) -> EvidenceSourceV2:
    obj = _dict(value, path=path)
    _exact(obj, _SOURCE_FIELDS, path=path)
    return EvidenceSourceV2(
        source_ref=_text(obj["source_ref"], path=f"{path}.source_ref"),
        document_id=_text(obj["document_id"], path=f"{path}.document_id"),
        document_revision=_text(
            obj["document_revision"], path=f"{path}.document_revision"
        ),
        publication_edition=_text(
            obj["publication_edition"], path=f"{path}.publication_edition"
        ),
        content_sha256=_text(obj["content_sha256"], path=f"{path}.content_sha256"),
    )


def _parse_claim(value: Any, *, path: str) -> AtomicEvidenceClaimV2:
    obj = _dict(value, path=path)
    _exact(obj, _CLAIM_FIELDS, path=path)
    return AtomicEvidenceClaimV2(
        claim_ref=_text(obj["claim_ref"], path=f"{path}.claim_ref"),
        claim_text=_text(obj["claim_text"], path=f"{path}.claim_text"),
        scope=_parse_scope(obj["scope"], path=f"{path}.scope"),
        source_refs=_canonical_strings(
            obj["source_refs"], path=f"{path}.source_refs", nonempty=True
        ),
    )


def _parse_binding(value: Any, *, path: str) -> RuleClaimBindingV2:
    obj = _dict(value, path=path)
    _exact(obj, _BINDING_FIELDS, path=path)
    return RuleClaimBindingV2(
        rule_ref=_text(obj["rule_ref"], path=f"{path}.rule_ref"),
        claim_ref=_text(obj["claim_ref"], path=f"{path}.claim_ref"),
    )


def parse_manifest_payload_v2(raw: str | bytes) -> EvidenceManifestPayloadV2:
    obj = parse_json_v2(raw)
    _exact(obj, _TOP_LEVEL_FIELDS, path="$")
    _version(
        obj["evidence_manifest_schema_version"],
        EVIDENCE_MANIFEST_SCHEMA_VERSION_V2,
        path="$.evidence_manifest_schema_version",
    )
    _version(
        obj["canonicalization_version"],
        CANONICALIZATION_VERSION_V2,
        path="$.canonicalization_version",
    )
    if (
        _text(obj["mat_evid_contract_version"], path="$.mat_evid_contract_version")
        != MAT_EVID_CONTRACT_VERSION_V2
    ):
        _fail(
            MaterialEvidenceV2ErrorCode.UNKNOWN_SCHEMA,
            "unknown MAT-EVID v2 contract",
            path="$.mat_evid_contract_version",
        )
    sources = tuple(
        sorted(
            (
                _parse_source(item, path=f"$.sources[{index}]")
                for index, item in enumerate(_list(obj["sources"], path="$.sources"))
            ),
            key=lambda item: item.source_ref,
        )
    )
    claims = tuple(
        sorted(
            (
                _parse_claim(item, path=f"$.claims[{index}]")
                for index, item in enumerate(_list(obj["claims"], path="$.claims"))
            ),
            key=lambda item: item.claim_ref,
        )
    )
    bindings = tuple(
        sorted(
            (
                _parse_binding(item, path=f"$.rule_claim_bindings[{index}]")
                for index, item in enumerate(
                    _list(obj["rule_claim_bindings"], path="$.rule_claim_bindings")
                )
            ),
            key=lambda item: (item.rule_ref, item.claim_ref),
        )
    )
    return EvidenceManifestPayloadV2(
        domain_pack_id=_text(obj["domain_pack_id"], path="$.domain_pack_id"),
        target=_parse_target(obj["target"], path="$.target"),
        sources=sources,
        claims=claims,
        rule_claim_bindings=bindings,
    )


def canonicalize_payload_v2(payload: EvidenceManifestPayloadV2) -> bytes:
    if type(payload) is not EvidenceManifestPayloadV2:
        raise TypeError("payload must be EvidenceManifestPayloadV2")
    return _canonical_json_v2(payload.to_dict())


def compute_content_sha256_v2(canonical_bytes: bytes) -> str:
    if type(canonical_bytes) is not bytes:
        raise TypeError("canonical_bytes must be bytes")
    return hashlib.sha256(CONTENT_HASH_DOMAIN_V2 + canonical_bytes).hexdigest()


def derive_snapshot_id_v2(manifest_id: str, content_sha256: str) -> str:
    validate_manifest_id_v2(manifest_id)
    _identifier(
        content_sha256,
        _SHA256_RE,
        path="$.content_sha256",
        message="expected lowercase SHA-256",
    )
    digest = hashlib.sha256(
        SNAPSHOT_ID_DOMAIN_V2
        + manifest_id.encode("ascii")
        + b"\x00"
        + content_sha256.encode("ascii")
    ).hexdigest()
    return f"mes_{digest}"


@dataclass(frozen=True, slots=True)
class EvidenceManifestSnapshotV2:
    manifest_id: str
    snapshot_id: str
    content_sha256: str
    canonical_bytes: bytes
    payload: EvidenceManifestPayloadV2

    def __post_init__(self) -> None:
        validate_manifest_id_v2(self.manifest_id)
        validate_snapshot_id_v2(self.snapshot_id)
        if type(self.payload) is not EvidenceManifestPayloadV2:
            raise TypeError("payload must be EvidenceManifestPayloadV2")
        if type(self.canonical_bytes) is not bytes:
            _fail(
                MaterialEvidenceV2ErrorCode.INVALID_TYPE,
                "canonical_bytes must be bytes",
                path="$.canonical_bytes",
            )
        expected_bytes = canonicalize_payload_v2(self.payload)
        if self.canonical_bytes != expected_bytes:
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.HASH_MISMATCH,
                "canonical bytes differ from payload",
            )
        expected_hash = compute_content_sha256_v2(expected_bytes)
        if self.content_sha256 != expected_hash:
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.HASH_MISMATCH,
                "content hash differs from canonical bytes",
            )
        if self.snapshot_id != derive_snapshot_id_v2(self.manifest_id, expected_hash):
            raise MaterialEvidenceV2IntegrityError(
                MaterialEvidenceV2ErrorCode.SNAPSHOT_ID_MISMATCH,
                "snapshot identity differs from manifest and content",
            )

    @classmethod
    def create(
        cls, manifest_id: str, payload: EvidenceManifestPayloadV2
    ) -> EvidenceManifestSnapshotV2:
        canonical_bytes = canonicalize_payload_v2(payload)
        content_sha256 = compute_content_sha256_v2(canonical_bytes)
        return cls(
            manifest_id=manifest_id,
            snapshot_id=derive_snapshot_id_v2(manifest_id, content_sha256),
            content_sha256=content_sha256,
            canonical_bytes=canonical_bytes,
            payload=payload,
        )

    @classmethod
    def from_json(
        cls, manifest_id: str, raw: str | bytes
    ) -> EvidenceManifestSnapshotV2:
        return cls.create(manifest_id, parse_manifest_payload_v2(raw))


def compute_validation_sha256_v2(snapshot: EvidenceManifestSnapshotV2) -> str:
    if type(snapshot) is not EvidenceManifestSnapshotV2:
        raise TypeError("snapshot must be EvidenceManifestSnapshotV2")
    return hashlib.sha256(
        VALIDATION_HASH_DOMAIN_V2
        + snapshot.snapshot_id.encode("ascii")
        + b"\x00"
        + snapshot.content_sha256.encode("ascii")
    ).hexdigest()


def compute_audit_sha256_v2(event_payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        AUDIT_HASH_DOMAIN_V2 + _canonical_json_v2(event_payload)
    ).hexdigest()


__all__ = [
    "AUDIT_HASH_DOMAIN_V2",
    "CANONICALIZATION_VERSION_V2",
    "CLAIM_REF_DOMAIN_V2",
    "CONTENT_HASH_DOMAIN_V2",
    "EVIDENCE_MANIFEST_SCHEMA_VERSION_V2",
    "EvidenceClaimScopeV2",
    "EvidenceManifestPayloadV2",
    "EvidenceManifestSnapshotV2",
    "EvidenceManifestTargetV2",
    "EvidenceScopeTypeV2",
    "EvidenceSourceV2",
    "HASH_ALGORITHM_V2",
    "MAT_EVID_CONTRACT_VERSION_V2",
    "MaterialEvidenceV2ErrorCode",
    "MaterialEvidenceV2IntegrityError",
    "MaterialEvidenceV2ValidationError",
    "MaterialRelationClaimScopeV2",
    "MaterialRelationTargetV2",
    "MediaIdentityClaimScopeV2",
    "MediaIdentityTargetV2",
    "RuleClaimBindingV2",
    "SNAPSHOT_ID_DOMAIN_V2",
    "SOURCE_REF_DOMAIN_V2",
    "VALIDATION_HASH_DOMAIN_V2",
    "AtomicEvidenceClaimV2",
    "canonicalize_payload_v2",
    "compute_audit_sha256_v2",
    "compute_content_sha256_v2",
    "compute_validation_sha256_v2",
    "derive_claim_ref_v2",
    "derive_snapshot_id_v2",
    "derive_source_ref_v2",
    "parse_json_v2",
    "parse_manifest_payload_v2",
    "validate_domain_pack_id_v2",
    "validate_manifest_id_v2",
    "validate_snapshot_id_v2",
]
