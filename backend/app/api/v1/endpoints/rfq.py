from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

@router.get("/download")
def rfq_download(path: str = Query(..., description="Server-Pfad zur PDF")):
    raise HTTPException(
        status_code=410,
        detail="RFQ download is temporarily disabled until an allowlisted document flow is available.",
    )
