from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status
from app.langgraph.compile import run_langgraph_stream
from pydantic import BaseModel, Field

router = APIRouter()  # Prefix und Tags werden im übergeordneten Router gesetzt


class _ConsultInvokeIn(BaseModel):
    text: str = Field(..., min_length=1)
    chat_id: Optional[str] = None


@router.post("/test/consult/invoke", tags=["test"])
async def test_consult_invoke(request: Request, _body: _ConsultInvokeIn) -> Dict[str, Any]:
    request.state.langgraph_payload = _body.model_dump()
    result = await run_langgraph_stream(request)
    return result
