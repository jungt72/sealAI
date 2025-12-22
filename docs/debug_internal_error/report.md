# Debug Internal Error Report

## Repro
- Command: `curl -k -N -sS https://localhost/api/chat -H "Authorization: Bearer $TOKEN" -H "Accept: text/event-stream" -H "Content-Type: application/json" --data "{\"input\":\"Ich brauche einen Radialwellendichtring für 40 mm Welle, Öl, 80 °C, 3000 rpm\",\"chat_id\":\"dbg-ui\",\"client_msg_id\":\"m1\"}"`
- Output (before): `{"detail":"Signature has expired."}`
- Artifact: `docs/debug_internal_error/live/repro_sse_before.txt`
- Blocker: Token rejected by backend (Signature expired), so SSE stream + request_id could not be captured yet.

## Root Cause
- Jinja StrictUndefined raised `UndefinedError: 'is_micro_smalltalk' is undefined` when rendering `final_answer_smalltalk_v2.j2` because the template context omitted `is_micro_smalltalk`. This exception was caught inside the SSE stream and surfaced as `internal_error`.
- The SSE stream handler swallowed exceptions without a traceback and without request context, so the client only saw `internal_error` while backend logs had no stacktrace.
- In MAI-DxO mode, invalid persisted state payloads (e.g., `open_questions`, `candidates`, `facts`) can raise Pydantic `ValidationError` during coercion and bubble up as `internal_error` without context.

## Fix
- Added `is_micro_smalltalk` to the final-answer template context and defaulted it in `_render_final_prompt_messages` to avoid StrictUndefined failures.
- Added `logger.exception` with request context (request_id, chat_id, client_msg_id, user_id, supervisor_mode) in the SSE stream producer and outer guard to surface real tracebacks.
- Always generate a `request_id` if missing; return it in response headers and in the SSE `error` payload.
- Defensive coercion for MAI-DxO state fields (`open_questions`, `candidates`, `facts`) to skip invalid persisted entries instead of crashing the stream.

## Why No Trace Was Visible Before
- `_event_stream_v2` caught all exceptions and only emitted `internal_error` without logging or request IDs, hiding the traceback and request scope from logs.

## Files Touched
- `backend/app/api/v1/endpoints/langgraph_v2.py`
- `backend/app/langgraph_v2/nodes/nodes_supervisor.py`
- `backend/app/langgraph_v2/sealai_graph_v2.py`
- `backend/tests/integration/test_langgraph_v2_sse.py`

## Tests
- `python3 -m compileall -q backend/app`
- `pytest backend/app/langgraph_v2/tests -q`

## Repro After Fix
- Output (after): `{"detail":"Signature has expired."}`
- Artifact: `docs/debug_internal_error/live/repro_sse_after.txt`
- Backend log excerpt: `docs/debug_internal_error/live/backend_logs_after.txt` (shows 401 Unauthorized due to expired signature)

## Next Evidence to Capture
- Run SSE repro again and store `docs/debug_internal_error/live/repro_sse_after.txt`.
- If an error persists, capture backend logs for the request_id into `docs/debug_internal_error/live/backend_logs_after.txt`.
