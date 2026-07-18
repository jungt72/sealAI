"""Closed Claude challenge and Codex adjudication contracts.

The audit corpus deliberately excludes tenant identity, customer data and any
creator reasoning.  Its only factual inputs are immutable claims, rule scopes,
source metadata, permitted excerpts, hashes and ratified invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
import unicodedata
from typing import Any

from sealai_v2.core.material_evidence_ai_review import (
    AIEvidenceRisk,
    AIClaimContextV1,
    AIMaterialGranularity,
    AIReviewErrorCode,
    AIReviewEventType,
    AIReviewSnapshotV1,
    AIReviewValidationError,
    AdjudicatorAgentRunV1,
    ChallengerAgentRunV1,
    _canonical_json,
    _enum,
    _exact,
    _fail,
    _id,
    _sha,
    _text,
)
from sealai_v2.core.material_evidence_v2 import (
    EvidenceManifestPayloadV2,
    EvidenceManifestSnapshotV2,
    MediaIdentityTargetV2,
    MaterialRelationTargetV2,
)
from sealai_v2.core.material_rulesets import (
    MaterialRulesetPayloadV1,
    MaterialRulesetSnapshotV1,
)


CLAUDE_AUDIT_SCHEMA_VERSION = 1
CLAUDE_AUDIT_CONTRACT_VERSION = "MAT-EVID-AI-CHALLENGE.v1"
CODEX_ADJUDICATION_SCHEMA_VERSION = 1
CODEX_ADJUDICATION_CONTRACT_VERSION = "MAT-EVID-AI-ADJUDICATION.v1"
CORPUS_SAFETY_CONTRACT_VERSION = "MAT-EVID-AI-CORPUS-SAFETY.v1"
CLAUDE_TASK_V1 = (
    "Independently red-team every claim against only the supplied source "
    "metadata and permitted excerpts. Return the closed JSON report."
)

AUDIT_INPUT_DOMAIN = b"sealai.material-evidence-ai-review.audit-input.v1\x00"
AUDIT_OUTPUT_DOMAIN = b"sealai.material-evidence-ai-review.audit-output.v1\x00"
CHALLENGE_DOMAIN = b"sealai.material-evidence-ai-review.challenge.v1\x00"
ADJUDICATION_DOMAIN = b"sealai.material-evidence-ai-review.adjudication.v1\x00"
CORPUS_SAFETY_DOMAIN = b"sealai.material-evidence-ai-review.corpus-safety.v1\x00"

_CHALLENGE_ID_RE = re.compile(r"^mac_[0-9a-f]{64}$", re.ASCII)
_ADJUDICATION_ID_RE = re.compile(r"^maa_[0-9a-f]{64}$", re.ASCII)
_FINDING_REF_RE = re.compile(r"^AIF-[A-Z0-9][A-Z0-9._:-]{0,124}$", re.ASCII)
_PERSON_NAME_TOKEN = (
    r"(?:[A-ZÀ-ÖØ-Þ](?:[a-zà-öø-ÿ]+"
    r"(?:[-'’][A-ZÀ-ÖØ-Þ]?[a-zà-öø-ÿ]+)?|\.)?|"
    r"[A-ZÀ-ÖØ-Þ]{2,40})"
)
_PERSON_NAME_SEQUENCE = rf"{_PERSON_NAME_TOKEN}(?:\s+{_PERSON_NAME_TOKEN}){{1,3}}"

_CORPUS_SECRET_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "github_token",
        re.compile(r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b"),
    ),
    (
        "openai_or_anthropic_key",
        re.compile(r"\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{32,})\b"),
    ),
    (
        "slack_token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    ),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    (
        "api_credential_assignment",
        re.compile(
            r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*[^\s,;]{8,}"
        ),
    ),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    ),
)
_CORPUS_DIRECT_IDENTIFIER_PATTERNS = (
    (
        "email_address",
        re.compile(
            r"(?i)(?<![A-Z0-9._%+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![A-Z0-9.-])"
        ),
    ),
    ("iban", re.compile(r"\b[A-Z]{2}[0-9]{2}(?:[ ]?[A-Z0-9]){11,30}\b")),
    ("us_ssn", re.compile(r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b")),
    (
        "telephone_number",
        re.compile(
            r"(?i)(?:\b(?:tel(?:ephone)?|phone|mobile|fax)\s*[:.]?\s*"
            r"\+?[0-9][0-9 ()/.-]{6,20}[0-9]\b|"
            r"(?<![A-Z0-9])\+[1-9][0-9 ()/.-]{7,20}[0-9](?![A-Z0-9]))"
        ),
    ),
    (
        "postal_address",
        re.compile(
            r"(?i)(?:\b[A-ZÀ-ÖØ-öø-ÿ][A-ZÀ-ÖØ-öø-ÿ'-]{1,40}"
            r"(?:straße|strasse|weg|platz)\s+[0-9]{1,5}[A-Z]?\b|"
            r"\b(?:street|road|avenue|boulevard|lane|drive|straße|"
            r"strasse|weg|platz)\s+[0-9]{1,5}[A-Z]?\b|"
            r"\b[0-9]{1,5}\s+[A-ZÀ-ÖØ-öø-ÿ][A-ZÀ-ÖØ-öø-ÿ .'-]{1,50}\s"
            r"(?:street|road|avenue|boulevard|lane|drive)\b)"
        ),
    ),
    (
        "ip_address",
        re.compile(
            r"(?<![0-9])(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})"
            r"(?:\.(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})){3}(?![0-9])"
        ),
    ),
    (
        "date_of_birth",
        re.compile(r"(?i)\b(?:date of birth|dob|geburtsdatum)\s*[:=]\s*[^,;\n]{4,32}"),
    ),
    (
        "named_person",
        re.compile(
            r"(?i:\b(?:contact person|prepared by|author|ansprechpartner|bearbeiter))\b"
            r"\s*(?::|=)?\s*[A-ZÀ-ÖØ-Þ][^,;\n]{2,80}"
        ),
    ),
    (
        "bare_person_name",
        re.compile(r"^\s*[A-ZÄÖÜ][a-zäöüß]{2,}\s+[A-ZÄÖÜ][a-zäöüß]{2,}\s*$"),
    ),
    (
        "person_name_in_sentence",
        re.compile(
            r"(?:^|[.!?]\s+)[A-ZÄÖÜ][a-zäöüß]{2,}\s+"
            r"[A-ZÄÖÜ][a-zäöüß]{2,}\s+"
            r"(?:prepared|authored|reviewed|approv"
            r"ed|wrote|erstellt|geprüft)\b"
        ),
    ),
    (
        "embedded_person_name",
        re.compile(
            rf"(?<![A-ZÀ-ÖØ-öø-ÿ]){_PERSON_NAME_SEQUENCE}" r"(?![A-ZÀ-ÖØ-öø-ÿ.'’-])"
        ),
    ),
    (
        "contextual_person_name",
        re.compile(
            r"(?i:\b(?:author|authored by|contact|contact person|prepared by|"
            r"reviewed by|approv"
            r"ed by|ansprechpartner|bearbeiter)\b)"
            r"\s*(?::|=)?\s*"
            rf"{_PERSON_NAME_TOKEN}"
            r"(?![A-ZÀ-ÖØ-öø-ÿ.'’-])"
        ),
    ),
    (
        "honorific_person_name",
        re.compile(
            r"(?i:\b(?:dr|mr|mrs|ms|prof)\.?)\s+"
            rf"{_PERSON_NAME_TOKEN}"
            r"(?![A-ZÀ-ÖØ-öø-ÿ.'’-])"
        ),
    ),
    (
        "single_person_name_candidate",
        re.compile(rf"^\s*{_PERSON_NAME_TOKEN}\s*$"),
    ),
    (
        "customer_identifier",
        re.compile(r"(?i)\b(?:customer|tenant|case)[_-]?id\s*[:=]\s*[^\s,;]{3,}"),
    ),
)
_ORGANIZATION_PUBLISHER_SUFFIXES = (
    " agency",
    " association",
    " board",
    " company",
    " corporation",
    " gmbh",
    " inc",
    " institute",
    " ltd",
    " office",
    " publisher",
    " solutions",
    " university",
)
_PUBLISHER_EXCEPTION_CONTRACT = {
    "comparison": "normalized-full-value-endswith-any.v1",
    "normalization": "unicode-casefold-after-split-join-ascii-space.v1",
    "path_suffix": ".publisher",
    "pattern_class": "embedded_person_name",
}
_SINGLE_NAME_PATH_SUFFIXES = (
    ".claim_text",
    ".document_title",
    ".excerpt.text",
    ".locator.reason",
    ".locator.value",
    ".publisher",
    ".rights_basis",
)


def _corpus_safety_receipt(value: dict[str, Any]) -> dict[str, Any]:
    """Scan the exact outbound corpus and fail closed without exposing matches."""

    strings: list[tuple[str, str]] = []

    def collect(item: Any, *, path: str) -> None:
        if type(item) is str:
            strings.append((path, item))
        elif type(item) is list:
            for index, child in enumerate(item):
                collect(child, path=f"{path}[{index}]")
        elif type(item) is dict:
            for key, child in item.items():
                collect(child, path=f"{path}.{key}")

    collect(value, path="$")
    secret_classes = sorted(
        name
        for name, pattern in _CORPUS_SECRET_PATTERNS
        if any(pattern.search(item) for _, item in strings)
    )

    def has_direct_identifier(
        name: str, pattern: re.Pattern[str], path: str, item: str
    ) -> bool:
        if not pattern.search(item):
            return False
        if name == "single_person_name_candidate" and not path.endswith(
            _SINGLE_NAME_PATH_SUFFIXES
        ):
            return False
        if name == _PUBLISHER_EXCEPTION_CONTRACT["pattern_class"] and path.endswith(
            _PUBLISHER_EXCEPTION_CONTRACT["path_suffix"]
        ):
            normalized = " ".join(item.split()).casefold()
            return not normalized.endswith(_ORGANIZATION_PUBLISHER_SUFFIXES)
        return True

    identifier_classes = sorted(
        name
        for name, pattern in _CORPUS_DIRECT_IDENTIFIER_PATTERNS
        if any(
            has_direct_identifier(name, pattern, path, item) for path, item in strings
        )
    )
    if secret_classes or identifier_classes:
        _fail(
            AIReviewErrorCode.SENSITIVE_DATA_FORBIDDEN,
            "outbound corpus failed the closed secret/direct-identifier preflight "
            f"classes={secret_classes + identifier_classes}",
        )
    canonical = _canonical_json(value)
    scanner_manifest = {
        "exceptions": [
            {
                "comparison": _PUBLISHER_EXCEPTION_CONTRACT["comparison"],
                "normalization": _PUBLISHER_EXCEPTION_CONTRACT["normalization"],
                "organization_suffixes": list(_ORGANIZATION_PUBLISHER_SUFFIXES),
                "path_suffix": _PUBLISHER_EXCEPTION_CONTRACT["path_suffix"],
                "pattern_class": _PUBLISHER_EXCEPTION_CONTRACT["pattern_class"],
            }
        ],
        "path_scopes": [
            {
                "path_suffixes": list(_SINGLE_NAME_PATH_SUFFIXES),
                "pattern_class": "single_person_name_candidate",
            }
        ],
        "patterns": [
            {"class": name, "pattern": pattern.pattern}
            for name, pattern in (
                *_CORPUS_SECRET_PATTERNS,
                *_CORPUS_DIRECT_IDENTIFIER_PATTERNS,
            )
        ],
    }
    return {
        "corpus_sha256": hashlib.sha256(CORPUS_SAFETY_DOMAIN + canonical).hexdigest(),
        "creator_reasoning_fields_included": False,
        "customer_or_tenant_fields_included": False,
        "direct_identifier_match_count": 0,
        "pattern_set_sha256": hashlib.sha256(
            CORPUS_SAFETY_DOMAIN + _canonical_json(scanner_manifest)
        ).hexdigest(),
        "scanner_contract_version": CORPUS_SAFETY_CONTRACT_VERSION,
        "secret_match_count": 0,
    }


def _publisher_identity(value: str) -> str:
    """Normalize only presentation-level publisher variations for comparison."""

    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


class ClaudeClaimVerdict(str, Enum):
    PASS = "PASS"
    CHANGES_REQUIRED = "CHANGES_REQUIRED"
    QUARANTINE = "QUARANTINE"


class AIFindingSeverity(str, Enum):
    NONE = "NONE"
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AIFindingCategory(str, Enum):
    NON_FACTUAL_DOCUMENTATION = "non_factual_documentation"
    SOURCE_COVERAGE = "source_coverage"
    SOURCE_INDEPENDENCE = "source_independence"
    SCOPE_ERROR = "scope_error"
    SOURCE_OVERREACH = "source_overreach"
    CONTRADICTION = "contradiction"
    MISSING_CONDITION = "missing_condition"
    MATERIAL_GRANULARITY = "material_granularity"
    POSITIVE_STATEMENT = "positive_statement"
    RIGHTS = "rights"
    HASH_OR_REFERENCE = "hash_or_reference"


class SourceIndependenceState(str, Enum):
    DISTINCT_PUBLISHERS_CONFIRMED = "distinct_publishers_confirmed"
    SINGLE_SOURCE = "single_source"
    SAME_PUBLISHER = "same_publisher"
    UNRESOLVED = "unresolved"


class FindingDisposition(str, Enum):
    CORRECTED_IN_NEW_SNAPSHOT = "corrected_in_new_snapshot"
    QUARANTINED = "quarantined"
    ACCEPTED_NONBLOCKING = "accepted_nonblocking"


class AIAdjudicationOutcome(str, Enum):
    AI_CROSS_REVIEWED_NON_AUTHORITATIVE = "ai_cross_reviewed_non_authoritative"
    CHANGES_REQUIRED = "changes_required"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class ClaudeAuditInputV1:
    canonical_bytes: bytes
    audit_input_sha256: str

    def __post_init__(self) -> None:
        if type(self.canonical_bytes) is not bytes:
            raise TypeError("canonical_bytes must be bytes")
        expected = hashlib.sha256(AUDIT_INPUT_DOMAIN + self.canonical_bytes).hexdigest()
        if self.audit_input_sha256 != expected:
            raise ValueError("audit input hash mismatch")


@dataclass(frozen=True, slots=True)
class ClaudeFindingV1:
    finding_ref: str
    category: AIFindingCategory
    severity: AIFindingSeverity
    detail: str
    recommended_correction: str

    def __post_init__(self) -> None:
        _id(self.finding_ref, _FINDING_REF_RE, path="$.finding.finding_ref")
        if type(self.category) is not AIFindingCategory:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid finding category")
        if (
            self.severity is AIFindingSeverity.NONE
            or type(self.severity) is not AIFindingSeverity
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE, "finding requires a non-NONE severity"
            )
        _text(self.detail, path="$.finding.detail", max_chars=2048)
        _text(
            self.recommended_correction,
            path="$.finding.recommended_correction",
            max_chars=2048,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "category": self.category.value,
            "detail": self.detail,
            "finding_ref": self.finding_ref,
            "recommended_correction": self.recommended_correction,
            "severity": self.severity.value,
        }


@dataclass(frozen=True, slots=True)
class ClaudeClaimAuditResultV1:
    claim_ref: str
    verdict: ClaudeClaimVerdict
    severity: AIFindingSeverity
    source_coverage: str
    source_independence_assessment: SourceIndependenceState
    scope_assessment: str
    source_overreach_assessment: str
    contradiction_assessment: str
    missing_conditions_assessment: str
    material_granularity_assessment: str
    positive_statement_assessment: str
    findings: tuple[ClaudeFindingV1, ...]

    def __post_init__(self) -> None:
        _id(
            self.claim_ref,
            re.compile(r"^mec_[0-9a-f]{64}$", re.ASCII),
            path="$.claim_ref",
        )
        if (
            type(self.verdict) is not ClaudeClaimVerdict
            or type(self.severity) is not AIFindingSeverity
            or type(self.source_independence_assessment) is not SourceIndependenceState
        ):
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid Claude claim result enums")
        for name, value in (
            ("source_coverage", self.source_coverage),
            ("scope_assessment", self.scope_assessment),
            ("source_overreach_assessment", self.source_overreach_assessment),
            ("contradiction_assessment", self.contradiction_assessment),
            ("missing_conditions_assessment", self.missing_conditions_assessment),
            ("material_granularity_assessment", self.material_granularity_assessment),
            ("positive_statement_assessment", self.positive_statement_assessment),
        ):
            _text(value, path=f"$.claim_result.{name}", max_chars=2048)
        if type(self.findings) is not tuple or any(
            type(item) is not ClaudeFindingV1 for item in self.findings
        ):
            _fail(AIReviewErrorCode.INVALID_TYPE, "findings must be a typed tuple")
        refs = tuple(item.finding_ref for item in self.findings)
        if refs != tuple(sorted(set(refs))):
            _fail(AIReviewErrorCode.NON_CANONICAL_ORDER, "findings must be ordered")
        if self.verdict is ClaudeClaimVerdict.PASS:
            if not self.findings and self.severity is not AIFindingSeverity.NONE:
                _fail(AIReviewErrorCode.INVALID_TYPE, "clean PASS requires NONE")
            if self.findings and (
                self.severity is not AIFindingSeverity.LOW
                or any(
                    finding.severity is not AIFindingSeverity.LOW
                    for finding in self.findings
                )
            ):
                _fail(
                    AIReviewErrorCode.INVALID_TYPE,
                    "PASS may carry only explicitly nonblocking LOW findings",
                )
        elif self.severity is AIFindingSeverity.NONE or not self.findings:
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "non-PASS result requires severity and findings",
            )
        if self.findings:
            order = {
                AIFindingSeverity.CRITICAL: 4,
                AIFindingSeverity.HIGH: 3,
                AIFindingSeverity.MEDIUM: 2,
                AIFindingSeverity.LOW: 1,
            }
            expected = max(
                self.findings, key=lambda item: order[item.severity]
            ).severity
            if self.severity is not expected:
                _fail(AIReviewErrorCode.INVALID_TYPE, "aggregate severity drift")

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_ref": self.claim_ref,
            "contradiction_assessment": self.contradiction_assessment,
            "findings": [item.to_dict() for item in self.findings],
            "material_granularity_assessment": self.material_granularity_assessment,
            "missing_conditions_assessment": self.missing_conditions_assessment,
            "positive_statement_assessment": self.positive_statement_assessment,
            "scope_assessment": self.scope_assessment,
            "severity": self.severity.value,
            "source_coverage": self.source_coverage,
            "source_independence_assessment": self.source_independence_assessment.value,
            "source_overreach_assessment": self.source_overreach_assessment,
            "verdict": self.verdict.value,
        }


@dataclass(frozen=True, slots=True)
class ClaudeAuditReportV1:
    review_snapshot_id: str
    review_content_sha256: str
    overall_verdict: ClaudeClaimVerdict
    claim_results: tuple[ClaudeClaimAuditResultV1, ...]
    transport_complete: bool
    audit_schema_version: int = CLAUDE_AUDIT_SCHEMA_VERSION
    audit_contract_version: str = CLAUDE_AUDIT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _id(
            self.review_snapshot_id,
            re.compile(r"^mas_[0-9a-f]{64}$", re.ASCII),
            path="$.review_snapshot_id",
        )
        _sha(self.review_content_sha256, path="$.review_content_sha256")
        if (
            type(self.audit_schema_version) is not int
            or self.audit_schema_version != CLAUDE_AUDIT_SCHEMA_VERSION
            or self.audit_contract_version != CLAUDE_AUDIT_CONTRACT_VERSION
        ):
            _fail(AIReviewErrorCode.UNKNOWN_SCHEMA, "unknown Claude audit contract")
        if self.transport_complete is not True:
            _fail(
                AIReviewErrorCode.INVALID_TYPE, "incomplete transport is not a verdict"
            )
        if type(self.overall_verdict) is not ClaudeClaimVerdict:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid overall verdict")
        if (
            type(self.claim_results) is not tuple
            or not self.claim_results
            or any(
                type(item) is not ClaudeClaimAuditResultV1
                for item in self.claim_results
            )
        ):
            _fail(AIReviewErrorCode.INVALID_TYPE, "claim_results must be non-empty")
        refs = tuple(item.claim_ref for item in self.claim_results)
        if refs != tuple(sorted(set(refs))):
            _fail(
                AIReviewErrorCode.NON_CANONICAL_ORDER, "claim results must be ordered"
            )
        finding_refs = tuple(
            finding.finding_ref
            for result in self.claim_results
            for finding in result.findings
        )
        if len(finding_refs) != len(set(finding_refs)):
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "finding references must be globally unique",
            )
        expected = ClaudeClaimVerdict.PASS
        if any(
            item.verdict is ClaudeClaimVerdict.QUARANTINE for item in self.claim_results
        ):
            expected = ClaudeClaimVerdict.QUARANTINE
        elif any(
            item.verdict is ClaudeClaimVerdict.CHANGES_REQUIRED
            for item in self.claim_results
        ):
            expected = ClaudeClaimVerdict.CHANGES_REQUIRED
        if self.overall_verdict is not expected:
            _fail(AIReviewErrorCode.INVALID_TYPE, "overall verdict drift")

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_contract_version": self.audit_contract_version,
            "audit_schema_version": self.audit_schema_version,
            "claim_results": [item.to_dict() for item in self.claim_results],
            "overall_verdict": self.overall_verdict.value,
            "review_content_sha256": self.review_content_sha256,
            "review_snapshot_id": self.review_snapshot_id,
            "transport_complete": True,
        }


def build_claude_audit_input(snapshot: AIReviewSnapshotV1) -> ClaudeAuditInputV1:
    if type(snapshot) is not AIReviewSnapshotV1:
        raise TypeError("snapshot must be AIReviewSnapshotV1")
    payload = snapshot.payload
    audit_value = {
        "audit_contract_version": CLAUDE_AUDIT_CONTRACT_VERSION,
        "audit_schema_version": CLAUDE_AUDIT_SCHEMA_VERSION,
        "claims": list(payload.audit_claims()),
        "evidence_binding": {
            "evidence_content_sha256": payload.evidence_content_sha256,
            "evidence_snapshot_id": payload.evidence_snapshot_id,
            "media_identity_evidence": [
                {
                    "evidence_content_sha256": item.evidence_content_sha256,
                    "evidence_snapshot_id": item.evidence_snapshot_id,
                    "identity_assertion_ref": item.identity_assertion_ref,
                    "media_ref": item.media_ref,
                }
                for item in payload.media_identities
            ],
            "ruleset_content_sha256": payload.ruleset_content_sha256,
            "ruleset_snapshot_id": payload.ruleset_snapshot_id,
        },
        "invariants": [
            "No fact may be added from model knowledge.",
            "Every claim must remain within its cited source and exact locator.",
            "Only unvertraeglich, opaque bedingt, or quarantine are permitted.",
            "No positive compatibility, application validation, or suitability release.",
            "Unknown rights, source, locator, scope, hash, or reference fails closed.",
            "Family-wide or safety-critical effects require independent evidence or narrower treatment.",
            "AI review is non-authoritative and must never be described as human review.",
        ],
        "media_identity_candidates": [
            item.to_dict() for item in payload.media_identities
        ],
        "required_output": {
            "claim_result_fields": [
                "claim_ref",
                "contradiction_assessment",
                "findings",
                "material_granularity_assessment",
                "missing_conditions_assessment",
                "positive_statement_assessment",
                "scope_assessment",
                "severity",
                "source_coverage",
                "source_independence_assessment",
                "source_overreach_assessment",
                "verdict",
            ],
            "claim_verdicts": ["PASS", "CHANGES_REQUIRED", "QUARANTINE"],
            "finding_categories": [item.value for item in AIFindingCategory],
            "finding_fields": [
                "category",
                "detail",
                "finding_ref",
                "recommended_correction",
                "severity",
            ],
            "finding_severities": [
                "CRITICAL",
                "HIGH",
                "MEDIUM",
                "LOW",
            ],
            "claim_severities": [
                "NONE",
                "CRITICAL",
                "HIGH",
                "MEDIUM",
                "LOW",
            ],
            "source_independence_values": [
                item.value for item in SourceIndependenceState
            ],
            "format": "exact JSON matching MAT-EVID-AI-CHALLENGE.v1",
            "required_assessments": [
                "source_coverage",
                "source_independence_assessment",
                "scope_assessment",
                "source_overreach_assessment",
                "contradiction_assessment",
                "missing_conditions_assessment",
                "material_granularity_assessment",
                "positive_statement_assessment",
            ],
            "top_level_fields": [
                "audit_contract_version",
                "audit_schema_version",
                "claim_results",
                "overall_verdict",
                "review_content_sha256",
                "review_snapshot_id",
                "transport_complete",
            ],
            "transport_complete": True,
        },
        "review_content_sha256": snapshot.content_sha256,
        "review_snapshot_id": snapshot.review_snapshot_id,
        "required_user_notice": payload.required_user_notice,
        "sources": [item.to_dict() for item in payload.sources],
        "task": CLAUDE_TASK_V1,
    }
    audit_value["corpus_safety_receipt"] = _corpus_safety_receipt(audit_value)
    canonical = _canonical_json(audit_value)
    return ClaudeAuditInputV1(
        canonical_bytes=canonical,
        audit_input_sha256=hashlib.sha256(AUDIT_INPUT_DOMAIN + canonical).hexdigest(),
    )


def _parse_finding(value: Any, *, path: str) -> ClaudeFindingV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "finding must be object", path=path)
    _exact(
        value,
        frozenset(
            {"category", "detail", "finding_ref", "recommended_correction", "severity"}
        ),
        path=path,
    )
    return ClaudeFindingV1(
        finding_ref=value["finding_ref"],
        category=_enum(AIFindingCategory, value["category"], path=f"{path}.category"),
        severity=_enum(AIFindingSeverity, value["severity"], path=f"{path}.severity"),
        detail=value["detail"],
        recommended_correction=value["recommended_correction"],
    )


def _parse_claim_result(value: Any, *, path: str) -> ClaudeClaimAuditResultV1:
    if type(value) is not dict:
        _fail(AIReviewErrorCode.INVALID_TYPE, "claim result must be object", path=path)
    _exact(
        value,
        frozenset(
            {
                "claim_ref",
                "contradiction_assessment",
                "findings",
                "material_granularity_assessment",
                "missing_conditions_assessment",
                "positive_statement_assessment",
                "scope_assessment",
                "severity",
                "source_coverage",
                "source_independence_assessment",
                "source_overreach_assessment",
                "verdict",
            }
        ),
        path=path,
    )
    if type(value["findings"]) is not list:
        _fail(AIReviewErrorCode.INVALID_TYPE, "findings must be array", path=path)
    return ClaudeClaimAuditResultV1(
        claim_ref=value["claim_ref"],
        verdict=_enum(ClaudeClaimVerdict, value["verdict"], path=f"{path}.verdict"),
        severity=_enum(AIFindingSeverity, value["severity"], path=f"{path}.severity"),
        source_coverage=value["source_coverage"],
        source_independence_assessment=_enum(
            SourceIndependenceState,
            value["source_independence_assessment"],
            path=f"{path}.source_independence_assessment",
        ),
        scope_assessment=value["scope_assessment"],
        source_overreach_assessment=value["source_overreach_assessment"],
        contradiction_assessment=value["contradiction_assessment"],
        missing_conditions_assessment=value["missing_conditions_assessment"],
        material_granularity_assessment=value["material_granularity_assessment"],
        positive_statement_assessment=value["positive_statement_assessment"],
        findings=tuple(
            _parse_finding(item, path=f"{path}.findings[{index}]")
            for index, item in enumerate(value["findings"])
        ),
    )


def parse_claude_audit_report(
    raw: str | bytes, snapshot: AIReviewSnapshotV1
) -> ClaudeAuditReportV1:
    if type(snapshot) is not AIReviewSnapshotV1:
        raise TypeError("snapshot must be AIReviewSnapshotV1")
    from sealai_v2.core.material_evidence_v2 import parse_json_v2

    try:
        value = parse_json_v2(raw)
    except Exception as exc:
        raise AIReviewValidationError(
            AIReviewErrorCode.INVALID_JSON, "Claude output is not strict JSON"
        ) from exc
    _exact(
        value,
        frozenset(
            {
                "audit_contract_version",
                "audit_schema_version",
                "claim_results",
                "overall_verdict",
                "review_content_sha256",
                "review_snapshot_id",
                "transport_complete",
            }
        ),
        path="$",
    )
    if type(value["claim_results"]) is not list:
        _fail(AIReviewErrorCode.INVALID_TYPE, "claim_results must be array")
    report = ClaudeAuditReportV1(
        review_snapshot_id=value["review_snapshot_id"],
        review_content_sha256=value["review_content_sha256"],
        overall_verdict=_enum(
            ClaudeClaimVerdict, value["overall_verdict"], path="$.overall_verdict"
        ),
        claim_results=tuple(
            _parse_claim_result(item, path=f"$.claim_results[{index}]")
            for index, item in enumerate(value["claim_results"])
        ),
        transport_complete=value["transport_complete"],
        audit_schema_version=value["audit_schema_version"],
        audit_contract_version=value["audit_contract_version"],
    )
    if (
        report.review_snapshot_id != snapshot.review_snapshot_id
        or report.review_content_sha256 != snapshot.content_sha256
        or tuple(item.claim_ref for item in report.claim_results)
        != snapshot.payload.audit_claim_refs
    ):
        _fail(AIReviewErrorCode.HASH_MISMATCH, "Claude report binding drift")
    rule_claims = {item.claim_ref: item for item in snapshot.payload.claims}
    identity_claims = {
        claim.claim_ref: claim
        for identity in snapshot.payload.media_identities
        for claim in identity.claims
    }
    publisher_by_source_ref = {
        item.source_ref: _publisher_identity(item.metadata.publisher)
        for item in snapshot.payload.sources
    }
    for result in report.claim_results:
        claim = rule_claims.get(result.claim_ref) or identity_claims[result.claim_ref]
        source_refs = (
            claim.primary_source_refs
            if type(claim) is AIClaimContextV1
            else claim.source_refs
        )
        state = result.source_independence_assessment
        publishers = {publisher_by_source_ref[item] for item in source_refs}
        if len(source_refs) == 1 and state is not SourceIndependenceState.SINGLE_SOURCE:
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "single-source claim requires the closed single_source assessment",
            )
        if len(source_refs) > 1 and state is SourceIndependenceState.SINGLE_SOURCE:
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "multi-source claim cannot use the single_source assessment",
            )
        if (
            len(source_refs) > 1
            and len(publishers) == 1
            and state is not SourceIndependenceState.SAME_PUBLISHER
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "identical frozen publisher identities require same_publisher",
            )
        requires_independence = type(claim) is AIClaimContextV1 and (
            claim.evidence_risk is not AIEvidenceRisk.ORDINARY
            or claim.material_granularity is AIMaterialGranularity.MATERIAL_FAMILY
        )
        if result.verdict is ClaudeClaimVerdict.PASS and (
            (
                len(source_refs) > 1
                and state is not SourceIndependenceState.DISTINCT_PUBLISHERS_CONFIRMED
            )
            or (
                requires_independence
                and state is not SourceIndependenceState.DISTINCT_PUBLISHERS_CONFIRMED
            )
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "PASS does not satisfy the closed source-independence contract",
            )
    return report


@dataclass(frozen=True, slots=True)
class ClaudeChallengeV1:
    challenge_id: str
    review_snapshot_id: str
    review_content_sha256: str
    challenger: ChallengerAgentRunV1
    report: ClaudeAuditReportV1
    report_sha256: str

    def __post_init__(self) -> None:
        _id(self.challenge_id, _CHALLENGE_ID_RE, path="$.challenge_id")
        if type(self.challenger) is not ChallengerAgentRunV1:
            _fail(AIReviewErrorCode.INVALID_AGENT, "invalid challenger provenance")
        if type(self.report) is not ClaudeAuditReportV1:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid Claude report")
        expected_report_hash = hashlib.sha256(
            AUDIT_OUTPUT_DOMAIN + _canonical_json(self.report.to_dict())
        ).hexdigest()
        if self.report_sha256 != expected_report_hash:
            _fail(AIReviewErrorCode.HASH_MISMATCH, "report hash mismatch")
        if (
            self.review_snapshot_id != self.report.review_snapshot_id
            or self.review_content_sha256 != self.report.review_content_sha256
            or self.challenger.audit_output_sha256 != self.report_sha256
        ):
            _fail(AIReviewErrorCode.HASH_MISMATCH, "challenge binding mismatch")
        expected_id = _derive_challenge_id(
            self.review_snapshot_id, self.challenger, self.report_sha256
        )
        if self.challenge_id != expected_id:
            _fail(AIReviewErrorCode.HASH_MISMATCH, "challenge identity mismatch")

    @classmethod
    def create(
        cls,
        snapshot: AIReviewSnapshotV1,
        challenger: ChallengerAgentRunV1,
        report: ClaudeAuditReportV1,
    ) -> "ClaudeChallengeV1":
        if (
            challenger.run_id == snapshot.payload.creator.run_id
            or challenger.audit_input_sha256
            != build_claude_audit_input(snapshot).audit_input_sha256
        ):
            _fail(
                AIReviewErrorCode.INVALID_AGENT,
                "challenger is not independent or input drifted",
            )
        report_hash = hashlib.sha256(
            AUDIT_OUTPUT_DOMAIN + _canonical_json(report.to_dict())
        ).hexdigest()
        if challenger.audit_output_sha256 != report_hash:
            _fail(AIReviewErrorCode.HASH_MISMATCH, "challenger output hash mismatch")
        return cls(
            challenge_id=_derive_challenge_id(
                snapshot.review_snapshot_id, challenger, report_hash
            ),
            review_snapshot_id=snapshot.review_snapshot_id,
            review_content_sha256=snapshot.content_sha256,
            challenger=challenger,
            report=report,
            report_sha256=report_hash,
        )

    def validate_against(self, snapshot: AIReviewSnapshotV1) -> None:
        """Re-derive the complete challenge at every trust boundary."""

        if type(snapshot) is not AIReviewSnapshotV1:
            raise TypeError("snapshot must be AIReviewSnapshotV1")
        expected = type(self).create(snapshot, self.challenger, self.report)
        if self != expected or self.to_dict() != expected.to_dict():
            _fail(
                AIReviewErrorCode.HASH_MISMATCH,
                "challenge differs from its canonical factory derivation",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "challenge_id": self.challenge_id,
            "challenger": self.challenger.to_dict(),
            "report": self.report.to_dict(),
            "report_sha256": self.report_sha256,
            "review_content_sha256": self.review_content_sha256,
            "review_snapshot_id": self.review_snapshot_id,
        }


def _derive_challenge_id(
    review_snapshot_id: str,
    challenger: ChallengerAgentRunV1,
    report_sha256: str,
) -> str:
    digest = hashlib.sha256(
        CHALLENGE_DOMAIN
        + review_snapshot_id.encode("ascii")
        + b"\x00"
        + _canonical_json(challenger.to_dict())
        + b"\x00"
        + report_sha256.encode("ascii")
    ).hexdigest()
    return f"mac_{digest}"


@dataclass(frozen=True, slots=True)
class FindingAdjudicationV1:
    finding_ref: str
    disposition: FindingDisposition
    rationale: str

    def __post_init__(self) -> None:
        _id(self.finding_ref, _FINDING_REF_RE, path="$.finding_ref")
        if type(self.disposition) is not FindingDisposition:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid finding disposition")
        _text(self.rationale, path="$.rationale", max_chars=2048)

    def to_dict(self) -> dict[str, str]:
        return {
            "disposition": self.disposition.value,
            "finding_ref": self.finding_ref,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class AIMediaIdentityCorrectionV1:
    media_ref: str
    previous_evidence_snapshot_id: str
    replacement_evidence_snapshot_id: str
    replacement_evidence_content_sha256: str

    def __post_init__(self) -> None:
        _id(
            self.media_ref,
            re.compile(r"^med_[0-9a-f]{64}$", re.ASCII),
            path="$.media_identity_correction.media_ref",
        )
        for field, value in (
            ("previous_evidence_snapshot_id", self.previous_evidence_snapshot_id),
            ("replacement_evidence_snapshot_id", self.replacement_evidence_snapshot_id),
        ):
            _id(
                value,
                re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII),
                path=f"$.media_identity_correction.{field}",
            )
        _sha(
            self.replacement_evidence_content_sha256,
            path="$.media_identity_correction.replacement_evidence_content_sha256",
        )
        if self.previous_evidence_snapshot_id == self.replacement_evidence_snapshot_id:
            _fail(
                AIReviewErrorCode.INVALID_TRANSITION,
                "media identity correction requires a new snapshot",
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "media_ref": self.media_ref,
            "previous_evidence_snapshot_id": self.previous_evidence_snapshot_id,
            "replacement_evidence_content_sha256": (
                self.replacement_evidence_content_sha256
            ),
            "replacement_evidence_snapshot_id": self.replacement_evidence_snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class AIAdjudicationV1:
    adjudication_id: str
    review_snapshot_id: str
    review_content_sha256: str
    challenge_id: str
    challenger_report_sha256: str
    adjudicator: AdjudicatorAgentRunV1
    outcome: AIAdjudicationOutcome
    finding_adjudications: tuple[FindingAdjudicationV1, ...]
    replacement_ruleset_snapshot_id: str
    replacement_evidence_snapshot_id: str
    replacement_media_identity_evidence: tuple[AIMediaIdentityCorrectionV1, ...]
    adjudication_schema_version: int = CODEX_ADJUDICATION_SCHEMA_VERSION
    adjudication_contract_version: str = CODEX_ADJUDICATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _id(self.adjudication_id, _ADJUDICATION_ID_RE, path="$.adjudication_id")
        _id(
            self.review_snapshot_id,
            re.compile(r"^mas_[0-9a-f]{64}$", re.ASCII),
            path="$.review_snapshot_id",
        )
        _sha(self.review_content_sha256, path="$.review_content_sha256")
        _id(self.challenge_id, _CHALLENGE_ID_RE, path="$.challenge_id")
        _sha(self.challenger_report_sha256, path="$.challenger_report_sha256")
        if type(self.adjudicator) is not AdjudicatorAgentRunV1:
            _fail(AIReviewErrorCode.INVALID_AGENT, "invalid adjudicator")
        if type(self.outcome) is not AIAdjudicationOutcome:
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid adjudication outcome")
        if type(self.finding_adjudications) is not tuple or any(
            type(item) is not FindingAdjudicationV1
            for item in self.finding_adjudications
        ):
            _fail(AIReviewErrorCode.INVALID_TYPE, "invalid finding adjudications")
        refs = tuple(item.finding_ref for item in self.finding_adjudications)
        if refs != tuple(sorted(set(refs))):
            _fail(
                AIReviewErrorCode.NON_CANONICAL_ORDER, "adjudications must be ordered"
            )
        if type(self.replacement_media_identity_evidence) is not tuple or any(
            type(item) is not AIMediaIdentityCorrectionV1
            for item in self.replacement_media_identity_evidence
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "invalid media identity replacement bindings",
            )
        media_refs = tuple(
            item.media_ref for item in self.replacement_media_identity_evidence
        )
        if media_refs != tuple(sorted(set(media_refs))):
            _fail(
                AIReviewErrorCode.NON_CANONICAL_ORDER,
                "media identity replacements must be unique and ordered",
            )
        if self.outcome is AIAdjudicationOutcome.CHANGES_REQUIRED:
            main_replacement = self.replacement_ruleset_snapshot_id != "not_applicable"
            if main_replacement:
                _id(
                    self.replacement_ruleset_snapshot_id,
                    re.compile(r"^mss_[0-9a-f]{64}$", re.ASCII),
                    path="$.replacement_ruleset_snapshot_id",
                )
                _id(
                    self.replacement_evidence_snapshot_id,
                    re.compile(r"^mes_[0-9a-f]{64}$", re.ASCII),
                    path="$.replacement_evidence_snapshot_id",
                )
            elif self.replacement_evidence_snapshot_id != "not_applicable":
                _fail(
                    AIReviewErrorCode.INVALID_TYPE,
                    "ruleset and material evidence replacements are an exact pair",
                )
            if not main_replacement and not self.replacement_media_identity_evidence:
                _fail(
                    AIReviewErrorCode.INVALID_TRANSITION,
                    "changes_required needs an immutable replacement artifact",
                )
        elif (
            self.replacement_ruleset_snapshot_id != "not_applicable"
            or self.replacement_evidence_snapshot_id != "not_applicable"
            or self.replacement_media_identity_evidence
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "replacement refs are allowed only for changes_required",
            )
        if (
            type(self.adjudication_schema_version) is not int
            or self.adjudication_schema_version != CODEX_ADJUDICATION_SCHEMA_VERSION
            or self.adjudication_contract_version != CODEX_ADJUDICATION_CONTRACT_VERSION
        ):
            _fail(AIReviewErrorCode.UNKNOWN_SCHEMA, "unknown adjudication contract")
        expected_id = _derive_adjudication_id(self.to_dict(include_id=False))
        if self.adjudication_id != expected_id:
            _fail(AIReviewErrorCode.HASH_MISMATCH, "adjudication identity mismatch")

    @property
    def event_type(self) -> AIReviewEventType:
        return {
            AIAdjudicationOutcome.AI_CROSS_REVIEWED_NON_AUTHORITATIVE: (
                AIReviewEventType.CROSS_REVIEWED
            ),
            AIAdjudicationOutcome.CHANGES_REQUIRED: AIReviewEventType.CHANGES_REQUIRED,
            AIAdjudicationOutcome.QUARANTINED: AIReviewEventType.QUARANTINED,
        }[self.outcome]

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        value = {
            "adjudication_contract_version": self.adjudication_contract_version,
            "adjudication_schema_version": self.adjudication_schema_version,
            "adjudicator": self.adjudicator.to_dict(),
            "challenge_id": self.challenge_id,
            "challenger_report_sha256": self.challenger_report_sha256,
            "finding_adjudications": [
                item.to_dict() for item in self.finding_adjudications
            ],
            "outcome": self.outcome.value,
            "replacement_evidence_snapshot_id": self.replacement_evidence_snapshot_id,
            "replacement_media_identity_evidence": [
                item.to_dict() for item in self.replacement_media_identity_evidence
            ],
            "replacement_ruleset_snapshot_id": self.replacement_ruleset_snapshot_id,
            "review_content_sha256": self.review_content_sha256,
            "review_snapshot_id": self.review_snapshot_id,
        }
        if include_id:
            value["adjudication_id"] = self.adjudication_id
        return value


def _derive_adjudication_id(value: dict[str, Any]) -> str:
    return f"maa_{hashlib.sha256(ADJUDICATION_DOMAIN + _canonical_json(value)).hexdigest()}"


def create_adjudication(
    *,
    snapshot: AIReviewSnapshotV1,
    challenge: ClaudeChallengeV1,
    adjudicator: AdjudicatorAgentRunV1,
    finding_adjudications: tuple[FindingAdjudicationV1, ...],
    replacement_ruleset: MaterialRulesetSnapshotV1 | None = None,
    replacement_evidence: EvidenceManifestSnapshotV2 | None = None,
    replacement_media_identity_evidence: tuple[EvidenceManifestSnapshotV2, ...] = (),
) -> AIAdjudicationV1:
    if challenge.review_snapshot_id != snapshot.review_snapshot_id:
        _fail(AIReviewErrorCode.HASH_MISMATCH, "challenge targets another snapshot")
    if adjudicator.run_id in {
        snapshot.payload.creator.run_id,
        challenge.challenger.run_id,
    }:
        _fail(AIReviewErrorCode.INVALID_AGENT, "adjudicator run must be independent")
    all_findings = {
        finding.finding_ref: finding
        for result in challenge.report.claim_results
        for finding in result.findings
    }
    finding_claim_refs = {
        finding.finding_ref: result.claim_ref
        for result in challenge.report.claim_results
        for finding in result.findings
    }
    provided = {item.finding_ref: item for item in finding_adjudications}
    if set(all_findings) != set(provided):
        _fail(
            AIReviewErrorCode.INCOMPLETE_COVERAGE, "every finding must be adjudicated"
        )
    for finding_ref, finding in all_findings.items():
        disposition = provided[finding_ref].disposition
        if finding.severity in {
            AIFindingSeverity.CRITICAL,
            AIFindingSeverity.HIGH,
            AIFindingSeverity.MEDIUM,
        } and disposition not in {
            FindingDisposition.CORRECTED_IN_NEW_SNAPSHOT,
            FindingDisposition.QUARANTINED,
        }:
            _fail(
                AIReviewErrorCode.INVALID_TRANSITION,
                "critical/high/medium findings require correction or quarantine",
            )
        if disposition is FindingDisposition.ACCEPTED_NONBLOCKING and (
            finding.severity is not AIFindingSeverity.LOW
            or finding.category is not AIFindingCategory.NON_FACTUAL_DOCUMENTATION
        ):
            _fail(
                AIReviewErrorCode.INVALID_TRANSITION,
                "nonblocking acceptance is restricted to non-factual LOW findings",
            )
    has_quarantine = (
        any(
            item.disposition is FindingDisposition.QUARANTINED
            for item in finding_adjudications
        )
        or challenge.report.overall_verdict is ClaudeClaimVerdict.QUARANTINE
    )
    has_correction = any(
        item.disposition is FindingDisposition.CORRECTED_IN_NEW_SNAPSHOT
        for item in finding_adjudications
    )
    if has_quarantine:
        outcome = AIAdjudicationOutcome.QUARANTINED
    elif (
        has_correction
        or challenge.report.overall_verdict is ClaudeClaimVerdict.CHANGES_REQUIRED
    ):
        outcome = AIAdjudicationOutcome.CHANGES_REQUIRED
    else:
        outcome = AIAdjudicationOutcome.AI_CROSS_REVIEWED_NON_AUTHORITATIVE
    replacement_ruleset_id = "not_applicable"
    replacement_evidence_id = "not_applicable"
    identity_corrections: tuple[AIMediaIdentityCorrectionV1, ...] = ()
    if outcome is AIAdjudicationOutcome.CHANGES_REQUIRED:
        corrected_claim_refs = {
            finding_claim_refs[item.finding_ref]
            for item in finding_adjudications
            if item.disposition is FindingDisposition.CORRECTED_IN_NEW_SNAPSHOT
        }
        material_claim_refs = {item.claim_ref for item in snapshot.payload.claims}
        corrected_material = bool(corrected_claim_refs & material_claim_refs)
        identity_by_claim = {
            claim.claim_ref: identity
            for identity in snapshot.payload.media_identities
            for claim in identity.claims
        }
        corrected_identity_media = {
            identity_by_claim[claim_ref].media_ref
            for claim_ref in corrected_claim_refs
            if claim_ref in identity_by_claim
        }
        if corrected_material:
            if (
                type(replacement_ruleset) is not MaterialRulesetSnapshotV1
                or type(replacement_evidence) is not EvidenceManifestSnapshotV2
                or replacement_evidence.snapshot_id
                == snapshot.payload.evidence_snapshot_id
                or replacement_evidence.content_sha256
                == snapshot.payload.evidence_content_sha256
                or type(replacement_evidence.payload.target)
                is not MaterialRelationTargetV2
                or replacement_evidence.payload.target.ruleset_snapshot_id
                != replacement_ruleset.snapshot_id
                or (
                    replacement_ruleset.snapshot_id
                    != snapshot.payload.ruleset_snapshot_id
                    and replacement_ruleset.content_sha256
                    == snapshot.payload.ruleset_content_sha256
                )
            ):
                _fail(
                    AIReviewErrorCode.INVALID_TRANSITION,
                    "material correction requires new bound ruleset and evidence snapshots",
                )
            replacement_ruleset_id = replacement_ruleset.snapshot_id
            replacement_evidence_id = replacement_evidence.snapshot_id
        elif replacement_ruleset is not None or replacement_evidence is not None:
            _fail(
                AIReviewErrorCode.INVALID_TRANSITION,
                "unchallenged material artifacts cannot be replaced",
            )
        if type(replacement_media_identity_evidence) is not tuple or any(
            type(item) is not EvidenceManifestSnapshotV2
            for item in replacement_media_identity_evidence
        ):
            _fail(
                AIReviewErrorCode.INVALID_TYPE,
                "media identity replacements must be an exact typed tuple",
            )
        replacements_by_media = {}
        for replacement in replacement_media_identity_evidence:
            if type(replacement.payload.target) is not MediaIdentityTargetV2:
                _fail(
                    AIReviewErrorCode.SCOPE_MISMATCH,
                    "identity replacement requires media_identity target",
                )
            media_ref = replacement.payload.target.media_ref
            if media_ref in replacements_by_media:
                _fail(
                    AIReviewErrorCode.INCOMPLETE_COVERAGE,
                    "duplicate media identity replacement",
                )
            replacements_by_media[media_ref] = replacement
        if set(replacements_by_media) != corrected_identity_media:
            _fail(
                AIReviewErrorCode.INCOMPLETE_COVERAGE,
                "every and only corrected media identity needs a replacement snapshot",
            )
        corrections: list[AIMediaIdentityCorrectionV1] = []
        previous_by_media = {
            item.media_ref: item for item in snapshot.payload.media_identities
        }
        for media_ref in sorted(replacements_by_media):
            replacement = replacements_by_media[media_ref]
            previous = previous_by_media[media_ref]
            if (
                replacement.payload.domain_pack_id != snapshot.payload.domain_pack_id
                or replacement.snapshot_id == previous.evidence_snapshot_id
                or replacement.content_sha256 == previous.evidence_content_sha256
            ):
                _fail(
                    AIReviewErrorCode.INVALID_TRANSITION,
                    "media identity correction must change exact immutable evidence",
                )
            corrections.append(
                AIMediaIdentityCorrectionV1(
                    media_ref=media_ref,
                    previous_evidence_snapshot_id=previous.evidence_snapshot_id,
                    replacement_evidence_snapshot_id=replacement.snapshot_id,
                    replacement_evidence_content_sha256=replacement.content_sha256,
                )
            )
        identity_corrections = tuple(corrections)
    value = {
        "adjudication_contract_version": CODEX_ADJUDICATION_CONTRACT_VERSION,
        "adjudication_schema_version": CODEX_ADJUDICATION_SCHEMA_VERSION,
        "adjudicator": adjudicator.to_dict(),
        "challenge_id": challenge.challenge_id,
        "challenger_report_sha256": challenge.report_sha256,
        "finding_adjudications": [item.to_dict() for item in finding_adjudications],
        "outcome": outcome.value,
        "replacement_evidence_snapshot_id": replacement_evidence_id,
        "replacement_media_identity_evidence": [
            item.to_dict() for item in identity_corrections
        ],
        "replacement_ruleset_snapshot_id": replacement_ruleset_id,
        "review_content_sha256": snapshot.content_sha256,
        "review_snapshot_id": snapshot.review_snapshot_id,
    }
    return AIAdjudicationV1(
        adjudication_id=_derive_adjudication_id(value),
        review_snapshot_id=snapshot.review_snapshot_id,
        review_content_sha256=snapshot.content_sha256,
        challenge_id=challenge.challenge_id,
        challenger_report_sha256=challenge.report_sha256,
        adjudicator=adjudicator,
        outcome=outcome,
        finding_adjudications=finding_adjudications,
        replacement_ruleset_snapshot_id=replacement_ruleset_id,
        replacement_evidence_snapshot_id=replacement_evidence_id,
        replacement_media_identity_evidence=identity_corrections,
    )


def create_corrected_snapshot_pair(
    *,
    previous_ruleset: MaterialRulesetSnapshotV1,
    previous_evidence: EvidenceManifestSnapshotV2,
    ruleset_id: str,
    ruleset_payload: MaterialRulesetPayloadV1,
    manifest_id: str,
    evidence_payload: EvidenceManifestPayloadV2,
) -> tuple[MaterialRulesetSnapshotV1, EvidenceManifestSnapshotV2]:
    """Create new immutable identities from explicit corrected domain payloads."""

    ruleset = MaterialRulesetSnapshotV1.create(ruleset_id, ruleset_payload)
    evidence = EvidenceManifestSnapshotV2.create(manifest_id, evidence_payload)
    if (
        evidence.snapshot_id == previous_evidence.snapshot_id
        or evidence.content_sha256 == previous_evidence.content_sha256
        or (
            ruleset.snapshot_id != previous_ruleset.snapshot_id
            and ruleset.content_sha256 == previous_ruleset.content_sha256
        )
        or type(evidence.payload.target) is not MaterialRelationTargetV2
        or evidence.payload.target.ruleset_snapshot_id != ruleset.snapshot_id
    ):
        _fail(
            AIReviewErrorCode.INVALID_TRANSITION,
            "correction must create a changed, exactly rebound snapshot pair",
        )
    return ruleset, evidence


def create_corrected_media_identity_snapshot(
    *,
    previous_evidence: EvidenceManifestSnapshotV2,
    manifest_id: str,
    evidence_payload: EvidenceManifestPayloadV2,
) -> EvidenceManifestSnapshotV2:
    """Create a new immutable media-identity claim snapshot after a finding."""

    if type(previous_evidence.payload.target) is not MediaIdentityTargetV2:
        _fail(
            AIReviewErrorCode.SCOPE_MISMATCH,
            "previous Evidence must target a media identity",
        )
    evidence = EvidenceManifestSnapshotV2.create(manifest_id, evidence_payload)
    if (
        type(evidence.payload.target) is not MediaIdentityTargetV2
        or evidence.payload.target.media_ref
        != previous_evidence.payload.target.media_ref
        or evidence.payload.domain_pack_id != previous_evidence.payload.domain_pack_id
        or evidence.snapshot_id == previous_evidence.snapshot_id
        or evidence.content_sha256 == previous_evidence.content_sha256
    ):
        _fail(
            AIReviewErrorCode.INVALID_TRANSITION,
            "identity correction must change content without laundering its scope",
        )
    return evidence


__all__ = [
    "AIAdjudicationOutcome",
    "AIAdjudicationV1",
    "AIMediaIdentityCorrectionV1",
    "AIFindingCategory",
    "AIFindingSeverity",
    "CLAUDE_AUDIT_CONTRACT_VERSION",
    "CLAUDE_AUDIT_SCHEMA_VERSION",
    "CLAUDE_TASK_V1",
    "ClaudeAuditInputV1",
    "ClaudeAuditReportV1",
    "ClaudeChallengeV1",
    "ClaudeClaimAuditResultV1",
    "ClaudeClaimVerdict",
    "ClaudeFindingV1",
    "FindingAdjudicationV1",
    "FindingDisposition",
    "SourceIndependenceState",
    "build_claude_audit_input",
    "create_adjudication",
    "create_corrected_snapshot_pair",
    "create_corrected_media_identity_snapshot",
    "parse_claude_audit_report",
]
