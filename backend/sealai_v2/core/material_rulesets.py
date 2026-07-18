"""MAT-GOV-03A immutable material-ruleset snapshot contract.

This module is deliberately runtime-inert.  It defines identity, strict schema
v1 parsing, the sealingAI JCS profile, content addressing, and deeply immutable
domain values.  It is not imported by the request pipeline, matrix loader, API,
or public serializers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import secrets
import unicodedata
from typing import Any, NoReturn

from sealai_v2.core.contracts import MaterialConstraintVerdict


SNAPSHOT_SCHEMA_VERSION = 1
CANONICALIZATION_VERSION = 1
MAT_GOV_CONTRACT_VERSION = "MAT-GOV-03A.v1"
HASH_ALGORITHM = "sha256-v1"

CONTENT_HASH_DOMAIN = b"sealai.material-ruleset.content.v1\x00"
SNAPSHOT_ID_DOMAIN = b"sealai.material-ruleset.snapshot.v1\x00"
VALIDATION_HASH_DOMAIN = b"sealai.material-ruleset.validation.v1\x00"
AUDIT_HASH_DOMAIN = b"sealai.material-ruleset.audit.v1\x00"

_RULESET_ID_RE = re.compile(r"^mrs_[0-9a-f]{32}$", re.ASCII)
_SNAPSHOT_ID_RE = re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII)
_RULE_REF_RE = re.compile(r"^MR-[A-Z0-9][A-Z0-9._:-]{0,124}$", re.ASCII)
_DOMAIN_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", re.ASCII)

_TOP_LEVEL_FIELDS = frozenset(
    {
        "snapshot_schema_version",
        "canonicalization_version",
        "mat_gov_contract_version",
        "domain_pack_id",
        "positive_statement_allowed",
        "rules",
    }
)
_RULE_FIELDS = frozenset(
    {
        "rule_ref",
        "material",
        "medium",
        "condition",
        "verdict",
        "statement",
        "scope",
        "evidence_binding",
    }
)
_SCOPE_FIELDS = frozenset({"materials", "media", "conditions"})
_EVIDENCE_FIELDS = frozenset({"state"})


class MaterialRulesetErrorCode(str, Enum):
    INVALID_JSON = "MAT_RULESET_INVALID_JSON"
    DUPLICATE_PROPERTY = "MAT_RULESET_DUPLICATE_PROPERTY"
    UNKNOWN_FIELD = "MAT_RULESET_UNKNOWN_FIELD"
    INVALID_TYPE = "MAT_RULESET_INVALID_TYPE"
    INVALID_ID = "MAT_RULESET_INVALID_ID"
    INVALID_UNICODE = "MAT_RULESET_INVALID_UNICODE"
    NON_NFC = "MAT_RULESET_NON_NFC"
    FLOAT_FORBIDDEN = "MAT_RULESET_FLOAT_FORBIDDEN"
    INVALID_CONSTANT = "MAT_RULESET_INVALID_CONSTANT"
    INVALID_EVIDENCE = "MAT_RULESET_INVALID_EVIDENCE"
    EMPTY_RULES = "MAT_RULESET_EMPTY_RULES"
    DUPLICATE_RULE_REF = "MAT_RULESET_DUPLICATE_RULE_REF"
    INVALID_SCOPE = "MAT_RULESET_INVALID_SCOPE"
    HASH_MISMATCH = "MAT_RULESET_HASH_MISMATCH"
    SNAPSHOT_ID_MISMATCH = "MAT_RULESET_SNAPSHOT_ID_MISMATCH"
    UNKNOWN_SCHEMA = "MAT_RULESET_UNKNOWN_SCHEMA"
    DB_INTEGRITY = "MAT_RULESET_DB_INTEGRITY"


class MaterialRulesetValidationError(ValueError):
    """Stable fail-closed validation error for untrusted snapshot input."""

    def __init__(
        self,
        code: MaterialRulesetErrorCode,
        message: str,
        *,
        path: str = "$",
    ) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value} at {path}: {message}")


class MaterialRulesetIntegrityError(RuntimeError):
    """A persisted snapshot failed revalidation and is a quarantine candidate."""

    quarantine_candidate = True

    def __init__(self, code: MaterialRulesetErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


def _fail(
    code: MaterialRulesetErrorCode,
    message: str,
    *,
    path: str,
) -> NoReturn:
    raise MaterialRulesetValidationError(code, message, path=path)


def _require_exact_fields(
    value: dict[str, Any], expected: frozenset[str], *, path: str
) -> None:
    actual = frozenset(value)
    unknown = sorted(actual - expected)
    if unknown:
        _fail(
            MaterialRulesetErrorCode.UNKNOWN_FIELD,
            f"unknown fields: {unknown}",
            path=path,
        )
    missing = sorted(expected - actual)
    if missing:
        _fail(
            MaterialRulesetErrorCode.UNKNOWN_FIELD,
            f"missing required fields: {missing}",
            path=path,
        )


def _require_dict(value: Any, *, path: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "expected JSON object",
            path=path,
        )
    return value


def _require_list(value: Any, *, path: str) -> list[Any]:
    if type(value) is not list:
        _fail(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "expected JSON array",
            path=path,
        )
    return value


def _require_string(value: Any, *, path: str, nonempty: bool = True) -> str:
    if type(value) is not str:
        _fail(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "expected JSON string",
            path=path,
        )
    if nonempty and not any(not char.isspace() for char in value):
        _fail(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "string must contain a non-whitespace character",
            path=path,
        )
    return value


def _require_int(value: Any, expected: int, *, path: str) -> int:
    if type(value) is not int:
        _fail(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "expected JSON integer",
            path=path,
        )
    if value != expected:
        _fail(
            MaterialRulesetErrorCode.UNKNOWN_SCHEMA,
            f"only version {expected} is supported",
            path=path,
        )
    return value


def _require_false(value: Any, *, path: str) -> bool:
    if type(value) is not bool:
        _fail(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "expected JSON boolean",
            path=path,
        )
    if value is not False:
        _fail(
            MaterialRulesetErrorCode.INVALID_CONSTANT,
            "positive material statements are forbidden",
            path=path,
        )
    return False


def _validate_unicode(value: Any, *, path: str = "$") -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            _fail(
                MaterialRulesetErrorCode.INVALID_UNICODE,
                "string contains a non-Unicode-scalar value",
                path=path,
            )
        if unicodedata.normalize("NFC", value) != value:
            _fail(
                MaterialRulesetErrorCode.NON_NFC,
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
                    MaterialRulesetErrorCode.INVALID_ID,
                    "property names must be ASCII",
                    path=path,
                )
            _validate_unicode(key, path=f"{path}.<property>")
            _validate_unicode(item, path=f"{path}.{key}")


def _reject_float(_value: str) -> NoReturn:
    _fail(
        MaterialRulesetErrorCode.FLOAT_FORBIDDEN,
        "floating-point values are forbidden",
        path="$",
    )


def _reject_constant(_value: str) -> NoReturn:
    _fail(
        MaterialRulesetErrorCode.FLOAT_FORBIDDEN,
        "NaN and Infinity are forbidden",
        path="$",
    )


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail(
                MaterialRulesetErrorCode.DUPLICATE_PROPERTY,
                f"duplicate property {key!r}",
                path="$",
            )
        value[key] = item
    return value


def parse_json_without_duplicates(raw: str | bytes) -> dict[str, Any]:
    """Parse strict UTF-8 JSON while rejecting duplicate properties and floats."""

    if isinstance(raw, bytes):
        if raw.startswith(b"\xef\xbb\xbf"):
            _fail(
                MaterialRulesetErrorCode.INVALID_JSON,
                "UTF-8 BOM is forbidden",
                path="$",
            )
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail(
                MaterialRulesetErrorCode.INVALID_UNICODE,
                "input is not valid UTF-8",
                path="$",
            )
    elif isinstance(raw, str):
        text = raw
        if text.startswith("\ufeff"):
            _fail(
                MaterialRulesetErrorCode.INVALID_JSON,
                "Unicode BOM is forbidden",
                path="$",
            )
        try:
            text.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            _fail(
                MaterialRulesetErrorCode.INVALID_UNICODE,
                "input contains a non-Unicode-scalar value",
                path="$",
            )
    else:
        _fail(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "snapshot input must be str or bytes",
            path="$",
        )
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except MaterialRulesetValidationError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MaterialRulesetValidationError(
            MaterialRulesetErrorCode.INVALID_JSON,
            "malformed JSON",
            path="$",
        ) from exc
    root = _require_dict(value, path="$")
    _validate_unicode(root)
    return root


def validate_ruleset_id(value: str) -> str:
    if type(value) is not str or not _RULESET_ID_RE.fullmatch(value):
        _fail(
            MaterialRulesetErrorCode.INVALID_ID,
            "ruleset_id must match mrs_<32 lowercase hex>",
            path="$.ruleset_id",
        )
    return value


def validate_snapshot_id(value: str) -> str:
    if type(value) is not str or not _SNAPSHOT_ID_RE.fullmatch(value):
        _fail(
            MaterialRulesetErrorCode.INVALID_ID,
            "snapshot_id must match mss_<64 lowercase hex>",
            path="$.snapshot_id",
        )
    return value


def validate_domain_pack_id(value: str) -> str:
    if type(value) is not str or not _DOMAIN_PACK_ID_RE.fullmatch(value):
        _fail(
            MaterialRulesetErrorCode.INVALID_ID,
            "domain_pack_id must use lowercase ASCII segments",
            path="$.domain_pack_id",
        )
    return value


def generate_ruleset_id() -> str:
    """Generate a server-side stable family identity without external state."""

    return f"mrs_{secrets.token_hex(16)}"


def _canonical_set(values: Any, *, path: str) -> tuple[str, ...]:
    items = _require_list(values, path=path)
    strings = tuple(
        _require_string(item, path=f"{path}[{index}]")
        for index, item in enumerate(items)
    )
    return tuple(sorted(set(strings), key=lambda item: item.encode("utf-8")))


@dataclass(frozen=True, slots=True)
class EvidenceBindingV1:
    """The only evidence representation allowed before MAT-EVID-01."""

    @property
    def state(self) -> str:
        return "unbound"

    def to_dict(self) -> dict[str, str]:
        return {"state": "unbound"}


@dataclass(frozen=True, slots=True)
class MaterialRuleScopeV1:
    materials: tuple[str, ...]
    media: tuple[str, ...]
    conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, values in (
            ("materials", self.materials),
            ("media", self.media),
            ("conditions", self.conditions),
        ):
            if type(values) is not tuple or any(
                type(item) is not str for item in values
            ):
                raise TypeError(f"scope {name} must be a tuple of strings")
            if values != tuple(
                sorted(set(values), key=lambda item: item.encode("utf-8"))
            ):
                raise ValueError(f"scope {name} must be unique and canonically ordered")
            _validate_unicode(list(values), path=f"$.scope.{name}")
        if not self.materials or not self.media:
            raise ValueError("scope materials and media must not be empty")

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "materials": list(self.materials),
            "media": list(self.media),
            "conditions": list(self.conditions),
        }


@dataclass(frozen=True, slots=True)
class MaterialRuleV1:
    rule_ref: str
    material: str
    medium: str
    condition: str
    verdict: MaterialConstraintVerdict
    statement: str
    scope: MaterialRuleScopeV1
    evidence_binding: EvidenceBindingV1 = EvidenceBindingV1()

    def __post_init__(self) -> None:
        if type(self.rule_ref) is not str or not _RULE_REF_RE.fullmatch(self.rule_ref):
            raise ValueError("rule_ref must match MR-<uppercase ASCII identifier>")
        for name, value in (
            ("material", self.material),
            ("medium", self.medium),
            ("condition", self.condition),
            ("statement", self.statement),
        ):
            if type(value) is not str or not any(not char.isspace() for char in value):
                raise ValueError(f"{name} must contain a non-whitespace string")
            _validate_unicode(value, path=f"$.rule.{name}")
        if not isinstance(self.verdict, MaterialConstraintVerdict):
            raise TypeError("verdict must use the canonical MaterialConstraintVerdict")
        if not isinstance(self.scope, MaterialRuleScopeV1):
            raise TypeError("scope must be MaterialRuleScopeV1")
        if type(self.evidence_binding) is not EvidenceBindingV1:
            raise TypeError("evidence_binding must be EvidenceBindingV1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_ref": self.rule_ref,
            "material": self.material,
            "medium": self.medium,
            "condition": self.condition,
            "verdict": self.verdict.value,
            "statement": self.statement,
            "scope": self.scope.to_dict(),
            "evidence_binding": self.evidence_binding.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class MaterialRulesetPayloadV1:
    domain_pack_id: str
    rules: tuple[MaterialRuleV1, ...]
    snapshot_schema_version: int = SNAPSHOT_SCHEMA_VERSION
    canonicalization_version: int = CANONICALIZATION_VERSION
    mat_gov_contract_version: str = MAT_GOV_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.snapshot_schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported snapshot schema version")
        if self.canonicalization_version != CANONICALIZATION_VERSION:
            raise ValueError("unsupported canonicalization version")
        if self.mat_gov_contract_version != MAT_GOV_CONTRACT_VERSION:
            raise ValueError("unsupported MAT-GOV contract version")
        # Keep the direct-domain constructor on the same stable fail-closed
        # error contract as the untrusted JSON parser.  Callers must not have
        # to infer an invalid domain-pack identifier from a generic ValueError.
        validate_domain_pack_id(self.domain_pack_id)
        if type(self.rules) is not tuple or not self.rules:
            raise ValueError("rules must be a non-empty tuple")
        if any(type(rule) is not MaterialRuleV1 for rule in self.rules):
            raise TypeError("rules must contain MaterialRuleV1 values")
        refs = [rule.rule_ref for rule in self.rules]
        if len(refs) != len(set(refs)):
            raise ValueError("rule_ref values must be unique")

    @property
    def positive_statement_allowed(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_schema_version": self.snapshot_schema_version,
            "canonicalization_version": self.canonicalization_version,
            "mat_gov_contract_version": self.mat_gov_contract_version,
            "domain_pack_id": self.domain_pack_id,
            "positive_statement_allowed": False,
            "rules": [rule.to_dict() for rule in self.rules],
        }


def _parse_scope(value: Any, *, path: str) -> MaterialRuleScopeV1:
    obj = _require_dict(value, path=path)
    _require_exact_fields(obj, _SCOPE_FIELDS, path=path)
    return MaterialRuleScopeV1(
        materials=_canonical_set(obj["materials"], path=f"{path}.materials"),
        media=_canonical_set(obj["media"], path=f"{path}.media"),
        conditions=_canonical_set(obj["conditions"], path=f"{path}.conditions"),
    )


def _parse_evidence(value: Any, *, path: str) -> EvidenceBindingV1:
    if type(value) is not dict:
        _fail(
            MaterialRulesetErrorCode.INVALID_EVIDENCE,
            'evidence_binding must equal exactly {"state":"unbound"}',
            path=path,
        )
    obj = value
    if frozenset(obj) != _EVIDENCE_FIELDS or obj.get("state") != "unbound":
        _fail(
            MaterialRulesetErrorCode.INVALID_EVIDENCE,
            'evidence_binding must equal exactly {"state":"unbound"}',
            path=path,
        )
    return EvidenceBindingV1()


def _parse_rule(value: Any, *, path: str) -> MaterialRuleV1:
    obj = _require_dict(value, path=path)
    _require_exact_fields(obj, _RULE_FIELDS, path=path)
    rule_ref = _require_string(obj["rule_ref"], path=f"{path}.rule_ref")
    if not _RULE_REF_RE.fullmatch(rule_ref):
        _fail(
            MaterialRulesetErrorCode.INVALID_ID,
            "rule_ref must match MR-<uppercase ASCII identifier>",
            path=f"{path}.rule_ref",
        )
    verdict_value = _require_string(obj["verdict"], path=f"{path}.verdict")
    try:
        verdict = MaterialConstraintVerdict(verdict_value)
    except ValueError as exc:
        raise MaterialRulesetValidationError(
            MaterialRulesetErrorCode.INVALID_CONSTANT,
            "unknown canonical material verdict",
            path=f"{path}.verdict",
        ) from exc
    return MaterialRuleV1(
        rule_ref=rule_ref,
        material=_require_string(obj["material"], path=f"{path}.material"),
        medium=_require_string(obj["medium"], path=f"{path}.medium"),
        condition=_require_string(obj["condition"], path=f"{path}.condition"),
        verdict=verdict,
        statement=_require_string(obj["statement"], path=f"{path}.statement"),
        scope=_parse_scope(obj["scope"], path=f"{path}.scope"),
        evidence_binding=_parse_evidence(
            obj["evidence_binding"], path=f"{path}.evidence_binding"
        ),
    )


def parse_snapshot_payload(raw: str | bytes) -> MaterialRulesetPayloadV1:
    obj = parse_json_without_duplicates(raw)
    _require_exact_fields(obj, _TOP_LEVEL_FIELDS, path="$")
    _require_int(
        obj["snapshot_schema_version"],
        SNAPSHOT_SCHEMA_VERSION,
        path="$.snapshot_schema_version",
    )
    _require_int(
        obj["canonicalization_version"],
        CANONICALIZATION_VERSION,
        path="$.canonicalization_version",
    )
    contract = _require_string(
        obj["mat_gov_contract_version"], path="$.mat_gov_contract_version"
    )
    if contract != MAT_GOV_CONTRACT_VERSION:
        _fail(
            MaterialRulesetErrorCode.UNKNOWN_SCHEMA,
            "unknown MAT-GOV contract version",
            path="$.mat_gov_contract_version",
        )
    domain_pack_id = _require_string(obj["domain_pack_id"], path="$.domain_pack_id")
    validate_domain_pack_id(domain_pack_id)
    _require_false(
        obj["positive_statement_allowed"], path="$.positive_statement_allowed"
    )
    raw_rules = _require_list(obj["rules"], path="$.rules")
    if not raw_rules:
        _fail(
            MaterialRulesetErrorCode.EMPTY_RULES,
            "rules must not be empty",
            path="$.rules",
        )
    rules = tuple(
        _parse_rule(item, path=f"$.rules[{index}]")
        for index, item in enumerate(raw_rules)
    )
    refs = [rule.rule_ref for rule in rules]
    if len(refs) != len(set(refs)):
        _fail(
            MaterialRulesetErrorCode.DUPLICATE_RULE_REF,
            "rule_ref values must be unique",
            path="$.rules",
        )
    return MaterialRulesetPayloadV1(domain_pack_id=domain_pack_id, rules=rules)


def canonicalize_payload(payload: MaterialRulesetPayloadV1) -> bytes:
    if type(payload) is not MaterialRulesetPayloadV1:
        raise TypeError("payload must be MaterialRulesetPayloadV1")
    try:
        text = json.dumps(
            payload.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return text.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaterialRulesetValidationError(
            MaterialRulesetErrorCode.INVALID_UNICODE,
            "payload cannot be serialized as canonical UTF-8 JSON",
            path="$",
        ) from exc


def compute_content_sha256(canonical_bytes: bytes) -> str:
    if type(canonical_bytes) is not bytes:
        raise TypeError("canonical_bytes must be bytes")
    return hashlib.sha256(CONTENT_HASH_DOMAIN + canonical_bytes).hexdigest()


def derive_snapshot_id(ruleset_id: str, content_sha256: str) -> str:
    validate_ruleset_id(ruleset_id)
    if not re.fullmatch(r"[0-9a-f]{64}", content_sha256, flags=re.ASCII):
        _fail(
            MaterialRulesetErrorCode.HASH_MISMATCH,
            "content_sha256 must be 64 lowercase hex characters",
            path="$.content_sha256",
        )
    digest = hashlib.sha256(
        SNAPSHOT_ID_DOMAIN
        + ruleset_id.encode("ascii")
        + b"\x00"
        + content_sha256.encode("ascii")
    ).hexdigest()
    return f"mss_{digest}"


@dataclass(frozen=True, slots=True)
class MaterialRulesetSnapshotV1:
    ruleset_id: str
    snapshot_id: str
    content_sha256: str
    canonical_bytes: bytes
    payload: MaterialRulesetPayloadV1

    def __post_init__(self) -> None:
        validate_ruleset_id(self.ruleset_id)
        validate_snapshot_id(self.snapshot_id)
        if type(self.payload) is not MaterialRulesetPayloadV1:
            raise TypeError("payload must be MaterialRulesetPayloadV1")
        expected_bytes = canonicalize_payload(self.payload)
        if self.canonical_bytes != expected_bytes:
            raise MaterialRulesetIntegrityError(
                MaterialRulesetErrorCode.HASH_MISMATCH,
                "canonical bytes do not match the validated payload",
            )
        expected_hash = compute_content_sha256(expected_bytes)
        if self.content_sha256 != expected_hash:
            raise MaterialRulesetIntegrityError(
                MaterialRulesetErrorCode.HASH_MISMATCH,
                "content hash does not match canonical bytes",
            )
        expected_id = derive_snapshot_id(self.ruleset_id, expected_hash)
        if self.snapshot_id != expected_id:
            raise MaterialRulesetIntegrityError(
                MaterialRulesetErrorCode.SNAPSHOT_ID_MISMATCH,
                "snapshot identity does not match ruleset and content hash",
            )

    @classmethod
    def create(
        cls, ruleset_id: str, payload: MaterialRulesetPayloadV1
    ) -> MaterialRulesetSnapshotV1:
        canonical_bytes = canonicalize_payload(payload)
        content_sha256 = compute_content_sha256(canonical_bytes)
        return cls(
            ruleset_id=ruleset_id,
            snapshot_id=derive_snapshot_id(ruleset_id, content_sha256),
            content_sha256=content_sha256,
            canonical_bytes=canonical_bytes,
            payload=payload,
        )

    @classmethod
    def from_json(cls, ruleset_id: str, raw: str | bytes) -> MaterialRulesetSnapshotV1:
        return cls.create(ruleset_id, parse_snapshot_payload(raw))


def compute_validation_sha256(snapshot: MaterialRulesetSnapshotV1) -> str:
    return hashlib.sha256(
        VALIDATION_HASH_DOMAIN
        + snapshot.snapshot_id.encode("ascii")
        + b"\x00"
        + snapshot.content_sha256.encode("ascii")
    ).hexdigest()


def compute_audit_sha256(event_payload: dict[str, Any]) -> str:
    _validate_unicode(event_payload)
    try:
        encoded = json.dumps(
            event_payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MaterialRulesetValidationError(
            MaterialRulesetErrorCode.INVALID_TYPE,
            "audit payload is not canonical JSON",
            path="$",
        ) from exc
    return hashlib.sha256(AUDIT_HASH_DOMAIN + encoded).hexdigest()
