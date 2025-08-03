# 📁 backend/app/services/chat/chat_chain.py

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from langchain_openai import ChatOpenAI
from langchain.callbacks.streaming_aiter import AsyncIteratorCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage
from app.core.config import settings
from app.services.memory.memory_core import get_memory_for_thread
from app.services.rag.rag_orchestrator import get_retriever  # <--- NEU

@asynccontextmanager
async def get_stream_handler():
    handler = AsyncIteratorCallbackHandler()
    try:
        yield handler
    finally:
        await handler.aiter_done()

async def _prepare_inputs(username: str, chat_id: str, user_text: str) -> dict:
    """
    Holt den bisherigen Verlauf (History) für Chat und User,
    holt RAG-Kontext und gibt alle Prompt-Felder für den LLM-Prompt zurück.
    """
    session_id = f"{username}:{chat_id}"
    memory = get_memory_for_thread(session_id)
    try:
        history_msgs = memory.messages
    except Exception:
        history_msgs = []

    # Verlauf in Markdown/Chat-Format serialisieren
    chat_history_str = ""
    for m in history_msgs:
        if isinstance(m, HumanMessage):
            chat_history_str += f"**Nutzer:** {m.content}\n"
        elif isinstance(m, AIMessage):
            chat_history_str += f"**KI:** {m.content}\n"
        else:
            chat_history_str += f"{m.content}\n"

    # --- RAG: Wissenskontext aus Qdrant holen ---
    context = ""
    try:
        retriever = get_retriever()
        docs = await retriever.ainvoke(user_text)
        if isinstance(docs, list) and docs:
            # Max. die Top 3 Passagen als Markdown-Block ins Prompt übernehmen
            context = "\n\n".join(
                [f"---\n{(d.page_content if hasattr(d, 'page_content') else str(d)).strip()}\n---"
                 for d in docs[:3]]
            )
    except Exception as exc:
        context = f"[RAG-Fehler: {exc}]"

    return {
        "summary": "",
        "computed": "",
        "context": context.strip(),
        "chat_history": chat_history_str.strip(),
        "input": user_text
    }

async def run_chat_ws(
    username: str, chat_id: str, message: str
) -> AsyncGenerator[dict, None]:
    """
    Legacy-Funktion für dedizierte Streaming-Tests (nicht in Endpoint aktiv).
    """
    async with get_stream_handler() as handler:
        llm = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            streaming=True
        )
        task = asyncio.create_task(
            llm.ainvoke(
                message,
                config={"callbacks": [handler]}
            )
        )
        async for token in handler.aiter():
            if token:
                yield {
                    "choices": [
                        {
                            "delta": {"content": token},
                            "index": 0,
                        }
                    ]
                }
        await task
    yield {"choices": [{"delta": {}, "index": 0, "finish_reason": "stop"}]}

# --- Dummy-Stubs für Legacy-Kompatibilität ---
async def run_chat(*args, **kwargs):
    return "run_chat ist im Debug-Modus deaktiviert."

async def run_chat_streaming(*args, **kwargs):
    yield "run_chat_streaming ist im Debug-Modus deaktiviert."
