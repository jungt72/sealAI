from __future__ import annotations

import pytest

from app.services.audit.event_builder import (
    TRUST_EVENT_NAMES,
    TrustAuditEventBuilder,
    build_trust_audit_event,
    redact_audit_payload,
)


def test_audit_event_contains_tenant_case_revision_and_source() -> None:
    event = build_trust_audit_event(
        event_name="RFQPreviewGenerated",
        tenant_id="tenant-1",
        case_id="case-1",
        case_revision=7,
        source="rfq_preview_service",
        payload={"preview_id": "preview-1"},
    )

    assert event.event_name == "RFQPreviewGenerated"
    assert event.tenant_id == "tenant-1"
    assert event.case_id == "case-1"
    assert event.case_revision == 7
    assert event.source == "rfq_preview_service"
    assert event.payload == {"preview_id": "preview-1"}


def test_audit_payload_redacts_secrets_recursively() -> None:
    payload = redact_audit_payload(
        {
            "api_key": "sk-secret",
            "nested": {
                "Authorization": "Bearer token",
                "safe": "value",
                "items": [{"refresh_token": "abc"}],
            },
        }
    )

    assert payload["api_key"] == "[REDACTED]"
    assert payload["nested"]["Authorization"] == "[REDACTED]"
    assert payload["nested"]["items"][0]["refresh_token"] == "[REDACTED]"
    assert payload["nested"]["safe"] == "value"


def test_llm_research_fallback_use_is_auditable() -> None:
    event = TrustAuditEventBuilder().build(
        event_name="LLMResearchFallbackUsed",
        tenant_id="tenant-1",
        case_id="case-knowledge",
        case_revision=None,
        source="knowledge_service",
        payload={
            "source_type": "llm_research_fallback",
            "validation_status": "unvalidated",
        },
    )

    assert event.event_name == "LLMResearchFallbackUsed"
    assert event.payload["validation_status"] == "unvalidated"
    assert event.as_dict()["payload"]["source_type"] == "llm_research_fallback"


def test_security_and_artifact_events_are_registered() -> None:
    expected = {
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

    assert TRUST_EVENT_NAMES == expected


def test_unsupported_event_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported audit event"):
        TrustAuditEventBuilder().build(
            event_name="UntrackedEvent",
            tenant_id="tenant-1",
            source="test",
        )


def test_missing_tenant_or_source_is_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        TrustAuditEventBuilder().build(
            event_name="TenantAccessDenied",
            tenant_id="",
            source="artifact_access_policy",
        )

    with pytest.raises(ValueError, match="source"):
        TrustAuditEventBuilder().build(
            event_name="TenantAccessDenied",
            tenant_id="tenant-1",
            source="",
        )
