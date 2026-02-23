# backend/app/main.py
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.v1.api import api_router
from app.api.v1.endpoints.rag import ensure_upload_directory
from app.langgraph_v2.constants import CHECKPOINTER_NAMESPACE_V2
from app.services.rag.qdrant_bootstrap import bootstrap_rag_collection
from app.services.jobs.worker import start_job_worker

log = logging.getLogger("uvicorn.error")


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


APP_NAME = os.getenv("APP_NAME", "sealAI-backend")
APP_VERSION = os.getenv("APP_VERSION", os.getenv("GIT_SHA", "dev"))
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://sealai.net")
ENABLE_CORS = _bool_env("ENABLE_CORS", "1")
WARMUP_ON_START = _bool_env("WARMUP_ON_START", "0")
JOB_WORKER_ENABLED = _bool_env("JOB_WORKER_ENABLED", "1")
DEV_CLEAR_LANGGRAPH_CHECKPOINTS_ON_STARTUP = _bool_env(
    "DEV_CLEAR_LANGGRAPH_CHECKPOINTS_ON_STARTUP",
    "1" if APP_ENV in {"dev", "development", "local", "test"} else "0",
)


# ---------------------------------------------------------------------------
# Prometheus middleware
# ---------------------------------------------------------------------------


class _PrometheusMiddleware(BaseHTTPMiddleware):
    """Record HTTP request counts and latencies for Prometheus."""

    def _normalize_path(self, path: str) -> str:
        """Replace variable path segments to avoid high cardinality."""
        import re
        # Replace UUIDs and numeric IDs
        path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/{id}", path)
        path = re.sub(r"/\d+", "/{id}", path)
        return path

    async def dispatch(self, request: Request, call_next):
        from app.core.metrics import http_requests_total, http_request_duration_seconds

        method = request.method
        path = self._normalize_path(request.url.path)
        start = time.perf_counter()

        response = await call_next(request)

        duration = time.perf_counter() - start
        status = str(response.status_code)

        http_requests_total.labels(method=method, path=path, status=status).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)

        return response


# ---------------------------------------------------------------------------
# Dev: clear LangGraph checkpoints
# ---------------------------------------------------------------------------


async def _clear_langgraph_checkpoints_for_dev_run() -> None:
    if not DEV_CLEAR_LANGGRAPH_CHECKPOINTS_ON_STARTUP:
        return
    redis_url = os.getenv("LANGGRAPH_V2_REDIS_URL") or os.getenv("REDIS_URL")
    if not redis_url:
        log.warning("LangGraph checkpoint clear skipped: no redis url configured.")
        return
    try:
        from redis.asyncio import Redis
    except Exception as exc:
        log.warning("LangGraph checkpoint clear skipped: redis async client unavailable (%s)", exc)
        return

    patterns = [
        f"{CHECKPOINTER_NAMESPACE_V2}*",
        f"checkpoint:{CHECKPOINTER_NAMESPACE_V2}*",
    ]
    deleted = 0
    client = Redis.from_url(redis_url, decode_responses=False)
    try:
        for pattern in patterns:
            batch = []
            async for key in client.scan_iter(match=pattern, count=500):
                batch.append(key)
                if len(batch) >= 500:
                    deleted += int(await client.delete(*batch))
                    batch = []
            if batch:
                deleted += int(await client.delete(*batch))
        log.warning(
            "LangGraph checkpoint reset finished for dev startup (deleted_keys=%s, namespace=%s).",
            deleted,
            CHECKPOINTER_NAMESPACE_V2,
        )
    except Exception as exc:
        log.warning("LangGraph checkpoint clear failed: %s", exc)
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("Starting %s v%s", APP_NAME, APP_VERSION)
    ensure_upload_directory()
    await _clear_langgraph_checkpoints_for_dev_run()
    bootstrap_status = bootstrap_rag_collection()
    log.info("Qdrant bootstrap status: %s", bootstrap_status)

    # Audit log table bootstrap
    await _bootstrap_audit_log()

    if WARMUP_ON_START:
        log.info("Warmup aktiviert, aber LangGraph wurde entfernt – überspringe Warmup.")
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


async def _bootstrap_audit_log() -> None:
    """Create audit_log table and register the global AuditLogger (idempotent)."""
    try:
        import asyncpg
        from app.core.config import settings
        from app.services.audit import AuditLogger
        from app.services.audit.audit_logger import set_global_audit_logger

        pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=3)
        al = AuditLogger(pool)
        await al.ensure_table()
        set_global_audit_logger(al)
        log.info("Audit log initialised")
    except Exception as exc:
        log.warning("Audit log bootstrap failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    from app.core.config import settings

    # LangSmith tracing — set env vars before any LangChain model is created
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
        log.info("LangSmith tracing enabled (project=%s)", settings.langchain_project)

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

    # Prometheus middleware (after CORS so CORS headers are present on /metrics too)
    if settings.prometheus_enabled:
        app.add_middleware(_PrometheusMiddleware)

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

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        """Prometheus metrics endpoint."""
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # v1-API mounten
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
