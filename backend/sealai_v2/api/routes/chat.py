"""POST /api/v2/chat — a thin projection over ``pipeline.run``. Tenant + session come ONLY from the
verified token (``current_identity``), never from the request body/headers (P0)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sealai_v2.api.deps import current_identity, get_pipeline
from sealai_v2.api.serializers import chat_response
from sealai_v2.core.contracts import SessionContext, VerifiedIdentity
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.security.tenant import TenantContext

router = APIRouter(prefix="/api/v2", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@router.post("/chat")
async def chat(
    req: ChatRequest,
    identity: VerifiedIdentity = Depends(current_identity),
    pipeline: Pipeline = Depends(get_pipeline),
) -> dict:
    result = await pipeline.run(
        req.message,
        tenant=TenantContext(identity.tenant_id),
        session=SessionContext(session_id=identity.session_id),
    )
    return chat_response(result)
