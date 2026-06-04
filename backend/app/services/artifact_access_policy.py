from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class ArtifactAccessDenied(PermissionError):
    """Raised when a tenant/user scoped artifact lookup must not be exposed."""

    def __init__(self, operation: str, *, public_reason: str = "not_found") -> None:
        super().__init__(public_reason)
        self.operation = operation
        self.public_reason = public_reason
        self.event_name = "TenantAccessDenied"


@dataclass(frozen=True, slots=True)
class ArtifactAccessDecision:
    allowed: bool
    operation: str
    tenant_id: str
    user_id: str | None
    resource_type: str
    event_names: tuple[str, ...]


def authorize_artifact_access(
    resource: Any,
    *,
    tenant_id: str,
    user_id: str | None = None,
    operation: str = "read_artifact",
    owner_case: Any | None = None,
) -> ArtifactAccessDecision:
    """Authorize tenant-scoped artifact access without leaking existence.

    The function accepts ORM objects, dataclasses, or dictionaries. It is
    intentionally small and side-effect-free so RFQ, generated artifacts,
    consent views, and future matching artifacts can share the same IDOR guard.
    """

    _require_value(tenant_id, "tenant_id")
    if user_id is not None:
        _require_value(user_id, "user_id")

    resource_type = _resource_type(resource)
    _assert_tenant(resource, tenant_id, operation)
    if owner_case is not None:
        _assert_tenant(owner_case, tenant_id, operation)
        if user_id is not None:
            _assert_user(owner_case, user_id, operation)
    elif user_id is not None:
        _assert_optional_user(resource, user_id, operation)

    return ArtifactAccessDecision(
        allowed=True,
        operation=operation,
        tenant_id=tenant_id,
        user_id=user_id,
        resource_type=resource_type,
        event_names=("TenantAccessAllowed",),
    )


def authorize_document_access(
    document: Any,
    *,
    tenant_id: str,
    user_id: str | None = None,
    operation: str = "read_document",
) -> ArtifactAccessDecision:
    return authorize_artifact_access(
        document,
        tenant_id=tenant_id,
        user_id=user_id,
        operation=operation,
    )


def authorize_preview_consent_access(
    preview: Any,
    *,
    tenant_id: str,
    user_id: str,
    owner_case: Any,
) -> ArtifactAccessDecision:
    return authorize_artifact_access(
        preview,
        tenant_id=tenant_id,
        user_id=user_id,
        operation="grant_preview_consent",
        owner_case=owner_case,
    )


def _assert_tenant(resource: Any, tenant_id: str, operation: str) -> None:
    resource_tenant = _get(resource, "tenant_id")
    if not resource_tenant or str(resource_tenant) != str(tenant_id):
        raise ArtifactAccessDenied(operation)


def _assert_user(resource: Any, user_id: str, operation: str) -> None:
    resource_user = _get(resource, "user_id")
    if not resource_user or str(resource_user) != str(user_id):
        raise ArtifactAccessDenied(operation)


def _assert_optional_user(resource: Any, user_id: str, operation: str) -> None:
    for field in ("user_id", "owner_user_id", "created_by"):
        resource_user = _get(resource, field)
        if resource_user is None:
            continue
        if str(resource_user) != str(user_id):
            raise ArtifactAccessDenied(operation)
        return


def _require_value(value: str | None, field_name: str) -> None:
    if not str(value or "").strip():
        raise ValueError(f"{field_name} is required")


def _get(resource: Any, field: str) -> Any:
    if isinstance(resource, Mapping):
        return resource.get(field)
    return getattr(resource, field, None)


def _resource_type(resource: Any) -> str:
    artifact_type = _get(resource, "artifact_type")
    if artifact_type:
        return str(artifact_type)
    if _get(resource, "document_id"):
        return "document"
    return type(resource).__name__
