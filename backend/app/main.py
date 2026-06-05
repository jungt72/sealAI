# backend/app/main.py
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.v1.api import api_router
from app.api.v1.endpoints.rag import (
    ensure_upload_directory,
    internal_router as rag_internal_router,
)
from app.core.config import settings
from app.observability.health import run_all_health_checks
from app.services.rag.qdrant_bootstrap import bootstrap_rag_collection
from app.services.jobs.worker import start_job_worker

# 🚀 IMPORT DES NEUEN SAUBEREN AGENTEN-ROUTERS
from app.agent.api.router import router as agent_router

log = logging.getLogger("uvicorn.error")
slog = structlog.get_logger("app.main")

CHECKPOINTER_NAMESPACE = "sealai_agent"


# ---------------------------------------------------------------------------
# Prometheus middleware
# ---------------------------------------------------------------------------


class _PrometheusMiddleware(BaseHTTPMiddleware):
    """Record HTTP request counts and latencies for Prometheus."""

    def _normalize_path(self, path: str) -> str:
        """Replace variable path segments to avoid high cardinality."""
        import re

        path = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?=/|$)",
            "/{id}",
            path,
            flags=re.IGNORECASE,
        )
        path = re.sub(r"/[0-9a-f]{32}(?=/|$)", "/{id}", path, flags=re.IGNORECASE)
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
        return path

    async def dispatch(self, request: Request, call_next):
        from app.observability.metrics import (
            HTTP_REQUEST_DURATION_SECONDS,
            HTTP_REQUESTS_TOTAL,
        )

        method = request.method
        path = self._normalize_path(request.url.path)
        start = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            status = str(status_code)

            HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(
                duration
            )
            slog.info(
                "http.request_completed",
                method=method,
                path=path,
                status=status_code,
                duration_ms=round(duration * 1000, 2),
            )


# ---------------------------------------------------------------------------
# Dev: clear LangGraph checkpoints
# ---------------------------------------------------------------------------


