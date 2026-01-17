from __future__ import annotations

from weakref import WeakKeyDictionary
import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List, Optional, Protocol, Set, Tuple

from redis.asyncio import Redis

from app.services.redis_client import make_async_redis_client

logger = logging.getLogger(__name__)

# (seq, event, data)
BroadcastEvent = Tuple[int, str, Dict[str, Any]]


class BroadcastRecord(Protocol):
    user_id: str
    chat_id: str
    event: str
    data: Dict[str, Any]
    timestamp: float
    seq: int
    tenant_id: Optional[str]


# Key: (scoped_user_id, chat_id)
BroadcastKey = Tuple[str, str]


def _scoped_user_id(user_id: str, tenant_id: Optional[str]) -> str:
    if tenant_id:
        return f"{tenant_id}:{user_id}"
    return user_id


class ReplayBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def next_seq(self, *, user_id: str, chat_id: str, tenant_id: Optional[str] = None) -> int:
        pass

    @abstractmethod
    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        pass

    @abstractmethod
    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int, tenant_id: Optional[str] = None
    ) -> Tuple[List[BroadcastRecord], bool]:
        """Returns (records, buffer_miss)."""
        pass


class MemoryReplayBackend(ReplayBackend):
    def __init__(self, max_buffer: int = 500) -> None:
        self._buffer: Dict[BroadcastKey, List[BroadcastRecord]] = {}
        self._seq_counters: Dict[BroadcastKey, int] = {}
        self._max_buffer = max_buffer
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "memory"

    async def next_seq(self, *, user_id: str, chat_id: str, tenant_id: Optional[str] = None) -> int:
        key = (tenant_id, user_id, chat_id)
        async with self._lock:
            return self._seq_counters.get(key, 0) + 1

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        key = (tenant_id, user_id, chat_id)
        async with self._lock:
            seq = self._seq_counters.get(key, 0) + 1
            self._seq_counters[key] = seq

            record = type(
                "Record",
                (),
                {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "event": event,
                    "data": data,
                    "timestamp": timestamp or time.time(),
                    "seq": seq,
                    "tenant_id": tenant_id,
                },
            )()

            buf = self._buffer.setdefault(key, [])
            buf.append(record)
            if len(buf) > self._max_buffer:
                buf.pop(0)
            return seq

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int, tenant_id: Optional[str] = None
    ) -> Tuple[List[BroadcastRecord], bool]:
        key = (tenant_id, user_id, chat_id)
        async with self._lock:
            buf = self._buffer.get(key, [])
            if not buf:
                return [], False

            # Simple check if last_seq is too old
            if buf[0].seq > last_seq + 1:
                return buf, True

            return [r for r in buf if r.seq > last_seq], False


