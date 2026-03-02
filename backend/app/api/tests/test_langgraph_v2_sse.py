from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure backend is on path
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Minimal env defaults for settings to load
os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ.setdefault("database_url", "postgresql+asyncpg://test:test@localhost:5432/testdb")
os.environ.setdefault("POSTGRES_SYNC_URL", "postgresql://test:test@localhost:5432/testdb")
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("qdrant_collection", "test")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from app.api.v1.endpoints import langgraph_v2 as endpoint  # noqa: E402


def test_format_sse_frame_is_valid():
    frame = endpoint._format_sse("token", {"type": "token", "text": "Hallo"}, event_id="msg-1:1")
    decoded = frame.decode("utf-8")
    assert decoded.startswith("id: msg-1:1\n")
    assert "\nevent: token\n" in decoded
    assert "\ndata: " in decoded
    assert decoded.endswith("\n\n")

    id_line = [line for line in decoded.splitlines() if line.startswith("id:")][0]
    assert id_line == "id: msg-1:1"

    payload_line = [line for line in decoded.splitlines() if line.startswith("data:")][0]
    payload = json.loads(payload_line.split(":", 1)[1].strip())
    assert payload["type"] == "token"
    assert payload["text"] == "Hallo"


def test_format_sse_multiline_payload_stays_single_data_line():
    frame = endpoint._format_sse(
        "token",
        {"type": "token", "text": "Line 1\nLine 2\nLine 3"},
        event_id="msg-1:2",
    )
    decoded = frame.decode("utf-8")
    data_lines = [line for line in decoded.splitlines() if line.startswith("data:")]
    assert len(data_lines) == 1
    payload = json.loads(data_lines[0].split(":", 1)[1].strip())
    assert payload["type"] == "token"
    assert payload["text"] == "Line 1\nLine 2\nLine 3"
