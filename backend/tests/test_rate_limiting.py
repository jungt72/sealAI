"""Tests for H2: Redis-based rate limiting on the RAG upload endpoint."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# _check_upload_rate_limit unit tests (no real Redis needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_allows_under_limit():
    """First N requests within the window must pass without raising."""
    from app.api.v1.endpoints.rag import _check_upload_rate_limit

    mock_redis_instance = AsyncMock()
    mock_redis_instance.incr = AsyncMock(return_value=5)   # 5th request, limit=20
    mock_redis_instance.expire = AsyncMock(return_value=True)
    mock_redis_instance.__aenter__ = AsyncMock(return_value=mock_redis_instance)
    mock_redis_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.api.v1.endpoints.rag.settings") as mock_settings,
        patch("os.getenv", return_value="redis://redis:6379"),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis_instance),
    ):
        mock_settings.rate_limit_upload = 20
        mock_settings.rate_limit_window_s = 60
        # Should not raise
        await _check_upload_rate_limit("tenant-abc")


@pytest.mark.asyncio
async def test_rate_limit_blocks_over_limit():
    """Requests exceeding the limit must raise HTTP 429."""
    from fastapi import HTTPException

    from app.api.v1.endpoints.rag import _check_upload_rate_limit

    mock_redis_instance = AsyncMock()
    mock_redis_instance.incr = AsyncMock(return_value=21)  # 21st request, limit=20
    mock_redis_instance.expire = AsyncMock(return_value=True)
    mock_redis_instance.__aenter__ = AsyncMock(return_value=mock_redis_instance)
    mock_redis_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.api.v1.endpoints.rag.settings") as mock_settings,
        patch("os.getenv", return_value="redis://redis:6379"),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis_instance),
    ):
        mock_settings.rate_limit_upload = 20
        mock_settings.rate_limit_window_s = 60

        with pytest.raises(HTTPException) as exc_info:
            await _check_upload_rate_limit("tenant-abc")

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_skipped_without_redis_url():
    """When REDIS_URL is not set, rate limiting must silently pass."""
    from app.api.v1.endpoints.rag import _check_upload_rate_limit

    with patch("os.getenv", return_value=""):
        # Must not raise even without Redis
        await _check_upload_rate_limit("tenant-xyz")


@pytest.mark.asyncio
async def test_rate_limit_fail_open_on_redis_error():
    """If Redis is unavailable, the check must fail-open (not block the upload)."""
    from app.api.v1.endpoints.rag import _check_upload_rate_limit

    mock_redis_class = MagicMock()
    mock_redis_class.from_url = MagicMock(side_effect=ConnectionRefusedError("redis down"))

    with (
        patch("app.api.v1.endpoints.rag.settings") as mock_settings,
        patch("os.getenv", return_value="redis://redis:6379"),
        patch("redis.asyncio.Redis", mock_redis_class),
    ):
        mock_settings.rate_limit_upload = 20
        mock_settings.rate_limit_window_s = 60
        # Must not raise — fail-open
        await _check_upload_rate_limit("tenant-abc")


@pytest.mark.asyncio
async def test_rate_limit_exact_boundary():
    """The 20th request must pass; the 21st must be blocked."""
    from fastapi import HTTPException

    from app.api.v1.endpoints.rag import _check_upload_rate_limit

    call_count = 0

    async def incr_side_effect(key: str) -> int:
        nonlocal call_count
        call_count += 1
        return call_count

    mock_redis_instance = AsyncMock()
    mock_redis_instance.incr = AsyncMock(side_effect=incr_side_effect)
    mock_redis_instance.expire = AsyncMock(return_value=True)
    mock_redis_instance.__aenter__ = AsyncMock(return_value=mock_redis_instance)
    mock_redis_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.api.v1.endpoints.rag.settings") as mock_settings,
        patch("os.getenv", return_value="redis://redis:6379"),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis_instance),
    ):
        mock_settings.rate_limit_upload = 20
        mock_settings.rate_limit_window_s = 60

        # Requests 1-20 must pass
        for _ in range(20):
            await _check_upload_rate_limit("tenant-test")

        # Request 21 must be blocked
        with pytest.raises(HTTPException) as exc_info:
            await _check_upload_rate_limit("tenant-test")

    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_different_tenants_independent():
    """Each tenant must have its own independent counter."""
    from app.api.v1.endpoints.rag import _check_upload_rate_limit

    counters: dict[str, int] = {}

    async def incr_side_effect(key: str) -> int:
        # Extract tenant from key: rl:rag_upload:{tenant_id}:{bucket}
        parts = key.split(":")
        tenant_part = parts[2] if len(parts) > 2 else key
        counters[tenant_part] = counters.get(tenant_part, 0) + 1
        return counters[tenant_part]

    mock_redis_instance = AsyncMock()
    mock_redis_instance.incr = AsyncMock(side_effect=incr_side_effect)
    mock_redis_instance.expire = AsyncMock(return_value=True)
    mock_redis_instance.__aenter__ = AsyncMock(return_value=mock_redis_instance)
    mock_redis_instance.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.api.v1.endpoints.rag.settings") as mock_settings,
        patch("os.getenv", return_value="redis://redis:6379"),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis_instance),
    ):
        mock_settings.rate_limit_upload = 20
        mock_settings.rate_limit_window_s = 60

        # 15 requests per tenant — both must pass
        for _ in range(15):
            await _check_upload_rate_limit("tenant-A")
            await _check_upload_rate_limit("tenant-B")

    # Both tenants: 15 requests each, both under the 20-request limit
    assert counters.get("tenant-A", 0) == 15
    assert counters.get("tenant-B", 0) == 15


# ---------------------------------------------------------------------------
# Config: rate_limit_upload / rate_limit_window_s exposed in settings
# ---------------------------------------------------------------------------

def test_config_has_rate_limit_upload_field():
    from app.core.config import Settings

    fields = Settings.model_fields
    assert "rate_limit_upload" in fields
    assert "rate_limit_window_s" in fields
