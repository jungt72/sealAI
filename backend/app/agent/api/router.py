import logging
from fastapi import APIRouter

from app.agent.api.routes import chat, workspace, history, review, system
from app.agent.api.dispatch import _resolve_runtime_dispatch, RuntimeDispatchResolution
from app.agent.api.streaming import event_generator, _stream_governed_graph, _stream_light_runtime
from app.agent.api.loaders import (
    _load_live_governed_state,
    _persist_live_governed_state,
    _update_governed_state_post_graph,
    require_structured_residual_state,
    _load_governed_state_snapshot_projection_source,
)
from app.agent.api.utils import (
    project_for_ui,
    _materialize_governed_graph_result,
)
from app.agent.api.assembly import (
    _build_governed_reply_context,
    _assemble_governed_stream_payload,
)
from app.agent.api.deps import SESSION_STORE, _runtime_mode_for_pre_gate
from app.agent.api.routes.chat import (
    chat_endpoint,
    _run_light_chat_response,
    _run_governed_chat_response,
    _run_governed_graph_once,
)
from app.agent.api.routes.review import session_override_endpoint
from app.agent.api.routes.system import agent_health
from app.agent.graph.topology import GOVERNED_GRAPH

router = APIRouter()

# Include sub-routers
router.include_router(chat.router)
router.include_router(workspace.router)
router.include_router(history.router)
router.include_router(review.router)
router.include_router(system.router)

_log = logging.getLogger(__name__)

# Re-exports for test compatibility (residual legacy)
__all__ = [
    "router",
    "chat_endpoint",
    "event_generator",
    "SESSION_STORE",
    "_resolve_runtime_dispatch",
    "_stream_governed_graph",
    "_stream_light_runtime",
    "_load_live_governed_state",
    "_persist_live_governed_state",
    "project_for_ui",
    "GOVERNED_GRAPH",
    "_runtime_mode_for_pre_gate",
    "agent_health",
]
