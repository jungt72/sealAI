import asyncio
import importlib
import json
import sys
import types

import pytest

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub
if "multipart" not in sys.modules:
    multipart_stub = types.ModuleType("multipart")
    multipart_module = types.ModuleType("multipart.multipart")

    def _parse_options_header(_value):
        return {}

    multipart_module.parse_options_header = _parse_options_header
    multipart_stub.__version__ = "0.0.13"
    sys.modules["multipart"] = multipart_stub
    sys.modules["multipart.multipart"] = multipart_module
if "python_multipart" not in sys.modules:
    python_multipart = types.ModuleType("python_multipart")
    python_multipart.__version__ = "0.0.13"
    sys.modules["python_multipart"] = python_multipart


def _collect_stream(stream) -> str:
    async def _run() -> str:
        chunks: list[str] = []
        async for chunk in stream:
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode("utf-8"))
            else:
                chunks.append(str(chunk))
        return "".join(chunks)

    return asyncio.run(_run())


def _auth(monkeypatch: pytest.MonkeyPatch, *, user: str = "test-user") -> None:
    deps = importlib.import_module("app.services.auth.dependencies")
    monkeypatch.setattr(
        deps,
        "verify_access_token",
        lambda _t: {"preferred_username": user, "sub": user, "tenant_id": "tenant-1"},
    )


def test_chat_v2_sse_streams_token_and_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    monkeypatch.setattr(ep, "upsert_conversation", lambda *args, **kwargs: None)

    async def _fake_stream(*_args, **_kwargs):
        yield b"event: token\ndata: {\"type\": \"token\", \"delta\": \"hello\"}\n\n"
        yield b"event: done\ndata: {\"type\": \"done\"}\n\n"

    monkeypatch.setattr(ep, "_event_stream_v2", _fake_stream)
    req = ep.LangGraphV2Request(input="hi", chat_id="default")
    stream = ep._event_stream_v2(req, user_id="test-user", tenant_id="tenant-1", is_privileged=True)
    text = _collect_stream(stream)

    assert "event: token" in text
    assert "event: done" in text


def test_chat_v2_sse_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    _auth(monkeypatch)
    ep = importlib.import_module("app.api.v1.endpoints.langgraph_v2")
    monkeypatch.setattr(ep, "upsert_conversation", lambda *args, **kwargs: None)

    async def _fake_stream(*_args, **_kwargs):
        yield b"event: error\ndata: {\"type\": \"error\", \"message\": \"internal_error\", \"request_id\": \"it-sse-2\"}\n\n"
        yield b"event: done\ndata: {\"type\": \"done\", \"request_id\": \"it-sse-2\"}\n\n"

    monkeypatch.setattr(ep, "_event_stream_v2", _fake_stream)
    req = ep.LangGraphV2Request(input="hi", chat_id="default")
    stream = ep._event_stream_v2(req, user_id="test-user", tenant_id="tenant-1", is_privileged=True)
    text = _collect_stream(stream)

    assert "event: error" in text
    assert "secret: do not leak this" not in text
    assert "request_id" in text

    error_payload = None
    for block in text.split("\n\n"):
        if "event: error" in block:
            for line in block.splitlines():
                if line.startswith("data: "):
                    error_payload = json.loads(line.replace("data: ", "", 1))
                    break
            break
    assert error_payload is not None
    assert error_payload.get("request_id") == "it-sse-2"
