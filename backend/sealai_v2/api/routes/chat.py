"""POST /api/v2/chat — a thin projection over ``pipeline.run``. Tenant + session come ONLY from the
verified token (``current_identity``), never from the request body/headers (P0)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from sealai_v2.api.deps import current_identity, get_pipeline, get_settings
from sealai_v2.api.serializers import chat_response
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Flags, SessionContext, VerifiedIdentity
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
    settings: Settings = Depends(get_settings),
) -> dict:
    # Production flag baseline from settings (tunable, not hardcoded). Eval columns stay
    # harness-constructed; the pipeline `or Flags()` fallback (flags_off) is untouched.
    result = await pipeline.run(
        req.message,
        tenant=TenantContext(identity.tenant_id),
        session=SessionContext(session_id=identity.session_id),
        flags=Flags(
            compliance_hint=settings.default_compliance_hint,
            safety_critical=settings.default_safety_critical,
        ),
    )
    return chat_response(result)
