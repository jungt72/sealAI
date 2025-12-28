# backend/app/api/v1/endpoints/consult_invoke.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/test", tags=["test"])


@router.api_route("/consult/invoke", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def legacy_langgraph_v1_consult_gone() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy LangGraph v1 endpoint removed; use /api/v1/langgraph/* (v2).",
    )
