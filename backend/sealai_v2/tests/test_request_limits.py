from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from sealai_v2.api.main import app
from sealai_v2.security.request_limits import RequestBoundaryMiddleware


def test_sensitive_case_and_token_query_parameters_are_rejected():
    client = TestClient(app)
    for query in (
        "case_id=case-1",
        "case=case-1",
        "token=secret",
        "access_token=secret",
    ):
        response = client.get(f"/api/v2/health?{query}")
        assert response.status_code == 400
        assert "query strings" in response.json()["detail"]


def test_ordinary_non_sensitive_query_parameters_remain_compatible():
    response = TestClient(app).get("/api/v2/health?view=compact")
    assert response.status_code == 200


def test_declared_and_streamed_oversize_bodies_are_413():
    client = TestClient(app)
    oversized = b"x" * 131_073
    declared = client.post(
        "/api/v2/chat",
        content=oversized,
        headers={"Content-Type": "application/json"},
    )
    assert declared.status_code == 413

    # A normal bounded body reaches schema validation rather than the limiter.
    bounded = client.post(
        "/api/v2/chat",
        json={"message": "x" * 8001},
        headers={"Authorization": "Bearer invalid"},
    )
    assert bounded.status_code in {401, 422, 503}


def test_replay_channel_delegates_to_disconnect_after_buffered_body():
    received: list[str] = []
    incoming = iter(
        [
            {"type": "http.request", "body": b"{}", "more_body": False},
            {"type": "http.disconnect"},
        ]
    )

    async def receive():
        return next(incoming)

    async def send(_message):
        return None

    async def downstream(_scope, replay_receive, _send):
        received.append((await replay_receive())["type"])
        received.append((await replay_receive())["type"])

    middleware = RequestBoundaryMiddleware(downstream, max_body_bytes=128)
    asyncio.run(
        middleware({"type": "http", "query_string": b"", "headers": []}, receive, send)
    )

    assert received == ["http.request", "http.disconnect"]
