from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def langgraph_health() -> dict:
    return {"status": "ok", "graph": "v2"}


__all__ = ["router"]

