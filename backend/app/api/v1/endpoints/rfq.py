from __future__ import annotations

from typing import Any, Literal, Mapping

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import error_detail
from app.database import get_db
from app.services.auth.dependencies import RequestUser, get_current_request_user
from app.services.rfq_preview_service import (
    RFQ_PREVIEW_ARTIFACT_TYPE,
    RfqExportBlockedError,
    RfqPreviewError,
    RfqPreviewNotFound,
    RfqPreviewService,
    RfqPreviewStaleError,
    RfqPreviewView,
)

router = APIRouter()


def _request_tenant_id(user: RequestUser) -> str:
    tenant_id = str(user.tenant_id or user.user_id or "").strip()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("missing_tenant_or_user_scope"),
        )
    return tenant_id


class RfqPreviewCreateRequest(BaseModel):
    action: Literal["create_preview"] = "create_preview"
    explicit_user_intent: bool = Field(
        ...,
        description="True only when the user explicitly requested RFQ preview creation.",
    )
    expected_case_revision: int | None = Field(
        default=None,
        ge=0,
        description="Optional frontend-observed case revision for stale-action protection.",
    )
    dispatch_allowed: bool = False
    external_contact_allowed: bool = False

    model_config = ConfigDict(extra="forbid")


class RfqPreviewConsentRequest(BaseModel):
    shared_sections: list[str] = Field(..., min_length=1)
    shared_documents: list[str] = Field(default_factory=list)
    intended_recipients: list[str] = Field(default_factory=list)
    user_acknowledged_open_points: bool = False
    user_acknowledged_no_final_release: bool = False
    user_acknowledged_export_intent: bool = False


@router.post("/preview")
async def create_rfq_preview(
    raw_request: Request,
    body: RfqPreviewCreateRequest = Body(...),
    case_id: str = Query(..., description="Case id to freeze into an RFQ preview"),
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    if not body.explicit_user_intent:
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "rfq_preview_explicit_intent_required",
                request_id=request_id,
                message="RFQ preview creation requires an explicit user action.",
            ),
        )
    if body.dispatch_allowed or body.external_contact_allowed:
        raise HTTPException(
            status_code=422,
            detail=error_detail(
                "rfq_preview_external_dispatch_not_allowed",
                request_id=request_id,
                message="RFQ preview creation does not permit dispatch or external contact.",
            ),
        )
    service = RfqPreviewService(session)
    try:
        view = await service.create_preview_for_case(
            case_id=case_id,
            tenant_id=_request_tenant_id(user),
            user_id=user.user_id,
            created_by=user.user_id,
            expected_case_revision=body.expected_case_revision,
        )
    except RfqPreviewStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail("rfq_preview_stale", request_id=request_id, message=str(exc)),
        ) from exc
    except RfqPreviewNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("rfq_preview_case_not_found", request_id=request_id),
        ) from exc
    except RfqPreviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail("rfq_preview_invalid", request_id=request_id, message=str(exc)),
        ) from exc
    return _preview_response(view)


@router.get("/preview")
async def get_rfq_preview(
    raw_request: Request,
    case_id: str = Query(..., description="Case id"),
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    service = RfqPreviewService(session)
    try:
        view = await service.get_latest_preview_for_case(
            case_id=case_id,
            tenant_id=_request_tenant_id(user),
            user_id=user.user_id,
        )
    except RfqPreviewNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("rfq_preview_not_found", request_id=request_id),
        ) from exc
    return _preview_response(view)


@router.get("/preview/{preview_id}/export")
async def get_rfq_preview_export(
    preview_id: str,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    service = RfqPreviewService(session)
    try:
        document = await service.generate_export(
            preview_id=preview_id,
            tenant_id=_request_tenant_id(user),
            user_id=user.user_id,
        )
    except RfqPreviewStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "rfq_export_stale",
                request_id=request_id,
                message=str(exc),
                event_names=(
                    "ExportBlocked",
                    "ExternalDispatchBlocked",
                    "RFQDispatchDisabled",
                ),
            ),
        ) from exc
    except RfqPreviewNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("rfq_preview_not_found", request_id=request_id),
        ) from exc
    except RfqExportBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail(
                "rfq_export_blocked",
                request_id=request_id,
                message=str(exc),
                event_names=exc.event_names,
            ),
        ) from exc
    return _json_safe(document.as_dict())


@router.post("/preview/{preview_id}/consent")
async def grant_rfq_preview_consent(
    preview_id: str,
    body: RfqPreviewConsentRequest,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    service = RfqPreviewService(session)
    try:
        view = await service.grant_preview_consent(
            preview_id=preview_id,
            tenant_id=_request_tenant_id(user),
            user_id=user.user_id,
            granted_by=user.user_id,
            consent_scope=body.model_dump(),
        )
    except RfqPreviewStaleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail("rfq_preview_stale", request_id=request_id, message=str(exc)),
        ) from exc
    except RfqPreviewNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("rfq_preview_not_found", request_id=request_id),
        ) from exc
    except RfqPreviewError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail("rfq_preview_consent_invalid", request_id=request_id, message=str(exc)),
        ) from exc
    return _preview_response(view)


@router.get("/download")
def rfq_download(path: str = Query(..., description="Server-Pfad zur PDF")):
    raise HTTPException(
        status_code=410,
        detail="RFQ download is temporarily disabled until an allowlisted document flow is available.",
    )


def _preview_response(view: RfqPreviewView) -> dict[str, Any]:
    return {
        "preview_id": view.preview_id,
        "case_id": view.case_id,
        "case_revision": view.case_revision,
        "current_case_revision": view.current_case_revision,
        "stale": view.stale,
        "consent_status": view.consent_status,
        "dispatch_enabled": view.dispatch_enabled,
        "dispatch_allowed": False,
        "external_contact_allowed": False,
        "preview_action": "create_rfq_preview",
        "preview_service_boundary": "RfqPreviewService.create_preview_for_case",
        "qualified_action_gate": {
            "consent_required_before_export_or_sharing": True,
            "dispatch_allowed": False,
            "external_contact_allowed": False,
            "preview_creation_requires_explicit_user_intent": True,
            "export_requires_consent": True,
        },
        "result_contract": {
            "artifact_type": RFQ_PREVIEW_ARTIFACT_TYPE,
            "action": "create_rfq_preview",
            "service_boundary": "RfqPreviewService.create_preview_for_case",
            "case_revision": view.case_revision,
            "no_external_dispatch": True,
            "manufacturer_review_required": True,
        },
        "created_at": view.created_at.isoformat() if view.created_at else None,
        "payload": _json_safe(view.payload),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
