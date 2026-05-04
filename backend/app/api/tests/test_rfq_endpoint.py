from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import rfq as rfq_endpoint
from app.api.v1.endpoints.rfq import (
    RfqPreviewCreateRequest,
    create_rfq_preview,
    get_rfq_preview_export,
    rfq_download,
)
from app.services.auth.dependencies import RequestUser, get_current_request_user
from app.services.rfq_preview_service import (
    RfqExportBlockedError,
    RfqPreviewStaleError,
    RfqPreviewView,
)


def test_rfq_download_is_disabled_even_with_server_path() -> None:
    with pytest.raises(HTTPException) as exc_info:
        rfq_download("/etc/passwd")

    assert exc_info.value.status_code == 410
    assert "temporarily disabled" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_rfq_preview_create_requires_authenticated_request_user() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_request_user(authorization=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_calls_service_boundary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, session: object) -> None:
            captured["session"] = session

        async def create_preview_for_case(
            self,
            *,
            case_id: str,
            tenant_id: str,
            user_id: str,
            created_by: str,
            expected_case_revision: int | None = None,
        ) -> RfqPreviewView:
            captured.update(
                {
                    "case_id": case_id,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "created_by": created_by,
                    "expected_case_revision": expected_case_revision,
                }
            )
            return RfqPreviewView(
                preview_id="preview-1",
                case_id=case_id,
                case_revision=4,
                current_case_revision=4,
                stale=False,
                consent_status="not_requested",
                dispatch_enabled=False,
                payload={"meta": {"artifact_type": "rfq_preview", "case_revision": 4}},
                created_at=None,
            )

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    payload = await create_rfq_preview(
        raw_request=_Request(),
        body=RfqPreviewCreateRequest(
            action="create_preview",
            explicit_user_intent=True,
            expected_case_revision=4,
        ),
        case_id="case-123",
        user=_user(),
        session=object(),
    )

    assert captured["case_id"] == "case-123"
    assert captured["tenant_id"] == "tenant-1"
    assert captured["user_id"] == "user-1"
    assert captured["created_by"] == "user-1"
    assert captured["expected_case_revision"] == 4
    assert payload["preview_id"] == "preview-1"
    assert payload["case_revision"] == 4
    assert payload["dispatch_enabled"] is False
    assert payload["dispatch_allowed"] is False
    assert payload["external_contact_allowed"] is False
    assert payload["preview_action"] == "create_rfq_preview"
    assert (
        payload["preview_service_boundary"]
        == "RfqPreviewService.create_preview_for_case"
    )
    gate = payload["qualified_action_gate"]
    assert gate["preview_creation_requires_explicit_user_intent"] is True
    assert gate["export_requires_consent"] is True
    assert gate["dispatch_allowed"] is False
    assert gate["external_contact_allowed"] is False
    contract = payload["result_contract"]
    assert contract["artifact_type"] == "rfq_preview"
    assert contract["action"] == "create_rfq_preview"
    assert contract["no_external_dispatch"] is True


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_requires_explicit_user_intent() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_rfq_preview(
            raw_request=_Request(),
            body=RfqPreviewCreateRequest(
                action="create_preview",
                explicit_user_intent=False,
            ),
            case_id="case-123",
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rfq_preview_explicit_intent_required"


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_rejects_dispatch_flags() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_rfq_preview(
            raw_request=_Request(),
            body=RfqPreviewCreateRequest(
                action="create_preview",
                explicit_user_intent=True,
                dispatch_allowed=True,
            ),
            case_id="case-123",
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "rfq_preview_external_dispatch_not_allowed"


@pytest.mark.asyncio
async def test_rfq_preview_create_endpoint_maps_expected_revision_mismatch(
    monkeypatch,
) -> None:
    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def create_preview_for_case(self, **_kwargs: object) -> object:
            raise RfqPreviewStaleError(
                "case revision changed; refresh before creating preview"
            )

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    with pytest.raises(HTTPException) as exc_info:
        await create_rfq_preview(
            raw_request=_Request(),
            body=RfqPreviewCreateRequest(
                action="create_preview",
                explicit_user_intent=True,
                expected_case_revision=3,
            ),
            case_id="case-123",
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "rfq_preview_stale"


@pytest.mark.asyncio
async def test_rfq_preview_export_endpoint_returns_manual_json_contract(monkeypatch) -> None:
    class FakeExportDocument:
        def as_dict(self) -> dict[str, object]:
            return {
                "export_generated": True,
                "preview_id": "preview-1",
                "case_revision": 4,
                "artifact_type": "rfq_preview",
                "export_format": "json",
                "dispatch_enabled": False,
                "automatic_dispatch_allowed": False,
                "no_final_technical_release": True,
                "event_names": (
                    "RFQConsentGranted",
                    "ExportGenerated",
                    "ExternalDispatchBlocked",
                    "RFQDispatchDisabled",
                ),
                "content": {"title": "RFQ Preview"},
            }

    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def generate_export(
            self,
            *,
            preview_id: str,
            tenant_id: str,
            user_id: str,
        ) -> FakeExportDocument:
            assert preview_id == "preview-1"
            assert tenant_id == "tenant-1"
            assert user_id == "user-1"
            return FakeExportDocument()

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    payload = await get_rfq_preview_export(
        preview_id="preview-1",
        raw_request=_Request(),
        user=_user(),
        session=object(),
    )

    assert payload["export_generated"] is True
    assert payload["artifact_type"] == "rfq_preview"
    assert payload["dispatch_enabled"] is False
    assert payload["automatic_dispatch_allowed"] is False
    assert "ExternalDispatchBlocked" in payload["event_names"]


@pytest.mark.asyncio
async def test_rfq_preview_export_endpoint_maps_blocked_export(monkeypatch) -> None:
    class FakeService:
        def __init__(self, session: object) -> None:
            self.session = session

        async def generate_export(self, **_kwargs: object) -> object:
            raise RfqExportBlockedError("RFQ preview consent is required before export")

    monkeypatch.setattr(rfq_endpoint, "RfqPreviewService", FakeService)

    with pytest.raises(HTTPException) as exc_info:
        await get_rfq_preview_export(
            preview_id="preview-1",
            raw_request=_Request(),
            user=_user(),
            session=object(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error"] == "rfq_export_blocked"
    assert "ExportBlocked" in exc_info.value.detail["event_names"]
    assert "ExternalDispatchBlocked" in exc_info.value.detail["event_names"]


class _Request:
    headers: dict[str, str] = {}


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="user-1",
        sub="user-1",
        roles=[],
        tenant_id="tenant-1",
    )
