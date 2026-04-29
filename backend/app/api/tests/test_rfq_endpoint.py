from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import rfq as rfq_endpoint
from app.api.v1.endpoints.rfq import get_rfq_preview_export, rfq_download
from app.services.auth.dependencies import RequestUser
from app.services.rfq_preview_service import RfqExportBlockedError


def test_rfq_download_is_disabled_even_with_server_path() -> None:
    with pytest.raises(HTTPException) as exc_info:
        rfq_download("/etc/passwd")

    assert exc_info.value.status_code == 410
    assert "temporarily disabled" in str(exc_info.value.detail)


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
