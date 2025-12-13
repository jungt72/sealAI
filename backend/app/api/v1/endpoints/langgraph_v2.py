from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from langgraph._internal._constants import CONFIG_KEY_CHECKPOINTER

from app.langgraph_v2.sealai_graph_v2 import build_v2_config, get_sealai_graph_v2
from app.langgraph_v2.state import SealAIState
from app.langgraph_v2.utils.confirm_checkpoint import build_confirm_checkpoint_payload
from app.langgraph_v2.utils.confirm_go import ConfirmGoRequest
from app.services.auth.dependencies import get_current_request_user

router = APIRouter()


class LangGraphV2Request(BaseModel):
    input: str = Field(default="", description="User prompt")
    chat_id: str = Field(default="default", description="Conversation/thread id")
    user_id: str = Field(default="anonymous", description="User id (for checkpointer identity)")


def _format_sse(event: str, payload: Dict[str, Any]) -> bytes:
    return (f"event: {event}\n" + f"data: {json.dumps(payload, ensure_ascii=False)}\n\n").encode(
        "utf-8"
    )


def _chunk_text(text: str, *, max_len: int = 700) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_len, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


async def _build_graph_config(*, thread_id: str, user_id: str) -> tuple[Any, Dict[str, Any]]:
    graph = await get_sealai_graph_v2()
    config = build_v2_config(thread_id=thread_id, user_id=user_id)
    configurable = config.setdefault("configurable", {})
    configurable[CONFIG_KEY_CHECKPOINTER] = graph.checkpointer
    return graph, config


async def _run_graph_to_state(req: LangGraphV2Request, *, user_id: str) -> SealAIState:
    graph, config = await _build_graph_config(thread_id=req.chat_id, user_id=user_id)
    initial_state = SealAIState(
        user_id=user_id,
        thread_id=req.chat_id,
        messages=[HumanMessage(content=req.input)],
    )
    result = await graph.ainvoke(initial_state, config=config)
    if isinstance(result, SealAIState):
        return result
    if isinstance(result, dict):
        return SealAIState(**result)
    raise TypeError(f"Unexpected graph result type: {type(result).__name__}")


def _should_emit_confirm_checkpoint(state: SealAIState) -> bool:
    if (state.phase or "") == "confirm":
        return True
    if (state.last_node or "") == "confirm_recommendation_node":
        return True
    return False


async def _event_stream_v2(req: LangGraphV2Request) -> AsyncIterator[bytes]:
    try:
        # NOTE: user_id for checkpointer identity must match the auth identity used by state updates.
        user_id = req.user_id
        result_state = await _run_graph_to_state(req, user_id=user_id)

        if _should_emit_confirm_checkpoint(result_state):
            yield _format_sse("confirm_checkpoint", build_confirm_checkpoint_payload(result_state))

        final_text = (result_state.final_text or "").strip()
        if final_text:
            for chunk in _chunk_text(final_text):
                yield _format_sse("token", {"type": "token", "text": chunk})

        yield _format_sse("done", {"type": "done"})
    except asyncio.CancelledError:
        yield _format_sse("done", {"type": "done"})
        return
    except Exception as exc:  # pragma: no cover
        yield _format_sse("error", {"type": "error", "message": str(exc)})
        yield _format_sse("done", {"type": "done"})


@router.post("/chat/v2")
async def langgraph_chat_v2_endpoint(
    request: LangGraphV2Request,
    username: str = Depends(get_current_request_user),
) -> StreamingResponse:
    # Override user_id with authenticated identity to keep checkpointer stable.
    request.user_id = username
    return StreamingResponse(_event_stream_v2(request), media_type="text/event-stream")


@router.post("/confirm/go")
async def confirm_go(
    body: ConfirmGoRequest,
    username: str = Depends(get_current_request_user),
) -> Dict[str, Any]:
    try:
        graph, config = await _build_graph_config(thread_id=body.chat_id, user_id=username)
        await graph.aupdate_state(
            config,
            {"recommendation_go": bool(body.go)},
            as_node="confirm_recommendation_node",
        )
        return {"ok": True, "chat_id": body.chat_id, "recommendation_go": bool(body.go)}
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc


__all__ = ["LangGraphV2Request"]
