# SSE Contract (Ist-Zustand)

## Endpoint
- `POST /api/v1/langgraph/chat/v2` (FastAPI router `backend/app/api/v1/endpoints/langgraph_v2.py`)
- Response: `text/event-stream`

## Event Types and Payloads

### `token`
- When: incremental text chunks or fallback chunks from `final_text`.
- Payload:
  - `type`: "token"
  - `text`: string

### `state_update`
- When: graph emits new `values` and parameters changed (delta vs previous state).
- Payload fields (only non-`null` values are included):
  - `type`: "state_update"
  - `phase`: string
  - `last_node`: string
  - `awaiting_user_input`: boolean
  - `awaiting_user_confirmation`: boolean
  - `recommendation_ready`: boolean
  - `recommendation_go`: boolean
  - `coverage_score`: number
  - `coverage_gaps`: list/structure
  - `missing_params`: list/structure
  - `parameters`: object (current parameter snapshot)
  - `pending_action`: string
  - `confirm_checkpoint_id`: string
  - `parameter_meta`: object (only when user-provenance deltas exist)
    - Per-parameter entry: `{ "source": "user", "force_overwrite": true }`

### `checkpoint_required`
- When: confirmation checkpoint should be shown (confirm flow).
- Payload:
  - Emits the state’s `confirm_checkpoint` dict if present, otherwise a payload
    from `build_confirm_checkpoint_payload(...)`.
  - Fields depend on the state; includes action/checkpoint identifiers.

### `parameter_patch_ack`
- When: parameter patch endpoint applies LWW and broadcasts to all clients in the same user/chat scope.
- Payload:
  - `chat_id`: string
  - `patch`: object (sanitized patch fields)
  - `applied_fields`: list
  - `rejected_fields`: list of `{field, reason}`
  - `versions`: object (per-field int)
  - `updated_at`: object (per-field float epoch seconds)
  - `source`: "patch_endpoint"
  - `request_id`: string or null

### `resync_required`
- When: `Last-Event-ID` cannot be replayed from the in-memory buffer.
- Payload:
  - `reason`: "buffer_miss"

### `slow_client`
- When: per-connection queue drops events due to backpressure.
- Payload:
  - `reason`: "backpressure"

### `trace`
- When: only if `SEALAI_LG_TRACE=1`.
- Payload fields (all optional, only present when detected):
  - `type`: string (trace mode, e.g. "messages" or "values")
  - `node`: string
  - `phase`: string
  - `action`: string
  - `ts`: ISO-8601 UTC timestamp (added by `_emit_trace`)

### `error`
- When: stream producer throws or outer error.
- Payload:
  - `type`: "error"
  - `message`: "dependency_unavailable" or "internal_error"
  - `request_id`: string or null

### `done`
- When: end of stream (always emitted; also after `error`).
- Payload (normal run):
  - `type`: "done"
  - `chat_id`: string
  - `request_id`: string or null
  - `client_msg_id`: string or null
  - `phase`: string or null
  - `last_node`: string or null
  - `awaiting_confirmation`: boolean
  - `checkpoint_id`: string or null
- Payload (error/cancel paths):
  - `type`: "done"
  - `chat_id`: string
  - `request_id`: string or null
  - `client_msg_id`: string or null

## `event_id` Format
- Each SSE event (except keepalive comments) includes `id: {seq}`.
- `seq` is monotonically increasing per `(user_id, chat_id)`.

## Keepalive / Retry
- Keepalive: the stream sends comment frames `: keepalive` on 15s inactivity.
- Retry: the stream emits `retry: 3000` at connection start.

## Replay / Resume
- If `Last-Event-ID` is provided and found in the in-memory ring buffer, the server replays buffered events with `seq > Last-Event-ID` before live streaming.
- If the buffer does not contain the requested sequence, the server emits `resync_required` and continues live streaming.
## Replay Backend
- Default replay backend is in-memory. Set `SEALAI_SSE_REPLAY_BACKEND=redis` to enable Redis-backed replay (uses `sse:seq:{user_id}:{chat_id}` + `sse:buf:{user_id}:{chat_id}`).
- Redis replay uses `SEALAI_SSE_REPLAY_MAXLEN` and `SEALAI_SSE_REPLAY_TTL_SEC` for buffer size/TTL; fallback to memory if Redis is unavailable.

## Backpressure Policy
- Per-connection queues are bounded; when full, the server drops oldest queued events and emits `slow_client` (rate-limited).
