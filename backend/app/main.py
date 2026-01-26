# backend/app/main.py
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.services.jobs.worker import start_job_worker
from app.services.rag.qdrant_bootstrap import bootstrap_rag_collection

log = logging.getLogger("uvicorn.error")


def _resolve_log_level(value: str | None) -> int:
    raw = (value or "INFO").strip()
    if not raw:
        return logging.INFO
    name = raw.upper()
    if name in logging._nameToLevel:
        return logging._nameToLevel[name]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return logging.INFO


def _configure_logging() -> None:
    level = _resolve_log_level(os.getenv("LOG_LEVEL"))
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
    else:
        logging.basicConfig(level=level)


_configure_logging()


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


APP_NAME = os.getenv("APP_NAME", "sealAI-backend")
APP_VERSION = os.getenv("APP_VERSION", os.getenv("GIT_SHA", "dev"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://sealai.net")
ENABLE_CORS = _bool_env("ENABLE_CORS", "1")
WARMUP_ON_START = _bool_env("WARMUP_ON_START", "0")
JOB_WORKER_ENABLED = _bool_env("JOB_WORKER_ENABLED", "1")
ENABLE_RAG_BOOTSTRAP = _bool_env("ENABLE_RAG_BOOTSTRAP", "0")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("Starting %s v%s", APP_NAME, APP_VERSION)
    if WARMUP_ON_START:
        log.info("Warmup aktiviert, aber LangGraph wurde entfernt – überspringe Warmup.")
    if ENABLE_RAG_BOOTSTRAP:
        log.info("RAG bootstrap enabled: ensuring Qdrant collection + payload indexes.")
        bootstrap_rag_collection()
    worker_task = None
    if JOB_WORKER_ENABLED:
        worker_task = asyncio.create_task(start_job_worker())
    app.state.warmed_up = True
    yield
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except Exception:
            pass
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
