from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="normen-agent", version="0.1.0")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(default=5, ge=1, le=50)
    tenant: Optional[str] = None


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/search")
async def search(_payload: SearchRequest) -> List[Dict[str, Any]]:
    # Minimal stub: external fallback is optional; return empty results.
    return []

