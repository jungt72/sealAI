# backend/app/api/v1/endpoints/consult_invoke.py
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/test", tags=["test"])  # wird unter /api/v1 gemountet

class ConsultInvokeIn(BaseModel):
    text: str = Field(..., description="Nutzereingabe")
    chat_id: str = Field(..., description="Thread/Chat ID")

class ConsultInvokeOut(BaseModel):
    text: str

@router.post("/consult/invoke", response_model=ConsultInvokeOut)
async def consult_invoke_endpoint(payload: ConsultInvokeIn):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="text empty")

    chat_id = f"api:{payload.chat_id.strip() or 'test'}"
    result = {
        "message": "LangGraph wurde entfernt. Dieser Test-Endpunkt liefert nur Platzhalterdaten.",
        "input": text,
        "chat_id": chat_id,
    }
    return {"text": json.dumps(result)}
