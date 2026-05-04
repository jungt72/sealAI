import logging
from fastapi import APIRouter, Depends, Query

from app.agent.services.medium_research import MediumResearchService
from app.services.auth.dependencies import RequestUser, get_current_request_user

_log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def agent_health() -> dict:
    return {"status": "ok", "service": "SSoT Agent Authority"}

@router.get("/medium-intelligence")
async def get_medium_intelligence(
    medium: str = Query(...),
    current_user: RequestUser = Depends(get_current_request_user),
):
    service = MediumResearchService()
    result = await service.build(
        medium,
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
    )
    return result.model_dump()
