"""Versioned, fail-closed governance schemas for API content and future uploads."""

from __future__ import annotations

import json
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RightsBasis(str, Enum):
    OWNER_SUPPLIED = "owner_supplied"
    DOCUMENTED_PERMISSION = "documented_permission"
    REVIEW_REQUIRED = "review_required"


class LicenseId(str, Enum):
    OWNER_SUPPLIED = "owner_supplied"
    DOCUMENTED_PERMISSION = "documented_permission"
    CC_BY_4_0 = "cc-by-4.0"
    CC0_1_0 = "cc0-1.0"
    REVIEW_REQUIRED = "review_required"


class DocumentType(str, Enum):
    FIELD_OUTCOME = "field_outcome"
    TECHNICAL_NOTE = "technical_note"
    TEST_REPORT = "test_report"
    OTHER_REVIEW_REQUIRED = "other_review_required"


class PiiClassification(str, Enum):
    NONE_DECLARED = "none_declared"
    PRESENT = "present"
    UNKNOWN = "unknown"


class LifecycleReason(str, Enum):
    USER_WITHDRAWAL = "user_withdrawal"
    LEAD_CANCELLED = "lead_cancelled"
    RETENTION_REVIEW_DUE = "retention_review_due"


class GovernanceEnvelope(BaseModel):
    """Client declaration plus server-authority version bindings.

    The server still treats every accepted text as untrusted and quarantined. A declaration is a
    workflow input, not a legal determination or a promotion into grounding.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._~-]+$")
    policy_authority_ref: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/~-]+$",
    )
    purpose_version: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/~-]+$",
    )
    consent_version: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/~-]+$",
    )
    rights_confirmed: Literal[True]
    rights_basis: RightsBasis
    license_id: LicenseId
    provenance: str = Field(min_length=1, max_length=255)
    document_type: DocumentType
    pii_classification: PiiClassification
    prompt_trust: Literal["untrusted"] = "untrusted"

    @model_validator(mode="after")
    def validate_rights_license_pair(self) -> "GovernanceEnvelope":
        allowed = {
            RightsBasis.OWNER_SUPPLIED: {
                LicenseId.OWNER_SUPPLIED,
                LicenseId.CC_BY_4_0,
                LicenseId.CC0_1_0,
                LicenseId.REVIEW_REQUIRED,
            },
            RightsBasis.DOCUMENTED_PERMISSION: {
                LicenseId.DOCUMENTED_PERMISSION,
                LicenseId.CC_BY_4_0,
                LicenseId.CC0_1_0,
                LicenseId.REVIEW_REQUIRED,
            },
            RightsBasis.REVIEW_REQUIRED: {LicenseId.REVIEW_REQUIRED},
        }
        if self.license_id not in allowed[self.rights_basis]:
            raise ValueError(
                "license identifier does not match the declared rights basis"
            )
        return self


class GovernedUploadMetadata(GovernanceEnvelope):
    """Mandatory metadata contract for any future binary upload endpoint.

    This schema does not activate file storage. A later upload implementation must additionally
    verify content bytes/type, quarantine the object outside the web root, and bind the digest below.
    """

    original_filename: str = Field(min_length=1, max_length=255)
    media_type: Literal[
        "application/pdf",
        "text/plain",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_bytes: int = Field(ge=1, le=10_485_760)


class HandoffGovernance(BaseModel):
    """Version-bound user confirmation for one manufacturer handoff."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9._~-]+$")
    policy_authority_ref: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/~-]+$",
    )
    purpose_version: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/~-]+$",
    )
    consent_version: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/~-]+$",
    )
    handoff_confirmed: Literal[True]
    pii_classification: PiiClassification
    prompt_trust: Literal["untrusted"] = "untrusted"


_PROMPT_INJECTION_SIGNALS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "ignoriere vorherige anweisungen",
    "system prompt",
    "developer message",
    "<|system|>",
    "instructions above",
)


def has_prompt_injection_signal(*values: str) -> bool:
    normalized = "\n".join(values).casefold()
    return any(signal in normalized for signal in _PROMPT_INJECTION_SIGNALS)


def canonical_content_bytes(payload: object) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
