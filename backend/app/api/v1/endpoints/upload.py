from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.services.context_state_store import merge_context_state

router = APIRouter()

SUPPORTED_EXTENSIONS = {".pdf", ".dxf", ".dwg", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def _infer_parameters_from_filename(filename: str) -> Dict[str, Any]:
    name = filename.lower()
    inferred: Dict[str, Any] = {}
    if "nbr" in name:
        inferred["sealingType"] = "NBR Dichtung"
    if "fkm" in name:
        inferred["sealingType"] = "FKM Hochtemperatur"
    if "hlp" in name:
        inferred["medium"] = "HLP 46"
    if "pressure" in name or "druck" in name:
        inferred["pressure"] = "120 bar"
    if "temp" in name or "180" in name:
        inferred["temperature"] = "180°C"
    return inferred


@router.post("/upload_technical_data")
async def upload_technical_data(
    files: List[UploadFile] = File(..., description="Technische Uploads (PDF, DXF/DWG, Bilder)"),
    user_id: str = Form("api_user"),
):
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Keine Dateien übergeben.")

    uploaded = []
    aggregated_context: Dict[str, Any] = {}

    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext and ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Dateityp {ext} wird nicht unterstützt.",
            )

        content = await file.read()
        uploaded.append(
            {
                "name": file.filename,
                "size": len(content),
                "type": file.content_type,
            }
        )

        inferred = _infer_parameters_from_filename(file.filename or "")
        aggregated_context.update(inferred)

    merged_context = merge_context_state(user_id, aggregated_context)

    return {
        "uploaded": uploaded,
        "context_state": merged_context,
    }
