from __future__ import annotations

from typing import Any, Literal, Mapping

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.renderers.rfq_pdf import render_rfq_export_pdf
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
from app.services.rwdr_mvp_brief import (
    RWDRCaseStateNotFound,
    RWDRCaseStateValidationError,
    build_rwdr_brief_from_confirmed_fields,
    create_db_persisted_rwdr_case,
    diff_db_persisted_rwdr_case_snapshots,
    evaluate_db_persisted_rwdr_case,
    export_db_persisted_rwdr_case_markdown,
    export_db_persisted_rwdr_case_pdf_document,
    generate_db_persisted_rwdr_brief,
    get_db_persisted_rwdr_case_snapshot,
    get_db_persisted_rwdr_case,
    list_db_persisted_rwdr_case_snapshots,
    update_db_persisted_rwdr_confirmations,
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


class RwdrAnalyzeRequest(BaseModel):
    raw_inquiry: str = Field(..., min_length=1, max_length=12000)

    model_config = ConfigDict(extra="forbid")


class RwdrBriefRequest(BaseModel):
    raw_inquiry: str = Field(default="", max_length=12000)
    fields: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RwdrConfirmationDecision(BaseModel):
    field: str
    action: Literal["confirm", "edit", "explicitly_unknown", "reject"]
    value: Any | None = None
    unit: str | None = None
    source_span: str | None = None

    model_config = ConfigDict(extra="forbid")


class RwdrConfirmationsRequest(BaseModel):
    decisions: list[RwdrConfirmationDecision] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


@router.post("/rwdr/analyze")
async def analyze_rwdr_inquiry(
    body: RwdrAnalyzeRequest,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("missing_user_scope"),
        )
    return _json_safe(
        await create_db_persisted_rwdr_case(
            session=session,
            raw_inquiry=body.raw_inquiry,
            user_id=user.user_id,
            tenant_id=_request_tenant_id(user),
        )
    )


@router.post("/rwdr/brief")
async def generate_rwdr_brief(
    body: RwdrBriefRequest,
    user: RequestUser = Depends(get_current_request_user),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("missing_user_scope"),
        )
    return _json_safe(
        build_rwdr_brief_from_confirmed_fields(
            raw_inquiry=body.raw_inquiry,
            fields=body.fields,
        )
    )


@router.get("/rwdr/cases/{case_id}")
async def get_rwdr_case(
    case_id: str,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(await get_db_persisted_rwdr_case(session=session, case_id=case_id))
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_case_not_found")) from exc


@router.get("/rwdr/cases/{case_id}/snapshots")
async def list_rwdr_case_snapshots(
    case_id: str,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(
            {
                "case_id": case_id,
                "snapshots": await list_db_persisted_rwdr_case_snapshots(session=session, case_id=case_id),
            }
        )
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_case_not_found")) from exc


@router.get("/rwdr/cases/{case_id}/snapshots/{revision_number}")
async def get_rwdr_case_snapshot(
    case_id: str,
    revision_number: int,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(
            await get_db_persisted_rwdr_case_snapshot(
                session=session,
                case_id=case_id,
                revision_number=revision_number,
            )
        )
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_snapshot_not_found")) from exc


@router.get("/rwdr/cases/{case_id}/diff/{from_revision}/{to_revision}")
async def diff_rwdr_case_snapshots(
    case_id: str,
    from_revision: int,
    to_revision: int,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(
            await diff_db_persisted_rwdr_case_snapshots(
                session=session,
                case_id=case_id,
                from_revision=from_revision,
                to_revision=to_revision,
            )
        )
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_snapshot_not_found")) from exc


@router.post("/rwdr/cases/{case_id}/confirmations")
async def update_rwdr_confirmations(
    case_id: str,
    body: RwdrConfirmationsRequest,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(
            await update_db_persisted_rwdr_confirmations(
                session=session,
                case_id=case_id,
                decisions=[item.model_dump() for item in body.decisions],
            )
        )
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_case_not_found")) from exc
    except RWDRCaseStateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error_detail("rwdr_confirmation_invalid", message=str(exc))) from exc


@router.post("/rwdr/cases/{case_id}/evaluate")
async def evaluate_rwdr_case(
    case_id: str,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(await evaluate_db_persisted_rwdr_case(session=session, case_id=case_id))
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_case_not_found")) from exc


@router.post("/rwdr/cases/{case_id}/brief")
async def generate_persisted_rwdr_case_brief(
    case_id: str,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(await generate_db_persisted_rwdr_brief(session=session, case_id=case_id))
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_case_not_found")) from exc


@router.get("/rwdr/cases/{case_id}/export.md")
async def export_rwdr_case_markdown(
    case_id: str,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        return _json_safe(await export_db_persisted_rwdr_case_markdown(session=session, case_id=case_id))
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_case_not_found")) from exc


@router.get("/rwdr/cases/{case_id}/export.pdf")
async def export_rwdr_case_pdf(
    case_id: str,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    if not user.user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_detail("missing_user_scope"))
    try:
        document = await export_db_persisted_rwdr_case_pdf_document(session=session, case_id=case_id)
    except RWDRCaseStateNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail("rwdr_case_not_found")) from exc
    pdf_bytes = render_rfq_export_pdf(document)
    filename = f"sealai-rwdr-{_safe_file_token(case_id)}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-SealAI-RWDR-Case-ID": case_id,
            "X-SealAI-Dispatch-Allowed": "false",
            "X-SealAI-External-Contact-Allowed": "false",
            "X-SealAI-No-Final-Technical-Release": "true",
        },
    )


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


@router.get("/preview/{preview_id}/export.pdf")
async def get_rfq_preview_export_pdf(
    preview_id: str,
    raw_request: Request,
    user: RequestUser = Depends(get_current_request_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
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

    pdf_bytes = render_rfq_export_pdf(document.as_dict())
    filename = (
        f"sealai-rfq-{_safe_file_token(document.case_id)}-"
        f"{_safe_file_token(document.preview_id)}.pdf"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-SealAI-RFQ-Preview-ID": document.preview_id,
            "X-SealAI-Dispatch-Allowed": "false",
            "X-SealAI-External-Contact-Allowed": "false",
            "X-SealAI-No-Final-Technical-Release": "true",
        },
    )


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


def _safe_file_token(value: object) -> str:
    token = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in str(value or "")
    ).strip("-")
    return token[:80] or "rfq"
