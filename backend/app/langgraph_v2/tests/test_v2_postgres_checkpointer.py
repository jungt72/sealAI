from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.langgraph_v2.utils import checkpointer as cp


@dataclass
class _FakeResult:
    rows: list[dict]

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)


class _FakeConnection:
    def __init__(self) -> None:
        self.checkpoints: dict[tuple[str, str, str], dict] = {}
        self.writes: dict[tuple[str, str, str, str, int], dict] = {}

    async def execute(self, statement, params=None):
        params = dict(params or {})
        sql = " ".join(str(statement).strip().split()).lower()

        if sql.startswith("create table if not exists"):
            return _FakeResult([])

        if sql.startswith("delete from langgraph_v2_checkpoints"):
            key = (params["thread_id"], params["checkpoint_ns"], params["checkpoint_id"])
            self.checkpoints.pop(key, None)
            return _FakeResult([])

        if sql.startswith("insert into langgraph_v2_checkpoints"):
            key = (params["thread_id"], params["checkpoint_ns"], params["checkpoint_id"])
            self.checkpoints[key] = dict(params)
            return _FakeResult([])

        if sql.startswith("delete from langgraph_v2_checkpoint_writes"):
            key = (
                params["thread_id"],
                params["checkpoint_ns"],
                params["checkpoint_id"],
                params["task_id"],
                params["idx"],
            )
            self.writes.pop(key, None)
            return _FakeResult([])

        if sql.startswith("insert into langgraph_v2_checkpoint_writes"):
            key = (
                params["thread_id"],
                params["checkpoint_ns"],
                params["checkpoint_id"],
                params["task_id"],
                params["idx"],
            )
            self.writes[key] = dict(params)
            return _FakeResult([])

        if "from langgraph_v2_checkpoints" in sql and "order by created_at desc" in sql:
            thread_id = params["thread_id"]
            checkpoint_ns = params["checkpoint_ns"]
            rows = [
                row
                for (tid, ns, _cid), row in self.checkpoints.items()
                if tid == thread_id and ns == checkpoint_ns
            ]
            rows.sort(key=lambda row: (row.get("created_at"), row.get("checkpoint_id")), reverse=True)
            return _FakeResult(rows[:1])

        if "from langgraph_v2_checkpoints" in sql and "checkpoint_id=:checkpoint_id" in sql:
            key = (params["thread_id"], params["checkpoint_ns"], params["checkpoint_id"])
            row = self.checkpoints.get(key)
            return _FakeResult([row] if row else [])

        if "from langgraph_v2_checkpoint_writes" in sql:
            thread_id = params["thread_id"]
            checkpoint_ns = params["checkpoint_ns"]
            checkpoint_id = params["checkpoint_id"]
            rows = [
                row
                for (tid, ns, cid, _task_id, _idx), row in self.writes.items()
                if tid == thread_id and ns == checkpoint_ns and cid == checkpoint_id
            ]
            rows.sort(key=lambda row: (row["task_id"], row["idx"]))
            return _FakeResult(rows)

        raise AssertionError(f"Unhandled SQL in fake connection: {sql}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self) -> None:
        self.conn = _FakeConnection()

    def begin(self):
        return self.conn

    def connect(self):
        return self.conn


@pytest.mark.anyio
async def test_postgres_saver_roundtrip_checkpoint_and_reload() -> None:
    saver = cp.AsyncSqlAlchemyPostgresSaver(
        conn_string="postgresql+asyncpg://unused",
        engine=_FakeEngine(),
    )
    await saver.asetup()
    config = {
        "configurable": {
            "thread_id": "tenant-1:user-1:chat-1",
            "checkpoint_ns": "sealai:v2:",
        },
        "metadata": {"tenant_id": "tenant-1"},
    }
    checkpoint = {
        "id": "chk-1",
        "v": 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "channel_values": {"final_text": "ok"},
        "channel_versions": {"final_text": 1},
        "versions_seen": {},
        "pending_sends": [],
        "updated_channels": ["final_text"],
    }
    new_config = await saver.aput(config, checkpoint, {"phase": "confirm"}, {"final_text": 1})
    await saver.aput_writes(new_config, [("messages", {"kind": "reject"})], task_id="task-1")

    loaded = await saver.aget_tuple(new_config)

    assert loaded is not None
    assert loaded.config["configurable"]["checkpoint_id"] == "chk-1"
    assert loaded.checkpoint["id"] == "chk-1"
    assert loaded.checkpoint["channel_values"]["final_text"] == "ok"
    assert loaded.metadata["phase"] == "confirm"
    assert loaded.metadata["tenant_id"] == "tenant-1"
    assert loaded.pending_writes is not None
    assert loaded.pending_writes[0][0] == "task-1"
    assert loaded.pending_writes[0][1] == "messages"
    assert loaded.pending_writes[0][2]["kind"] == "reject"


@pytest.mark.anyio
async def test_postgres_backend_fails_fast_when_unavailable_without_memory_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGGRAPH_V2_CHECKPOINTER_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x:y@127.0.0.1:1/test")
    monkeypatch.delenv("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", raising=False)

    with pytest.raises(RuntimeError, match="memory fallback is disabled"):
        await cp.make_v2_checkpointer_async()
