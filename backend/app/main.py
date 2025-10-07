# backend/app/main.py
from __future__ import annotations

import logging
import os
from fastapi import FastAPI
from langchain_core.messages import HumanMessage

# Router (Fallback, falls api_router fehlt)
try:
    from app.api.v1.api import api_router  # type: ignore
except Exception:
    from fastapi import APIRouter
    from app.api.v1.endpoints import chat_ws  # type: ignore
    api_router = APIRouter()
    api_router.include_router(chat_ws.router)

from app.api.routes.chat import router as chat_router
from app.services.langgraph.llm_factory import get_llm as make_llm
from app.services.langgraph.redis_lifespan import get_redis_checkpointer
from app.services.langgraph.tools import long_term_memory as ltm

# Graph-Builder
from app.services.langgraph.graph.supervisor_graph import build_supervisor_graph as _build_supervisor_graph
from app.services.langgraph.graph.consult.build import build_consult_graph as _build_consult_graph
try:
    from app.services.langgraph.graph.mvp_graph import build_mvp_graph as _build_mvp_graph
except Exception:
    _build_mvp_graph = None  # type: ignore

log = logging.getLogger("uvicorn.error")


def _compile_graph(app: FastAPI, name: str) -> None:
    desired = (name or "supervisor").strip().lower()
    if desired == getattr(app.state, "graph_name", None) and (
        getattr(app.state, "graph_async", None) is not None
        or getattr(app.state, "graph_sync", None) is not None
    ):
        return

    if desired == "supervisor":
        builder = _build_supervisor_graph
    elif desired == "mvp" and _build_mvp_graph is not None:
        builder = _build_mvp_graph
    else:
        builder = _build_consult_graph
    graph = builder()

    saver = None
    try:
        saver = get_redis_checkpointer(app)
    except RuntimeError as exc:
        log.error("[startup] Redis checkpointer required but unavailable: %s", exc)
        raise
    except Exception as exc:
        log.warning("[startup] Redis checkpointer optional fallback: %s", exc)
        saver = None

    try:
        compiled = graph.compile(checkpointer=saver) if saver else graph.compile()
    except Exception:
        compiled = graph.compile()

    app.state.graph_async = compiled
    app.state.graph_sync = compiled
    app.state.graph_name = desired
    log.info("[startup] graph compiled: %s", desired)


def _warmup_llm(app: FastAPI) -> None:
    # persistent streaming client
    if not getattr(app.state, "llm", None):
        app.state.llm = make_llm(streaming=True)
        log.info("[startup] LLM client initialised (streaming=True)")

    # optional one-shot ping (TLS/DNS warm)
    # CHANGE: Default jetzt "1" -> Warmup standardmäßig aktiv
    if os.getenv("WARMUP_PING_LLM", "1") == "1":
        try:
            non_stream = make_llm(streaming=False)
            non_stream.invoke([HumanMessage(content="ok")])
            log.info("[startup] LLM ping completed")
        except Exception as exc:
            log.warning("[startup] LLM ping failed: %r", exc)


def _warmup_ltm() -> None:
    try:
        ltm.prewarm_ltm()
        log.info("[startup] LTM prewarm completed")
    except Exception as exc:
        log.warning("[startup] LTM prewarm failed: %r", exc)


def create_app() -> FastAPI:
    app = FastAPI(title="SealAI Backend")
    app.include_router(chat_router)
    app.include_router(api_router, prefix="/api/v1")

    @app.on_event("startup")
    async def on_startup() -> None:
        _warmup_llm(app)
        desired = (os.getenv("GRAPH_BUILDER", "supervisor") or "supervisor").strip().lower()
        _compile_graph(app, desired)
        _warmup_ltm()
        log.info("[startup] warmup done (graph=%s)", desired)

    return app


app = create_app()
