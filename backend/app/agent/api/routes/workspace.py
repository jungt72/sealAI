import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from fastapi.responses import HTMLResponse

from app.agent.api.models import (
    CaseListItemResponse,
    CaseMetadataResponse,
    GovernedSnapshotResponse,
    GovernedSnapshotRevisionListItemResponse,
)
from app.api.v1.schemas.case_workspace import CaseWorkspaceProjection
from app.api.v1.projections.case_workspace import (
    project_case_workspace_from_governed_state,
    project_case_workspace_from_ssot,
)
from app.api.v1.renderers.rfq_html import render_rfq_html
from app.agent.state.persistence import (
    list_cases_async,
    get_case_by_number_async,
    get_latest_governed_case_snapshot_async,
    list_governed_case_snapshots_async,
    get_governed_case_snapshot_by_revision_async,
)
from app.services.auth.dependencies import RequestUser, get_current_request_user, canonical_user_id
from app.agent.api.deps import _canonical_scope
from app.agent.api.loaders import (
    _load_live_governed_state,
    _load_guarded_workspace_projection_source,
    _load_governed_state_snapshot_projection_source,
    _load_preferred_governed_workspace_source,
)

_log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/cases", response_model=List[CaseListItemResponse])
async def list_cases(
    limit: int = Query(50, ge=1, le=200),
    current_user: RequestUser = Depends(get_current_request_user),
):
    owner_id = canonical_user_id(current_user)
    items = await list_cases_async(user_id=owner_id, limit=limit)
    return [CaseListItemResponse(**item) for item in items]

@router.get("/cases/{case_id}", response_model=CaseMetadataResponse)
async def get_case_metadata(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
):
    owner_id = canonical_user_id(current_user)
    case_data = await get_case_by_number_async(case_number=case_id, user_id=owner_id)
    if not case_data:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return CaseMetadataResponse(**case_data)

@router.get("/cases/{case_id}/snapshots/latest", response_model=GovernedSnapshotResponse)
async def get_latest_case_snapshot(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
):
    owner_id = canonical_user_id(current_user)
    snapshot = await get_latest_governed_case_snapshot_async(
        case_number=case_id, user_id=owner_id
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshots found for case '{case_id}'")

    return GovernedSnapshotResponse(
        case_number=snapshot.case_number,
        revision=snapshot.revision,
        state_json=snapshot.state_json,
        basis_hash=snapshot.basis_hash,
        created_at=snapshot.created_at,
    )

@router.get("/cases/{case_id}/snapshots", response_model=List[GovernedSnapshotRevisionListItemResponse])
async def list_case_snapshots(
    case_id: str,
    limit: int = Query(50, ge=1, le=200),
    current_user: RequestUser = Depends(get_current_request_user),
):
    owner_id = canonical_user_id(current_user)
    snapshots = await list_governed_case_snapshots_async(
        case_number=case_id, user_id=owner_id, limit=limit
    )
    return [
        GovernedSnapshotRevisionListItemResponse(
            revision=s.revision,
            created_at=s.created_at,
            basis_hash=s.basis_hash,
        )
        for s in snapshots
    ]

@router.get("/cases/{case_id}/snapshots/{revision}", response_model=GovernedSnapshotResponse)
async def get_case_snapshot_by_revision(
    case_id: str,
    revision: int = Path(..., ge=0),
    current_user: RequestUser = Depends(get_current_request_user),
):
    owner_id = canonical_user_id(current_user)
    snapshot = await get_governed_case_snapshot_by_revision_async(
        case_number=case_id, user_id=owner_id, revision=revision
    )
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot revision {revision} not found for case '{case_id}'",
        )

    return GovernedSnapshotResponse(
        case_number=snapshot.case_number,
        revision=snapshot.revision,
        state_json=snapshot.state_json,
        basis_hash=snapshot.basis_hash,
        created_at=snapshot.created_at,
    )

@router.get("/workspace/{case_id}", response_model=CaseWorkspaceProjection)
async def get_workspace_projection(
    case_id: str,
    revision: Optional[int] = Query(None, ge=0),
    current_user: RequestUser = Depends(get_current_request_user),
):
    if revision is not None:
        governed = await _load_governed_state_snapshot_projection_source(
            current_user=current_user,
            case_id=case_id,
            revision=revision,
        )
    else:
        governed = await _load_guarded_workspace_projection_source(
            current_user=current_user,
            case_id=case_id,
        )
    if not governed:
        if revision is not None:
            raise HTTPException(status_code=404, detail=f"Snapshot revision {revision} missing")
        governed = await _load_live_governed_state(
            current_user=current_user,
            session_id=case_id,
            create_if_missing=True,
        )

    return project_case_workspace_from_governed_state(governed, chat_id=case_id)

@router.get("/workspace/{case_id}/rfq-document", response_class=HTMLResponse)
async def get_workspace_rfq_document(
    case_id: str,
    current_user: RequestUser = Depends(get_current_request_user),
):
    governed = await _load_preferred_governed_workspace_source(
        current_user=current_user,
        case_id=case_id,
    )
    workspace = project_case_workspace_from_governed_state(governed, chat_id=case_id)
    return render_rfq_html(workspace)
