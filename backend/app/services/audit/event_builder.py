from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "private_key",
    }
)

TRUST_EVENT_NAMES = frozenset(
    {
        "RFQPreviewGenerated",
        "RFQConsentGranted",
        "ExportGenerated",
        "ManufacturerFitComputed",
        "NoSuitablePartnerFound",
        "LLMResearchFallbackUsed",
        "ArtifactMarkedStale",
        "TenantAccessDenied",
        "UploadRejected",
    }
)


@dataclass(frozen=True, slots=True)
class TrustAuditEvent:
    event_name: str
    tenant_id: str
    case_id: str | None
    case_revision: int | None
    source: str
    payload: dict[str, Any]
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "tenant_id": self.tenant_id,
            "case_id": self.case_id,
            "case_revision": self.case_revision,
            "source": self.source,
            "payload": self.payload,
            "created_at": self.created_at,
        }


class TrustAuditEventBuilder:
    """Build redacted audit events for trust-relevant v0.8.3 transitions."""

    def build(
        self,
        *,
        event_name: str,
        tenant_id: str,
        source: str,
        case_id: str | None = None,
        case_revision: int | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> TrustAuditEvent:
        if event_name not in TRUST_EVENT_NAMES:
            raise ValueError(f"unsupported audit event: {event_name}")
        if not str(tenant_id or "").strip():
            raise ValueError("tenant_id is required")
        if not str(source or "").strip():
            raise ValueError("source is required")
        if case_revision is not None and (
            not isinstance(case_revision, int) or isinstance(case_revision, bool)
        ):
            raise ValueError("case_revision must be an integer or None")

        return TrustAuditEvent(
            event_name=event_name,
            tenant_id=str(tenant_id),
            case_id=None if case_id is None else str(case_id),
            case_revision=case_revision,
            source=str(source),
            payload=redact_audit_payload(dict(payload or {})),
            created_at=datetime.now(timezone.utc).isoformat(),
        )


def build_trust_audit_event(
    *,
    event_name: str,
    tenant_id: str,
    source: str,
    case_id: str | None = None,
    case_revision: int | None = None,
    payload: Mapping[str, Any] | None = None,
) -> TrustAuditEvent:
    return TrustAuditEventBuilder().build(
        event_name=event_name,
        tenant_id=tenant_id,
        source=source,
        case_id=case_id,
        case_revision=case_revision,
        payload=payload,
    )


def redact_audit_payload(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                redacted[str(key)] = "[REDACTED]"
            else:
                redacted[str(key)] = redact_audit_payload(item)
        return redacted
    if isinstance(value, tuple):
        return tuple(redact_audit_payload(item) for item in value)
    if isinstance(value, list):
        return [redact_audit_payload(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().casefold().replace("-", "_")
    return normalized in SENSITIVE_KEYS or any(
        marker in normalized for marker in ("password", "secret", "token")
    )
