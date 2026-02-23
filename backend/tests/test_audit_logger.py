"""Tests for AuditLogger (Sprint 9).

All DB interaction is replaced with unittest.mock.AsyncMock so no real
Postgres connection is needed.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audit.audit_logger import (
    AuditLogger,
    get_global_audit_logger,
    set_global_audit_logger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pool() -> MagicMock:
    """Return a mock asyncpg Pool whose acquire() yields an async context manager."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    acm = AsyncMock()
    acm.__aenter__ = AsyncMock(return_value=conn)
    acm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acm)
    return pool, conn


# ---------------------------------------------------------------------------
# ensure_table
# ---------------------------------------------------------------------------


class TestEnsureTable:
    @pytest.mark.asyncio
    async def test_creates_table_with_correct_ddl(self):
        pool, conn = _make_pool()
        al = AuditLogger(pool)
        await al.ensure_table()

        assert conn.execute.called
        ddl = conn.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS audit_log" in ddl
        assert "session_id" in ddl
        assert "tenant_id" in ddl
        assert "working_profile" in ddl
        assert "calculation_result" in ddl
        assert "critique_log" in ddl
        assert "phase" in ddl
        assert "created_at" in ddl


# ---------------------------------------------------------------------------
# append / _insert
# ---------------------------------------------------------------------------


class TestAppend:
    @pytest.mark.asyncio
    async def test_append_inserts_row(self):
        pool, conn = _make_pool()
        al = AuditLogger(pool)

        state = {
            "working_profile": {"medium": "steam"},
            "calculation_result": {"safety_factor": 2.1},
            "critique_log": ["[WARNING] Thermal margin low"],
            "phase": "quality_gate",
        }

        # Call _insert directly to avoid task scheduling complexities
        await al._insert(session_id="sess-1", tenant_id="acme", state=state)

        assert conn.execute.called
        args = conn.execute.call_args[0]
        # First arg is the INSERT SQL
        assert "INSERT INTO audit_log" in args[0]
        # session_id
        assert args[1] == "sess-1"
        # tenant_id
        assert args[2] == "acme"
        # working_profile (JSONB as string)
        working_profile_json = args[3]
        assert working_profile_json is not None
        assert json.loads(working_profile_json) == {"medium": "steam"}

    @pytest.mark.asyncio
    async def test_missing_optional_fields_do_not_raise(self):
        pool, conn = _make_pool()
        al = AuditLogger(pool)

        # Completely empty state
        await al._insert(session_id="sess-2", tenant_id=None, state={})

        assert conn.execute.called
        args = conn.execute.call_args[0]
        # working_profile should be None
        assert args[3] is None
        assert args[4] is None  # calculation_result
        assert args[5] is None  # critique_log

    @pytest.mark.asyncio
    async def test_multiple_inserts_produce_independent_rows(self):
        pool, conn = _make_pool()
        al = AuditLogger(pool)

        await al._insert(session_id="s1", tenant_id="t1", state={"phase": "a"})
        await al._insert(session_id="s2", tenant_id="t2", state={"phase": "b"})

        assert conn.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_db_error_is_swallowed(self):
        pool, conn = _make_pool()
        conn.execute = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        al = AuditLogger(pool)

        # Should not raise
        await al._insert(session_id="s3", tenant_id=None, state={})

    @pytest.mark.asyncio
    async def test_append_fires_task(self):
        """append() schedules an asyncio.Task without raising."""
        pool, conn = _make_pool()
        al = AuditLogger(pool)

        al.append(session_id="s4", tenant_id="t4", state={"phase": "done"})
        # Allow the task to run
        await asyncio.sleep(0)
        # No exception


# ---------------------------------------------------------------------------
# Global logger registry
# ---------------------------------------------------------------------------


class TestGlobalAuditLogger:
    def test_set_and_get_global_logger(self):
        pool, _ = _make_pool()
        al = AuditLogger(pool)

        set_global_audit_logger(al)
        assert get_global_audit_logger() is al

    def test_get_global_logger_returns_none_before_set(self, monkeypatch):
        import app.services.audit.audit_logger as mod
        monkeypatch.setattr(mod, "_global_audit_logger", None)
        assert get_global_audit_logger() is None