async def _clear_langgraph_checkpoints_for_dev_run() -> None:
    if not settings.dev_clear_langgraph_checkpoints_on_startup:
        return
    if not settings.is_dev_or_test:
        log.warning(
            "LangGraph checkpoint clear skipped: app_env=%s is not dev/test.",
            settings.normalized_app_env,
        )
        return
    redis_url = (
        settings.langgraph_v2_redis_url or settings.REDIS_URL or settings.redis_url
    )
    if not redis_url:
        log.warning("LangGraph checkpoint clear skipped: no redis url configured.")
        return
    try:
        from redis.asyncio import Redis
    except Exception as exc:
        log.warning(
            "LangGraph checkpoint clear skipped: redis async client unavailable (%s)",
            exc,
        )
        return

    patterns = [
        f"{CHECKPOINTER_NAMESPACE}*",
        f"checkpoint:{CHECKPOINTER_NAMESPACE}*",
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
            CHECKPOINTER_NAMESPACE,
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
    log.info("Starting %s v%s", settings.app_name, settings.app_version)
    ensure_upload_directory()
    await _clear_langgraph_checkpoints_for_dev_run()
    if settings.qdrant_bootstrap_on_startup:
        bootstrap_status = bootstrap_rag_collection()
        log.info("Qdrant bootstrap status: %s", bootstrap_status)
    else:
        log.info("Qdrant bootstrap skipped: qdrant_bootstrap_on_startup=false")

    if settings.audit_log_bootstrap_on_startup:
        await _bootstrap_audit_log()
    else:
        log.info(
            "Audit log table bootstrap skipped: audit_log_bootstrap_on_startup=false"
        )

    try:
        from app.agent.graph.topology import get_governed_graph

        await get_governed_graph()
        log.info("LangGraph governed graph initialised")
    except Exception as exc:
        log.warning("LangGraph governed graph warmup failed (non-fatal): %s", exc)

    if settings.warmup_on_start:
        # Stage B (Rang 2 / W2): actually prewarm the RAG embedders + sparse +
        # reranker + BM25 (previously this block only logged). Background task so
        # readiness is not blocked by model loading (no deploy-health risk);
        # non-fatal — a cold start degrades gracefully via the lazy loaders.
        async def _prewarm_rag() -> None:
            try:
                from app.services.rag.rag_orchestrator import prewarm

                await asyncio.to_thread(prewarm)
                log.info("RAG prewarm (embeddings/sparse/reranker/bm25) completed")
            except Exception as exc:  # noqa: BLE001
                log.warning("RAG prewarm at startup failed (non-fatal): %s", exc)

        app.state.prewarm_task = asyncio.create_task(_prewarm_rag())
        log.info("RAG prewarm scheduled (warmup_on_start) — non-blocking.")
    worker_task = None
    if settings.job_worker_enabled:
        worker_task = asyncio.create_task(start_job_worker())
    else:
        log.info("Job worker startup skipped: job_worker_enabled=false")
    app.state.warmed_up = True
    yield
    if worker_task:
        worker_task.cancel()
        try:
            await worker_task
        except Exception:
            pass
    try:
        from app.agent.graph.topology import close_governed_graph_resources

        await close_governed_graph_resources()
    except Exception as exc:
        log.warning("LangGraph governed graph shutdown cleanup failed: %s", exc)
    log.info("Stopping %s", settings.app_name)


async def _bootstrap_audit_log() -> None:
    """Create audit_log table and register the global AuditLogger (idempotent)."""
    try:
        import asyncpg
        from app.core.config import settings
        from app.services.audit import AuditLogger
        from app.services.audit.audit_logger import set_global_audit_logger

        dsn = settings.database_url
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif dsn.startswith("postgresql+psycopg://"):
            dsn = dsn.replace("postgresql+psycopg://", "postgresql://", 1)
        elif dsn.startswith("postgres+asyncpg://"):
            dsn = dsn.replace("postgres+asyncpg://", "postgres://", 1)
        elif dsn.startswith("postgres+psycopg://"):
            dsn = dsn.replace("postgres+psycopg://", "postgres://", 1)
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)
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
    from app.observability import metrics as _metrics  # noqa: F401
    from app.observability.langsmith import configure_langsmith_environment

    app_name = getattr(settings, "app_name", "sealAI-backend")
    app_version = getattr(settings, "app_version", os.getenv("GIT_SHA", "dev"))
    fastapi_docs_enabled = bool(getattr(settings, "fastapi_docs_enabled", False))
    enable_cors = bool(getattr(settings, "enable_cors", True))
    frontend_origin = getattr(settings, "frontend_origin", "http://localhost:3000")
    prometheus_enabled = bool(getattr(settings, "prometheus_enabled", True))

    # LangSmith tracing
    if configure_langsmith_environment(
        tracing_enabled=bool(
            getattr(settings, "langsmith_tracing", False)
            or getattr(settings, "langchain_tracing_v2", False)
        ),
        api_key=getattr(settings, "langsmith_api_key", None)
        or getattr(settings, "langchain_api_key", None),
        project=getattr(settings, "langsmith_project", None)
        or getattr(settings, "langchain_project", None),
        endpoint=getattr(settings, "langsmith_endpoint", None)
        or getattr(settings, "langchain_endpoint", None),
    ):
        log.info(
            "LangSmith tracing enabled (project=%s)",
            getattr(settings, "langsmith_project", None)
            or getattr(settings, "langchain_project", None),
        )

    app = FastAPI(
        title=app_name,
        version=app_version,
        docs_url="/docs" if fastapi_docs_enabled else None,
        redoc_url="/redoc" if fastapi_docs_enabled else None,
        openapi_url="/openapi.json" if fastapi_docs_enabled else None,
        lifespan=lifespan,
    )

    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                frontend_origin,
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Prometheus middleware
    if prometheus_enabled:
        app.add_middleware(_PrometheusMiddleware)
        try:
            from prometheus_fastapi_instrumentator import Instrumentator

            instrumentator = Instrumentator(
                should_group_status_codes=False,
                should_ignore_untemplated=True,
                should_respect_env_var=True,
                should_instrument_requests_inprogress=True,
                excluded_handlers=[r"/metrics", r"/health", r"/healthz", r"/readyz"],
                env_var_name="ENABLE_METRICS",
                inprogress_name="sealai_http_requests_inprogress",
                inprogress_labels=True,
            )
            instrumentator.instrument(app).expose(
                app, endpoint="/metrics", include_in_schema=False
            )
        except Exception as exc:
            log.warning("Prometheus instrumentator setup failed (non-fatal): %s", exc)

    @app.get("/")
    async def root():
        return {"ok": True, "name": app_name, "version": app_version}

    @app.get("/version")
    async def version():
        return {"version": app_version}

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/readyz")
    async def ready():
        return {"ready": bool(getattr(app.state, "warmed_up", False))}

    @app.get("/health", include_in_schema=False)
    async def health_check():
        result = await run_all_health_checks()
        status_code = 200 if result.get("status") == "healthy" else 503
        return JSONResponse(status_code=status_code, content=result)

    @app.get("/api/v1/ping")
    async def ping():
        return {"pong": True}

    # Legacy v1-API mounten
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(rag_internal_router)

    # 🚀 Neuen Agent Router mounten
    app.include_router(agent_router, prefix="/api/agent", tags=["Agent"])

    # 🖥️ UI PoC Static Files mounten
    static_dir = os.path.join(os.path.dirname(__file__), "agent", "api", "static")
    if os.path.exists(static_dir):
        app.mount(
            "/poc", StaticFiles(directory=static_dir, html=True), name="static_poc"
        )

    return app


app = create_app()
