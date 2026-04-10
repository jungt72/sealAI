"""
Phase 0F — PATCH 3: Canonical endpoint consistency tests.

Verifies:
1. Expected routes are registered on the agent router (no accidental renames).
2. The agent router is NOT double-mounted under /api/v1 in the main API router
   (canonical path: /api/agent, mounted in main.py).
3. Route methods are correct (POST for chat/stream/review, GET for health).
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Router route presence
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def agent_router():
    from app.agent.api.router import router
    return router


def _route_paths_and_methods(router):
    """Return {path: set_of_methods} for all routes on a FastAPI APIRouter."""
    result = {}
    for route in router.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path is not None:
            result[path] = {m.upper() for m in methods}
    return result


class TestAgentRouterRoutes:
    def test_chat_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/chat" in paths, "POST /chat must be registered on agent router"

    def test_chat_route_is_post(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "POST" in paths.get("/chat", set()), "/chat must accept POST"

    def test_chat_stream_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/chat/stream" in paths, "POST /chat/stream must be registered on agent router"

    def test_chat_stream_route_is_post(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "POST" in paths.get("/chat/stream", set()), "/chat/stream must accept POST"

    def test_health_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/health" in paths, "GET /health must be registered on agent router"

    def test_health_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/health", set()), "/health must accept GET"

    def test_workspace_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/workspace/{case_id}" in paths, "GET /workspace/{case_id} must be registered on agent router"

    def test_workspace_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/workspace/{case_id}", set()), "/workspace/{case_id} must accept GET"

    def test_case_metadata_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/cases/{case_id}" in paths, "GET /cases/{case_id} must be registered on agent router"

    def test_case_metadata_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/cases/{case_id}", set()), "/cases/{case_id} must accept GET"

    def test_case_list_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/cases" in paths, "GET /cases must be registered on agent router"

    def test_case_list_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/cases", set()), "/cases must accept GET"

    def test_case_latest_snapshot_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/cases/{case_id}/snapshots/latest" in paths, "GET /cases/{case_id}/snapshots/latest must be registered on agent router"

    def test_case_latest_snapshot_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/cases/{case_id}/snapshots/latest", set()), "/cases/{case_id}/snapshots/latest must accept GET"

    def test_case_revision_snapshot_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/cases/{case_id}/snapshots/{revision}" in paths, "GET /cases/{case_id}/snapshots/{revision} must be registered on agent router"

    def test_case_revision_snapshot_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/cases/{case_id}/snapshots/{revision}", set()), "/cases/{case_id}/snapshots/{revision} must accept GET"

    def test_case_snapshot_list_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/cases/{case_id}/snapshots" in paths, "GET /cases/{case_id}/snapshots must be registered on agent router"

    def test_case_snapshot_list_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/cases/{case_id}/snapshots", set()), "/cases/{case_id}/snapshots must accept GET"

    def test_workspace_rfq_document_route_registered(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "/workspace/{case_id}/rfq-document" in paths, "GET /workspace/{case_id}/rfq-document must be registered on agent router"

    def test_workspace_rfq_document_route_is_get(self, agent_router):
        paths = _route_paths_and_methods(agent_router)
        assert "GET" in paths.get("/workspace/{case_id}/rfq-document", set()), "/workspace/{case_id}/rfq-document must accept GET"

    def test_no_unexpected_double_slash_routes(self, agent_router):
        """Route paths must not start with // (accidental prefix concatenation)."""
        paths = _route_paths_and_methods(agent_router)
        for path in paths:
            assert not path.startswith("//"), (
                f"Double-slash route detected: {path!r} — possible prefix misconfiguration"
            )


# ---------------------------------------------------------------------------
# No double-mount under /api/v1
# ---------------------------------------------------------------------------

class TestNoDoubleMountUnderV1:
    @pytest.fixture(scope="class")
    def v1_api_source(self):
        # Path relative to this file: ../../api/v1/api.py
        api_path = Path(__file__).parents[2] / "api" / "v1" / "api.py"
        return api_path.read_text(encoding="utf-8")

    def test_agent_router_not_in_v1_api(self, v1_api_source):
        """The agent router must NOT be included in the /api/v1 API router.

        Canonical mount: /api/agent (via main.py include_router).
        A double-mount under /api/v1 would expose the same endpoints at two
        different paths, creating ambiguity and breaking the canonical contract.
        """
        assert "api_router.include_router(agent_router" not in v1_api_source, (
            "Agent router must not be double-mounted under /api/v1. "
            "Canonical path is /api/agent (main.py)."
        )

    def test_v1_has_no_agent_chat_path(self, v1_api_source):
        """There must be no /agent/chat route registered directly in the /api/v1 router."""
        assert 'prefix="/agent"' not in v1_api_source
        assert '"/agent/chat"' not in v1_api_source
