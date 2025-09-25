from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from app.services.langgraph.graph.consult.io import invoke_consult
from app.services.langgraph.redis_lifespan import get_redis_checkpointer

router = APIRouter(prefix="/test", tags=["test"])  # wird unter /api/v1 gemountet

class ConsultInvokeIn(BaseModel):
    text: str = Field(..., description="Nutzereingabe")
    chat_id: str = Field(..., description="Thread/Chat ID")

class ConsultInvokeOut(BaseModel):
    text: str

@router.post("/consult/invoke", response_model=ConsultInvokeOut)
async def consult_invoke_endpoint(payload: ConsultInvokeIn, request: Request):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text empty")

    chat_id = f"api:{payload.chat_id.strip() or 'test'}"
    try:
        saver = None
        try:
            saver = get_redis_checkpointer(request.app)
        except Exception:
            saver = None
        out = invoke_consult(text, thread_id=chat_id, checkpointer=saver)
        return {"text": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"invoke_failed: {e}")
