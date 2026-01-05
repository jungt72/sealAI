from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections import deque
from typing import Any, Deque, Dict, Iterable, Optional, Tuple

try:
    from redis.asyncio import Redis
except Exception:  # pragma: no cover - optional dependency
    Redis = None

logger = logging.getLogger(__name__)

BroadcastKey = Tuple[str, str]
BroadcastEvent = Tuple[int, str, Dict[str, Any]]
BroadcastRecord = Dict[str, Any]


class ReplayBackend:
    async def next_seq(self, *, user_id: str, chat_id: str) -> int:
        raise NotImplementedError

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> int:
        raise NotImplementedError

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int
    ) -> tuple[list[BroadcastRecord], bool]:
        raise NotImplementedError

    @property
    def name(self) -> str:
        raise NotImplementedError


class MemoryReplayBackend(ReplayBackend):
    def __init__(self, *, max_buffer: int = 500) -> None:
        self._buffers: Dict[BroadcastKey, Deque[BroadcastRecord]] = {}
        self._seq: Dict[BroadcastKey, int] = {}
        self._lock = asyncio.Lock()
        self._max_buffer = max_buffer

    @property
    def name(self) -> str:
        return "memory"

    async def next_seq(self, *, user_id: str, chat_id: str) -> int:
        key = (user_id, chat_id)
        async with self._lock:
            current = self._seq.get(key, 0) + 1
            self._seq[key] = current
        return current

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> int:
        seq_value = await self.next_seq(user_id=user_id, chat_id=chat_id)
        record = {
            "seq": seq_value,
            "event": event,
            "data": data,
            "ts": float(timestamp if timestamp is not None else time.time()),
        }
        key = (user_id, chat_id)
        async with self._lock:
            buffer = self._buffers.get(key)
            if buffer is None:
                buffer = deque(maxlen=self._max_buffer)
                self._buffers[key] = buffer
            buffer.append(record)
        return seq_value

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int
    ) -> tuple[list[BroadcastRecord], bool]:
        key = (user_id, chat_id)
        async with self._lock:
            buffer = list(self._buffers.get(key, deque()))
        if not buffer:
            return [], True
        oldest_seq = buffer[0].get("seq", 0)
        if last_seq < oldest_seq:
            return [], True
        return [item for item in buffer if item.get("seq", 0) > last_seq], False