class RedisReplayBackend(ReplayBackend):
    def __init__(
        self,
        redis_url: str,
        max_buffer: int = 500,
        ttl_sec: int = 3600,
        fallback: Optional[ReplayBackend] = None,
    ) -> None:
        self._redis_url = redis_url
        self._max_buffer = max_buffer
        self._ttl_sec = ttl_sec
        self._fallback = fallback or MemoryReplayBackend(max_buffer=max_buffer)
        self._client_store: "WeakKeyDictionary[asyncio.AbstractEventLoop, Redis]" = WeakKeyDictionary()

    @property
    def name(self) -> str:
        return "redis"

    async def _get_client(self) -> Redis:
        # Best practice: central helper -> pooling/timeouts/health checks
        # decode_responses=True makes redis return str; our payload is JSON strings
        loop = asyncio.get_running_loop()
        client = self._client_store.get(loop)
        if client is None:
            client = make_async_redis_client(
                self._redis_url,
                decode_responses=True,
            )
            self._client_store[loop] = client
        return client

    def _get_redis_key(self, user_id: str, chat_id: str, tenant_id: Optional[str]) -> str:
        if tenant_id:
            return f"sse:replay:{tenant_id}:{user_id}:{chat_id}"
        return f"sse:replay:{user_id}:{chat_id}"

    def _get_seq_key(self, user_id: str, chat_id: str, tenant_id: Optional[str]) -> str:
        if tenant_id:
            return f"sse:seq:{tenant_id}:{user_id}:{chat_id}"
        return f"sse:seq:{user_id}:{chat_id}"

    async def next_seq(self, *, user_id: str, chat_id: str, tenant_id: Optional[str] = None) -> int:
        try:
            client = await self._get_client()
            seq_key = self._get_seq_key(user_id, chat_id, tenant_id)
            val = await client.get(seq_key)
            return int(val or 0) + 1
        except Exception:
            if self._fallback:
                return await self._fallback.next_seq(user_id=user_id, chat_id=chat_id, tenant_id=tenant_id)
            raise

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        try:
            client = await self._get_client()
            list_key = self._get_redis_key(user_id, chat_id, tenant_id)
            seq_key = self._get_seq_key(user_id, chat_id, tenant_id)

            # Using INCR for stable monotonic sequence
            ts = timestamp or time.time()
            async with client.pipeline(transaction=True) as pipe:
                pipe.incr(seq_key)
                pipe.expire(seq_key, self._ttl_sec)
                results = await pipe.execute()

            seq = int(results[0])

            payload = json.dumps(
                {
                    "u": user_id,
                    "c": chat_id,
                    "e": event,
                    "d": data,
                    "t": ts,
                    "ten": tenant_id,
                    "s": seq,
                }
            )

            async with client.pipeline(transaction=True) as pipe:
                pipe.rpush(list_key, payload)
                pipe.ltrim(list_key, -self._max_buffer, -1)
                pipe.expire(list_key, self._ttl_sec)
                await pipe.execute()

            return seq
        except Exception:
            if self._fallback:
                return await self._fallback.record_event(
                    user_id=user_id,
                    chat_id=chat_id,
                    event=event,
                    data=data,
                    tenant_id=tenant_id,
                    timestamp=timestamp,
                )
            raise

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int, tenant_id: Optional[str] = None
    ) -> Tuple[List[BroadcastRecord], bool]:
        try:
            client = await self._get_client()
            list_key = self._get_redis_key(user_id, chat_id, tenant_id)

            raw_records = await client.lrange(list_key, 0, -1)
            records: List[BroadcastRecord] = []

            if not raw_records:
                return [], False

            # decode_responses=True -> raw_records are str
            parsed_records: List[dict] = []
            for raw in raw_records:
                if not raw:
                    continue
                try:
                    parsed_records.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    continue

            if not parsed_records:
                return [], False

            buffer_miss = False

            # Check if last_seq is before our earliest record
            first_seq = int(parsed_records[0].get("s", 0) or 0)
            if last_seq > 0 and last_seq < first_seq - 1:
                buffer_miss = True

            for item in parsed_records:
                s = int(item.get("s", 0) or 0)
                if s > last_seq:
                    rec = type(
                        "Record",
                        (),
                        {
                            "user_id": item.get("u"),
                            "chat_id": item.get("c"),
                            "event": item.get("e"),
                            "data": item.get("d"),
                            "timestamp": item.get("t"),
                            "seq": s,
                            "tenant_id": item.get("ten"),
                        },
                    )()
                    records.append(rec)

            return records, buffer_miss
        except Exception:
            if self._fallback:
                return await self._fallback.replay_after(
                    user_id=user_id,
                    chat_id=chat_id,
                    last_seq=last_seq,
                    tenant_id=tenant_id,
                )
            raise


def build_replay_backend(redis_url: Optional[str] = None) -> ReplayBackend:
    redis_url = redis_url or os.getenv("REDIS_URL")
    maxlen = int(os.getenv("SSE_REPLAY_MAX", "500"))
    ttl = int(os.getenv("SSE_REPLAY_TTL", "3600"))
    memory_backend = MemoryReplayBackend(max_buffer=maxlen)
    if not redis_url:
        return memory_backend
    return RedisReplayBackend(
        redis_url=redis_url,
        max_buffer=maxlen,
        ttl_sec=ttl,
        fallback=memory_backend,
    )


