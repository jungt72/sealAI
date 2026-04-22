import logging
from fastapi import APIRouter, Query

from app.agent.services.medium_context import resolve_medium_context

_log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/health")
async def agent_health() -> dict:
    return {"status": "ok", "service": "SSoT Agent Authority"}

@router.get("/medium-intelligence")
async def get_medium_intelligence(
    medium: str = Query(...),
):
    context = await resolve_medium_context(medium)
    return {
        "canonical_name": context.canonical_name,
        "is_hazardous": context.is_hazardous,
        "is_food_grade": context.is_food_grade,
        "is_gas": context.is_gas,
        "context_notes": list(context.context_notes),
    }