class RedisReplayBackend(ReplayBackend):
    def __init__(
        self,
        *,
        redis_url: str,
        max_buffer: int = 500,
        ttl_sec: int = 3600,
        fallback: ReplayBackend,
    ) -> None:
        self._redis_url = redis_url
        self._max_buffer = max_buffer
        self._ttl_sec = ttl_sec
        self._fallback = fallback
        self._client: Redis | None = None
        self._failed = False

    @property
    def name(self) -> str:
        return "redis"

    async def _get_client(self) -> Redis | None:
        if self._failed:
            return None
        if Redis is None or not self._redis_url:
            self._failed = True
            return None
        if self._client is None:
            self._client = Redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _seq_key(self, user_id: str, chat_id: str) -> str:
        return f"sse:seq:{user_id}:{chat_id}"

    def _buf_key(self, user_id: str, chat_id: str) -> str:
        return f"sse:buf:{user_id}:{chat_id}"

    async def _fallback_warn(self, msg: str, *, user_id: str, chat_id: str, exc: Exception | None) -> None:
        if not self._failed:
            logger.warning(
                msg,
                extra={
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "error": str(exc) if exc else None,
                },
            )
        self._failed = True

    async def next_seq(self, *, user_id: str, chat_id: str) -> int:
        client = await self._get_client()
        if client is None:
            return await self._fallback.next_seq(user_id=user_id, chat_id=chat_id)
        try:
            seq_key = self._seq_key(user_id, chat_id)
            value = await client.incr(seq_key)
            if self._ttl_sec > 0:
                await client.expire(seq_key, self._ttl_sec)
            return int(value)
        except Exception as exc:
            await self._fallback_warn("sse_replay_redis_seq_failed", user_id=user_id, chat_id=chat_id, exc=exc)
            return await self._fallback.next_seq(user_id=user_id, chat_id=chat_id)

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> int:
        client = await self._get_client()
        if client is None:
            return await self._fallback.record_event(
                user_id=user_id,
                chat_id=chat_id,
                event=event,
                data=data,
                timestamp=timestamp,
            )
        seq_value = await self.next_seq(user_id=user_id, chat_id=chat_id)
        record = {
            "seq": seq_value,
            "event": event,
            "data": data,
            "ts": float(timestamp if timestamp is not None else time.time()),
        }
        try:
            payload = json.dumps(record, ensure_ascii=False)
            buf_key = self._buf_key(user_id, chat_id)
            pipe = client.pipeline()
            pipe.lpush(buf_key, payload)
            pipe.ltrim(buf_key, 0, max(self._max_buffer - 1, 0))
            if self._ttl_sec > 0:
                pipe.expire(buf_key, self._ttl_sec)
            await pipe.execute()
            return seq_value
        except Exception as exc:
            await self._fallback_warn("sse_replay_redis_record_failed", user_id=user_id, chat_id=chat_id, exc=exc)
            return await self._fallback.record_event(
                user_id=user_id,
                chat_id=chat_id,
                event=event,
                data=data,
                timestamp=timestamp,
            )

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int
    ) -> tuple[list[BroadcastRecord], bool]:
        client = await self._get_client()
        if client is None:
            return await self._fallback.replay_after(user_id=user_id, chat_id=chat_id, last_seq=last_seq)
        try:
            buf_key = self._buf_key(user_id, chat_id)
            raw_items = await client.lrange(buf_key, 0, max(self._max_buffer - 1, 0))
            events: list[BroadcastRecord] = []
            for raw in raw_items:
                try:
                    item = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                if "seq" not in item or "event" not in item:
                    continue
                events.append(item)
            if not events:
                return [], True
            min_seq = min(int(item.get("seq", 0)) for item in events)
            if last_seq < min_seq:
                return [], True
            filtered = [item for item in events if int(item.get("seq", 0)) > last_seq]
            filtered.sort(key=lambda item: int(item.get("seq", 0)))
            return filtered, False
        except Exception as exc:
            await self._fallback_warn("sse_replay_redis_read_failed", user_id=user_id, chat_id=chat_id, exc=exc)
            return await self._fallback.replay_after(user_id=user_id, chat_id=chat_id, last_seq=last_seq)


def _resolve_redis_url() -> str:
    return (
        os.getenv("LANGGRAPH_V2_REDIS_URL")
        or os.getenv("REDIS_URL")
        or os.getenv("redis_url")
        or ""
    )


def build_replay_backend() -> ReplayBackend:
    backend = os.getenv("SEALAI_SSE_REPLAY_BACKEND", "memory").strip().lower()
    maxlen = int(os.getenv("SEALAI_SSE_REPLAY_MAXLEN", "500"))
    ttl = int(os.getenv("SEALAI_SSE_REPLAY_TTL_SEC", "3600"))
    memory_backend = MemoryReplayBackend(max_buffer=maxlen)
    if backend != "redis":
        return memory_backend
    redis_url = _resolve_redis_url()
    if Redis is None or not redis_url:
        logger.warning(
            "sse_replay_redis_unavailable",
            extra={"backend": backend, "redis_url_set": bool(redis_url)},
        )
        return memory_backend
    return RedisReplayBackend(
        redis_url=redis_url,
        max_buffer=maxlen,
        ttl_sec=ttl,
        fallback=memory_backend,
    )


