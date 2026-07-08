"""GET /api/v2/legal/doctrine + POST /api/v2/legal/acceptance (Legal-by-Design Phase A+B).

``/doctrine`` is PUBLIC (mirrors ``api/routes/framing.py``'s documented exception to the fail-closed
/api/v2 default — the SPA's Legal-Gate screen must render the current versions pre-acceptance,
i.e. before any token-gated call is meaningful). ``/acceptance`` requires a verified identity (the
tenant boundary the record is keyed on) but is deliberately NOT behind ``require_legal_acceptance``
itself — that would make accepting the gate impossible.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from sealai_v2.api.deps import current_identity, get_legal_acceptance_store, get_settings
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.legal_doctrine import doctrine_payload, is_business_email
from sealai_v2.db.legal_acceptance import LegalAcceptance, LegalAcceptanceStore
from sealai_v2.security.ip_hash import hash_ip

router = APIRouter(prefix="/api/v2/legal", tags=["legal"])

# Deliberately simple (RFC-5322-complete validation needs the email-validator dependency this repo
# doesn't otherwise carry — "keine unnötigen Dependencies"). Good enough to reject obvious garbage;
# the freemail-domain check below is the actual business rule this endpoint cares about.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.get("/doctrine")
async def doctrine() -> JSONResponse:
    # Short public TTL, same rationale as /api/v2/framing: a reviewed text bump propagates quickly.
    return JSONResponse(
        content=doctrine_payload(), headers={"Cache-Control": "public, max-age=300"}
    )


class LegalAcceptanceRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    business_email: str = Field(min_length=3, max_length=255)
    role: str = Field(min_length=1, max_length=128)

    @field_validator("business_email")
    @classmethod
    def _valid_email_format(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v
    vat_id: str = Field(default="", max_length=64)
    legal_basis_accepted: bool
    dpa_accepted: bool
    business_user_confirmed: bool
    # The client echoes back the doctrine versions it displayed (from GET /doctrine) so the server
    # can refuse a stale acceptance (e.g. a tab left open across a reviewed text bump) instead of
    # silently recording agreement to text the user never actually saw.
    terms_version: str = Field(min_length=1, max_length=32)
    privacy_version: str = Field(min_length=1, max_length=32)
    dpa_version: str = Field(min_length=1, max_length=32)


def _client_ip(request: Request) -> str:
    # Single nginx ingress (this deployment's only proxy hop) — the first X-Forwarded-For entry is
    # the real client; falls back to the direct peer when unset (e.g. tests, no proxy).
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post("/acceptance")
async def accept(
    req: LegalAcceptanceRequest,
    request: Request,
    identity: VerifiedIdentity = Depends(current_identity),
    store: LegalAcceptanceStore = Depends(get_legal_acceptance_store),
    settings: Settings = Depends(get_settings),
    user_agent: str = Header(default=""),
) -> dict:
    if not req.legal_basis_accepted or not req.dpa_accepted or not req.business_user_confirmed:
        raise HTTPException(
            status_code=422, detail="alle drei Bestätigungen sind für die Produktivnutzung erforderlich"
        )
    if not is_business_email(req.business_email):
        raise HTTPException(
            status_code=422,
            detail="bitte eine geschäftliche E-Mail-Adresse angeben (keine privaten Freemail-Anbieter)",
        )
    current = doctrine_payload()
    if (
        req.terms_version != current["terms_version"]
        or req.privacy_version != current["privacy_version"]
        or req.dpa_version != current["dpa_version"]
    ):
        raise HTTPException(
            status_code=409,
            detail="die akzeptierten Dokumentversionen sind veraltet — bitte die aktuellen Seiten erneut prüfen",
        )

    store.upsert(
        LegalAcceptance(
            tenant_id=identity.tenant_id,
            company_name=req.company_name.strip(),
            business_email=req.business_email,
            role=req.role.strip(),
            vat_id=req.vat_id.strip(),
            legal_basis_accepted=True,
            dpa_accepted=True,
            business_user_confirmed=True,
            accepted_terms_version=req.terms_version,
            accepted_privacy_version=req.privacy_version,
            accepted_dpa_version=req.dpa_version,
            accepted_at=datetime.now(timezone.utc).isoformat(),
            accepted_ip_hash=hash_ip(_client_ip(request), pepper=settings.legal_ip_hash_pepper),
            accepted_user_agent=user_agent[:512],
        )
    )
    return {"status": "accepted", **current}


@router.get("/acceptance-status")
async def acceptance_status(
    identity: VerifiedIdentity = Depends(current_identity),
    store: LegalAcceptanceStore = Depends(get_legal_acceptance_store),
) -> dict:
    """Lets the SPA check gate status on load without re-submitting the form every time."""
    a = store.get(identity.tenant_id)
    current = doctrine_payload()
    up_to_date = a is not None and (
        a.accepted_terms_version == current["terms_version"]
        and a.accepted_privacy_version == current["privacy_version"]
        and a.accepted_dpa_version == current["dpa_version"]
    )
    return {"accepted": up_to_date}
