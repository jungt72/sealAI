import asyncio

import pytest
from fastapi import HTTPException

from app.services.auth import dependencies


class DummyWebSocket:
    """Minimal stub matching the subset of WebSocket API that the dependency uses."""

    def __init__(self, token: str) -> None:
        self.headers = {"Authorization": f"Bearer {token}"}
        self.query_params: dict[str, str] = {}
        self.closed_codes: list[int] = []

    async def close(self, code: int) -> None:
        self.closed_codes.append(code)


def test_get_current_request_user_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(token: str) -> dict[str, str]:
        raise ValueError("expired access token")

    monkeypatch.setattr(dependencies, "verify_access_token", fake_verify)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(dependencies.get_current_request_user("Bearer foo"))

    assert exc_info.value.status_code == 401
    assert "expired access token" in str(exc_info.value.detail)


def test_get_current_ws_user_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_verify(token: str) -> dict[str, str]:
        raise ValueError("jwt invalid")

    monkeypatch.setattr(dependencies, "verify_access_token", fake_verify)

    ws = DummyWebSocket("foobar")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(dependencies.get_current_ws_user(ws))

    assert exc_info.value.status_code == 401
    assert "jwt invalid" in str(exc_info.value.detail)
