# backend/main.py
from __future__ import annotations

import logging
import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router   # enthält bereits prefix="/api/v1"

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="SealAI",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 👉 Doppelte /api/v1 vermeiden: prefix hier weglassen
app.include_router(api_router)          # ← KEIN prefix mehr

@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}

if __name__ == "__main__":              # pragma: no cover
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
