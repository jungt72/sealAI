# backend/app/main.py
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.observability.metrics import observe_http_request, render_metrics
from app.services.jobs.worker import start_job_worker
from app.services.langgraph_ttl_enforcer import start_ttl_enforcer

log = logging.getLogger("uvicorn.error")
request_log = logging.getLogger("app.request")


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


APP_NAME = os.getenv("APP_NAME", "sealAI-backend")
APP_VERSION = os.getenv("APP_VERSION", os.getenv("GIT_SHA", "dev"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://sealai.net")
ENABLE_CORS = _bool_env("ENABLE_CORS", "1")
WARMUP_ON_START = _bool_env("WARMUP_ON_START", "0")
JOB_WORKER_ENABLED = _bool_env("JOB_WORKER_ENABLED", "1")


async def _cancel_and_await(task: asyncio.Task | None, name: str) -> None:
    """
    Cancel a background task and await it.
    CancelledError is normal on shutdown/restart and must NOT bubble up.
    """
    if task is None:
        return

    if task.done():
        # Drain exception if any
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            log.warning("Background task %s failed before shutdown: %s", name, exc)
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return
    except Exception as exc:
        log.warning("Background task %s raised during shutdown: %s", name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info("Starting %s v%s", APP_NAME, APP_VERSION)
    if WARMUP_ON_START:
        log.info("Warmup aktiviert, aber LangGraph wurde entfernt – überspringe Warmup.")

    worker_task: asyncio.Task[None] | None = None
    ttl_task: asyncio.Task[None] | None = None
    ttl_stop: asyncio.Event | None = None

    if JOB_WORKER_ENABLED:
        worker_task = asyncio.create_task(start_job_worker())
        try:
            worker_task.set_name("job_worker")  # py3.11
        except Exception:
            pass

    # Phase 1: TTL-Enforcer gegen LangGraph Redis leak (checkpoint_write ohne TTL)
    ttl_task, ttl_stop = start_ttl_enforcer()
    if ttl_task is not None:
        try:
            ttl_task.set_name("lg_ttl_enforcer")  # py3.11
        except Exception:
            pass

    app.state.warmed_up = True
    yield

    # Stop background tasks (order: signal -> cancel/await)
    if ttl_stop is not None:
        ttl_stop.set()

    await _cancel_and_await(ttl_task, "lg_ttl_enforcer")
    await _cancel_and_await(worker_task, "job_worker")

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

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("X-Request-Id") or request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            request_log.exception(
                "http_request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise
        duration_ms = int((time.perf_counter() - start) * 1000)
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or request.url.path
        observe_http_request(
            method=request.method,
            route=route_path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        request_log.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": route_path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers.setdefault("X-Request-Id", request_id)
        return response

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

    @app.get("/metrics")
    async def metrics():
        return Response(render_metrics(), media_type="text/plain; version=0.0.4")

    @app.get("/api/v1/ping")
    async def ping():
        return {"pong": True}

    # v1-API mounten
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
