from __future__ import annotations

import time
from threading import Event

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.memory import outbox_daemon


class _Qdrant:
    calls: list[str] = []

    def get_collection(self, name: str):
        self.calls.append(name)
        return {"status": "green"}


class _DisposableBind:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class _ScopedSession:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, statement) -> None:
        self.calls.append(str(statement))


class _ScopedFactory:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.bind = _DisposableBind()
        self.kw = {"bind": self.bind}

    def __call__(self) -> _ScopedSession:
        return _ScopedSession(self.calls)


def test_worker_healthchecks_heartbeat_database_and_qdrant(tmp_path, monkeypatch):
    heartbeat = tmp_path / "heartbeat"
    now = time.time()
    heartbeat.write_text(str(now - 2), encoding="ascii")
    monkeypatch.setattr(outbox_daemon, "_make_client", lambda _settings: _Qdrant())
    result = outbox_daemon.healthcheck(
        Settings(
            worker_database_url=f"sqlite:///{tmp_path / 'worker.db'}",
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
            Settings(worker_database_url="sqlite://", qdrant_url="http://qdrant"),
            heartbeat_path=heartbeat,
            now=1000,
        )


def test_worker_healthcheck_exercises_rls_role_adapter(tmp_path, monkeypatch):
    heartbeat = tmp_path / "heartbeat"
    heartbeat.write_text("100", encoding="ascii")
    factory = _ScopedFactory()
    monkeypatch.setattr(
        outbox_daemon, "make_worker_sessionmaker", lambda _settings: factory
    )
    monkeypatch.setattr(outbox_daemon, "_make_client", lambda _settings: _Qdrant())

    result = outbox_daemon.healthcheck(
        Settings(
            worker_database_url="postgresql+psycopg2://worker@localhost/test",
            database_rls_scope_enabled=True,
            qdrant_url="http://qdrant",
        ),
        heartbeat_path=heartbeat,
        now=101,
    )

    assert result == {"status": "ok", "heartbeat_age_s": "1.0"}
    assert factory.calls == ["SELECT 1"]
    assert factory.bind.disposed is True


def test_empty_daemon_keeps_paid_gate_and_embedder_lazy(tmp_path, monkeypatch):
    factories: list[str] = []
    monkeypatch.setattr(
        outbox_daemon,
        "_make_client",
        lambda _settings: factories.append("qdrant") or _Qdrant(),
    )
    monkeypatch.setattr(
        outbox_daemon,
        "_make_memory_embedder",
        lambda _settings: factories.append("embedder"),
    )

    monkeypatch.setattr(outbox_daemon, "_write_heartbeat", lambda: None)
    stop = Event()
    stop.set()
    outbox_daemon.run(
        Settings(
            worker_database_url=f"sqlite:///{tmp_path / 'worker.db'}",
            qdrant_url="http://qdrant",
            embed_provider="openai",
        ),
        stop=stop,
    )

    assert factories == ["qdrant"]
