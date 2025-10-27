from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()  # Prefix und Tags werden im übergeordneten Router gesetzt


class _ConsultInvokeIn(BaseModel):
    text: str = Field(..., min_length=1)
    chat_id: Optional[str] = None


@router.post("/test/consult/invoke", tags=["test"])
async def test_consult_invoke(body: _ConsultInvokeIn) -> Dict[str, Any]:
    return {
        "final": {
            "message": (
                "LangGraph wurde entfernt. "
                "Test-Endpunkt liefert derzeit nur Platzhalterdaten."
            ),
            "input": body.text,
            "chat_id": body.chat_id,
        }
    }
