# backend/app/main.py
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Unser API-Router (REST + WS)
from app.api.v1.api import api_router

# Optionaler Graph-Zugriff fürs Warmup
# (stream_consult ist ein Async-Generator, invoke_consult eine Sync/Async-Funktion)
try:
    from app.langgraph.graph_chat import stream_consult, invoke_consult  # type: ignore
except Exception:  # pragma: no cover
    stream_consult = None  # type: ignore[assignment]
    invoke_consult = None  # type: ignore[assignment]

log = logging.getLogger("uvicorn.error")


def _bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() in ("1", "true", "True", "yes", "on")


APP_NAME = os.getenv("APP_NAME", "sealAI-backend")
APP_VERSION = os.getenv("APP_VERSION", os.getenv("GIT_SHA", "dev"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "https://sealai.net")
ENABLE_CORS = _bool_env("ENABLE_CORS", "1")
WARMUP_ON_START = _bool_env("WARMUP_ON_START", "1")
WARMUP_TIMEOUT_SEC = float(os.getenv("WARMUP_TIMEOUT_SEC", "4.0"))


async def _do_warmup() -> None:
    """
    Fährt den Graphen einmal „kalt“ an, damit erste echte Anfragen weniger Latenz haben.
    Bricht nach WARMUP_TIMEOUT_SEC ab, wenn es klemmt – Start soll nicht blockieren.
    """
    if not (stream_consult or invoke_consult):
        log.info("[warmup] graph_chat nicht importierbar – überspringe Warmup.")
        return

    # Minimaler State – wir nutzen dieselbe Struktur, die dein ai-Endpoint baut.
    state = {
        "chat_id": "warmup",
        "input": "ping",
        "messages": [{"role": "user", "content": "ping"}],
    }

    async def _warmup_async() -> None:
        # Prefer: kurzer Stream-Tick (wenn verfügbar)
        if stream_consult:
            async for _ in stream_consult(state):  # type: ignore[misc]
                break  # uns genügt der erste Tick
            return
        # Fallback: direkte Auswertung
        if invoke_consult:
            try:
                res = invoke_consult(state)  # type: ignore[misc]
                _ = res is not None
            except Exception:
                pass

    try:
        await asyncio.wait_for(_warmup_async(), timeout=WARMUP_TIMEOUT_SEC)
        log.info("[warmup] Graph warm.")
    except asyncio.TimeoutError:
        log.warning("[warmup] Timeout nach %.1fs – fahre trotzdem hoch.", WARMUP_TIMEOUT_SEC)
    except Exception as e:  # pragma: no cover
        log.warning("[warmup] ignorierter Fehler: %r", e)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    log.info("Starting %s v%s", APP_NAME, APP_VERSION)
    if WARMUP_ON_START:
        await _do_warmup()
    app.state.warmed_up = True
    yield
    # Shutdown
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

    # Root/Health
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

    # v1-Router unter /api/v1
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
