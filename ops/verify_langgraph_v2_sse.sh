#!/usr/bin/env bash
set -euo pipefail

require() { command -v "$1" >/dev/null 2>&1 || { echo "missing command: $1" >&2; exit 2; }; }

require curl
require awk
require mktemp
require wc
require tr

if [[ -z "${BEARER_TOKEN:-}" ]]; then
  echo "BEARER_TOKEN is required (will not be printed)." >&2
  exit 2
fi
if [[ "${BEARER_TOKEN}" == "null" ]]; then
  echo "BEARER_TOKEN is \"null\". Hint: use jq -er '.access_token' to fail fast." >&2
  exit 2
fi
dot_only=${BEARER_TOKEN//[^.]/}
dot_count=${#dot_only}
if [[ "$dot_count" -ne 2 ]]; then
  echo "BEARER_TOKEN does not look like a JWT (dot_count=${dot_count})." >&2
  exit 2
fi

NGINX_BASE_URL="${NGINX_BASE_URL:-https://sealai.net}"
BACKEND_BASE_URL="${BACKEND_BASE_URL:-http://localhost:8000}"
MAX_EVENTS="${MAX_EVENTS:-5}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-25}"
CURL_INSECURE="${CURL_INSECURE:-}"

INPUT_TEXT="${INPUT_TEXT:-Streaming verify test}"
CHAT_ID="${CHAT_ID:-thread-verify-$(date +%s)}"
CLIENT_MSG_ID="${CLIENT_MSG_ID:-verify-$(date +%s)}"
export INPUT_TEXT CHAT_ID CLIENT_MSG_ID

format_data() {
  if command -v jq >/dev/null 2>&1; then
    echo "$1" | jq -c . 2>/dev/null || echo "$1"
  else
    echo "$1"
  fi
}

make_payload() {
  python3 - <<'PY'
import json, os
payload = {
  "input": os.environ.get("INPUT_TEXT", "Streaming verify test"),
  "chat_id": os.environ.get("CHAT_ID", "thread-verify"),
  "client_msg_id": os.environ.get("CLIENT_MSG_ID", "verify"),
}
print(json.dumps(payload, ensure_ascii=True))
PY
}

run_stream_test() {
  local label="$1"
  local url="$2"

  local tmpdir hdr timed cerr payload
  tmpdir=$(mktemp -d)
  hdr="$tmpdir/headers.txt"
  timed="$tmpdir/events.txt"
  cerr="$tmpdir/curl.err"

  payload=$(make_payload)

  echo "== ${label} =="
  echo "URL: ${url}"
  echo "chat_id: ${CHAT_ID}"

  local curl_opts=(-sS -N -D "$hdr" -H "Authorization: Bearer ${BEARER_TOKEN}" -H "Content-Type: application/json" -H "Accept: text/event-stream")
  if [[ -n "$CURL_INSECURE" ]]; then
    curl_opts+=(-k)
  fi

  set +e
  if command -v timeout >/dev/null 2>&1; then
    timeout "$TIMEOUT_SECONDS" curl "${curl_opts[@]}" -X POST "$url" --data "$payload" 2>"$cerr" \
      | awk -v max="$MAX_EVENTS" '
          /^data:/ {
            count++;
            now = systime();
            print now "\t" substr($0, 6);
            fflush();
            if (count >= max) exit 0;
          }
        ' > "$timed"
  else
    curl "${curl_opts[@]}" -X POST "$url" --data "$payload" 2>"$cerr" \
      | awk -v max="$MAX_EVENTS" '
          /^data:/ {
            count++;
            now = systime();
            print now "\t" substr($0, 6);
            fflush();
            if (count >= max) exit 0;
          }
        ' > "$timed"
  fi
  rc_curl=${PIPESTATUS[0]}
  set -e

  # rc=23 is expected when awk exits early (broken pipe). rc=28 is timeout (expected for SSE).
  if [[ "$rc_curl" -ne 0 && "$rc_curl" -ne 23 && "$rc_curl" -ne 28 ]]; then
    echo "curl failed (rc=$rc_curl)" >&2
    sed -n '1,120p' "$cerr" >&2 || true
    exit "$rc_curl"
  fi

  local status content_type cache_control connection accel
  status=$(head -n 1 "$hdr" | tr -d '\r' || true)
  content_type=$(grep -i '^content-type:' "$hdr" | tail -n 1 | tr -d '\r' || true)
  cache_control=$(grep -i '^cache-control:' "$hdr" | tail -n 1 | tr -d '\r' || true)
  connection=$(grep -i '^connection:' "$hdr" | tail -n 1 | tr -d '\r' || true)
  accel=$(grep -i '^x-accel-buffering:' "$hdr" | tail -n 1 | tr -d '\r' || true)

  echo "status: ${status:-<missing>}"
  echo "content-type: ${content_type:-<missing>}"
  echo "cache-control: ${cache_control:-<missing>}"
  echo "connection: ${connection:-<missing>}"
  echo "x-accel-buffering: ${accel:-<missing>}"

  local count incremental
  count=$(wc -l < "$timed" | tr -d ' ' || echo 0)
  if [[ "${count:-0}" -gt 0 ]]; then
    echo "events (first ${MAX_EVENTS} data frames):"
    while IFS=$'\t' read -r ts data; do
      [[ -n "${ts:-}" ]] || continue
      echo "  [${ts}] $(format_data "$data")"
    done < "$timed"
  else
    echo "events: <none>"
  fi

  incremental="no"
  if [[ "${count:-0}" -ge 2 ]]; then incremental="yes"; fi
  echo "incremental-data: ${incremental}"
  echo

  rm -rf "$tmpdir"
}

run_stream_test "nginx (/api/chat)" "${NGINX_BASE_URL%/}/api/chat"
run_stream_test "backend (/api/v1/langgraph/chat/v2)" "${BACKEND_BASE_URL%/}/api/v1/langgraph/chat/v2"