class SseBroadcastManager:
    @staticmethod
    def parse_last_event_id(chat_id: str, last_event_id: str | None) -> Optional[int]:
        if not last_event_id:
            return None
        raw = last_event_id.strip()
        if raw.isdigit():
            return int(raw)
        if raw.startswith(chat_id + ":"):
            suffix = raw.split(":", 1)[1]
            if suffix.isdigit():
                return int(suffix)
        return None

    def __init__(
        self,
        redis_url: Optional[str] = None,
        *,
        replay_backend: Optional[ReplayBackend] = None,
        queue_maxsize: int = 200,
        slow_notice_interval: float = 5.0,
    ) -> None:
        self._subscribers: Dict[BroadcastKey, Set[asyncio.Queue[BroadcastEvent]]] = {}
        self._slow_notice: Dict[asyncio.Queue[BroadcastEvent], float] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = queue_maxsize
        self._slow_notice_interval = slow_notice_interval
        self._replay_backend = replay_backend or build_replay_backend(redis_url)

    @property
    def backend_name(self) -> str:
        return self._replay_backend.name

    def _get_redis_key(self, chat_id: str, tenant_id: Optional[str] = None) -> str:
        if tenant_id:
            return f"sse:events:{tenant_id}:{chat_id}"
        return f"sse:events:{chat_id}"

    def _get_redis_channel(self, chat_id: str, tenant_id: Optional[str] = None) -> str:
        if tenant_id:
            return f"sse:channel:{tenant_id}:{chat_id}"
        return f"sse:channel:{chat_id}"

    async def subscribe(
        self, *, user_id: str, chat_id: str, tenant_id: Optional[str] = None
    ) -> asyncio.Queue[BroadcastEvent]:
        queue: asyncio.Queue[BroadcastEvent] = asyncio.Queue(maxsize=self._queue_maxsize)
        scoped_user_id = _scoped_user_id(user_id, tenant_id)
        key = (scoped_user_id, chat_id)
        async with self._lock:
            self._subscribers.setdefault(key, set()).add(queue)
        return queue

    async def unsubscribe(
        self,
        *,
        user_id: str,
        chat_id: str,
        queue: asyncio.Queue[BroadcastEvent],
        tenant_id: Optional[str] = None,
    ) -> None:
        scoped_user_id = _scoped_user_id(user_id, tenant_id)
        key = (scoped_user_id, chat_id)
        async with self._lock:
            subscribers = self._subscribers.get(key)
            if subscribers:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(key, None)
            self._slow_notice.pop(queue, None)

    async def next_seq(self, *, user_id: str, chat_id: str, tenant_id: Optional[str] = None) -> int:
        scoped_user_id = _scoped_user_id(user_id, tenant_id)
        return await self._replay_backend.next_seq(user_id=scoped_user_id, chat_id=chat_id)

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        scoped_user_id = _scoped_user_id(user_id, tenant_id)
        if tenant_id:
            return await self._replay_backend.record_event(
                user_id=scoped_user_id,
                chat_id=chat_id,
                event=event,
                data=data,
                timestamp=timestamp,
            )
        return await self._replay_backend.record_event(
            user_id=scoped_user_id,
            chat_id=chat_id,
            event=event,
            data=data,
            tenant_id=tenant_id,
            timestamp=timestamp,
        )

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int, tenant_id: Optional[str] = None
    ) -> Tuple[List[BroadcastRecord], bool]:
        scoped_user_id = _scoped_user_id(user_id, tenant_id)
        if tenant_id:
            return await self._replay_backend.replay_after(
                user_id=scoped_user_id,
                chat_id=chat_id,
                last_seq=last_seq,
            )
        return await self._replay_backend.replay_after(
            user_id=scoped_user_id,
            chat_id=chat_id,
            last_seq=last_seq,
            tenant_id=tenant_id,
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
        tenant_id: Optional[str] = None,
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
                    tenant_id=tenant_id,
                )
                queue.put_nowait((slow_seq, "slow_client", {"reason": "backpressure"}))

    async def broadcast(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
    ) -> int:
        seq_value = await self.record_event(
            user_id=user_id,
            chat_id=chat_id,
            event=event,
            data=data,
            tenant_id=tenant_id,
        )
        scoped_user_id = _scoped_user_id(user_id, tenant_id)
        key = (scoped_user_id, chat_id)
        async with self._lock:
            subscribers: Iterable[asyncio.Queue[BroadcastEvent]] = list(self._subscribers.get(key, set()))
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
                    tenant_id=tenant_id,
                )
                delivered += 1
            except Exception as exc:
                logger.warning(
                    "sse_broadcast_failed",
                    extra={
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "tenant_id": tenant_id,
                        "event": event,
                        "error": str(exc),
                    },
                )
        return delivered


