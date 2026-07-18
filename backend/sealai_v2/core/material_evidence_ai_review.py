"""Immutable, non-authoritative AI cross-review contract for material evidence.

This aggregate is additive to MAT-EVID-01C.  It never represents a verified
human, factual approval, runtime authority, activation, or suitability release.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
import unicodedata
from typing import Any, NoReturn

from sealai_v2.core.contracts import MaterialConstraintVerdict
from sealai_v2.core.material_evidence_review import (
    EvidenceDocumentType,
    EvidenceRightsState,
    ExactLocatorV1,
    IncludedExcerptV1,
    OmittedExcerptV1,
    ReviewedSourceMetadataV1,
    SourceExcerptV1,
    SourceLocatorV1,
    UnavailableLocatorV1,
)
from sealai_v2.core.material_evidence_v2 import (
    EvidenceManifestSnapshotV2,
    MaterialEvidenceV2ErrorCode,
    MaterialEvidenceV2ValidationError,
    MediaIdentityClaimScopeV2,
    MediaIdentityTargetV2,
    MaterialRelationClaimScopeV2,
    MaterialRelationTargetV2,
    parse_json_v2,
)
from sealai_v2.core.material_rulesets import MaterialRulesetSnapshotV1
from sealai_v2.core.medium_catalog import (
    MediumIdentityKind,
    derive_media_id,
    derive_medium_identity_assertion_ref,
)


AI_REVIEW_SCHEMA_VERSION = 1
AI_REVIEW_CANONICALIZATION_VERSION = 1
MAT_EVID_AI_REVIEW_CONTRACT_VERSION = "MAT-EVID-AI-REVIEW.v1"
AI_REVIEW_AUTHORITY = "AI_CROSS_REVIEW_NON_AUTHORITATIVE"
AI_REVIEW_REQUIRED_USER_NOTICE = (
    "KI-gestützte, quellenbasierte Ausschlussprüfung – keine individuelle "
    "technische Freigabe."
)
ZERO_EVENT_HASH = "0" * 64

CONTENT_DOMAIN = b"sealai.material-evidence-ai-review.content.v1\x00"
SNAPSHOT_DOMAIN = b"sealai.material-evidence-ai-review.snapshot.v1\x00"
VALIDATION_DOMAIN = b"sealai.material-evidence-ai-review.validation.v1\x00"
AUDIT_DOMAIN = b"sealai.material-evidence-ai-review.audit.v1\x00"
LIFECYCLE_DOMAIN = b"sealai.material-evidence-ai-review.lifecycle.v1\x00"
SOURCE_ORIGIN_DOMAIN = b"sealai.material-evidence-ai-review.source-origin.v1\x00"

_BATCH_ID_RE = re.compile(r"^mai_[0-9a-f]{32}$", re.ASCII)
_SNAPSHOT_ID_RE = re.compile(r"^mas_[0-9a-f]{64}$", re.ASCII)
_EVIDENCE_SNAPSHOT_ID_RE = re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII)
_RULESET_SNAPSHOT_ID_RE = re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII)
_CLAIM_REF_RE = re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII)
_SOURCE_REF_RE = re.compile(r"^msr_[0-9a-f]{64}$", re.ASCII)
_RULE_REF_RE = re.compile(r"^MR-[A-Z0-9][A-Z0-9._:-]{0,124}$", re.ASCII)
_MEDIA_REF_RE = re.compile(r"^med_[0-9a-f]{64}$", re.ASCII)
_IDENTITY_ASSERTION_REF_RE = re.compile(
    r"^med-norm-identity-sha256:[0-9a-f]{64}$", re.ASCII
)
_DOMAIN_PACK_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


class AIReviewErrorCode(str, Enum):
    INVALID_JSON = "MAT_EVID_AI_REVIEW_INVALID_JSON"
    DUPLICATE_PROPERTY = "MAT_EVID_AI_REVIEW_DUPLICATE_PROPERTY"
    UNKNOWN_FIELD = "MAT_EVID_AI_REVIEW_UNKNOWN_FIELD"
    INVALID_TYPE = "MAT_EVID_AI_REVIEW_INVALID_TYPE"
    INVALID_ID = "MAT_EVID_AI_REVIEW_INVALID_ID"
    INVALID_UNICODE = "MAT_EVID_AI_REVIEW_INVALID_UNICODE"
    NON_NFC = "MAT_EVID_AI_REVIEW_NON_NFC"
    UNKNOWN_SCHEMA = "MAT_EVID_AI_REVIEW_UNKNOWN_SCHEMA"
    NON_CANONICAL_ORDER = "MAT_EVID_AI_REVIEW_NON_CANONICAL_ORDER"
    HASH_MISMATCH = "MAT_EVID_AI_REVIEW_HASH_MISMATCH"
    SNAPSHOT_ID_MISMATCH = "MAT_EVID_AI_REVIEW_SNAPSHOT_ID_MISMATCH"
    SCOPE_MISMATCH = "MAT_EVID_AI_REVIEW_SCOPE_MISMATCH"
    INCOMPLETE_COVERAGE = "MAT_EVID_AI_REVIEW_INCOMPLETE_COVERAGE"
    RIGHTS_BLOCKED = "MAT_EVID_AI_REVIEW_RIGHTS_BLOCKED"
    SOURCE_BLOCKED = "MAT_EVID_AI_REVIEW_SOURCE_BLOCKED"
    POSITIVE_STATEMENT_FORBIDDEN = "MAT_EVID_AI_REVIEW_POSITIVE_FORBIDDEN"
    PRODUCTION_FORBIDDEN = "MAT_EVID_AI_REVIEW_PRODUCTION_FORBIDDEN"
    INVALID_AGENT = "MAT_EVID_AI_REVIEW_INVALID_AGENT"
    INVALID_TRANSITION = "MAT_EVID_AI_REVIEW_INVALID_TRANSITION"
    TENANT_MISMATCH = "MAT_EVID_AI_REVIEW_TENANT_MISMATCH"
    DB_INTEGRITY = "MAT_EVID_AI_REVIEW_DB_INTEGRITY"
    SENSITIVE_DATA_FORBIDDEN = "MAT_EVID_AI_REVIEW_SENSITIVE_DATA_FORBIDDEN"


class AIReviewValidationError(ValueError):
    def __init__(
        self, code: AIReviewErrorCode, message: str, *, path: str = "$"
    ) -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code.value} at {path}: {message}")


class AIReviewIntegrityError(RuntimeError):
    quarantine_candidate = True

    def __init__(self, code: AIReviewErrorCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


class AIReviewState(str, Enum):
    AI_DRAFT = "ai_draft"
    AI_CHALLENGED = "ai_challenged"
    AI_CROSS_REVIEWED_NON_AUTHORITATIVE = "ai_cross_reviewed_non_authoritative"
    CHANGES_REQUIRED = "changes_required"
    QUARANTINED = "quarantined"
    REVOKED = "revoked"


class AIReviewEventType(str, Enum):
    CHALLENGED = "challenged"
    CROSS_REVIEWED = "cross_reviewed_non_authoritative"
    CHANGES_REQUIRED = "changes_required"
    QUARANTINED = "quarantined"
    REVOKED = "revoked"


class AIReviewEnvironment(str, Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    DARK_STAGING = "dark_staging"


class AIClaimPurpose(str, Enum):
    RULE_PRIMARY = "rule_primary"
    RULE_SUPPORTING = "rule_supporting"


class AIEvidenceRisk(str, Enum):
    ORDINARY = "ordinary"
    SAFETY_CRITICAL = "safety_critical"
    HARD_GATE = "hard_gate"
    TEMPERATURE_LIMIT = "temperature_limit"
    FAMILY_WIDE = "family_wide"


class AIMaterialGranularity(str, Enum):
    EXACT_COMPOUND = "exact_compound"
    EXACT_MATERIAL = "exact_material"
    MATERIAL_FAMILY = "material_family"


class AISingleSourceTreatment(str, Enum):
    STANDARD = "standard"
    NARROW_SCOPE = "narrow_scope"
    OPAQUE_BEDINGT = "opaque_bedingt"
    QUARANTINE = "quarantine"


class AgentProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


def _fail(code: AIReviewErrorCode, message: str, *, path: str = "$") -> NoReturn:
    raise AIReviewValidationError(code, message, path=path)


def _text(value: Any, *, path: str, max_chars: int = 1024) -> str:
    if type(value) is not str or not any(not char.isspace() for char in value):
        _fail(
            AIReviewErrorCode.INVALID_TYPE, "expected non-whitespace string", path=path
        )
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _fail(AIReviewErrorCode.INVALID_UNICODE, "invalid Unicode scalar", path=path)
    if unicodedata.normalize("NFC", value) != value:
        _fail(AIReviewErrorCode.NON_NFC, "string must be NFC", path=path)
    if len(value) > max_chars or len(encoded) > max_chars * 4:
        _fail(
            AIReviewErrorCode.INVALID_TYPE, "string exceeds contract limit", path=path
        )
    return value


def _id(value: Any, pattern: re.Pattern[str], *, path: str) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        _fail(AIReviewErrorCode.INVALID_ID, "invalid identifier", path=path)
    return value


def _sha(value: Any, *, path: str) -> str:
    return _id(value, _SHA256_RE, path=path)


def _exact(value: dict[str, Any], fields: frozenset[str], *, path: str) -> None:
    actual = frozenset(value)
    if actual != fields:
        _fail(
            AIReviewErrorCode.UNKNOWN_FIELD,
            f"unknown={sorted(actual - fields)} missing={sorted(fields - actual)}",
            path=path,
        )


def _enum(enum_type: type[Enum], value: Any, *, path: str):
    if type(value) is not str:
        _fail(AIReviewErrorCode.INVALID_TYPE, "expected enum string", path=path)
    try:
        return enum_type(value)
    except ValueError:
        _fail(
            AIReviewErrorCode.INVALID_TYPE, f"unknown {enum_type.__name__}", path=path
        )


def _canonical_tuple(
    values: Any, *, path: str, allow_empty: bool = False
) -> tuple[str, ...]:
    if type(values) not in {list, tuple}:
        _fail(AIReviewErrorCode.INVALID_TYPE, "expected array", path=path)
    result = tuple(
        _text(item, path=f"{path}[{index}]") for index, item in enumerate(values)
    )
    if not allow_empty and not result:
        _fail(AIReviewErrorCode.INVALID_TYPE, "array must not be empty", path=path)
    expected = tuple(sorted(set(result), key=lambda item: item.encode("utf-8")))
    if result != expected:
        _fail(
            AIReviewErrorCode.NON_CANONICAL_ORDER,
            "array must be unique and UTF-8-byte ordered",
            path=path,
        )
    return result


def _canonical_json(value: dict[str, Any]) -> bytes:
    def validate(item: Any, path: str) -> None:
        if item is None or type(item) in {bool, int}:
            return
        if type(item) is str:
            _text(item, path=path, max_chars=max(1024, len(item)))
            return
        if type(item) is list:
            for index, child in enumerate(item):
                validate(child, f"{path}[{index}]")
            return
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or not key.isascii():
                    _fail(
                        AIReviewErrorCode.INVALID_TYPE,
                        "JSON object keys must be ASCII strings",
                        path=path,
                    )
                validate(child, f"{path}.{key}")
            return
        _fail(AIReviewErrorCode.INVALID_TYPE, "outside exact JSON domain", path=path)

    validate(value, "$")
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_JSON, "cannot canonicalize JSON"
        ) from exc


@dataclass(frozen=True, slots=True)
class AgentExecutionIsolationV1:
    tools_enabled: bool
    mcp_enabled: bool
    hooks_enabled: bool
    web_search_requests: int
    web_fetch_requests: int
    session_persistence_enabled: bool

    def __post_init__(self) -> None:
        if any(
            type(value) is not bool
            for value in (
                self.tools_enabled,
                self.mcp_enabled,
                self.hooks_enabled,
                self.session_persistence_enabled,
            )
        ):
            _fail(AIReviewErrorCode.INVALID_TYPE, "isolation flags must be booleans")
        if (
            self.tools_enabled
            or self.mcp_enabled
            or self.hooks_enabled
            or self.session_persistence_enabled
            or type(self.web_search_requests) is not int
            or self.web_search_requests != 0
            or type(self.web_fetch_requests) is not int
            or self.web_fetch_requests != 0
        ):
            _fail(
                AIReviewErrorCode.INVALID_AGENT,
                "challenger isolation must disable tools, MCP, hooks, web and sessions",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hooks_enabled": False,
            "mcp_enabled": False,
            "session_persistence_enabled": False,
            "tools_enabled": False,
            "web_fetch_requests": 0,
            "web_search_requests": 0,
        }


@dataclass(frozen=True, slots=True)
class CreatorAgentRunV1:
    agent_model: str
    agent_version: str
    prompt_version: str
    prompt_sha256: str
    run_id: str
    input_sha256: str
    output_sha256: str
    agent_provider: AgentProvider = AgentProvider.OPENAI

    def __post_init__(self) -> None:
        if self.agent_provider is not AgentProvider.OPENAI:
            _fail(AIReviewErrorCode.INVALID_AGENT, "creator provider must be openai")
        for name, value in (
            ("agent_model", self.agent_model),
            ("agent_version", self.agent_version),
            ("prompt_version", self.prompt_version),
            ("run_id", self.run_id),
        ):
            _text(value, path=f"$.creator.{name}", max_chars=256)
        for name, value in (
            ("prompt_sha256", self.prompt_sha256),
            ("input_sha256", self.input_sha256),
            ("output_sha256", self.output_sha256),
        ):
            _sha(value, path=f"$.creator.{name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_model": self.agent_model,
            "agent_provider": self.agent_provider.value,
            "agent_version": self.agent_version,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "prompt_sha256": self.prompt_sha256,
            "prompt_version": self.prompt_version,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class ChallengerAgentRunV1:
    agent_version: str
    prompt_version: str
    prompt_sha256: str
    run_id: str
    audit_input_sha256: str
    audit_output_sha256: str
    isolation: AgentExecutionIsolationV1
    agent_provider: AgentProvider = AgentProvider.ANTHROPIC
    agent_model: str = "claude-sonnet-5"

    def __post_init__(self) -> None:
        if (
            self.agent_provider is not AgentProvider.ANTHROPIC
            or self.agent_model != "claude-sonnet-5"
        ):
            _fail(
                AIReviewErrorCode.INVALID_AGENT,
                "challenger must be exactly anthropic/claude-sonnet-5",
            )
        for name, value in (
            ("agent_version", self.agent_version),
            ("prompt_version", self.prompt_version),
            ("run_id", self.run_id),
        ):
            _text(value, path=f"$.challenger.{name}", max_chars=256)
        for name, value in (
            ("prompt_sha256", self.prompt_sha256),
            ("audit_input_sha256", self.audit_input_sha256),
            ("audit_output_sha256", self.audit_output_sha256),
        ):
            _sha(value, path=f"$.challenger.{name}")
        if type(self.isolation) is not AgentExecutionIsolationV1:
            _fail(AIReviewErrorCode.INVALID_AGENT, "invalid challenger isolation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_model": self.agent_model,
            "agent_provider": self.agent_provider.value,
            "agent_version": self.agent_version,
            "audit_input_sha256": self.audit_input_sha256,
            "audit_output_sha256": self.audit_output_sha256,
            "isolation": self.isolation.to_dict(),
            "prompt_sha256": self.prompt_sha256,
            "prompt_version": self.prompt_version,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class AdjudicatorAgentRunV1:
    agent_model: str
    agent_version: str
    prompt_version: str
    prompt_sha256: str
    run_id: str
    input_sha256: str
    output_sha256: str
    agent_provider: AgentProvider = AgentProvider.OPENAI

    def __post_init__(self) -> None:
        if self.agent_provider is not AgentProvider.OPENAI:
            _fail(
                AIReviewErrorCode.INVALID_AGENT, "adjudicator provider must be openai"
            )
        for name, value in (
            ("agent_model", self.agent_model),
            ("agent_version", self.agent_version),
            ("prompt_version", self.prompt_version),
            ("run_id", self.run_id),
        ):
            _text(value, path=f"$.adjudicator.{name}", max_chars=256)
        for name, value in (
            ("prompt_sha256", self.prompt_sha256),
            ("input_sha256", self.input_sha256),
            ("output_sha256", self.output_sha256),
        ):
            _sha(value, path=f"$.adjudicator.{name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_model": self.agent_model,
            "agent_provider": self.agent_provider.value,
            "agent_version": self.agent_version,
            "input_sha256": self.input_sha256,
            "output_sha256": self.output_sha256,
            "prompt_sha256": self.prompt_sha256,
            "prompt_version": self.prompt_version,
            "run_id": self.run_id,
        }


@dataclass(frozen=True, slots=True)
class AISourceContextV1:
    metadata: ReviewedSourceMetadataV1

    def __post_init__(self) -> None:
        if type(self.metadata) is not ReviewedSourceMetadataV1:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid source metadata")

    @property
    def source_ref(self) -> str:
        return self.metadata.source_ref

    @property
    def origin_ref(self) -> str:
        """Bind the exact Evidence-v2 source identity, not a creator publisher label."""

        return derive_source_origin_ref(
            document_id=self.metadata.document_id,
            document_revision=self.metadata.document_revision,
            publication_edition=self.metadata.publication_edition,
            content_sha256=self.metadata.content_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.metadata.to_dict(),
            "origin_ref": self.origin_ref,
        }


def derive_source_origin_ref(
    *,
    document_id: str,
    document_revision: str,
    publication_edition: str,
    content_sha256: str,
) -> str:
    """Derive a neutral reference from the complete bound Evidence source identity.

    This deliberately does not claim publisher independence. Organizational
    independence is a separate Claude challenge judgment and may not be inferred
    from creator-controlled display metadata.
    """

    for name, value in (
        ("document_id", document_id),
        ("document_revision", document_revision),
        ("publication_edition", publication_edition),
    ):
        _text(value, path=f"$.source.{name}", max_chars=256)
    _sha(content_sha256, path="$.source.content_sha256")
    value = {
        "content_sha256": content_sha256,
        "document_id": document_id,
        "document_revision": document_revision,
        "publication_edition": publication_edition,
    }
    return (
        "mso_"
        + hashlib.sha256(
            SOURCE_ORIGIN_DOMAIN
            + json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class AIClaimContextV1:
    claim_ref: str
    rule_ref: str
    purpose: AIClaimPurpose
    claim_text: str
    scope: MaterialRelationClaimScopeV2
    source_refs: tuple[str, ...]
    primary_source_refs: tuple[str, ...]
    seal_type_scope: str
    temperature_scope: str
    application_scope: str
    conditions_and_exclusions: str
    expected_verdict: MaterialConstraintVerdict
    evidence_risk: AIEvidenceRisk
    material_granularity: AIMaterialGranularity
    single_source_treatment: AISingleSourceTreatment
    conflicting_claim_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _id(self.claim_ref, _CLAIM_REF_RE, path="$.claim.claim_ref")
        _id(self.rule_ref, _RULE_REF_RE, path="$.claim.rule_ref")
        if type(self.purpose) is not AIClaimPurpose:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid claim purpose")
        _text(self.claim_text, path="$.claim.claim_text", max_chars=512)
        if type(self.scope) is not MaterialRelationClaimScopeV2:
            _fail(
                AIReviewErrorCode.SCOPE_MISMATCH,
                "AI rule review requires material_relation scope",
            )
        for media_ref in self.scope.media:
            _id(media_ref, _MEDIA_REF_RE, path="$.claim.scope.media")
        for name, values, pattern in (
            ("source_refs", self.source_refs, _SOURCE_REF_RE),
            ("primary_source_refs", self.primary_source_refs, _SOURCE_REF_RE),
            ("conflicting_claim_refs", self.conflicting_claim_refs, _CLAIM_REF_RE),
        ):
            if type(values) is not tuple:
                _fail(AIReviewErrorCode.INVALID_TYPE, f"{name} must be a tuple")
            if name != "conflicting_claim_refs" and not values:
                _fail(AIReviewErrorCode.SOURCE_BLOCKED, f"{name} must not be empty")
            if any(
                type(item) is not str or not pattern.fullmatch(item) for item in values
            ):
                _fail(AIReviewErrorCode.INVALID_ID, f"invalid {name}")
            if values != tuple(sorted(set(values))):
                _fail(AIReviewErrorCode.NON_CANONICAL_ORDER, f"invalid {name} order")
        if not set(self.primary_source_refs) <= set(self.source_refs):
            _fail(
                AIReviewErrorCode.SOURCE_BLOCKED,
                "primary sources must be claim sources",
            )
        for name, value in (
            ("seal_type_scope", self.seal_type_scope),
            ("temperature_scope", self.temperature_scope),
            ("application_scope", self.application_scope),
            ("conditions_and_exclusions", self.conditions_and_exclusions),
        ):
            _text(value, path=f"$.claim.{name}", max_chars=512)
        if self.expected_verdict not in {
            MaterialConstraintVerdict.UNVERTRAEGLICH,
            MaterialConstraintVerdict.BEDINGT,
        }:
            _fail(
                AIReviewErrorCode.POSITIVE_STATEMENT_FORBIDDEN,
                "only unvertraeglich or opaque bedingt are permitted",
            )
        for enum_value, enum_type in (
            (self.evidence_risk, AIEvidenceRisk),
            (self.material_granularity, AIMaterialGranularity),
            (self.single_source_treatment, AISingleSourceTreatment),
        ):
            if type(enum_value) is not enum_type:
                _fail(AIReviewErrorCode.INVALID_TYPE, "invalid closed claim enum")

    @property
    def ai_assisted(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ai_assisted": True,
            "application_scope": self.application_scope,
            "claim_ref": self.claim_ref,
            "claim_text": self.claim_text,
            "conditions_and_exclusions": self.conditions_and_exclusions,
            "conflicting_claim_refs": list(self.conflicting_claim_refs),
            "evidence_risk": self.evidence_risk.value,
            "expected_verdict": self.expected_verdict.value,
            "material_granularity": self.material_granularity.value,
            "primary_source_refs": list(self.primary_source_refs),
            "purpose": self.purpose.value,
            "rule_ref": self.rule_ref,
            "scope": self.scope.to_dict(),
            "seal_type_scope": self.seal_type_scope,
            "single_source_treatment": self.single_source_treatment.value,
            "source_refs": list(self.source_refs),
            "temperature_scope": self.temperature_scope,
        }


@dataclass(frozen=True, slots=True)
class AIMediumIdentityClaimContextV1:
    """One source-derived assertion about an otherwise inert media candidate."""

    claim_ref: str
    claim_text: str
    scope: MediaIdentityClaimScopeV2
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _id(self.claim_ref, _CLAIM_REF_RE, path="$.medium_identity.claim.claim_ref")
        _text(
            self.claim_text,
            path="$.medium_identity.claim.claim_text",
            max_chars=512,
        )
        if type(self.scope) is not MediaIdentityClaimScopeV2:
            _fail(
                AIReviewErrorCode.SCOPE_MISMATCH,
                "media identity claim requires media_identity scope",
            )
        if type(self.source_refs) is not tuple or not self.source_refs:
            _fail(AIReviewErrorCode.SOURCE_BLOCKED, "source_refs must not be empty")
        for source_ref in self.source_refs:
            _id(
                source_ref,
                _SOURCE_REF_RE,
                path="$.medium_identity.claim.source_refs",
            )
        if self.source_refs != tuple(sorted(set(self.source_refs))):
            _fail(
                AIReviewErrorCode.NON_CANONICAL_ORDER,
                "media identity source_refs must be unique and ordered",
            )

    @property
    def ai_assisted(self) -> bool:
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ai_assisted": True,
            "claim_kind": "media_identity",
            "claim_ref": self.claim_ref,
            "claim_text": self.claim_text,
            "scope": self.scope.to_dict(),
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True, slots=True)
class AIMediumIdentityContextV1:
    """Non-authoritative, source-bound MED-NORM identity candidate.

    It is intentionally not a ``MediumCatalogEntryV1`` and cannot cross the
    verified-human catalog capability boundary.
    """

    media_ref: str
    canonical_name: str
    identity_kind: MediumIdentityKind
    aliases: tuple[str, ...]
    identity_assertion_ref: str
    evidence_snapshot_id: str
    evidence_content_sha256: str
    claims: tuple[AIMediumIdentityClaimContextV1, ...]

    def __post_init__(self) -> None:
        _id(self.media_ref, _MEDIA_REF_RE, path="$.medium_identity.media_ref")
        _text(
            self.canonical_name,
            path="$.medium_identity.canonical_name",
            max_chars=256,
        )
        if type(self.identity_kind) is not MediumIdentityKind:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid medium identity kind")
        if self.media_ref != derive_media_id(self.canonical_name, self.identity_kind):
            _fail(
                AIReviewErrorCode.HASH_MISMATCH,
                "media_ref is not derived from the exact structured identity",
            )
        if type(self.aliases) is not tuple:
            _fail(AIReviewErrorCode.INVALID_TYPE, "aliases must be a tuple")
        for index, alias in enumerate(self.aliases):
            _text(alias, path=f"$.medium_identity.aliases[{index}]", max_chars=256)
        expected_aliases = tuple(
            sorted(set(self.aliases), key=lambda item: item.encode("utf-8"))
        )
        if self.aliases != expected_aliases or self.canonical_name in self.aliases:
            _fail(
                AIReviewErrorCode.NON_CANONICAL_ORDER,
                "aliases must be unique, ordered, and exclude canonical_name",
            )
        _id(
            self.identity_assertion_ref,
            _IDENTITY_ASSERTION_REF_RE,
            path="$.medium_identity.identity_assertion_ref",
        )
        if self.identity_assertion_ref != derive_medium_identity_assertion_ref(
            media_id=self.media_ref,
            canonical_name=self.canonical_name,
            identity_kind=self.identity_kind,
            aliases=self.aliases,
        ):
            _fail(
                AIReviewErrorCode.HASH_MISMATCH,
                "identity assertion does not bind the exact media candidate",
            )
        _id(
            self.evidence_snapshot_id,
            _EVIDENCE_SNAPSHOT_ID_RE,
            path="$.medium_identity.evidence_snapshot_id",
        )
        _sha(
            self.evidence_content_sha256,
            path="$.medium_identity.evidence_content_sha256",
        )
        if (
            type(self.claims) is not tuple
            or not self.claims
            or any(
                type(item) is not AIMediumIdentityClaimContextV1 for item in self.claims
            )
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "media identity claims must be a non-empty typed tuple",
            )
        refs = tuple(item.claim_ref for item in self.claims)
        if refs != tuple(sorted(set(refs))):
            _fail(
                AIReviewErrorCode.NON_CANONICAL_ORDER,
                "media identity claims must be unique and ordered",
            )
        if any(
            claim.scope.media_ref != self.media_ref
            or claim.scope.identity_assertion_ref != self.identity_assertion_ref
            for claim in self.claims
        ):
            _fail(
                AIReviewErrorCode.SCOPE_MISMATCH,
                "media identity claim scope differs from its exact candidate",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "aliases": list(self.aliases),
            "canonical_name": self.canonical_name,
            "claims": [item.to_dict() for item in self.claims],
            "evidence_content_sha256": self.evidence_content_sha256,
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "identity_assertion_ref": self.identity_assertion_ref,
            "identity_kind": self.identity_kind.value,
            "media_ref": self.media_ref,
        }


@dataclass(frozen=True, slots=True)
class AIReviewPayloadV1:
    environment: AIReviewEnvironment
    tenant_id: str
    domain_pack_id: str
    ruleset_snapshot_id: str
    ruleset_content_sha256: str
    evidence_snapshot_id: str
    evidence_content_sha256: str
    creator: CreatorAgentRunV1
    sources: tuple[AISourceContextV1, ...]
    media_identities: tuple[AIMediumIdentityContextV1, ...]
    claims: tuple[AIClaimContextV1, ...]
    ai_review_schema_version: int = AI_REVIEW_SCHEMA_VERSION
    canonicalization_version: int = AI_REVIEW_CANONICALIZATION_VERSION
    mat_evid_ai_review_contract_version: str = MAT_EVID_AI_REVIEW_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if type(self.environment) is not AIReviewEnvironment:
            _fail(
                AIReviewErrorCode.PRODUCTION_FORBIDDEN,
                "environment must be an exact non-production enum",
            )
        _text(self.tenant_id, path="$.tenant_id", max_chars=255)
        _id(self.domain_pack_id, _DOMAIN_PACK_ID_RE, path="$.domain_pack_id")
        _id(
            self.ruleset_snapshot_id,
            _RULESET_SNAPSHOT_ID_RE,
            path="$.ruleset_snapshot_id",
        )
        _sha(self.ruleset_content_sha256, path="$.ruleset_content_sha256")
        _id(
            self.evidence_snapshot_id,
            _EVIDENCE_SNAPSHOT_ID_RE,
            path="$.evidence_snapshot_id",
        )
        _sha(self.evidence_content_sha256, path="$.evidence_content_sha256")
        if (
            type(self.ai_review_schema_version) is not int
            or self.ai_review_schema_version != AI_REVIEW_SCHEMA_VERSION
            or type(self.canonicalization_version) is not int
            or self.canonicalization_version != AI_REVIEW_CANONICALIZATION_VERSION
            or self.mat_evid_ai_review_contract_version
            != MAT_EVID_AI_REVIEW_CONTRACT_VERSION
        ):
            _fail(AIReviewErrorCode.UNKNOWN_SCHEMA, "unsupported AI review contract")
        if type(self.creator) is not CreatorAgentRunV1:
            _fail(AIReviewErrorCode.INVALID_AGENT, "invalid creator run")
        for name, values, expected_type in (
            ("sources", self.sources, AISourceContextV1),
            ("media_identities", self.media_identities, AIMediumIdentityContextV1),
            ("claims", self.claims, AIClaimContextV1),
        ):
            if (
                type(values) is not tuple
                or not values
                or any(type(item) is not expected_type for item in values)
            ):
                _fail(AIReviewErrorCode.INVALID_TYPE, f"invalid {name}")
        source_refs = tuple(item.source_ref for item in self.sources)
        claim_refs = tuple(item.claim_ref for item in self.claims)
        identity_refs = tuple(item.media_ref for item in self.media_identities)
        identity_claim_refs = tuple(
            claim.claim_ref
            for identity in self.media_identities
            for claim in identity.claims
        )
        if source_refs != tuple(sorted(set(source_refs))):
            _fail(AIReviewErrorCode.NON_CANONICAL_ORDER, "sources must be ordered")
        if claim_refs != tuple(sorted(set(claim_refs))):
            _fail(AIReviewErrorCode.NON_CANONICAL_ORDER, "claims must be ordered")
        if identity_refs != tuple(sorted(set(identity_refs))):
            _fail(
                AIReviewErrorCode.NON_CANONICAL_ORDER,
                "media identities must be unique and ordered",
            )
        if set(claim_refs) & set(identity_claim_refs) or len(
            identity_claim_refs
        ) != len(set(identity_claim_refs)):
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "claim references must be globally unique",
            )
        used_source_refs = {
            ref for claim in self.claims for ref in claim.source_refs
        } | {
            ref
            for identity in self.media_identities
            for claim in identity.claims
            for ref in claim.source_refs
        }
        if used_source_refs != set(source_refs):
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "every and only every source must be used",
            )
        referenced_media = {
            media_ref for claim in self.claims for media_ref in claim.scope.media
        }
        if referenced_media != set(identity_refs):
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "every and only every rule medium needs an AI-reviewed identity candidate",
            )
        claim_ref_set = set(claim_refs)
        for claim in self.claims:
            if (
                claim.claim_ref in claim.conflicting_claim_refs
                or not set(claim.conflicting_claim_refs) <= claim_ref_set
            ):
                _fail(
                    AIReviewErrorCode.INCOMPLETE_COVERAGE,
                    "conflict references must identify other claims in the snapshot",
                )

    @property
    def positive_statement_allowed(self) -> bool:
        return False

    @property
    def authority(self) -> str:
        return AI_REVIEW_AUTHORITY

    @property
    def required_user_notice(self) -> str:
        return AI_REVIEW_REQUIRED_USER_NOTICE

    def eligibility_failures(self) -> tuple[str, ...]:
        failures: list[str] = []
        source_by_ref = {item.source_ref: item for item in self.sources}
        primary_source_types = {
            EvidenceDocumentType.MANUFACTURER_DATASHEET,
            EvidenceDocumentType.PEER_REVIEWED_PUBLICATION,
            EvidenceDocumentType.REGULATORY_DOCUMENT,
            EvidenceDocumentType.TECHNICAL_REPORT,
        }
        for source in self.sources:
            if source.metadata.rights_state in {
                EvidenceRightsState.UNKNOWN,
                EvidenceRightsState.RESTRICTED,
            }:
                failures.append(f"rights:{source.source_ref}")
            if type(source.metadata.locator) is UnavailableLocatorV1:
                failures.append(f"locator:{source.source_ref}")
            if type(source.metadata.excerpt) is OmittedExcerptV1:
                failures.append(f"excerpt:{source.source_ref}")
        for claim in self.claims:
            bound_primary_sources = {
                source_by_ref[source_ref].origin_ref
                for source_ref in claim.primary_source_refs
            }
            if any(
                source_by_ref[source_ref].metadata.document_type
                not in primary_source_types
                for source_ref in claim.primary_source_refs
            ):
                failures.append(f"primary_source_quality:{claim.claim_ref}")
            if claim.conflicting_claim_refs and (
                claim.expected_verdict is not MaterialConstraintVerdict.BEDINGT
            ):
                failures.append(f"conflict:{claim.claim_ref}")
            if len(bound_primary_sources) < 2:
                if claim.material_granularity is AIMaterialGranularity.MATERIAL_FAMILY:
                    failures.append(f"family_single_source:{claim.claim_ref}")
                elif (
                    claim.single_source_treatment is AISingleSourceTreatment.QUARANTINE
                ):
                    failures.append(f"single_source_quarantine:{claim.claim_ref}")
                elif (
                    claim.single_source_treatment is AISingleSourceTreatment.STANDARD
                    and claim.evidence_risk is not AIEvidenceRisk.ORDINARY
                ):
                    failures.append(
                        f"single_source_treatment_required:{claim.claim_ref}"
                    )
                elif (
                    claim.single_source_treatment
                    is AISingleSourceTreatment.OPAQUE_BEDINGT
                    and claim.expected_verdict is not MaterialConstraintVerdict.BEDINGT
                ):
                    failures.append(f"opaque_treatment_mismatch:{claim.claim_ref}")
        return tuple(sorted(failures))

    @property
    def audit_claim_refs(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                [item.claim_ref for item in self.claims]
                + [
                    claim.claim_ref
                    for identity in self.media_identities
                    for claim in identity.claims
                ]
            )
        )

    def audit_claims(self) -> tuple[dict[str, Any], ...]:
        claims: list[dict[str, Any]] = [
            {"claim_kind": "material_rule", **item.to_dict()} for item in self.claims
        ]
        claims.extend(
            claim.to_dict()
            for identity in self.media_identities
            for claim in identity.claims
        )
        return tuple(sorted(claims, key=lambda item: item["claim_ref"]))

    def validate_against(
        self,
        ruleset: MaterialRulesetSnapshotV1,
        evidence: EvidenceManifestSnapshotV2,
        media_identity_evidence: tuple[EvidenceManifestSnapshotV2, ...],
    ) -> None:
        if type(ruleset) is not MaterialRulesetSnapshotV1:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid ruleset snapshot")
        if type(evidence) is not EvidenceManifestSnapshotV2:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid evidence snapshot")
        if type(media_identity_evidence) is not tuple or any(
            type(item) is not EvidenceManifestSnapshotV2
            for item in media_identity_evidence
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "media identity evidence must be an exact typed tuple",
            )
        if (
            ruleset.snapshot_id != self.ruleset_snapshot_id
            or ruleset.content_sha256 != self.ruleset_content_sha256
            or evidence.snapshot_id != self.evidence_snapshot_id
            or evidence.content_sha256 != self.evidence_content_sha256
        ):
            _fail(AIReviewErrorCode.HASH_MISMATCH, "snapshot/hash binding drift")
        if (
            ruleset.payload.domain_pack_id != self.domain_pack_id
            or evidence.payload.domain_pack_id != self.domain_pack_id
        ):
            _fail(AIReviewErrorCode.SCOPE_MISMATCH, "domain pack drift")
        if (
            type(evidence.payload.target) is not MaterialRelationTargetV2
            or evidence.payload.target.ruleset_snapshot_id != ruleset.snapshot_id
        ):
            _fail(AIReviewErrorCode.SCOPE_MISMATCH, "evidence target drift")
        rules = {rule.rule_ref: rule for rule in ruleset.payload.rules}
        evidence_claims = {claim.claim_ref: claim for claim in evidence.payload.claims}
        evidence_sources = {
            source.source_ref: source for source in evidence.payload.sources
        }
        bindings = {
            (binding.rule_ref, binding.claim_ref)
            for binding in evidence.payload.rule_claim_bindings
        }
        expected_bindings = {(claim.rule_ref, claim.claim_ref) for claim in self.claims}
        if bindings != expected_bindings:
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "rule-to-claim binding set differs from the exact AI review scope",
            )
        if set(evidence_claims) != {claim.claim_ref for claim in self.claims}:
            _fail(AIReviewErrorCode.INCOMPLETE_COVERAGE, "claim coverage drift")
        all_evidence_sources = dict(evidence_sources)
        identity_evidence_by_id = {
            item.snapshot_id: item for item in media_identity_evidence
        }
        if len(identity_evidence_by_id) != len(media_identity_evidence):
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "duplicate media identity evidence snapshot",
            )
        if set(identity_evidence_by_id) != {
            item.evidence_snapshot_id for item in self.media_identities
        }:
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "media identity evidence coverage drift",
            )
        for identity in self.media_identities:
            identity_evidence = identity_evidence_by_id[identity.evidence_snapshot_id]
            if (
                identity_evidence.content_sha256 != identity.evidence_content_sha256
                or identity_evidence.payload.domain_pack_id != self.domain_pack_id
                or type(identity_evidence.payload.target) is not MediaIdentityTargetV2
                or identity_evidence.payload.target.media_ref != identity.media_ref
            ):
                _fail(
                    AIReviewErrorCode.HASH_MISMATCH,
                    "media identity evidence binding drift",
                )
            identity_claims = {
                item.claim_ref: item for item in identity_evidence.payload.claims
            }
            if set(identity_claims) != {item.claim_ref for item in identity.claims}:
                _fail(
                    AIReviewErrorCode.INCOMPLETE_COVERAGE,
                    "media identity claim coverage drift",
                )
            for claim in identity.claims:
                evidence_claim = identity_claims[claim.claim_ref]
                if (
                    claim.claim_text != evidence_claim.claim_text
                    or claim.scope != evidence_claim.scope
                    or claim.source_refs != evidence_claim.source_refs
                ):
                    _fail(
                        AIReviewErrorCode.SCOPE_MISMATCH,
                        "media identity claim or scope drift",
                    )
            for source in identity_evidence.payload.sources:
                previous = all_evidence_sources.setdefault(source.source_ref, source)
                if previous != source:
                    _fail(
                        AIReviewErrorCode.HASH_MISMATCH,
                        "same source_ref has conflicting source identity",
                    )
        if set(all_evidence_sources) != {source.source_ref for source in self.sources}:
            _fail(AIReviewErrorCode.INCOMPLETE_COVERAGE, "source coverage drift")
        for source in self.sources:
            evidence_source = all_evidence_sources[source.source_ref]
            if (
                source.metadata.document_id,
                source.metadata.document_revision,
                source.metadata.publication_edition,
                source.metadata.content_sha256,
            ) != (
                evidence_source.document_id,
                evidence_source.document_revision,
                evidence_source.publication_edition,
                evidence_source.content_sha256,
            ):
                _fail(AIReviewErrorCode.HASH_MISMATCH, "source identity drift")
        primary_by_rule: dict[str, list[AIClaimContextV1]] = {}
        for claim in self.claims:
            evidence_claim = evidence_claims[claim.claim_ref]
            if (
                claim.claim_text != evidence_claim.claim_text
                or claim.scope != evidence_claim.scope
                or claim.source_refs != evidence_claim.source_refs
            ):
                _fail(AIReviewErrorCode.SCOPE_MISMATCH, "claim or binding drift")
            rule = rules.get(claim.rule_ref)
            if rule is None:
                _fail(AIReviewErrorCode.INCOMPLETE_COVERAGE, "foreign rule")
            if rule.verdict not in {
                MaterialConstraintVerdict.UNVERTRAEGLICH,
                MaterialConstraintVerdict.BEDINGT,
            }:
                _fail(
                    AIReviewErrorCode.POSITIVE_STATEMENT_FORBIDDEN,
                    "rule pack contains a positive verdict",
                )
            if claim.expected_verdict is not rule.verdict:
                _fail(AIReviewErrorCode.SCOPE_MISMATCH, "expected verdict drift")
            if (
                len(rule.scope.materials) != 1
                or len(rule.scope.media) != 1
                or len(rule.scope.conditions) != 1
                or rule.material != rule.scope.materials[0]
                or rule.medium != rule.scope.media[0]
                or rule.condition != rule.scope.conditions[0]
                or claim.scope.materials != rule.scope.materials
                or claim.scope.media != rule.scope.media
                or claim.scope.conditions != rule.scope.conditions
            ):
                _fail(AIReviewErrorCode.SCOPE_MISMATCH, "rule is not atomic")
            if claim.purpose is AIClaimPurpose.RULE_PRIMARY:
                primary_by_rule.setdefault(claim.rule_ref, []).append(claim)
        if set(rules) != {claim.rule_ref for claim in self.claims}:
            _fail(AIReviewErrorCode.INCOMPLETE_COVERAGE, "rule coverage drift")
        for rule_ref, rule in rules.items():
            primary = primary_by_rule.get(rule_ref, [])
            if len(primary) != 1 or primary[0].claim_text != rule.statement:
                _fail(
                    AIReviewErrorCode.INCOMPLETE_COVERAGE,
                    "each rule requires one byte-identical primary claim",
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ai_review_schema_version": self.ai_review_schema_version,
            "authority": AI_REVIEW_AUTHORITY,
            "canonicalization_version": self.canonicalization_version,
            "claims": [item.to_dict() for item in self.claims],
            "creator": self.creator.to_dict(),
            "domain_pack_id": self.domain_pack_id,
            "environment": self.environment.value,
            "evidence_content_sha256": self.evidence_content_sha256,
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "mat_evid_ai_review_contract_version": (
                self.mat_evid_ai_review_contract_version
            ),
            "media_identities": [item.to_dict() for item in self.media_identities],
            "positive_statement_allowed": False,
            "required_user_notice": AI_REVIEW_REQUIRED_USER_NOTICE,
            "ruleset_content_sha256": self.ruleset_content_sha256,
            "ruleset_snapshot_id": self.ruleset_snapshot_id,
            "sources": [item.to_dict() for item in self.sources],
            "tenant_id": self.tenant_id,
        }


def canonicalize_ai_review_payload(payload: AIReviewPayloadV1) -> bytes:
    if type(payload) is not AIReviewPayloadV1:
        raise TypeError("payload must be AIReviewPayloadV1")
    return _canonical_json(payload.to_dict())


def compute_ai_review_content_sha256(canonical_bytes: bytes) -> str:
    if type(canonical_bytes) is not bytes:
        raise TypeError("canonical_bytes must be bytes")
    return hashlib.sha256(CONTENT_DOMAIN + canonical_bytes).hexdigest()


def derive_ai_review_snapshot_id(batch_id: str, content_sha256: str) -> str:
    validate_ai_review_batch_id(batch_id)
    _sha(content_sha256, path="$.content_sha256")
    digest = hashlib.sha256(
        SNAPSHOT_DOMAIN
        + batch_id.encode("ascii")
        + b"\x00"
        + content_sha256.encode("ascii")
    ).hexdigest()
    return f"mas_{digest}"


def validate_ai_review_batch_id(value: str) -> str:
    return _id(value, _BATCH_ID_RE, path="$.batch_id")


def validate_ai_review_snapshot_id(value: str) -> str:
    return _id(value, _SNAPSHOT_ID_RE, path="$.review_snapshot_id")


@dataclass(frozen=True, slots=True)
class AIReviewSnapshotV1:
    batch_id: str
    review_snapshot_id: str
    content_sha256: str
    canonical_bytes: bytes
    payload: AIReviewPayloadV1

    def __post_init__(self) -> None:
        validate_ai_review_batch_id(self.batch_id)
        validate_ai_review_snapshot_id(self.review_snapshot_id)
        if type(self.payload) is not AIReviewPayloadV1:
            raise TypeError("payload must be AIReviewPayloadV1")
        expected_bytes = canonicalize_ai_review_payload(self.payload)
        if self.canonical_bytes != expected_bytes:
            raise AIReviewIntegrityError(
                AIReviewErrorCode.HASH_MISMATCH, "canonical payload drift"
            )
        expected_hash = compute_ai_review_content_sha256(expected_bytes)
        if self.content_sha256 != expected_hash:
            raise AIReviewIntegrityError(
                AIReviewErrorCode.HASH_MISMATCH, "content hash drift"
            )
        if self.review_snapshot_id != derive_ai_review_snapshot_id(
            self.batch_id, expected_hash
        ):
            raise AIReviewIntegrityError(
                AIReviewErrorCode.SNAPSHOT_ID_MISMATCH, "snapshot identity drift"
            )

    @classmethod
    def create(cls, batch_id: str, payload: AIReviewPayloadV1) -> "AIReviewSnapshotV1":
        canonical = canonicalize_ai_review_payload(payload)
        content_hash = compute_ai_review_content_sha256(canonical)
        return cls(
            batch_id=batch_id,
            review_snapshot_id=derive_ai_review_snapshot_id(batch_id, content_hash),
            content_sha256=content_hash,
            canonical_bytes=canonical,
            payload=payload,
        )

    @classmethod
    def from_json(cls, batch_id: str, raw: str | bytes) -> "AIReviewSnapshotV1":
        return cls.create(batch_id, parse_ai_review_payload(raw))


@dataclass(frozen=True, slots=True)
class AIReviewProjectionV1:
    state: AIReviewState = AIReviewState.AI_DRAFT
    last_sequence: int = 0
    last_event_sha256: str = ZERO_EVENT_HASH

    def __post_init__(self) -> None:
        if type(self.state) is not AIReviewState:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid review state")
        if type(self.last_sequence) is not int or self.last_sequence < 0:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid sequence")
        _sha(self.last_event_sha256, path="$.last_event_sha256")


def transition_ai_review(
    current: AIReviewProjectionV1, event_type: AIReviewEventType
) -> AIReviewProjectionV1:
    if (
        type(current) is not AIReviewProjectionV1
        or type(event_type) is not AIReviewEventType
    ):
        _fail(AIReviewErrorCode.INVALID_TYPE, "typed projection and event required")
    allowed: dict[AIReviewState, dict[AIReviewEventType, AIReviewState]] = {
        AIReviewState.AI_DRAFT: {
            AIReviewEventType.CHALLENGED: AIReviewState.AI_CHALLENGED,
            AIReviewEventType.CHANGES_REQUIRED: AIReviewState.CHANGES_REQUIRED,
            AIReviewEventType.QUARANTINED: AIReviewState.QUARANTINED,
            AIReviewEventType.REVOKED: AIReviewState.REVOKED,
        },
        AIReviewState.AI_CHALLENGED: {
            AIReviewEventType.CROSS_REVIEWED: (
                AIReviewState.AI_CROSS_REVIEWED_NON_AUTHORITATIVE
            ),
            AIReviewEventType.CHANGES_REQUIRED: AIReviewState.CHANGES_REQUIRED,
            AIReviewEventType.QUARANTINED: AIReviewState.QUARANTINED,
            AIReviewEventType.REVOKED: AIReviewState.REVOKED,
        },
        AIReviewState.AI_CROSS_REVIEWED_NON_AUTHORITATIVE: {
            AIReviewEventType.QUARANTINED: AIReviewState.QUARANTINED,
            AIReviewEventType.REVOKED: AIReviewState.REVOKED,
        },
        AIReviewState.CHANGES_REQUIRED: {
            AIReviewEventType.QUARANTINED: AIReviewState.QUARANTINED,
            AIReviewEventType.REVOKED: AIReviewState.REVOKED,
        },
        AIReviewState.QUARANTINED: {
            AIReviewEventType.REVOKED: AIReviewState.REVOKED,
        },
        AIReviewState.REVOKED: {},
    }
    next_state = allowed[current.state].get(event_type)
    if next_state is None:
        _fail(AIReviewErrorCode.INVALID_TRANSITION, "invalid AI review transition")
    return AIReviewProjectionV1(
        state=next_state,
        last_sequence=current.last_sequence,
        last_event_sha256=current.last_event_sha256,
    )


def compute_ai_review_validation_sha256(snapshot: AIReviewSnapshotV1) -> str:
    return hashlib.sha256(
        VALIDATION_DOMAIN
        + snapshot.review_snapshot_id.encode("ascii")
        + b"\x00"
        + snapshot.content_sha256.encode("ascii")
    ).hexdigest()


def compute_ai_review_audit_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(AUDIT_DOMAIN + _canonical_json(payload)).hexdigest()


def compute_ai_review_lifecycle_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(LIFECYCLE_DOMAIN + _canonical_json(payload)).hexdigest()


def _parse_locator(value: Any, *, path: str) -> SourceLocatorV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "locator must be object", path=path)
    state = value.get("state")
    if state == "exact":
        _exact(value, frozenset({"state", "value"}), path=path)
        return ExactLocatorV1(
            _text(value["value"], path=f"{path}.value", max_chars=512)
        )
    if state == "unavailable":
        _exact(value, frozenset({"state", "reason"}), path=path)
        return UnavailableLocatorV1(
            _text(value["reason"], path=f"{path}.reason", max_chars=512)
        )
    _fail(AIReviewErrorCode.INVALID_TYPE, "unknown locator state", path=path)


def _parse_excerpt(value: Any, *, path: str) -> SourceExcerptV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "excerpt must be object", path=path)
    state = value.get("state")
    if state == "omitted":
        _exact(value, frozenset({"state"}), path=path)
        return OmittedExcerptV1()
    if state == "included":
        _exact(value, frozenset({"state", "text", "rights_basis"}), path=path)
        return IncludedExcerptV1(
            text=_text(value["text"], path=f"{path}.text", max_chars=280),
            rights_basis=_text(
                value["rights_basis"], path=f"{path}.rights_basis", max_chars=512
            ),
        )
    _fail(AIReviewErrorCode.INVALID_TYPE, "unknown excerpt state", path=path)


def _parse_creator(value: Any) -> CreatorAgentRunV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "creator must be object")
    _exact(
        value,
        frozenset(
            {
                "agent_model",
                "agent_provider",
                "agent_version",
                "input_sha256",
                "output_sha256",
                "prompt_sha256",
                "prompt_version",
                "run_id",
            }
        ),
        path="$.creator",
    )
    return CreatorAgentRunV1(
        agent_model=value["agent_model"],
        agent_provider=_enum(
            AgentProvider, value["agent_provider"], path="$.creator.agent_provider"
        ),
        agent_version=value["agent_version"],
        input_sha256=value["input_sha256"],
        output_sha256=value["output_sha256"],
        prompt_sha256=value["prompt_sha256"],
        prompt_version=value["prompt_version"],
        run_id=value["run_id"],
    )


def _parse_source(value: Any, *, path: str) -> AISourceContextV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "source must be object", path=path)
    _exact(
        value,
        frozenset(
            {
                "content_sha256",
                "document_id",
                "document_revision",
                "document_title",
                "document_type",
                "excerpt",
                "origin_ref",
                "locator",
                "publication_edition",
                "publisher",
                "rights_basis",
                "rights_state",
                "source_ref",
            }
        ),
        path=path,
    )
    source = AISourceContextV1(
        metadata=ReviewedSourceMetadataV1(
            source_ref=value["source_ref"],
            document_id=value["document_id"],
            document_title=value["document_title"],
            publisher=value["publisher"],
            document_type=_enum(
                EvidenceDocumentType,
                value["document_type"],
                path=f"{path}.document_type",
            ),
            document_revision=value["document_revision"],
            publication_edition=value["publication_edition"],
            content_sha256=value["content_sha256"],
            locator=_parse_locator(value["locator"], path=f"{path}.locator"),
            rights_state=_enum(
                EvidenceRightsState,
                value["rights_state"],
                path=f"{path}.rights_state",
            ),
            rights_basis=value["rights_basis"],
            excerpt=_parse_excerpt(value["excerpt"], path=f"{path}.excerpt"),
        )
    )
    if value["origin_ref"] != source.origin_ref:
        _fail(
            AIReviewErrorCode.HASH_MISMATCH,
            "source origin is not derived from the exact publisher identity",
            path=f"{path}.origin_ref",
        )
    return source


def _parse_claim(value: Any, *, path: str) -> AIClaimContextV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "claim must be object", path=path)
    _exact(
        value,
        frozenset(
            {
                "ai_assisted",
                "application_scope",
                "claim_ref",
                "claim_text",
                "conditions_and_exclusions",
                "conflicting_claim_refs",
                "evidence_risk",
                "expected_verdict",
                "material_granularity",
                "primary_source_refs",
                "purpose",
                "rule_ref",
                "scope",
                "seal_type_scope",
                "single_source_treatment",
                "source_refs",
                "temperature_scope",
            }
        ),
        path=path,
    )
    if value["ai_assisted"] is not True:
        _fail(AIReviewErrorCode.INVALID_TYPE, "ai_assisted must be true", path=path)
    scope = value["scope"]
    if type(scope) is not dict:
        _fail(
            AIReviewErrorCode.INVALID_TYPE, "scope must be object", path=f"{path}.scope"
        )
    _exact(
        scope,
        frozenset({"scope_type", "materials", "media", "conditions"}),
        path=f"{path}.scope",
    )
    if scope["scope_type"] != "material_relation":
        _fail(AIReviewErrorCode.SCOPE_MISMATCH, "material_relation required")
    return AIClaimContextV1(
        claim_ref=value["claim_ref"],
        rule_ref=value["rule_ref"],
        purpose=_enum(AIClaimPurpose, value["purpose"], path=f"{path}.purpose"),
        claim_text=value["claim_text"],
        scope=MaterialRelationClaimScopeV2(
            materials=_canonical_tuple(
                scope["materials"], path=f"{path}.scope.materials"
            ),
            media=_canonical_tuple(scope["media"], path=f"{path}.scope.media"),
            conditions=_canonical_tuple(
                scope["conditions"], path=f"{path}.scope.conditions"
            ),
        ),
        source_refs=_canonical_tuple(value["source_refs"], path=f"{path}.source_refs"),
        primary_source_refs=_canonical_tuple(
            value["primary_source_refs"], path=f"{path}.primary_source_refs"
        ),
        seal_type_scope=value["seal_type_scope"],
        temperature_scope=value["temperature_scope"],
        application_scope=value["application_scope"],
        conditions_and_exclusions=value["conditions_and_exclusions"],
        expected_verdict=_enum(
            MaterialConstraintVerdict,
            value["expected_verdict"],
            path=f"{path}.expected_verdict",
        ),
        evidence_risk=_enum(
            AIEvidenceRisk, value["evidence_risk"], path=f"{path}.evidence_risk"
        ),
        material_granularity=_enum(
            AIMaterialGranularity,
            value["material_granularity"],
            path=f"{path}.material_granularity",
        ),
        single_source_treatment=_enum(
            AISingleSourceTreatment,
            value["single_source_treatment"],
            path=f"{path}.single_source_treatment",
        ),
        conflicting_claim_refs=_canonical_tuple(
            value["conflicting_claim_refs"],
            path=f"{path}.conflicting_claim_refs",
            allow_empty=True,
        ),
    )


def _parse_medium_identity_claim(
    value: Any, *, path: str
) -> AIMediumIdentityClaimContextV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "claim must be object", path=path)
    _exact(
        value,
        frozenset(
            {
                "ai_assisted",
                "claim_kind",
                "claim_ref",
                "claim_text",
                "scope",
                "source_refs",
            }
        ),
        path=path,
    )
    if value["ai_assisted"] is not True or value["claim_kind"] != "media_identity":
        _fail(
            AIReviewErrorCode.INVALID_TYPE,
            "media identity claim discriminator is invalid",
            path=path,
        )
    scope = value["scope"]
    if type(scope) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "scope must be object", path=path)
    _exact(
        scope,
        frozenset({"scope_type", "media_ref", "identity_assertion_ref"}),
        path=f"{path}.scope",
    )
    if scope["scope_type"] != "media_identity":
        _fail(AIReviewErrorCode.SCOPE_MISMATCH, "media_identity scope required")
    return AIMediumIdentityClaimContextV1(
        claim_ref=value["claim_ref"],
        claim_text=value["claim_text"],
        scope=MediaIdentityClaimScopeV2(
            media_ref=scope["media_ref"],
            identity_assertion_ref=scope["identity_assertion_ref"],
        ),
        source_refs=_canonical_tuple(value["source_refs"], path=f"{path}.source_refs"),
    )


def _parse_medium_identity(value: Any, *, path: str) -> AIMediumIdentityContextV1:
    if type(value) is not dict:
        _fail(
            AIReviewErrorCode.INVALID_TYPE,
            "media identity must be object",
            path=path,
        )
    _exact(
        value,
        frozenset(
            {
                "aliases",
                "canonical_name",
                "claims",
                "evidence_content_sha256",
                "evidence_snapshot_id",
                "identity_assertion_ref",
                "identity_kind",
                "media_ref",
            }
        ),
        path=path,
    )
    if type(value["claims"]) is not list:
        _fail(AIReviewErrorCode.INVALID_TYPE, "claims must be array", path=path)
    return AIMediumIdentityContextV1(
        media_ref=value["media_ref"],
        canonical_name=value["canonical_name"],
        identity_kind=_enum(
            MediumIdentityKind,
            value["identity_kind"],
            path=f"{path}.identity_kind",
        ),
        aliases=_canonical_tuple(
            value["aliases"], path=f"{path}.aliases", allow_empty=True
        ),
        identity_assertion_ref=value["identity_assertion_ref"],
        evidence_snapshot_id=value["evidence_snapshot_id"],
        evidence_content_sha256=value["evidence_content_sha256"],
        claims=tuple(
            _parse_medium_identity_claim(item, path=f"{path}.claims[{index}]")
            for index, item in enumerate(value["claims"])
        ),
    )


def parse_ai_review_payload(raw: str | bytes) -> AIReviewPayloadV1:
    try:
        value = parse_json_v2(raw)
    except MaterialEvidenceV2ValidationError as exc:
        mapped = {
            MaterialEvidenceV2ErrorCode.DUPLICATE_PROPERTY: (
                AIReviewErrorCode.DUPLICATE_PROPERTY
            ),
            MaterialEvidenceV2ErrorCode.INVALID_UNICODE: (
                AIReviewErrorCode.INVALID_UNICODE
            ),
            MaterialEvidenceV2ErrorCode.NON_NFC: AIReviewErrorCode.NON_NFC,
        }.get(exc.code, AIReviewErrorCode.INVALID_JSON)
        raise AIReviewValidationError(
            mapped,
            "strict JSON parsing failed",
            path=exc.path,
        ) from exc
    _exact(
        value,
        frozenset(
            {
                "ai_review_schema_version",
                "authority",
                "canonicalization_version",
                "claims",
                "creator",
                "domain_pack_id",
                "environment",
                "evidence_content_sha256",
                "evidence_snapshot_id",
                "mat_evid_ai_review_contract_version",
                "media_identities",
                "positive_statement_allowed",
                "required_user_notice",
                "ruleset_content_sha256",
                "ruleset_snapshot_id",
                "sources",
                "tenant_id",
            }
        ),
        path="$",
    )
    if value["authority"] != AI_REVIEW_AUTHORITY:
        _fail(AIReviewErrorCode.UNKNOWN_SCHEMA, "invalid AI authority marker")
    if value["positive_statement_allowed"] is not False:
        _fail(
            AIReviewErrorCode.POSITIVE_STATEMENT_FORBIDDEN,
            "positive_statement_allowed must be false",
        )
    if value["required_user_notice"] != AI_REVIEW_REQUIRED_USER_NOTICE:
        _fail(
            AIReviewErrorCode.UNKNOWN_SCHEMA,
            "required user notice must match the frozen non-release notice",
        )
    if (
        type(value["sources"]) is not list
        or type(value["claims"]) is not list
        or type(value["media_identities"]) is not list
    ):
        _fail(
            AIReviewErrorCode.INVALID_TYPE,
            "sources, media_identities and claims must be arrays",
        )
    return AIReviewPayloadV1(
        environment=_enum(
            AIReviewEnvironment, value["environment"], path="$.environment"
        ),
        tenant_id=value["tenant_id"],
        domain_pack_id=value["domain_pack_id"],
        ruleset_snapshot_id=value["ruleset_snapshot_id"],
        ruleset_content_sha256=value["ruleset_content_sha256"],
        evidence_snapshot_id=value["evidence_snapshot_id"],
        evidence_content_sha256=value["evidence_content_sha256"],
        creator=_parse_creator(value["creator"]),
        sources=tuple(
            _parse_source(item, path=f"$.sources[{index}]")
            for index, item in enumerate(value["sources"])
        ),
        media_identities=tuple(
            _parse_medium_identity(item, path=f"$.media_identities[{index}]")
            for index, item in enumerate(value["media_identities"])
        ),
        claims=tuple(
            _parse_claim(item, path=f"$.claims[{index}]")
            for index, item in enumerate(value["claims"])
        ),
        ai_review_schema_version=value["ai_review_schema_version"],
        canonicalization_version=value["canonicalization_version"],
        mat_evid_ai_review_contract_version=value[
            "mat_evid_ai_review_contract_version"
        ],
    )


__all__ = [
    "AI_REVIEW_AUTHORITY",
    "AI_REVIEW_CANONICALIZATION_VERSION",
    "AI_REVIEW_SCHEMA_VERSION",
    "AI_REVIEW_REQUIRED_USER_NOTICE",
    "AIEvidenceRisk",
    "AIClaimContextV1",
    "AIClaimPurpose",
    "AIMaterialGranularity",
    "AIMediumIdentityClaimContextV1",
    "AIMediumIdentityContextV1",
    "AIReviewEnvironment",
    "AIReviewErrorCode",
    "AIReviewEventType",
    "AIReviewIntegrityError",
    "AIReviewPayloadV1",
    "AIReviewProjectionV1",
    "AIReviewSnapshotV1",
    "AIReviewState",
    "AIReviewValidationError",
    "AISingleSourceTreatment",
    "AISourceContextV1",
    "AdjudicatorAgentRunV1",
    "AgentExecutionIsolationV1",
    "AgentProvider",
    "ChallengerAgentRunV1",
    "CreatorAgentRunV1",
    "MAT_EVID_AI_REVIEW_CONTRACT_VERSION",
    "ZERO_EVENT_HASH",
    "canonicalize_ai_review_payload",
    "compute_ai_review_audit_sha256",
    "compute_ai_review_content_sha256",
    "compute_ai_review_lifecycle_sha256",
    "compute_ai_review_validation_sha256",
    "derive_ai_review_snapshot_id",
    "derive_source_origin_ref",
    "parse_ai_review_payload",
    "transition_ai_review",
    "validate_ai_review_batch_id",
    "validate_ai_review_snapshot_id",
]
