# backend/app/main.py
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router

log = logging.getLogger("uvicorn.error")


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


APP_NAME = os.getenv("APP_NAME", "sealAI-backend")
APP_VERSION = os.getenv("APP_VERSION", os.getenv("GIT_SHA", "dev"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://sealai.net")
ENABLE_CORS = _bool_env("ENABLE_CORS", "1")
WARMUP_ON_START = _bool_env("WARMUP_ON_START", "0")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("Starting %s v%s", APP_NAME, APP_VERSION)
    if WARMUP_ON_START:
        log.info("Warmup aktiviert, aber LangGraph wurde entfernt – überspringe Warmup.")
    app.state.warmed_up = True
    yield
    log.info("Stopping %s", APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    if ENABLE_CORS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/")
    async def root():
        return {"ok": True, "name": APP_NAME, "version": APP_VERSION}

    @app.get("/version")
    async def version():
        return {"version": APP_VERSION}

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready():
        return {"ready": bool(getattr(app.state, "warmed_up", False))}

    @app.get("/api/v1/ping")
    async def ping():
        return {"pong": True}

    # v1-API mounten
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
