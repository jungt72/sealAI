"""Legacy chat endpoint removed in favor of LangGraph v2."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.api_route("/chat/stream", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def legacy_langgraph_v1_stream_gone() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy LangGraph v1 endpoint removed; use /api/v1/langgraph/* (v2).",
    )


__all__ = ["router"]
