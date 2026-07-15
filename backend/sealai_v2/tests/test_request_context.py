from __future__ import annotations

import asyncio
import io
import logging
import re

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from sealai_v2.obs.log_redaction import configure_safe_logging
from sealai_v2.obs.request_context import RequestIdMiddleware, current_request_id

_REQUEST_ID_RE = re.compile(r"\A[0-9a-f]{32}\Z")


def _app(observed: list[str | None]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/plain")
    async def plain() -> dict[str, str | None]:
        observed.append(current_request_id())
        return {"request_id": current_request_id()}

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        async def body():
            await asyncio.sleep(0)
            observed.append(current_request_id())
            yield b"ok"

        return StreamingResponse(body())

    return app


def test_server_generates_and_returns_request_id() -> None:
    observed: list[str | None] = []
    response = TestClient(_app(observed)).get("/plain")
    request_id = response.headers["x-request-id"]
    assert _REQUEST_ID_RE.fullmatch(request_id)
    assert response.json() == {"request_id": request_id}
    assert observed == [request_id]
    assert current_request_id() is None


def test_client_supplied_request_id_is_ignored() -> None:
    observed: list[str | None] = []
    canary = "attacker-controlled-correlation-id"
    response = TestClient(_app(observed)).get(
        "/plain", headers={"X-Request-ID": canary}
    )
    assert response.headers["x-request-id"] != canary
    assert _REQUEST_ID_RE.fullmatch(response.headers["x-request-id"])


def test_context_survives_stream_delivery() -> None:
    observed: list[str | None] = []
    response = TestClient(_app(observed)).get("/stream")
    assert response.text == "ok"
    assert observed == [response.headers["x-request-id"]]
    assert current_request_id() is None


def test_request_id_is_in_application_log_and_client_header_is_not() -> None:
    configure_safe_logging()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("sealai_v2.tests.request_context")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    observed: list[str | None] = []
    app = _app(observed)

    @app.get("/logged")
    async def logged() -> dict[str, bool]:
        logger.info("event=request_context_test")
        return {"ok": True}

    canary = "client-canary-request-id"
    response = TestClient(app).get("/logged", headers={"X-Request-ID": canary})
    rendered = stream.getvalue()
    assert f"request_id={response.headers['x-request-id']}" in rendered
    assert canary not in rendered