_SSE_MANAGER_STORE: "WeakKeyDictionary[asyncio.AbstractEventLoop, SseBroadcastManager]" = WeakKeyDictionary()


def _get_sse_manager(loop: asyncio.AbstractEventLoop) -> SseBroadcastManager:
    manager = _SSE_MANAGER_STORE.get(loop)
    if manager is None:
        manager = SseBroadcastManager()
        _SSE_MANAGER_STORE[loop] = manager
    return manager


def get_sse_broadcast() -> SseBroadcastManager:
    loop = asyncio.get_running_loop()
    return _get_sse_manager(loop)


class _SseBroadcastProxy:
    @property
    def backend_name(self) -> str:
        return get_sse_broadcast().backend_name

    def parse_last_event_id(self, chat_id: str, last_event_id: str | None) -> Optional[int]:
        return SseBroadcastManager.parse_last_event_id(chat_id, last_event_id)

    async def subscribe(self, *, user_id: str, chat_id: str, tenant_id: Optional[str] = None) -> asyncio.Queue[BroadcastEvent]:
        return await get_sse_broadcast().subscribe(user_id=user_id, chat_id=chat_id, tenant_id=tenant_id)

    async def unsubscribe(
        self, *, user_id: str, chat_id: str, queue: asyncio.Queue[BroadcastEvent], tenant_id: Optional[str] = None
    ) -> None:
        await get_sse_broadcast().unsubscribe(user_id=user_id, chat_id=chat_id, queue=queue, tenant_id=tenant_id)

    async def next_seq(self, *, user_id: str, chat_id: str, tenant_id: Optional[str] = None) -> int:
        return await get_sse_broadcast().next_seq(user_id=user_id, chat_id=chat_id, tenant_id=tenant_id)

    async def record_event(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> int:
        return await get_sse_broadcast().record_event(
            user_id=user_id,
            chat_id=chat_id,
            event=event,
            data=data,
            tenant_id=tenant_id,
            timestamp=timestamp,
        )

    async def replay_after(
        self, *, user_id: str, chat_id: str, last_seq: int, tenant_id: Optional[str] = None
    ) -> Tuple[List[BroadcastRecord], bool]:
        return await get_sse_broadcast().replay_after(
            user_id=user_id,
            chat_id=chat_id,
            last_seq=last_seq,
            tenant_id=tenant_id,
        )

    async def broadcast(
        self,
        *,
        user_id: str,
        chat_id: str,
        event: str,
        data: Dict[str, Any],
        tenant_id: Optional[str] = None,
    ) -> int:
        return await get_sse_broadcast().broadcast(
            user_id=user_id,
            chat_id=chat_id,
            event=event,
            data=data,
            tenant_id=tenant_id,
        )


sse_broadcast = _SseBroadcastProxy()
