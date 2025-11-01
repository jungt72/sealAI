from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()  # Prefix und Tags werden im übergeordneten Router gesetzt


class _ConsultInvokeIn(BaseModel):
    text: str = Field(..., min_length=1)
    chat_id: Optional[str] = None


@router.post("/test/consult/invoke", tags=["test"])
async def test_consult_invoke(_body: _ConsultInvokeIn) -> Dict[str, Any]:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="LangGraph temporarily unavailable. Use WS /chat/stream.",
    )
