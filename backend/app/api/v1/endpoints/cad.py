from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.schemas.cad import SealRenderRequest, SealRenderResponse
from app.services.freecad_runner import run_freecad_script

router = APIRouter()


@router.post("/cad/render-seal", response_model=SealRenderResponse, tags=["cad"])
async def render_seal(payload: SealRenderRequest) -> SealRenderResponse:
    result = await run_freecad_script(payload.script_path, payload.params)
    return SealRenderResponse(**result)
