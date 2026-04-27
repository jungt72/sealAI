from __future__ import annotations

from typing import Any, Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import error_detail
from app.database import get_db
from app.services.auth.dependencies import RequestUser, get_current_request_user
from app.services.rfq_preview_service import (
    RfqPreviewError,
    RfqPreviewNotFound,
    RfqPreviewService,
    RfqPreviewStaleError,
    RfqPreviewView,
)

router = APIRouter()


class RfqPreviewConsentRequest(BaseModel):
    shared_sections: list[str] = Field(..., min_length=1)
    shared_documents: list[str] = Field(default_factory=list)
    intended_recipients: list[str] = Field(default_factory=list)
    user_acknowledged_open_points: bool = False
    user_acknowledged_no_final_release: bool = False


@router.post("/preview")
async def create_rfq_preview(
    raw_request: Request,
    case_id: str = Query(..., description="Case id to freeze into an RFQ preview"),
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    request_id = raw_request.headers.get("X-Request-Id") or raw_request.headers.get("X-Request-ID")
    service = RfqPreviewService(session)
    try:
        view = await service.create_preview_for_case(
            case_id=case_id,
            user_id=user.user_id,
            created_by=user.user_id,
        )
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
        view = await service.get_latest_preview_for_case(case_id=case_id, user_id=user.user_id)
    except RfqPreviewNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("rfq_preview_not_found", request_id=request_id),
        ) from exc
    return _preview_response(view)


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
    return value
