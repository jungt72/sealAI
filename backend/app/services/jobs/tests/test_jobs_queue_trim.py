import asyncio
from unittest.mock import AsyncMock

from app.services.jobs import queue as queue_module


def test_enqueue_job_trims_queue(monkeypatch) -> None:
    class DummyClient:
        def __init__(self) -> None:
            self.rpush = AsyncMock()
            self.ltrim = AsyncMock()

    client = DummyClient()
    monkeypatch.setattr(queue_module, "_queue_client", lambda: client)

    asyncio.run(queue_module.enqueue_job("jobs:chat_transcripts", {"hello": "world"}))

    client.rpush.assert_awaited_once()
    client.ltrim.assert_awaited_once_with(
        "jobs:chat_transcripts",
        -queue_module.MAX_JOBS_QUEUE_LEN,
        -1,
    )
