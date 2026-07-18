from __future__ import annotations

import time

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.memory import outbox_daemon


class _Qdrant:
    calls: list[str] = []

    def get_collection(self, name: str):
        self.calls.append(name)
        return {"status": "green"}


def test_worker_healthchecks_heartbeat_database_and_qdrant(tmp_path, monkeypatch):
    heartbeat = tmp_path / "heartbeat"
    now = time.time()
    heartbeat.write_text(str(now - 2), encoding="ascii")
    monkeypatch.setattr(outbox_daemon, "_make_client", lambda _settings: _Qdrant())
    result = outbox_daemon.healthcheck(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'worker.db'}",
            qdrant_url="http://qdrant",
            memory_qdrant_collection="sealai_v2_memory_local_minilm_v1",
            qdrant_collection="sealai_v2_knowledge_local_minilm_v1",
        ),
        heartbeat_path=heartbeat,
        now=now,
    )
    assert result == {"status": "ok", "heartbeat_age_s": "2.0"}
    assert _Qdrant.calls[-2:] == [
        "sealai_v2_memory_local_minilm_v1",
        "sealai_v2_knowledge_local_minilm_v1",
    ]


def test_worker_healthcheck_rejects_stale_heartbeat(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    heartbeat.write_text("1", encoding="ascii")
    with pytest.raises(RuntimeError, match="stale"):
        outbox_daemon.healthcheck(
            Settings(database_url="sqlite://", qdrant_url="http://qdrant"),
            heartbeat_path=heartbeat,
            now=1000,
        )
