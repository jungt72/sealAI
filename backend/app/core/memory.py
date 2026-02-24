import json
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from typing import Any, Awaitable, Iterable, Optional, TypeVar

from langgraph.store.base import BaseStore, Item, Op
try:
    from psycopg_pool import AsyncConnectionPool
except Exception:  # pragma: no cover - optional in lightweight test environments
    AsyncConnectionPool = None  # type: ignore[assignment]
from app.core.config import settings

T = TypeVar("T")

_pool: Any = None

def get_connection_pool() -> Any:
    global _pool
    if _pool is None:
        if AsyncConnectionPool is None:
            raise RuntimeError("psycopg_pool is required for postgres store")
        conninfo = settings.postgres_dsn or settings.POSTGRES_SYNC_URL or settings.database_url
        # DB URL assumed compatible with psycopg (e.g. postgresql://...)
        _pool = AsyncConnectionPool(
            conninfo=conninfo,
            max_size=20, 
            kwargs={"autocommit": True},
            open=False # Don't open in constructor to avoid warnings
        )
    return _pool

class AsyncPostgresStore(BaseStore):
    def __init__(self, pool: Any):
        self.pool = pool
        self._sync_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="store-sync")
        self._sync_timeout_sec = float(os.getenv("STORE_SYNC_TIMEOUT_SEC", "15"))

    async def setup(self) -> None:
        # Check if pool needs opening (psycopg_pool internal)
        if not getattr(self.pool, "_opened", False):
            await self.pool.open()
            print("DATABASE POOL OPENED SUCCESSFULLY")
        async with self.pool.connection() as conn:
            # We use 'namespace' as column name as requested.
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS store_items (
                    namespace text NOT NULL,
                    key text NOT NULL,
                    value jsonb,
                    created_at timestamptz DEFAULT now(),
                    updated_at timestamptz DEFAULT now(),
                    PRIMARY KEY (namespace, key)
                );
            """)

    @staticmethod
    def _run_coro_in_new_loop(coro: Awaitable[T]) -> T:
        return asyncio.run(coro)

    def _run_sync(self, coro: Awaitable[T]) -> T:
        """Run async store calls safely from sync BaseStore methods."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        future = self._sync_executor.submit(self._run_coro_in_new_loop, coro)
        try:
            return future.result(timeout=self._sync_timeout_sec)
        except FutureTimeoutError as exc:
            cancelled = future.cancel()
            if cancelled and hasattr(coro, "close"):
                try:
                    coro.close()  # type: ignore[attr-defined]
                except Exception:
                    pass
            raise RuntimeError(
                f"AsyncPostgresStore sync bridge timed out after {self._sync_timeout_sec}s. "
                "Use async store methods (aget/aput/...) from async contexts to avoid loop stalls."
            ) from exc

    # --- Sync Methods (Required by BaseStore) ---
    def get(self, namespace: tuple[str, ...], key: str) -> Optional[Item]:
        return self._run_sync(self.aget(namespace, key))

    def put(self, namespace: tuple[str, ...], key: str, value: Any) -> None:
        return self._run_sync(self.aput(namespace, key, value))

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        return self._run_sync(self.adelete(namespace, key))

    def search(self, namespace_prefix: tuple[str, ...], *, filter: dict[str, Any] | None = None, limit: int = 10, offset: int = 0) -> list[Item]:
        return self._run_sync(self.asearch(namespace_prefix, filter=filter, limit=limit, offset=offset))

    def list_namespaces(self, *, prefix: tuple[str, ...] | None = None, suffix: tuple[str, ...] | None = None, limit: int = 100, offset: int = 0) -> list[tuple[str, ...]]:
        return self._run_sync(self.alist_namespaces(prefix=prefix, suffix=suffix, limit=limit, offset=offset))

    def batch(self, requests: Iterable[Op]) -> list[Any]:
        return self._run_sync(self.abatch(requests))

    # --- Async Methods ---
    async def aget(self, namespace: tuple[str, ...], key: str) -> Optional[Item]:
        ns_str = json.dumps(namespace)
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT value, created_at, updated_at FROM store_items WHERE namespace = %s AND key = %s",
                    (ns_str, key),
                )
                row = await cur.fetchone()
                if row:
                    value, created_at, updated_at = row
                    return Item(
                        value=value,
                        key=key,
                        namespace=namespace,
                        created_at=created_at,
                        updated_at=updated_at,
                    )
        return None

    async def aput(self, namespace: tuple[str, ...], key: str, value: Any) -> None:
        ns_str = json.dumps(namespace)
        now = datetime.now(timezone.utc)
        async with self.pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO store_items (namespace, key, value, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (namespace, key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                """,
                (ns_str, key, json.dumps(value), now, now),
            )

    async def adelete(self, namespace: tuple[str, ...], key: str) -> None:
        ns_str = json.dumps(namespace)
        async with self.pool.connection() as conn:
            await conn.execute("DELETE FROM store_items WHERE namespace = %s AND key = %s", (ns_str, key))

    async def abatch(self, requests: Iterable[Op]) -> list[Any]:
        results = []
        for op in requests:
            if op[0] == "get":
                results.append(await self.aget(op[1], op[2]))
            elif op[0] == "put":
                await self.aput(op[1], op[2], op[3])
                results.append(None)
            elif op[0] == "delete":
                await self.adelete(op[1], op[2])
                results.append(None)
            else:
                results.append(None)
        return results

    async def asearch(self, namespace_prefix: tuple[str, ...], *, filter: dict[str, Any] | None = None, limit: int = 10, offset: int = 0) -> list[Item]:
        prefix_str = json.dumps(namespace_prefix)[:-1] 
        results = []
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                pattern = prefix_str + "%"
                await cur.execute(
                    "SELECT namespace, key, value, created_at, updated_at FROM store_items WHERE namespace LIKE %s LIMIT %s OFFSET %s",
                    (pattern, limit, offset),
                )
                async for row in cur:
                    p_str, key, value, created_at, updated_at = row
                    ns = tuple(json.loads(p_str))
                    results.append(Item(
                        value=value,
                        key=key,
                        namespace=ns,
                        created_at=created_at,
                        updated_at=updated_at,
                    ))
        return results

    async def alist_namespaces(self, *, prefix: tuple[str, ...] | None = None, suffix: tuple[str, ...] | None = None, limit: int = 100, offset: int = 0) -> list[tuple[str, ...]]:
         namespaces = set()
         async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT DISTINCT namespace FROM store_items")
                async for row in cur:
                    ns = tuple(json.loads(row[0]))
                    if prefix and not all(ns[i] == prefix[i] for i in range(len(prefix))):
                        continue
                    if suffix and not all(ns[-(len(suffix)-i)] == suffix[i] for i in range(len(suffix))):
                        continue
                    namespaces.add(ns)
         
         sorted_ns = sorted(list(namespaces))
         return sorted_ns[offset : offset + limit]


async def get_postgres_store() -> AsyncPostgresStore:
    pool = get_connection_pool()
    store = AsyncPostgresStore(pool)
    await store.setup()
    return store
