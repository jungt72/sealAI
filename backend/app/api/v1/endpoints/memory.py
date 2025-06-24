# backend/app/api/v1/endpoints/memory.py

from fastapi import APIRouter
from app.services.memory.memory_core import get_memory_for_thread

router = APIRouter()

@router.get("/memory/{session_id}")
async def get_memory(session_id: str):
    memory = get_memory_for_thread(session_id)
    # Zeige die letzten 20 Nachrichten (Short-Term). Passe an, falls mehr/weniger erwünscht:
    return {"messages": memory.messages[-20:]}
