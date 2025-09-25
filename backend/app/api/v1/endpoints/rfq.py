from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter()

@router.get("/download")
def rfq_download(path: str = Query(..., description="Server-Pfad zur PDF")):
    if not os.path.isfile(path):
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(path, filename=os.path.basename(path), media_type="application/pdf")
