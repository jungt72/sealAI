from __future__ import annotations

import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.v1.api import api_router
from app.services.langgraph.graph.consult.build import build_consult_graph

# Bevorzugte LLM-Factory (nutzt das zentrale LLM für WS/SSE)
try:
    from app.services.langgraph.llm_factory import get_llm as _make_llm  # hat meist streaming=True
except Exception:  # Fallback nur, falls Modul nicht vorhanden
    _make_llm = None  # type: ignore

# Zweite Option: LLM-Factory aus der Consult-Config
try:
    from app.services.langgraph.graph.consult.config import create_llm as _create_llm_cfg
except Exception:
    _create_llm_cfg = None  # type: ignore

# RAG-Orchestrator für Warmup
try:
    from app.services.rag import rag_orchestrator as ro  # enthält prewarm(), hybrid_retrieve, …
except Exception:
    ro = None  # type: ignore

# ---- Access-Log-Filter: /health stummschalten ----
class _HealthSilencer(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return "/health" not in msg

logging.getLogger("uvicorn.access").addFilter(_HealthSilencer())
# ---------------------------------------------------

log = logging.getLogger("uvicorn.error")


def _init_llm():
    """
    Initialisiert ein Chat LLM für Streaming-Endpoints.
    Robust gegen unterschiedliche Factory-Signaturen/Module.
    """
    # 1) Primär: zentrale LLM-Factory
    if _make_llm:
        try:
            return _make_llm(streaming=True)  # neue Signatur
        except TypeError:
            # ältere Signatur ohne streaming-Param
            return _make_llm()

    # 2) Fallback: Consult-Config Factory
    if _create_llm_cfg:
        try:
            return _create_llm_cfg(streaming=True)
        except TypeError:
            return _create_llm_cfg()

    return None


def create_app() -> FastAPI:
    app = FastAPI(title="SealAI Backend", version=os.getenv("APP_VERSION", "dev"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health für LB/Compose
    @app.get("/health")
    async def _health() -> PlainTextResponse:
        return PlainTextResponse("ok")

    # API v1
    app.include_router(api_router, prefix="/api/v1")

    @app.on_event("startup")
    async def _startup():
        # 1) LLM für Streaming-Endpoints initialisieren
        try:
            app.state.llm = _init_llm()
            if app.state.llm is None:
                raise RuntimeError("No LLM factory available")
            log.info("LLM initialized for streaming endpoints.")
        except Exception as e:
            app.state.llm = None
            log.warning("LLM init failed: %s", e)

        # 2) RAG Warmup (Embedding, Reranker, Redis, Qdrant) – verhindert langen ersten Request
        try:
            if ro and hasattr(ro, "prewarm"):
                ro.prewarm()
                log.info("RAG prewarm completed.")
            else:
                log.info("RAG prewarm skipped (no ro.prewarm available).")
        except Exception as e:
            log.warning("RAG prewarm failed: %s", e)

        # 3) Sync-Fallback-Graph (ohne Checkpointer) vorbereiten
        try:
            app.state.graph_sync = build_consult_graph().compile()
            log.info("Consult graph compiled for sync fallback.")
        except Exception as e:
            app.state.graph_sync = None
            log.warning("Graph compile failed: %s", e)

        log.info("Startup: no prebuilt async graph (lazy build in chat_ws).")

    return app


app = create_app()
