"""M6c — /api/v2/briefing: the M4b deterministic render projected over a token-scoped pipeline run."""

from __future__ import annotations

from sealai_v2.tests._apiutil import auth, make_client


def test_briefing_renders_artifact():
    client, _ = make_client(pipeline=None)
    r = client.post(
        "/api/v2/briefing",
        json={"message": "FKM bei 150°C in Öl?"},
        headers=auth("tok-A"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "briefing" and isinstance(body["body"], str) and body["body"]


def test_briefing_requires_auth():
    client, _ = make_client()
    assert client.post("/api/v2/briefing", json={"message": "x"}).status_code == 401
