import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Endpoints
from app.api.v1.endpoints.ai import router as ai_router
from app.api.v1.endpoints.chat_ws import router as ws_router
from app.api.v1.endpoints.langgraph_sse import router as sse_router

# LangGraph (Consult)
from app.services.langgraph.graph.consult.build import build_consult_graph

# Redis Checkpointer
from app.services.langgraph.redis_lifespan import get_redis_checkpointer

log = logging.getLogger("app.main")


def create_app() -> FastAPI:
    app = FastAPI(title="SealAI Backend", version="0.1.0")

    # CORS (eng fassen, wenn Domains bekannt sind)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/debug/routes")
    async def debug_routes():
        return JSONResponse([{"path": r.path, "name": r.name} for r in app.router.routes])

    # Routen: konsistent /api/v1
    app.include_router(ai_router,  prefix="/api/v1/ai")
    app.include_router(ws_router,  prefix="/api/v1")                  # /api/v1/ai/ws …
    app.include_router(sse_router, prefix="/api/v1/langgraph")        # /api/v1/langgraph/…

    @app.on_event("startup")
    async def on_startup():
        log.info("Startup: building consult graph…")

        # Redis Checkpointer holen
        saver = None
        try:
            saver = get_redis_checkpointer(app)
        except Exception as e:
            log.warning("Redis checkpointer unavailable, falling back to in-memory: %r", e)

        # Graph einmal bauen & konsistent kompilieren
        g = build_consult_graph()
        try:
            compiled = g.compile(checkpointer=saver) if saver else g.compile()
        except Exception as e:
            log.warning("Compile with checkpointer failed (%r). Falling back to no-cp.", e)
            compiled = g.compile()

        # Bereitstellen
        app.state.graph_sync = compiled
        app.state.graph_async = compiled
        app.state.checkpoint_ns = os.getenv("LANGGRAPH_CHECKPOINT_NS", "chat.supervisor.v1")
        app.state.swarm_checkpointer = saver

        log.info("Graph ready; routes registered.")

    return app


app = create_app()
