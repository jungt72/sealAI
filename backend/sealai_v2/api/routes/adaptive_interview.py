"""Admin-only aggregate review surface for adaptive-interview shadow telemetry."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from sealai_v2.api.deps import (
    get_interview_shadow_store,
    get_settings,
    require_admin,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.interview.shadow_reporting import summarize_shadow_records
from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack

router = APIRouter(
    prefix="/api/v2/admin/adaptive-interview",
    tags=["adaptive-interview-shadow"],
)


def _utc_iso(value: datetime | None, *, field: str) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=400, detail=f"{field} must include a timezone")
    return value.astimezone(timezone.utc).isoformat()


@router.get("/shadow-summary")
def shadow_summary(
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=10_000, ge=1, le=50_000),
    identity: VerifiedIdentity = Depends(require_admin),
    store=Depends(get_interview_shadow_store),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.adaptive_interview_shadow_reporting_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "product_mode_unavailable",
                "mode": "adaptive_interview_shadow_reporting",
                "maturity": "implemented_default_off",
            },
        )
    since_iso = _utc_iso(since, field="since")
    until_iso = _utc_iso(until, field="until")
    if since_iso is not None and until_iso is not None and since_iso >= until_iso:
        raise HTTPException(status_code=400, detail="since must be earlier than until")

    pack = load_rwdr_v1_pack()
    page = store.list_shadow_records(
        tenant_id=identity.tenant_id,
        pack_id=pack.pack_id,
        pack_version=pack.version,
        policy_version=pack.policy_version,
        since=since_iso,
        until=until_iso,
        limit=limit,
    )
    summary = summarize_shadow_records(
        page,
        pack_id=pack.pack_id,
        pack_version=pack.version,
        policy_version=pack.policy_version,
        since=since_iso,
        until=until_iso,
        question_to_need={
            question.question_id: question.primary_need_id
            for question in pack.questions
        },
    )
    return {
        "summary": summary.to_dict(),
        "individual_records_exposed": False,
        "human_adjudication_required": True,
    }
