"""PostgreSQL append-only audit log for SEALAI v4.4.0 (Sprint 9).

Table schema (created by ensure_table()):
    audit_log (
        id                 BIGSERIAL PRIMARY KEY,
        session_id         TEXT        NOT NULL,
        tenant_id          TEXT,
        working_profile    JSONB,
        calculation_result JSONB,
        critique_log       JSONB,
        phase              TEXT,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    )

Design rules:
- Append-only: no UPDATE or DELETE is ever issued by this module.
- append() is fire-and-forget: it schedules an asyncio.Task and returns
  immediately so it never blocks the SSE response stream.
- All exceptions are swallowed after logging — observability must not
  degrade user-facing reliability.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import asyncpg

logger = logging.getLogger("sealai.audit")

_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          TEXT        NOT NULL,
    tenant_id           TEXT,
    working_profile     JSONB,
    calculation_result  JSONB,
    critique_log        JSONB,
    phase               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_INSERT = """
INSERT INTO audit_log
    (session_id, tenant_id, working_profile, calculation_result, critique_log, phase)
VALUES ($1, $2, $3, $4, $5, $6);
"""


def _to_jsonb(value: Any) -> Optional[str]:
    """Serialise a value to a JSON string for asyncpg JSONB parameters."""
    if value is None:
        return None
    try:
        return json.dumps(value, default=str)
    except Exception:
        return None


class AuditLogger:
    """Append-only audit log backed by PostgreSQL.

    Usage:
        logger = AuditLogger(pool)
        await logger.ensure_table()
        logger.append(session_id="...", tenant_id="...", state=state_dict)
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ensure_table(self) -> None:
        """Create the audit_log table if it doesn't exist."""
        async with self._pool.acquire() as conn:
            await conn.execute(_DDL)
        logger.info("audit_log table ensured")

    def append(
        self,
        *,
        session_id: str,
        tenant_id: Optional[str],
        state: Dict[str, Any],
    ) -> None:
        """Fire-and-forget: schedule audit row insert without awaiting."""
        asyncio.create_task(
            self._insert(session_id=session_id, tenant_id=tenant_id, state=state)
        )

    async def _insert(
        self,
        *,
        session_id: str,
        tenant_id: Optional[str],
        state: Dict[str, Any],
    ) -> None:
        try:
            working_profile = _to_jsonb(state.get("working_profile"))
            calculation_result = _to_jsonb(state.get("calculation_result"))
            critique_log = _to_jsonb(state.get("critique_log"))
            phase = state.get("phase") or state.get("last_node")

            async with self._pool.acquire() as conn:
                await conn.execute(
                    _INSERT,
                    session_id,
                    tenant_id,
                    working_profile,
                    calculation_result,
                    critique_log,
                    phase,
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("audit_log insert failed: %s", exc)


_global_audit_logger: "AuditLogger | None" = None


def set_global_audit_logger(logger: "AuditLogger") -> None:
    """Register a global AuditLogger instance (called once on startup)."""
    global _global_audit_logger
    _global_audit_logger = logger


def get_global_audit_logger() -> "AuditLogger | None":
    """Return the global AuditLogger, or None if not yet initialised."""
    return _global_audit_logger


__all__ = ["AuditLogger", "get_global_audit_logger", "set_global_audit_logger"]
