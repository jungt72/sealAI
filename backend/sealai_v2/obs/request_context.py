"""Server-generated request correlation without accepting client-controlled identifiers."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from contextvars import ContextVar, Token
from typing import Any

_REQUEST_ID: ContextVar[str | None] = ContextVar("sealai_v2_request_id", default=None)


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


def bind_request_id(request_id: str) -> Token[str | None]:
    """Test/worker seam; normal HTTP requests use ``RequestIdMiddleware``."""
    return _REQUEST_ID.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _REQUEST_ID.reset(token)


class RequestIdMiddleware:
    """Pure ASGI middleware that keeps context alive through streamed response delivery.

    A fresh server ID is always generated. Client-supplied IDs are deliberately ignored so an
    attacker cannot inject identifiers into access/application logs or correlate other users.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[..., Awaitable[MutableMapping[str, Any]]],
        send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        token = bind_request_id(request_id)

        async def send_with_request_id(message: MutableMapping[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            reset_request_id(token)
