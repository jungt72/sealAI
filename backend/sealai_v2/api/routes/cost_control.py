"""System-operator-only aggregate quota/budget posture (no raw subject/tenant identifiers)."""

from fastapi import APIRouter, Depends, HTTPException

from sealai_v2.api.deps import (
    get_cost_control_store,
    get_settings,
    require_system_operator,
)
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity

router = APIRouter(prefix="/api/v2/admin", tags=["admin", "provider-cost-control"])


@router.get("/provider-costs")
def provider_costs(
    _: VerifiedIdentity = Depends(require_system_operator),
    settings: Settings = Depends(get_settings),
    store=Depends(get_cost_control_store),
) -> dict:
    try:
        usage = store.summary()
    except Exception:
        raise HTTPException(
            status_code=503, detail="provider cost control unavailable"
        ) from None
    return {
        "provider_requests_enabled": settings.provider_requests_enabled,
        "hard_limits": {
            "daily_budget_micros": settings.provider_daily_budget_micros,
            "monthly_budget_micros": settings.provider_monthly_budget_micros,
            "reservation_per_request_micros": settings.provider_request_reservation_micros,
            "subject_requests_per_minute": settings.provider_subject_requests_per_minute,
            "tenant_requests_per_minute": settings.provider_tenant_requests_per_minute,
            "subject_requests_per_day": settings.provider_subject_requests_per_day,
            "tenant_requests_per_day": settings.provider_tenant_requests_per_day,
            "tenant_requests_per_month": settings.provider_tenant_requests_per_month,
            "subject_max_concurrent": settings.provider_subject_max_concurrent,
            "tenant_max_concurrent": settings.provider_tenant_max_concurrent,
        },
        "usage": usage,
    }
