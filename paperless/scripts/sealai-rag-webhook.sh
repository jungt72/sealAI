#!/usr/bin/env sh
set -eu

document_id="${DOCUMENT_ID:-}"
if [ -z "$document_id" ]; then
  echo "sealai-rag-webhook: DOCUMENT_ID missing, skipping"
  exit 0
fi

webhook_url="${SEALAI_RAG_WEBHOOK_URL:-http://backend-v2:8001/internal/rag/ingest}"
webhook_token="${SEALAI_RAG_WEBHOOK_TOKEN:-${PAPERLESS_WEBHOOK_TOKEN:-}}"
if [ -z "$webhook_token" ]; then
  echo "sealai-rag-webhook: webhook token missing, skipping document ${document_id}"
  exit 0
fi

(
  python - "$webhook_url" "$webhook_token" "$document_id" <<'PY'
import json
import sys
import urllib.error
import urllib.request

url, token, document_id = sys.argv[1:4]
payload = json.dumps({"document_id": document_id}).encode("utf-8")
request = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "X-SeaLAI-Webhook-Token": token,
    },
    method="POST",
)
try:
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read(1000).decode("utf-8", errors="replace")
        print(f"sealai-rag-webhook: document={document_id} status={response.status} body={body}")
except urllib.error.HTTPError as exc:
    body = exc.read(1000).decode("utf-8", errors="replace")
    print(f"sealai-rag-webhook: document={document_id} http_error={exc.code} body={body}")
    raise
except Exception as exc:
    print(f"sealai-rag-webhook: document={document_id} error={type(exc).__name__}: {exc}")
    raise
PY
# Incident 2026-07-01: a leftover root-owned /tmp/sealai-rag-webhook.log (created by an earlier
# manual docker-exec test run as root) made the real consumer process (a different, non-root
# user) fail this redirect with 'Permission denied' -- which aborted the WHOLE backgrounded
# compound command, so the webhook was silently never sent. /dev/null is always writable
# regardless of which user runs this, so that class of failure cannot recur. Paperless itself
# already captures this script's own stdout/stderr (docker logs paperless); the actual
# ingestion result is logged authoritatively on the backend-v2 side.
) >/dev/null 2>&1 &

exit 0
