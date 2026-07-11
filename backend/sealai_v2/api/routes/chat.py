"""POST /api/v2/chat (+ /chat/stream, P4a) — thin projections over ``pipeline.run``. Tenant comes
ONLY from the verified token (``current_identity``), never from the request body/headers (P0).
Both endpoints share ``_run_pipeline`` — same body, same auth, same flags; only the response
transport differs. The stream's doctrine: stage frames carry keys only, the answer is ONE complete
gated payload after verify + cite (see ``api/sse.py``).

"Fälle"-Sidebar (Patch B): ``ChatRequest.case_id`` is an OPTIONAL override of the effective
session — ``req.case_id or identity.session_id``. Omitted, this is byte-identical to before (the
whole point of Patch A/B's design: the token-derived session stays the default everywhere). Present,
it lets the client target one of its own several persisted cases instead of always "the current
login's conversation" — still exclusively tenant-scoped by the verified token, never by the client
(P0 unchanged; see ``api/routes/conversations.py``'s module docstring for the identical reasoning)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sealai_v2.api.deps import (
    flags_from_settings,
    get_pipeline,
    get_settings,
    require_legal_acceptance,
)
from sealai_v2.api.serializers import chat_response
from sealai_v2.api.sse import STREAM_SCHEMA_VERSION, stream_frames
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import SessionContext, VerifiedIdentity
from sealai_v2.pipeline.pipeline import (
    Pipeline,
    ProductModeUnavailable,
    ProgressSink,
    TokenSink,
)
from sealai_v2.security.tenant import TenantContext

router = APIRouter(prefix="/api/v2", tags=["chat"])

_log = logging.getLogger("sealai_v2.api.chat")

# Fixed in-stream failure text — NEVER the exception detail (no prompt/PII leak; mirrors the
# opaque 500 of the non-streaming endpoint).
_STREAM_ERROR_MESSAGE = (
    "Die Anfrage konnte nicht verarbeitet werden — bitte erneut versuchen."
)
_MODE_UNAVAILABLE_MESSAGE = (
    "Dieser Produktmodus befindet sich noch in der fachlichen Freigabe und ist "
    "derzeit nicht aktiviert."
)


def _mode_unavailable_detail(exc: ProductModeUnavailable) -> dict:
    return {
        "code": "product_mode_unavailable",
        "mode": exc.mode,
        "maturity": exc.maturity,
        "message": _MODE_UNAVAILABLE_MESSAGE,
    }


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    # max_length matches V2Session.session_id's own column width (db/models.py) — an over-long
    # value now fails closed with a clean 422 instead of a generic 500 from the DB constraint.
    case_id: str | None = Field(default=None, max_length=255)


async def _run_pipeline(
    req: ChatRequest,
    identity: VerifiedIdentity,
    pipeline: Pipeline,
    settings: Settings,
    progress: ProgressSink | None = None,
    token_sink: TokenSink | None = None,
):
    # Production flag baseline from settings (tunable, not hardcoded). Eval columns stay
    # harness-constructed; the pipeline `or Flags()` fallback (flags_off) is untouched.
    return await pipeline.run(
        req.message,
        tenant=TenantContext(identity.tenant_id),
        session=SessionContext(session_id=req.case_id or identity.session_id),
        flags=flags_from_settings(settings),
        progress=progress,
        token_sink=token_sink,
    )


@router.post("/chat")
async def chat(
    req: ChatRequest,
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    pipeline: Pipeline = Depends(get_pipeline),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        result = await _run_pipeline(req, identity, pipeline, settings)
    except ProductModeUnavailable as exc:
        raise HTTPException(
            status_code=503, detail=_mode_unavailable_detail(exc)
        ) from exc
    return chat_response(result)


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    identity: VerifiedIdentity = Depends(require_legal_acceptance),
    pipeline: Pipeline = Depends(get_pipeline),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue()

    def progress(stage: str, status: str) -> None:
        queue.put_nowait(("stage", {"stage": stage, "status": status}))

    # Phase 3A + Phase 3B: the token sink is constructed ONLY here, in the SSE path (where the queue
    # exists). It carries ONLY {"text": <raw delta>, "draft": <bool>} -- no ids/tenant/case/PII ever
    # crosses it. ``draft=False`` (Phase 3A) means the delta IS the final, authoritative answer being
    # typed (smalltalk_navigation only -- structurally the route requires zero deterministic
    # signals). ``draft=True`` (Phase 3B) means the delta is a NON-AUTHORITATIVE preview of the full
    # L1 generator's output for every other route -- the actual delivered answer still arrives only
    # via the atomic "result" frame after the full output_guard + L3 pipeline. The plain /chat handler
    # passes NO sink, so it stays byte-identical either way.
    def token(delta: str, draft: bool) -> None:
        queue.put_nowait(("token", {"text": delta, "draft": draft}))

    async def _run() -> None:
        try:
            result = await _run_pipeline(
                req, identity, pipeline, settings, progress=progress, token_sink=token
            )
            queue.put_nowait(("result", chat_response(result)))
        except ProductModeUnavailable as exc:
            queue.put_nowait(("error", _mode_unavailable_detail(exc)))
        except Exception:  # noqa: BLE001 — surfaced as ONE fixed-message error frame
            _log.exception("chat/stream pipeline failed")
            queue.put_nowait(("error", {"message": _STREAM_ERROR_MESSAGE}))

    task = asyncio.create_task(_run())
    return StreamingResponse(
        stream_frames(queue, task),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",  # nginx: per-response unbuffered (no config edit)
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-SealingAI-Stream-Version": STREAM_SCHEMA_VERSION,
        },
    )