class SseBroadcastManager:
    def __init__(
        self,
        *,
        replay_backend: Optional[ReplayBackend] = None,
        queue_maxsize: int = 200,
        slow_notice_interval: float = 5.0,
    ) -> None:
        self._subscribers: Dict[BroadcastKey, set[asyncio.Queue[BroadcastEvent]]] = {}
        self._slow_notice: Dict[asyncio.Queue[BroadcastEvent], float] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = queue_maxsize
        self._slow_notice_interval = slow_notice_interval
        self._replay_backend = replay_backend or build_replay_backend()

    @property
    def backend_name(self) -> str:
        return self._replay_backend.name

    @staticmethod
    def parse_last_event_id(chat_id: str, last_event_id: str | None) -> Optional[int]:
        if not last_event_id:
            return None
        raw = last_event_id.strip()
        if raw.isdigit():
            return int(raw)
        if ":" in raw:
            suffix = raw.rpartition(":")[2]
            if suffix.isdigit():
                return int(suffix)
        if raw.startswith(chat_id + ":"):
            suffix = raw.split(":", 1)[1]
            if suffix.isdigit():
                return int(suffix)
        return None

    async def subscribe(self, *, user_id: str, chat_id: str) -> asyncio.Queue[BroadcastEvent]:
        queue: asyncio.Queue[BroadcastEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
        key = (user_id, chat_id)
        async with self._lock:
            self._subscribers.setdefault(key, set()).add(queue)
        return queue

    async def unsubscribe(
        self, *, user_id: str, chat_id: str, queue: asyncio.Queue[BroadcastEvent]
    ) -> None:
        key = (user_id, chat_id)
        async with self._lock:
            subscribers = self._subscribers.get(key)
            if subscribers:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(key, None)
            self._slow_notice.pop(queue, None)

    async def next_seq(self, *, user_id: str, chat_id: str) -> int:
        return await self._replay_backend.next_seq(user_id=user_id, chat_id=chat_id)

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        timestamp: Optional[float] = None,
    ) -> int:
        return await self._replay_backend.record_event(
            user_id=user_id,
            chat_id=chat_id,
            event=event,
            data=data,
            timestamp=timestamp,
        )

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int
    ) -> tuple[list[BroadcastRecord], bool]:
        return await self._replay_backend.replay_after(
            user_id=user_id,
            chat_id=chat_id,
            last_seq=last_seq,
        )

    async def _enqueue(
        self,
        queue: asyncio.Queue[BroadcastEvent],
        *,
        user_id: str,
        chat_id: str,
        seq: int,
        event: str,
        data: Dict[str, Any],
    ) -> None:
        if queue.maxsize <= 0:
            queue.put_nowait((seq, event, data))
            return

        send_slow_notice = False
        if queue.full():
            now = time.time()
            last_notice = self._slow_notice.get(queue, 0.0)
            if now - last_notice >= self._slow_notice_interval:
                send_slow_notice = True
                self._slow_notice[queue] = now

            while queue.qsize() > queue.maxsize - 1:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

        if queue.qsize() <= queue.maxsize - 1:
            queue.put_nowait((seq, event, data))

        if send_slow_notice and queue.maxsize >= 2:
            while queue.qsize() > queue.maxsize - 1:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            if queue.qsize() <= queue.maxsize - 1:
                slow_seq = await self.record_event(
                    user_id=user_id,
                    chat_id=chat_id,
                    event="slow_client",
                    data={"reason": "backpressure"},
                )
                queue.put_nowait((slow_seq, "slow_client", {"reason": "backpressure"}))

    async def broadcast(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
    ) -> int:
        seq_value = await self.record_event(
            user_id=user_id,
            chat_id=chat_id,
            event=event,
            data=data,
        )
        key = (user_id, chat_id)
        async with self._lock:
            subscribers: Iterable[asyncio.Queue[BroadcastEvent]] = list(
                self._subscribers.get(key, set())
            )
        delivered = 0
        for queue in subscribers:
            try:
                await self._enqueue(
                    queue,
                    user_id=user_id,
                    chat_id=chat_id,
                    seq=seq_value,
                    event=event,
                    data=data,
                )
                delivered += 1
            except Exception as exc:
                logger.warning(
                    "sse_broadcast_failed",
                    extra={
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "event": event,
                        "error": str(exc),
                    },
                )
        return delivered


sse_broadcast = SseBroadcastManager()
