"""ASGI request boundary: bounded bodies and denial of sensitive query parameters."""

from __future__ import annotations

from urllib.parse import parse_qsl

from starlette.responses import JSONResponse

_FORBIDDEN_QUERY_KEYS = frozenset(
    {"case", "case_id", "access_token", "id_token", "id_token_hint", "token"}
)


class RequestBoundaryMiddleware:
    def __init__(self, app, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            query = parse_qsl(
                scope.get("query_string", b"").decode("ascii"),
                keep_blank_values=True,
                max_num_fields=64,
            )
        except (UnicodeDecodeError, ValueError):
            await JSONResponse({"detail": "invalid query"}, status_code=400)(
                scope, receive, send
            )
            return
        if any(key.lower() in _FORBIDDEN_QUERY_KEYS for key, _ in query):
            await JSONResponse(
                {"detail": "sensitive identifiers are not accepted in query strings"},
                status_code=400,
            )(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await JSONResponse(
                    {"detail": "invalid content length"}, status_code=400
                )(scope, receive, send)
                return
            if declared < 0 or declared > self.max_body_bytes:
                await JSONResponse(
                    {"detail": "request body too large"}, status_code=413
                )(scope, receive, send)
                return

        messages: list[dict] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            total += len(message.get("body", b""))
            if total > self.max_body_bytes:
                await JSONResponse(
                    {"detail": "request body too large"}, status_code=413
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        iterator = iter(messages)

        async def replay_receive():
            try:
                return next(iterator)
            except StopIteration:
                # Once the buffered request has been replayed, delegate to the original
                # channel.  StreamingResponse concurrently waits for ``http.disconnect``;
                # returning an endless sequence of empty request messages here would turn
                # that listener into a busy loop and prevent the stream from completing.
                return await receive()

        await self.app(scope, replay_receive, send)
