# --- Test: Consult-Sync-Invoke ---------------------------------------------
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import Request
import json

from app.services.langgraph.graph.consult.io import invoke_consult
from app.services.langgraph.redis_lifespan import get_redis_checkpointer

class _ConsultInvokeIn(BaseModel):
    text: str = Field(..., min_length=1)
    chat_id: Optional[str] = None

@router.post("/test/consult/invoke", tags=["test"])
async def test_consult_invoke(body: _ConsultInvokeIn, request: Request) -> Dict[str, Any]:
    thread_id = f"api:{body.chat_id or 'test'}"
    try:
        saver = get_redis_checkpointer(request.app)
    except Exception:
        saver = None

    out = invoke_consult(body.text, thread_id=thread_id, checkpointer=saver)

    try:
        parsed = json.loads(out)
        payload = {"json": parsed} if isinstance(parsed, (dict, list)) else {"text": out}
    except Exception:
        payload = {"text": out}

    return {"final": payload}
