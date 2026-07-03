"""P4a — POST /api/v2/chat/stream (SSE stage progress + the single gated result frame).

The doctrine pins live here:
- stage frames carry ONLY {stage, status} — never answer/question text, facts, tenant/session
  ids, or any PII (same bar as the P0 timing line);
- the ANSWER crosses the wire exactly once, as the complete gated /chat payload, after
  verify + cite;
- a pipeline failure surfaces as ONE fixed-message `error` frame (never exception detail);
- client disconnect cancels the in-flight pipeline task; silence produces keepalive comments.
"""

from __future__ import annotations

import asyncio

import json

from sealai_v2.api.sse import stream_frames
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.tests._apiutil import auth, make_client, make_pipeline
from sealai_v2.tests._fakes import FakeLlmClient

_ALLOWED_STAGES = {
    "recall",
    "understand",
    "ground",
    "compute",
    "generate",
    "verify",
    "cite",
}
_Q = "SENTINEL-FRAGE-123 Wie dichtet man?"


def _frames(raw: str) -> list[dict]:
    """Parse SSE text into [{event, data}] frames; keepalive comments are kept as event=None."""
    out = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        if block.startswith(":"):
            out.append({"event": None, "data": block})
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        out.append({"event": event, "data": data})
    return out


def _stream(client, body, token="tok-A") -> tuple[int, dict, str]:
    with client.stream(
        "POST", "/api/v2/chat/stream", json=body, headers=auth(token)
    ) as r:
        raw = "".join(r.iter_text())
        return r.status_code, dict(r.headers), raw


def test_stream_emits_stage_frames_then_exactly_one_result_and_sse_headers():
    client, _ = make_client(make_pipeline("SENTINEL-ANTWORT-XYZ"))
    status, headers, raw = _stream(client, {"message": _Q})
    assert status == 200
    assert headers["content-type"].startswith("text/event-stream")
    assert headers["x-accel-buffering"] == "no"
    assert headers["cache-control"] == "no-cache"
    frames = _frames(raw)
    stage_frames = [f for f in frames if f["event"] == "stage"]
    result_frames = [f for f in frames if f["event"] == "result"]
    assert len(result_frames) == 1
    assert frames[-1]["event"] == "result"  # the answer is the LAST frame
    assert [f["data"]["stage"] for f in stage_frames if f["data"]["status"] == "start"]
    for f in stage_frames:
        assert f["data"]["stage"] in _ALLOWED_STAGES
        assert f["data"]["status"] in {"start", "end"}


def test_doctrine_no_pii_or_content_in_any_pre_result_frame():
    client, _ = make_client(make_pipeline("SENTINEL-ANTWORT-XYZ"))
    _, _, raw = _stream(client, {"message": _Q})
    pre_result = raw.split("event: result", 1)[0]
    for sentinel in (
        "SENTINEL-FRAGE",  # question text
        "SENTINEL-ANTWORT",  # answer/draft text
        "tenant-A",  # tenant id (token tok-A → tenant-A)
        "sess-A",  # session id
        "user-A",  # subject
    ):
        assert sentinel not in pre_result
    for f in _frames(pre_result):
        if f["event"] == "stage":
            assert set(f["data"].keys()) == {"stage", "status"}  # nothing else, ever


def test_result_frame_equals_the_non_streaming_chat_payload():
    plain, _ = make_client(make_pipeline("Antwort A."))
    r = plain.post("/api/v2/chat", json={"message": _Q}, headers=auth("tok-A"))
    assert r.status_code == 200

    streamed, _ = make_client(make_pipeline("Antwort A."))  # fresh, identical pipeline
    _, _, raw = _stream(streamed, {"message": _Q})
    result = [f for f in _frames(raw) if f["event"] == "result"][0]
    assert result["data"] == r.json()


def test_pipeline_failure_yields_one_fixed_error_frame_and_no_result():
    class _Boom(FakeLlmClient):
        async def generate(self, *, system, user, model_config):
            raise RuntimeError("SENTINEL-EXCEPTION-DETAIL")

    boom = _Boom()
    pipeline = Pipeline(
        generator=L1Generator(boom, PromptAssembler(), ModelConfig("fake-l1")),
        client=boom,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
    )
    client, _ = make_client(pipeline)
    status, _, raw = _stream(client, {"message": _Q})
    assert status == 200  # transport opened; the failure is an in-stream event
    frames = _frames(raw)
    errors = [f for f in frames if f["event"] == "error"]
    assert len(errors) == 1
    assert not [f for f in frames if f["event"] == "result"]
    assert "SENTINEL-EXCEPTION-DETAIL" not in raw  # fixed message, never the exception
    assert errors[0]["data"]["message"]  # non-empty fixed text


def test_stream_case_id_targets_that_case_not_the_tokens_session():
    # "Fälle"-Sidebar Patch B: the case_id override works identically over SSE as over /chat.
    pipeline = make_pipeline("Antwort.")
    client, _ = make_client(pipeline)
    _stream(client, {"message": _Q, "case_id": "case-2"})
    assert pipeline.memory.history(tenant_id="tenant-A", session_id="case-2")
    assert pipeline.memory.history(tenant_id="tenant-A", session_id="sess-A") == ()


def test_stream_requires_auth_like_chat():
    client, _ = make_client()
    r = client.post("/api/v2/chat/stream", json={"message": _Q})
    assert r.status_code == 401


def test_disconnect_cancels_the_pipeline_task():
    async def main() -> bool:
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(asyncio.sleep(30))  # stands in for pipeline.run
        gen = stream_frames(queue, task, heartbeat_s=0.01)
        assert (await gen.__anext__()) == ": keepalive\n\n"  # stream is live
        await gen.aclose()  # client disconnect → Starlette closes the generator
        await asyncio.sleep(0)
        return task.cancelled()

    assert asyncio.run(main()) is True


def test_keepalive_comment_during_silent_stages_then_terminal_frame_closes():
    async def main() -> list[str]:
        queue: asyncio.Queue = asyncio.Queue()

        async def slow_pipeline():
            await asyncio.sleep(0.05)  # a long, silent gpt-5.1 stage
            queue.put_nowait(("result", {"answer": "ok"}))

        task = asyncio.create_task(slow_pipeline())
        return [frame async for frame in stream_frames(queue, task, heartbeat_s=0.01)]

    frames = asyncio.run(main())
    assert ": keepalive\n\n" in frames
    assert frames[-1].startswith("event: result\n")
