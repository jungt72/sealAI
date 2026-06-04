from __future__ import annotations

import pytest

from app.services.artifact_access_policy import (
    ArtifactAccessDenied,
    authorize_artifact_access,
    authorize_document_access,
    authorize_preview_consent_access,
)


def _case(*, tenant_id: str = "tenant-a", user_id: str = "user-a") -> dict[str, str]:
    return {"id": "case-1", "tenant_id": tenant_id, "user_id": user_id}


def _artifact(
    *,
    tenant_id: str = "tenant-a",
    artifact_type: str = "rfq_preview",
    created_by: str | None = None,
) -> dict[str, str]:
    payload = {
        "extract_id": "artifact-1",
        "case_id": "case-1",
        "tenant_id": tenant_id,
        "artifact_type": artifact_type,
    }
    if created_by is not None:
        payload["created_by"] = created_by
    return payload


def test_user_a_cannot_read_user_b_rfq_preview() -> None:
    with pytest.raises(ArtifactAccessDenied) as exc_info:
        authorize_artifact_access(
            _artifact(tenant_id="tenant-b", artifact_type="rfq_preview"),
            tenant_id="tenant-a",
            user_id="user-a",
            owner_case=_case(tenant_id="tenant-b", user_id="user-b"),
        )

    assert exc_info.value.public_reason == "not_found"
    assert exc_info.value.event_name == "TenantAccessDenied"
    assert "artifact-1" not in str(exc_info.value)


def test_user_a_cannot_consent_user_b_preview() -> None:
    with pytest.raises(ArtifactAccessDenied) as exc_info:
        authorize_preview_consent_access(
            _artifact(tenant_id="tenant-b", artifact_type="rfq_preview"),
            tenant_id="tenant-a",
            user_id="user-a",
            owner_case=_case(tenant_id="tenant-b", user_id="user-b"),
        )

    assert exc_info.value.operation == "grant_preview_consent"
    assert exc_info.value.public_reason == "not_found"


def test_user_a_cannot_read_user_b_generated_artifact() -> None:
    with pytest.raises(ArtifactAccessDenied):
        authorize_artifact_access(
            _artifact(tenant_id="tenant-b", artifact_type="compatibility_matrix"),
            tenant_id="tenant-a",
            user_id="user-a",
        )


def test_user_a_cannot_read_user_b_document() -> None:
    with pytest.raises(ArtifactAccessDenied):
        authorize_document_access(
            {
                "document_id": "doc-b",
                "tenant_id": "tenant-b",
                "artifact_type": "document",
            },
            tenant_id="tenant-a",
            user_id="user-a",
        )


def test_user_a_cannot_read_user_b_matching_artifact() -> None:
    with pytest.raises(ArtifactAccessDenied):
        authorize_artifact_access(
            _artifact(tenant_id="tenant-b", artifact_type="manufacturer_fit_matrix"),
            tenant_id="tenant-a",
            user_id="user-a",
        )


def test_same_tenant_same_user_artifact_access_is_allowed() -> None:
    decision = authorize_artifact_access(
        _artifact(tenant_id="tenant-a", artifact_type="rfq_preview"),
        tenant_id="tenant-a",
        user_id="user-a",
        owner_case=_case(tenant_id="tenant-a", user_id="user-a"),
    )

    assert decision.allowed is True
    assert decision.resource_type == "rfq_preview"
    assert decision.event_names == ("TenantAccessAllowed",)


def test_same_tenant_cross_user_case_is_denied() -> None:
    with pytest.raises(ArtifactAccessDenied):
        authorize_artifact_access(
            _artifact(tenant_id="tenant-a", artifact_type="rfq_preview"),
            tenant_id="tenant-a",
            user_id="user-a",
            owner_case=_case(tenant_id="tenant-a", user_id="user-b"),
        )


def test_explicit_created_by_cross_user_artifact_is_denied() -> None:
    with pytest.raises(ArtifactAccessDenied):
        authorize_artifact_access(
            _artifact(
                tenant_id="tenant-a",
                artifact_type="internal_engineering_note",
                created_by="user-b",
            ),
            tenant_id="tenant-a",
            user_id="user-a",
        )
