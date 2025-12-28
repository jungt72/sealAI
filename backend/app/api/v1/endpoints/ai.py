from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

router = APIRouter()


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def legacy_langgraph_v1_gone(path: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Legacy LangGraph v1 endpoint removed; use /api/v1/langgraph/* (v2).",
    )
