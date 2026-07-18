"""Public, non-aspirational product maturity metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from sealai_v2.api.deps import get_settings
from sealai_v2.config.product_maturity import runtime_product_maturity
from sealai_v2.config.settings import Settings

router = APIRouter(prefix="/api/v2/meta", tags=["meta"])


@router.get("/maturity")
async def maturity(settings: Settings = Depends(get_settings)) -> dict:
    return runtime_product_maturity(settings)
