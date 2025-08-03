from fastapi import APIRouter, Query
from app.services.memory.memory_core import get_memory_for_thread

router = APIRouter()

@router.get("/memory")
async def get_memory(user_id: str = Query(...), chat_id: str = Query(default="default")):
    session_id = f"{user_id}:{chat_id}"
    memory = get_memory_for_thread(session_id)
    # Beispiel: die letzten 20 Nachrichten zurückgeben
    return {"messages": memory.messages[-20:]}
