# backend/app/services/chat/chat_chain.py

"""
Chat-Service mit produktiver Prompt-Optimierung und OpenAI-Kostensenkung.
* HTTP-Streaming (Server-Sent Events) über `run_chat_streaming`
* WebSocket-Streaming über  `run_chat_ws`
* Klassischer Sync-Call     über `run_chat`
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, List

from fastapi import HTTPException, Request, WebSocket, status
from langchain_core.runnables import Runnable, RunnableLambda, RunnableWithMessageHistory

from app.core.config import settings
from app.services.auth.token import verify_access_token
from app.services.llm.llm_factory import get_llm
from app.services.memory.memory_core import get_memory_for_thread
from app.services.prompt.prompt_orchestrator import build_dynamic_prompt
from app.services.rag.rag_orchestrator import get_vectorstore

RAG_MIN_SCORE: float = 0.50

def _looks_like_smalltalk(text: str) -> bool:
    greetings = {"hi", "hallo", "hello", "hey", "moin", "servus"}
    words = text.lower().split()
    return len(words) < 3 or any(w in greetings for w in words)

async def _prepare_inputs(username: str, chat_id: str, message: str) -> dict:
    import redis.asyncio as redis
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    summary: str = await redis_client.get(f"summary:{username}:{chat_id}") or ""
    computed: str = await redis_client.get(f"calc:{username}") or ""

    context_chunks: List[str] = []
    debug_scores: list = []

    if not _looks_like_smalltalk(message):
        vectorstore = get_vectorstore()
        results = vectorstore.similarity_search_with_score(
            message, k=getattr(settings, "rag_k", 5)
        )
        for doc, score in results:
            debug_scores.append((float(score), getattr(doc, "page_content", "")[:120]))
            if float(score) >= RAG_MIN_SCORE:
                content = getattr(doc, "page_content", str(doc))
                if content and content not in context_chunks:
                    context_chunks.append(content)

    logging.warning("RAG-DEBUG: %s", debug_scores)

    return {
        "input": message,
        "summary": summary,
        "computed": computed,
        "context": "\n".join(context_chunks),
        "chat_history": "",
    }

def _build_chain(chat_id: str, username: str, streaming: bool = False) -> Runnable:
    llm = get_llm(streaming=streaming)
    chat_prompt = build_dynamic_prompt()

    def _hist(_):
        return get_memory_for_thread(f"{username}:{chat_id}")

    def chain_func(inputs):
        prompt_value = chat_prompt.format_prompt(**inputs)
        # OpenAI-kompatibel: messages-Array!
        return llm.invoke(prompt_value.to_messages())

    chain = RunnableLambda(chain_func)

    return RunnableWithMessageHistory(
        runnable=chain,
        get_session_history=_hist,
        input_messages_key="input",
        history_messages_key="chat_history",
    ).with_config(configurable={"session_id": f"{username}:{chat_id}"})

async def run_chat(input_text: str, chat_id: str, request: Request):
    token = _extract_bearer(request.headers.get("Authorization"))
    payload = await verify_access_token(token)
    username = payload.get("preferred_username", "anonymous")

    prepared = await _prepare_inputs(username, chat_id, input_text)
    chain = _build_chain(chat_id, username, streaming=False)
    return await chain.ainvoke(prepared)

async def run_chat_streaming(
    username: str, chat_id: str, message: str, request: Request
) -> AsyncGenerator[str, None]:
    prepared = await _prepare_inputs(username, chat_id, message)
    chain = _build_chain(chat_id, username, streaming=True)
    async for chunk in chain.astream(prepared):
        yield getattr(chunk, "content", str(chunk))

async def run_chat_ws(username: str, chat_id: str, websocket: WebSocket) -> None:
    await websocket.accept()
    chain = _build_chain(chat_id, username, streaming=True)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                user_msg: str = data.get("input", "").strip()
            except json.JSONDecodeError:
                await websocket.send_json({"error": "invalid json"})
                continue

            if not user_msg:
                await websocket.send_json({"error": "empty input"})
                continue

            prepared = await _prepare_inputs(username, chat_id, user_msg)
            await websocket.send_json({"role": "assistant", "delta": ""})

            async for chunk in chain.astream(prepared):
                delta = getattr(chunk, "content", str(chunk))
                await websocket.send_json({"role": "assistant", "delta": delta})

            await websocket.send_json({"role": "assistant", "finish": True})

    except Exception as exc:
        logging.exception("WebSocket-Fehler: %s", exc)
        await websocket.close(code=1011)

def _extract_bearer(header: str | None) -> str:
    if not header or not header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header fehlt oder ungültig",
        )
    return header.removeprefix("Bearer ").strip()
