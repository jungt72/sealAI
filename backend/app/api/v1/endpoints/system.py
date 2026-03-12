from __future__ import annotations

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()  # Prefix und Tags werden im übergeordneten Router gesetzt

class _ConsultInvokeIn(BaseModel):
    text: str = Field(..., min_length=1)
    chat_id: Optional[str] = None

@router.post("/test/consult/invoke", tags=["test"])
async def test_consult_invoke(body: _ConsultInvokeIn, request: Request) -> Dict[str, Any]:
    raise HTTPException(
        status_code=410,
        detail="Legacy consult test endpoint disabled. Use /api/agent for active orchestration.",
    )
