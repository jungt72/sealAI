from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from app.main import app


def test_langgraph_rest_endpoint():
    client = TestClient(app)
    payload = {"chat_id": "test", "input": "Ich brauche eine Dichtung fuer 120C.", "params": {}}
    response = client.post("/api/v1/ai/beratung", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "text" in body and body["text"]
