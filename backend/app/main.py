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
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.api.v1.api import api_router
from app.services.rag.utils import ensure_upload_directory

# 🚀 IMPORT DES NEUEN SAUBEREN AGENTEN-ROUTERS
from app.agent.api.router import router as agent_router

log = logging.getLogger("uvicorn.error")
slog = structlog.get_logger("app.main")


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

CHECKPOINTER_NAMESPACE = "sealai_agent"


def _extract_missing_settings(exc: Exception) -> list[str]:
    if not isinstance(exc, ValidationError):
        return []
    missing: list[str] = []
    for error in exc.errors():
        if error.get("type") != "missing":
            continue
        loc = error.get("loc") or ()
        field = ".".join(str(part) for part in loc if part is not None).strip(".")
        if field:
            missing.append(field)
    return sorted(set(missing))


def _resolve_config_readiness():
    from app.core.config import get_settings

    try:
        settings = get_settings()
        return settings, {
            "status": "ready",
            "config_ready": True,
            "reason": None,
            "missing_settings": [],
        }
    except Exception as exc:
        missing_settings = _extract_missing_settings(exc)
        log.warning("Settings unavailable during app bootstrap: %s", exc)
        return None, {
            "status": "not_ready",
            "config_ready": False,
            "reason": "required_settings_missing" if missing_settings else type(exc).__name__,
            "missing_settings": missing_settings,
        }


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
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration)
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
    from app.services.jobs.worker import start_job_worker
    from app.services.rag.qdrant_bootstrap import bootstrap_rag_collection

    log.info("Starting %s v%s", APP_NAME, APP_VERSION)
    ensure_upload_directory()
    await _clear_langgraph_checkpoints_for_dev_run()
    bootstrap_status = bootstrap_rag_collection()
    log.info("Qdrant bootstrap status: %s", bootstrap_status)

    # Audit log table bootstrap
    await _bootstrap_audit_log()

    if WARMUP_ON_START:
        log.info("Warmup aktiviert.")
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

        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
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
    settings, config_readiness = _resolve_config_readiness()
    metrics_available = False
    try:
        if settings is not None:
            from app.observability import metrics as _metrics  # noqa: F401
            metrics_available = True
    except Exception as exc:
        log.warning("Prometheus metrics import unavailable during app bootstrap: %s", exc)

    # LangSmith tracing
    if settings is not None and settings.langchain_tracing_v2 and settings.langchain_api_key:
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
    app.state.config_readiness = config_readiness

    if ENABLE_CORS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Prometheus middleware
    if settings is not None and settings.prometheus_enabled and metrics_available:
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
            instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
        except Exception as exc:
            log.warning("Prometheus instrumentator setup failed (non-fatal): %s", exc)

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
        config_status = dict(getattr(app.state, "config_readiness", {}))
        ready_now = bool(getattr(app.state, "warmed_up", False)) and bool(config_status.get("config_ready", False))
        return JSONResponse(
            status_code=200 if ready_now else 503,
            content={"ready": ready_now, "config": config_status},
        )

    @app.get("/health", include_in_schema=False)
    async def health_check():
        config_status = dict(getattr(app.state, "config_readiness", {}))
        if not bool(config_status.get("config_ready", False)):
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "checks": {"config": config_status}},
            )

        from app.observability.health import run_all_health_checks

        result = await run_all_health_checks()
        checks = dict(result.get("checks") or {})
        checks["config"] = config_status
        result["checks"] = checks
        status_code = 200 if result.get("status") == "healthy" else 503
        return JSONResponse(status_code=status_code, content=result)

    @app.get("/api/v1/ping")
    async def ping():
        return {"pong": True}

    # Legacy v1-API mounten
    app.include_router(api_router, prefix="/api/v1")
    
    # 🚀 Neuen Agent Router mounten
    app.include_router(agent_router, prefix="/api/agent", tags=["Agent"])
    
    # 🖥️ UI PoC Static Files mounten
    static_dir = os.path.join(os.path.dirname(__file__), "agent", "api", "static")
    if os.path.exists(static_dir):
        app.mount("/poc", StaticFiles(directory=static_dir, html=True), name="static_poc")

    return app

app = create_app()
