"""MAT-EVID-01A immutable evidence-manifest contract.

This module is runtime-inert. It defines only strict schema validation,
content-addressed identities, deterministic canonicalization, and deeply
immutable values. It neither imports existing matrix text nor grants review,
approval, recommendation, deployment, or activation authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any, NoReturn


EVIDENCE_MANIFEST_SCHEMA_VERSION = 1
CANONICALIZATION_VERSION = 1
MAT_EVID_CONTRACT_VERSION = "MAT-EVID-01A.v1"
HASH_ALGORITHM = "sha256-v1"

SOURCE_REF_DOMAIN = b"sealai.material-evidence.source.v1\x00"
CLAIM_REF_DOMAIN = b"sealai.material-evidence.claim.v1\x00"
CONTENT_HASH_DOMAIN = b"sealai.material-evidence.content.v1\x00"
SNAPSHOT_ID_DOMAIN = b"sealai.material-evidence.snapshot.v1\x00"
VALIDATION_HASH_DOMAIN = b"sealai.material-evidence.validation.v1\x00"
AUDIT_HASH_DOMAIN = b"sealai.material-evidence.audit.v1\x00"

_MANIFEST_ID_RE = re.compile(r"^mef_[0-9a-f]{32}$", re.ASCII)
_SNAPSHOT_ID_RE = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_RULESET_SNAPSHOT_ID_RE = re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII)
_SOURCE_REF_RE = re.compile(r"^msr_[0-9a-f]{64}$", re.ASCII)
_CLAIM_REF_RE = re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII)
# Pinned to the MAT-GOV-03A.v1 rule-ref grammar without modifying that schema.
_RULE_REF_RE = re.compile(r"^MR-[A-Z0-9][A-Z0-9._:-]{0,124}$", re.ASCII)
_DOMAIN_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "evidence_manifest_schema_version",
        "canonicalization_version",
        "mat_evid_contract_version",
        "ruleset_snapshot_id",
        "domain_pack_id",
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
_SCOPE_FIELDS = frozenset({"materials", "media", "conditions"})
_BINDING_FIELDS = frozenset({"rule_ref", "claim_ref"})


class MaterialEvidenceErrorCode(str, Enum):
    INVALID_JSON = "MAT_EVID_INVALID_JSON"
    DUPLICATE_PROPERTY = "MAT_EVID_DUPLICATE_PROPERTY"
    UNKNOWN_FIELD = "MAT_EVID_UNKNOWN_FIELD"
    INVALID_TYPE = "MAT_EVID_INVALID_TYPE"
    INVALID_ID = "MAT_EVID_INVALID_ID"
    INVALID_UNICODE = "MAT_EVID_INVALID_UNICODE"
    NON_NFC = "MAT_EVID_NON_NFC"
    FLOAT_FORBIDDEN = "MAT_EVID_FLOAT_FORBIDDEN"
    UNKNOWN_SCHEMA = "MAT_EVID_UNKNOWN_SCHEMA"
    INVALID_CONSTANT = "MAT_EVID_INVALID_CONSTANT"
    EMPTY_COLLECTION = "MAT_EVID_EMPTY_COLLECTION"
    DUPLICATE_REF = "MAT_EVID_DUPLICATE_REF"
    DANGLING_REF = "MAT_EVID_DANGLING_REF"
    ORPHAN_REF = "MAT_EVID_ORPHAN_REF"
    NON_CANONICAL_ORDER = "MAT_EVID_NON_CANONICAL_ORDER"
    HASH_MISMATCH = "MAT_EVID_HASH_MISMATCH"
    SNAPSHOT_ID_MISMATCH = "MAT_EVID_SNAPSHOT_ID_MISMATCH"
    DB_INTEGRITY = "MAT_EVID_DB_INTEGRITY"


class MaterialEvidenceValidationError(ValueError):
    """Stable fail-closed validation error for untrusted manifest input."""

    def __init__(
        self,
        code: MaterialEvidenceErrorCode,
        message: str,
        *,
        path: str = "$",
    ) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value} at {path}: {message}")


class MaterialEvidenceIntegrityError(RuntimeError):
    """A persisted manifest failed revalidation and requires quarantine."""

    quarantine_candidate = True

    def __init__(self, code: MaterialEvidenceErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(
    code: MaterialEvidenceErrorCode,
    message: str,
    *,
    path: str,
) -> NoReturn:
    raise MaterialEvidenceValidationError(code, message, path=path)


def _require_exact_fields(
    value: dict[str, Any], expected: frozenset[str], *, path: str
) -> None:
    actual = frozenset(value)
    unknown = sorted(actual - expected)
    missing = sorted(expected - actual)
    if unknown or missing:
        _fail(
            MaterialEvidenceErrorCode.UNKNOWN_FIELD,
            f"unknown={unknown} missing={missing}",
            path=path,
        )


def _require_dict(value: Any, *, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(MaterialEvidenceErrorCode.INVALID_TYPE, "expected object", path=path)
    return value


def _require_list(value: Any, *, path: str) -> list[Any]:
    if type(value) is not list:
        _fail(MaterialEvidenceErrorCode.INVALID_TYPE, "expected array", path=path)
    return value


def _require_string(value: Any, *, path: str) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        _fail(
            MaterialEvidenceErrorCode.INVALID_TYPE,
            "expected a non-whitespace string",
            path=path,
        )
    return value


def _require_version(value: Any, expected: int, *, path: str) -> int:
    if type(value) is not int:
        _fail(MaterialEvidenceErrorCode.INVALID_TYPE, "expected integer", path=path)
    if value != expected:
        _fail(
            MaterialEvidenceErrorCode.UNKNOWN_SCHEMA,
            f"only version {expected} is supported",
            path=path,
        )
    return value


def _validate_unicode(value: Any, *, path: str = "$") -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            _fail(
                MaterialEvidenceErrorCode.INVALID_UNICODE,
                "string contains a non-Unicode-scalar value",
                path=path,
            )
        if unicodedata.normalize("NFC", value) != value:
            _fail(
                MaterialEvidenceErrorCode.NON_NFC,
                "string must already be NFC",
                path=path,
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_unicode(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not key.isascii():
                _fail(
                    MaterialEvidenceErrorCode.INVALID_ID,
                    "property names must be ASCII",
                    path=path,
                )
            _validate_unicode(item, path=f"{path}.{key}")


def _reject_float(_value: str) -> NoReturn:
    _fail(
        MaterialEvidenceErrorCode.FLOAT_FORBIDDEN,
        "floating-point values are forbidden",
        path="$",
    )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail(
                MaterialEvidenceErrorCode.DUPLICATE_PROPERTY,
                f"duplicate property {key!r}",
                path="$",
            )
        value[key] = item
    return value


def parse_json_without_duplicates(raw: str | bytes) -> dict[str, Any]:
    if isinstance(raw, bytes):
        if raw.startswith(b"\xef\xbb\xbf"):
            _fail(MaterialEvidenceErrorCode.INVALID_JSON, "BOM is forbidden", path="$")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail(
                MaterialEvidenceErrorCode.INVALID_UNICODE,
                "input is not valid UTF-8",
                path="$",
            )
    elif isinstance(raw, str):
        text = raw
        if text.startswith("\ufeff"):
            _fail(MaterialEvidenceErrorCode.INVALID_JSON, "BOM is forbidden", path="$")
    else:
        _fail(
            MaterialEvidenceErrorCode.INVALID_TYPE,
            "manifest input must be str or bytes",
            path="$",
        )
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except MaterialEvidenceValidationError:
        raise
    except (json.JSONDecodeError, RecursionError, UnicodeEncodeError) as exc:
        raise MaterialEvidenceValidationError(
            MaterialEvidenceErrorCode.INVALID_JSON,
            "malformed JSON",
        ) from exc
    root = _require_dict(value, path="$")
    _validate_unicode(root)
    return root


def _canonical_json(value: dict[str, Any]) -> bytes:
    _validate_unicode(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaterialEvidenceValidationError(
            MaterialEvidenceErrorCode.INVALID_TYPE,
            "value is not canonical JSON",
        ) from exc


def _validate_id(
    value: str, pattern: re.Pattern[str], message: str, *, path: str
) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _fail(MaterialEvidenceErrorCode.INVALID_ID, message, path=path)
    return value


def validate_manifest_id(value: str) -> str:
    return _validate_id(
        value, _MANIFEST_ID_RE, "expected mef_<32 lowercase hex>", path="$.manifest_id"
    )


def validate_snapshot_id(value: str) -> str:
    return _validate_id(
        value, _SNAPSHOT_ID_RE, "expected mes_<64 lowercase hex>", path="$.snapshot_id"
    )


def validate_ruleset_snapshot_id(value: str) -> str:
    return _validate_id(
        value,
        _RULESET_SNAPSHOT_ID_RE,
        "expected mss_<64 lowercase hex>",
        path="$.ruleset_snapshot_id",
    )


def validate_domain_pack_id(value: str) -> str:
    return _validate_id(
        value, _DOMAIN_PACK_ID_RE, "invalid domain_pack_id", path="$.domain_pack_id"
    )


def validate_rule_ref(value: str) -> str:
    return _validate_id(
        value, _RULE_REF_RE, "invalid MAT-GOV-03A rule_ref", path="$.rule_ref"
    )


def _canonical_strings(value: Any, *, path: str, nonempty: bool) -> tuple[str, ...]:
    raw = _require_list(value, path=path)
    items = tuple(
        _require_string(item, path=f"{path}[{index}]") for index, item in enumerate(raw)
    )
    if nonempty and not items:
        _fail(
            MaterialEvidenceErrorCode.EMPTY_COLLECTION,
            "array must not be empty",
            path=path,
        )
    if len(items) != len(set(items)):
        _fail(
            MaterialEvidenceErrorCode.DUPLICATE_REF, "duplicate array value", path=path
        )
    return tuple(sorted(items, key=lambda item: item.encode("utf-8")))


def _identity(domain: bytes, payload: dict[str, Any], prefix: str) -> str:
    return f"{prefix}_{hashlib.sha256(domain + _canonical_json(payload)).hexdigest()}"


@dataclass(frozen=True, slots=True)
class EvidenceSourceV1:
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
            _require_string(value, path=f"$.source.{name}")
            _validate_unicode(value, path=f"$.source.{name}")
        _validate_id(
            self.content_sha256,
            _SHA256_RE,
            "expected 64 lowercase hex",
            path="$.source.content_sha256",
        )
        expected = derive_source_ref(
            document_id=self.document_id,
            document_revision=self.document_revision,
            publication_edition=self.publication_edition,
            content_sha256=self.content_sha256,
        )
        if self.source_ref != expected:
            _fail(
                MaterialEvidenceErrorCode.HASH_MISMATCH,
                "source_ref does not match source identity",
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


def derive_source_ref(
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
        _require_string(value, path=f"$.source.{name}")
        _validate_unicode(value, path=f"$.source.{name}")
    _validate_id(
        content_sha256,
        _SHA256_RE,
        "expected 64 lowercase hex",
        path="$.source.content_sha256",
    )
    return _identity(
        SOURCE_REF_DOMAIN,
        {
            "content_sha256": content_sha256,
            "document_id": document_id,
            "document_revision": document_revision,
            "publication_edition": publication_edition,
        },
        "msr",
    )


@dataclass(frozen=True, slots=True)
class EvidenceClaimScopeV1:
    materials: tuple[str, ...]
    media: tuple[str, ...]
    conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, values, nonempty in (
            ("materials", self.materials, True),
            ("media", self.media, True),
            ("conditions", self.conditions, False),
        ):
            if type(values) is not tuple or any(
                type(item) is not str for item in values
            ):
                _fail(
                    MaterialEvidenceErrorCode.INVALID_TYPE,
                    f"{name} must be a tuple of strings",
                    path=f"$.claim.scope.{name}",
                )
            if nonempty and not values:
                _fail(
                    MaterialEvidenceErrorCode.EMPTY_COLLECTION,
                    f"{name} must not be empty",
                    path=f"$.claim.scope.{name}",
                )
            expected = tuple(sorted(set(values), key=lambda item: item.encode("utf-8")))
            if values != expected:
                _fail(
                    MaterialEvidenceErrorCode.NON_CANONICAL_ORDER,
                    f"{name} must be unique and ordered",
                    path=f"$.claim.scope.{name}",
                )
            _validate_unicode(list(values), path=f"$.claim.scope.{name}")

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "conditions": list(self.conditions),
            "materials": list(self.materials),
            "media": list(self.media),
        }


def derive_claim_ref(*, claim_text: str, scope: EvidenceClaimScopeV1) -> str:
    _require_string(claim_text, path="$.claim.claim_text")
    _validate_unicode(claim_text, path="$.claim.claim_text")
    if type(scope) is not EvidenceClaimScopeV1:
        _fail(
            MaterialEvidenceErrorCode.INVALID_TYPE,
            "scope must be EvidenceClaimScopeV1",
            path="$.claim.scope",
        )
    return _identity(
        CLAIM_REF_DOMAIN, {"claim_text": claim_text, "scope": scope.to_dict()}, "mec"
    )


@dataclass(frozen=True, slots=True)
class AtomicEvidenceClaimV1:
    claim_ref: str
    claim_text: str
    scope: EvidenceClaimScopeV1
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.scope) is not EvidenceClaimScopeV1:
            _fail(
                MaterialEvidenceErrorCode.INVALID_TYPE,
                "scope must be EvidenceClaimScopeV1",
                path="$.claim.scope",
            )
        _require_string(self.claim_text, path="$.claim.claim_text")
        _validate_unicode(self.claim_text, path="$.claim.claim_text")
        if type(self.source_refs) is not tuple or not self.source_refs:
            _fail(
                MaterialEvidenceErrorCode.EMPTY_COLLECTION,
                "source_refs must be a non-empty tuple",
                path="$.claim.source_refs",
            )
        if any(
            type(item) is not str or not _SOURCE_REF_RE.fullmatch(item)
            for item in self.source_refs
        ):
            _fail(
                MaterialEvidenceErrorCode.INVALID_ID,
                "invalid source_ref",
                path="$.claim.source_refs",
            )
        if self.source_refs != tuple(sorted(set(self.source_refs))):
            _fail(
                MaterialEvidenceErrorCode.NON_CANONICAL_ORDER,
                "source_refs must be unique and ordered",
                path="$.claim.source_refs",
            )
        expected = derive_claim_ref(claim_text=self.claim_text, scope=self.scope)
        if self.claim_ref != expected:
            _fail(
                MaterialEvidenceErrorCode.HASH_MISMATCH,
                "claim_ref does not match claim text and scope",
                path="$.claim.claim_ref",
            )

    def identity_dict(self) -> dict[str, Any]:
        return {"claim_text": self.claim_text, "scope": self.scope.to_dict()}

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_ref": self.claim_ref,
            **self.identity_dict(),
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True, slots=True)
class RuleClaimBindingV1:
    rule_ref: str
    claim_ref: str

    def __post_init__(self) -> None:
        validate_rule_ref(self.rule_ref)
        _validate_id(
            self.claim_ref,
            _CLAIM_REF_RE,
            "invalid claim_ref",
            path="$.binding.claim_ref",
        )

    def to_dict(self) -> dict[str, str]:
        return {"claim_ref": self.claim_ref, "rule_ref": self.rule_ref}


@dataclass(frozen=True, slots=True)
class EvidenceManifestPayloadV1:
    ruleset_snapshot_id: str
    domain_pack_id: str
    sources: tuple[EvidenceSourceV1, ...]
    claims: tuple[AtomicEvidenceClaimV1, ...]
    rule_claim_bindings: tuple[RuleClaimBindingV1, ...]
    evidence_manifest_schema_version: int = EVIDENCE_MANIFEST_SCHEMA_VERSION
    canonicalization_version: int = CANONICALIZATION_VERSION
    mat_evid_contract_version: str = MAT_EVID_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.evidence_manifest_schema_version != EVIDENCE_MANIFEST_SCHEMA_VERSION:
            _fail(
                MaterialEvidenceErrorCode.UNKNOWN_SCHEMA,
                "unsupported evidence schema",
                path="$.evidence_manifest_schema_version",
            )
        if self.canonicalization_version != CANONICALIZATION_VERSION:
            _fail(
                MaterialEvidenceErrorCode.UNKNOWN_SCHEMA,
                "unsupported canonicalization",
                path="$.canonicalization_version",
            )
        if self.mat_evid_contract_version != MAT_EVID_CONTRACT_VERSION:
            _fail(
                MaterialEvidenceErrorCode.UNKNOWN_SCHEMA,
                "unsupported MAT-EVID contract",
                path="$.mat_evid_contract_version",
            )
        validate_ruleset_snapshot_id(self.ruleset_snapshot_id)
        validate_domain_pack_id(self.domain_pack_id)
        for name, values, expected_type in (
            ("sources", self.sources, EvidenceSourceV1),
            ("claims", self.claims, AtomicEvidenceClaimV1),
            ("rule_claim_bindings", self.rule_claim_bindings, RuleClaimBindingV1),
        ):
            if (
                type(values) is not tuple
                or not values
                or any(type(item) is not expected_type for item in values)
            ):
                _fail(
                    MaterialEvidenceErrorCode.EMPTY_COLLECTION,
                    f"{name} must be a non-empty typed tuple",
                    path=f"$.{name}",
                )
        source_refs = tuple(item.source_ref for item in self.sources)
        claim_refs = tuple(item.claim_ref for item in self.claims)
        binding_keys = tuple(
            (item.rule_ref, item.claim_ref) for item in self.rule_claim_bindings
        )
        if source_refs != tuple(sorted(set(source_refs))):
            _fail(
                MaterialEvidenceErrorCode.NON_CANONICAL_ORDER,
                "sources must be unique and ordered",
                path="$.sources",
            )
        if claim_refs != tuple(sorted(set(claim_refs))):
            _fail(
                MaterialEvidenceErrorCode.NON_CANONICAL_ORDER,
                "claims must be unique and ordered",
                path="$.claims",
            )
        if binding_keys != tuple(sorted(set(binding_keys))):
            _fail(
                MaterialEvidenceErrorCode.NON_CANONICAL_ORDER,
                "bindings must be unique and ordered",
                path="$.rule_claim_bindings",
            )
        source_set = set(source_refs)
        referenced_sources = {ref for claim in self.claims for ref in claim.source_refs}
        if not referenced_sources <= source_set:
            _fail(
                MaterialEvidenceErrorCode.DANGLING_REF,
                "claim references an absent source",
                path="$.claims",
            )
        if source_set != referenced_sources:
            _fail(
                MaterialEvidenceErrorCode.ORPHAN_REF,
                "every source must support a claim",
                path="$.sources",
            )
        claim_set = set(claim_refs)
        bound_claims = {binding.claim_ref for binding in self.rule_claim_bindings}
        if not bound_claims <= claim_set:
            _fail(
                MaterialEvidenceErrorCode.DANGLING_REF,
                "binding references an absent claim",
                path="$.rule_claim_bindings",
            )
        if claim_set != bound_claims:
            _fail(
                MaterialEvidenceErrorCode.ORPHAN_REF,
                "every claim must be bound to a rule",
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
            "ruleset_snapshot_id": self.ruleset_snapshot_id,
            "sources": [item.to_dict() for item in self.sources],
        }


def _parse_scope(value: Any, *, path: str) -> EvidenceClaimScopeV1:
    obj = _require_dict(value, path=path)
    _require_exact_fields(obj, _SCOPE_FIELDS, path=path)
    return EvidenceClaimScopeV1(
        materials=_canonical_strings(
            obj["materials"], path=f"{path}.materials", nonempty=True
        ),
        media=_canonical_strings(obj["media"], path=f"{path}.media", nonempty=True),
        conditions=_canonical_strings(
            obj["conditions"], path=f"{path}.conditions", nonempty=False
        ),
    )


def _parse_source(value: Any, *, path: str) -> EvidenceSourceV1:
    obj = _require_dict(value, path=path)
    _require_exact_fields(obj, _SOURCE_FIELDS, path=path)
    return EvidenceSourceV1(
        source_ref=_require_string(obj["source_ref"], path=f"{path}.source_ref"),
        document_id=_require_string(obj["document_id"], path=f"{path}.document_id"),
        document_revision=_require_string(
            obj["document_revision"], path=f"{path}.document_revision"
        ),
        publication_edition=_require_string(
            obj["publication_edition"], path=f"{path}.publication_edition"
        ),
        content_sha256=_require_string(
            obj["content_sha256"], path=f"{path}.content_sha256"
        ),
    )


def _parse_claim(value: Any, *, path: str) -> AtomicEvidenceClaimV1:
    obj = _require_dict(value, path=path)
    _require_exact_fields(obj, _CLAIM_FIELDS, path=path)
    return AtomicEvidenceClaimV1(
        claim_ref=_require_string(obj["claim_ref"], path=f"{path}.claim_ref"),
        claim_text=_require_string(obj["claim_text"], path=f"{path}.claim_text"),
        scope=_parse_scope(obj["scope"], path=f"{path}.scope"),
        source_refs=_canonical_strings(
            obj["source_refs"], path=f"{path}.source_refs", nonempty=True
        ),
    )


def _parse_binding(value: Any, *, path: str) -> RuleClaimBindingV1:
    obj = _require_dict(value, path=path)
    _require_exact_fields(obj, _BINDING_FIELDS, path=path)
    return RuleClaimBindingV1(
        rule_ref=_require_string(obj["rule_ref"], path=f"{path}.rule_ref"),
        claim_ref=_require_string(obj["claim_ref"], path=f"{path}.claim_ref"),
    )


def parse_manifest_payload(raw: str | bytes) -> EvidenceManifestPayloadV1:
    obj = parse_json_without_duplicates(raw)
    _require_exact_fields(obj, _TOP_LEVEL_FIELDS, path="$")
    _require_version(
        obj["evidence_manifest_schema_version"],
        EVIDENCE_MANIFEST_SCHEMA_VERSION,
        path="$.evidence_manifest_schema_version",
    )
    _require_version(
        obj["canonicalization_version"],
        CANONICALIZATION_VERSION,
        path="$.canonicalization_version",
    )
    contract = _require_string(
        obj["mat_evid_contract_version"], path="$.mat_evid_contract_version"
    )
    if contract != MAT_EVID_CONTRACT_VERSION:
        _fail(
            MaterialEvidenceErrorCode.UNKNOWN_SCHEMA,
            "unknown MAT-EVID contract version",
            path="$.mat_evid_contract_version",
        )
    sources = tuple(
        sorted(
            (
                _parse_source(item, path=f"$.sources[{index}]")
                for index, item in enumerate(
                    _require_list(obj["sources"], path="$.sources")
                )
            ),
            key=lambda item: item.source_ref,
        )
    )
    claims = tuple(
        sorted(
            (
                _parse_claim(item, path=f"$.claims[{index}]")
                for index, item in enumerate(
                    _require_list(obj["claims"], path="$.claims")
                )
            ),
            key=lambda item: item.claim_ref,
        )
    )
    bindings = tuple(
        sorted(
            (
                _parse_binding(item, path=f"$.rule_claim_bindings[{index}]")
                for index, item in enumerate(
                    _require_list(
                        obj["rule_claim_bindings"], path="$.rule_claim_bindings"
                    )
                )
            ),
            key=lambda item: (item.rule_ref, item.claim_ref),
        )
    )
    return EvidenceManifestPayloadV1(
        ruleset_snapshot_id=_require_string(
            obj["ruleset_snapshot_id"], path="$.ruleset_snapshot_id"
        ),
        domain_pack_id=_require_string(obj["domain_pack_id"], path="$.domain_pack_id"),
        sources=sources,
        claims=claims,
        rule_claim_bindings=bindings,
    )


def canonicalize_payload(payload: EvidenceManifestPayloadV1) -> bytes:
    if type(payload) is not EvidenceManifestPayloadV1:
        raise TypeError("payload must be EvidenceManifestPayloadV1")
    return _canonical_json(payload.to_dict())


def compute_content_sha256(canonical_bytes: bytes) -> str:
    if type(canonical_bytes) is not bytes:
        raise TypeError("canonical_bytes must be bytes")
    return hashlib.sha256(CONTENT_HASH_DOMAIN + canonical_bytes).hexdigest()


def derive_snapshot_id(manifest_id: str, content_sha256: str) -> str:
    validate_manifest_id(manifest_id)
    _validate_id(
        content_sha256, _SHA256_RE, "expected 64 lowercase hex", path="$.content_sha256"
    )
    digest = hashlib.sha256(
        SNAPSHOT_ID_DOMAIN
        + manifest_id.encode("ascii")
        + b"\x00"
        + content_sha256.encode("ascii")
    ).hexdigest()
    return f"mes_{digest}"


@dataclass(frozen=True, slots=True)
class EvidenceManifestSnapshotV1:
    manifest_id: str
    snapshot_id: str
    content_sha256: str
    canonical_bytes: bytes
    payload: EvidenceManifestPayloadV1

    def __post_init__(self) -> None:
        validate_manifest_id(self.manifest_id)
        validate_snapshot_id(self.snapshot_id)
        if type(self.payload) is not EvidenceManifestPayloadV1:
            raise TypeError("payload must be EvidenceManifestPayloadV1")
        expected_bytes = canonicalize_payload(self.payload)
        if self.canonical_bytes != expected_bytes:
            raise MaterialEvidenceIntegrityError(
                MaterialEvidenceErrorCode.HASH_MISMATCH,
                "canonical bytes differ from payload",
            )
        expected_hash = compute_content_sha256(expected_bytes)
        if self.content_sha256 != expected_hash:
            raise MaterialEvidenceIntegrityError(
                MaterialEvidenceErrorCode.HASH_MISMATCH,
                "content hash differs from canonical bytes",
            )
        if self.snapshot_id != derive_snapshot_id(self.manifest_id, expected_hash):
            raise MaterialEvidenceIntegrityError(
                MaterialEvidenceErrorCode.SNAPSHOT_ID_MISMATCH,
                "snapshot identity differs from manifest and content",
            )

    @classmethod
    def create(
        cls, manifest_id: str, payload: EvidenceManifestPayloadV1
    ) -> EvidenceManifestSnapshotV1:
        canonical_bytes = canonicalize_payload(payload)
        content_sha256 = compute_content_sha256(canonical_bytes)
        return cls(
            manifest_id=manifest_id,
            snapshot_id=derive_snapshot_id(manifest_id, content_sha256),
            content_sha256=content_sha256,
            canonical_bytes=canonical_bytes,
            payload=payload,
        )

    @classmethod
    def from_json(
        cls, manifest_id: str, raw: str | bytes
    ) -> EvidenceManifestSnapshotV1:
        return cls.create(manifest_id, parse_manifest_payload(raw))


def compute_validation_sha256(snapshot: EvidenceManifestSnapshotV1) -> str:
    return hashlib.sha256(
        VALIDATION_HASH_DOMAIN
        + snapshot.snapshot_id.encode("ascii")
        + b"\x00"
        + snapshot.content_sha256.encode("ascii")
    ).hexdigest()


def compute_audit_sha256(event_payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        AUDIT_HASH_DOMAIN + _canonical_json(event_payload)
    ).hexdigest()
