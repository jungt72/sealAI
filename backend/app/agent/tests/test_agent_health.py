"""
Tests for Phase 0C.5 — Agent health endpoint.

Verifies:
1. GET /health returns 200 with {"status": "ok", "service": "sealai-agent"}
2. Response is deterministic (no LLM / DB calls required)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.agent.api.router import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestAgentHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"

    def test_health_returns_service_name(self, client):
        data = client.get("/health").json()
        assert data["service"] == "sealai-agent"

    def test_health_is_deterministic(self, client):
        """Two consecutive calls must return identical payloads."""
        r1 = client.get("/health").json()
        r2 = client.get("/health").json()
        assert r1 == r2
