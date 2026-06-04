from __future__ import annotations

from fastapi import APIRouter

from app.agent.api.router import agent_health

router = APIRouter(tags=["health"])


@router.get("/health")
async def langgraph_health() -> dict:
    payload = await agent_health()
    return {
        **payload,
        "compatibility_alias": True,
        "canonical_path": "/api/agent/health",
    }


__all__ = ["router"]
