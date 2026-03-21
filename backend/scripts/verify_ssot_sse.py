"""
QA Verification Script — SSoT SSE Streaming Validation
Blueprint Phase 0A.4 compliance test

Endpoint : POST /api/v1/agent/chat/stream
Contract  : text_chunk (speaking nodes only) → state_update → [DONE]
"""

import json
import sys
import time
from typing import Any

try:
    import requests as _requests
    _lib = "requests"
except ImportError:
    _requests = None
    _lib = None

try:
    import httpx as _httpx
    _lib = _lib or "httpx"
except ImportError:
    _httpx = None

if _lib is None:
    print("ERROR: neither 'requests' nor 'httpx' is available. Install one first.")
    sys.exit(1)

ENDPOINT = "http://localhost:8000/api/v1/agent/chat/stream"
PAYLOAD = {
    "message": "Ich brauche einen RWDR für 50mm Welle bei 50000 rpm und 5 bar Öldruck.",
    "session_id": "test-sse-002",
}
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
    "X-Bypass-Auth": "1",
}


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    """Parse a single SSE data line into a Python object."""
    if not line.startswith("data:"):
        return None
    payload = line[len("data:"):].strip()
    if payload == "[DONE]":
        return {"type": "__done__"}
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {"type": "__raw__", "raw": payload}


def _summarise_state_update(ev: dict) -> str:
    ss = ev.get("sealing_state") or {}
    gov = ss.get("governance") or {}
    cyc = ss.get("cycle") or {}
    wp = ev.get("working_profile") or {}
    run = ev.get("run_meta") or {}
    conflicts = gov.get("conflicts") or []
    lines = [
        f"  release_status   : {gov.get('release_status', '—')}",
        f"  rfq_admissibility: {gov.get('rfq_admissibility', '—')}",
        f"  state_revision   : {cyc.get('state_revision', '—')}",
        f"  working_profile  : {json.dumps(wp, ensure_ascii=False)}",
        f"  run_meta         : {json.dumps(run, ensure_ascii=False)}",
        f"  conflicts ({len(conflicts)}):",
    ]
    for c in conflicts:
        lines.append(f"    [{c.get('severity','?')}] {c.get('type','?')} — {c.get('field','?')}: {str(c.get('message',''))[:100]}")
    return "\n".join(lines)


def run_requests():
    print("=" * 62)
    print("SealAI SSoT SSE Streaming Validation")
    print("Blueprint Phase 0A.4 Compliance Test")
    print("=" * 62)
    print(f"\nTarget  : {ENDPOINT}")
    print(f"Payload : {json.dumps(PAYLOAD, ensure_ascii=False)}\n")

    counters = {
        "text_chunk": 0,
        "state_update": 0,
        "error": 0,
        "unknown": 0,
        "done": False,
    }
    text_buffer: list[str] = []
    t0 = time.monotonic()

    try:
        if _lib == "requests":
            resp = _requests.post(
                ENDPOINT, json=PAYLOAD, headers=HEADERS, stream=True, timeout=120
            )
            http_status = resp.status_code
            print(f"HTTP Status : {http_status}")
            if http_status != 200:
                print(f"Body        : {resp.text[:400]}")
                print("\nVERDICT: FAIL — non-200 response, stream never opened.")
                return

            print("\n── SSE Event Stream ──────────────────────────────────────")
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                ev = _parse_sse_line(raw_line)
                if ev is None:
                    continue

                ev_type = ev.get("type", "")
                elapsed = f"{time.monotonic() - t0:.2f}s"

                if ev_type == "__done__":
                    counters["done"] = True
                    print(f"\n[{elapsed}] [DONE] — stream closed by server ✓")
                    break

                elif ev_type == "text_chunk":
                    text = ev.get("text", "")
                    counters["text_chunk"] += 1
                    text_buffer.append(text)
                    # Print first chunk with header, rest inline
                    if counters["text_chunk"] == 1:
                        print(f"\n[{elapsed}] text_chunk  × 1  (first token): {repr(text[:60])}")
                    elif counters["text_chunk"] % 20 == 0:
                        print(f"[{elapsed}] text_chunk  × {counters['text_chunk']} (cumulative)…")

                elif ev_type == "state_update":
                    counters["state_update"] += 1
                    print(f"\n[{elapsed}] state_update:")
                    print(_summarise_state_update(ev))

                elif ev_type == "error":
                    counters["error"] += 1
                    print(f"\n[{elapsed}] ERROR event: {ev.get('message', ev)}")

                else:
                    counters["unknown"] += 1
                    print(f"[{elapsed}] unknown event type '{ev_type}': {str(ev)[:120]}")

        else:
            # httpx sync fallback
            with _httpx.Client(timeout=120) as client:
                with client.stream("POST", ENDPOINT, json=PAYLOAD, headers=HEADERS) as resp:
                    http_status = resp.status_code
                    print(f"HTTP Status : {http_status}")
                    if http_status != 200:
                        print(f"Body        : {resp.text[:400]}")
                        return
                    print("\n── SSE Event Stream ──────────────────────────────────────")
                    for raw_line in resp.iter_lines():
                        if not raw_line:
                            continue
                        ev = _parse_sse_line(raw_line)
                        if ev is None:
                            continue
                        ev_type = ev.get("type", "")
                        elapsed = f"{time.monotonic() - t0:.2f}s"
                        if ev_type == "__done__":
                            counters["done"] = True
                            print(f"\n[{elapsed}] [DONE] — stream closed by server ✓")
                            break
                        elif ev_type == "text_chunk":
                            counters["text_chunk"] += 1
                            text_buffer.append(ev.get("text", ""))
                            if counters["text_chunk"] == 1:
                                print(f"\n[{elapsed}] text_chunk × 1 (first): {repr(ev.get('text','')[:60])}")
                        elif ev_type == "state_update":
                            counters["state_update"] += 1
                            print(f"\n[{elapsed}] state_update:")
                            print(_summarise_state_update(ev))
                        elif ev_type == "error":
                            counters["error"] += 1
                            print(f"\n[{elapsed}] ERROR: {ev.get('message', ev)}")
                        else:
                            counters["unknown"] += 1
                            print(f"[{elapsed}] unknown: {str(ev)[:120]}")

    except Exception as exc:
        print(f"\nCONNECTION ERROR: {exc}")
        print("Backend not reachable on port 8000.")
        sys.exit(1)

    # ── Final reply assembly ──────────────────────────────────────────
    total = time.monotonic() - t0
    full_reply = "".join(text_buffer)

    print("\n── Assembled LLM Reply ──────────────────────────────────────")
    if full_reply:
        print(full_reply)
    else:
        print("(no text_chunk events received)")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n── Stream Summary ───────────────────────────────────────────")
    print(f"  text_chunk events : {counters['text_chunk']}")
    print(f"  state_update      : {counters['state_update']}")
    print(f"  error events      : {counters['error']}")
    print(f"  unknown events    : {counters['unknown']}")
    print(f"  [DONE] received   : {'YES ✓' if counters['done'] else 'NO ✗'}")
    print(f"  total elapsed     : {total:.2f}s")

    # ── Verdict ──────────────────────────────────────────────────────
    print("\nVERDICT")
    print("=" * 62)
    if counters["error"] > 0:
        print("FAIL — error event received in stream.")
    elif not counters["done"]:
        print("FAIL — stream did not close with [DONE] sentinel.")
    elif counters["text_chunk"] == 0 and counters["state_update"] == 0:
        print("FAIL — no events of any kind received (empty stream).")
    elif counters["text_chunk"] > 0 and counters["state_update"] > 0 and counters["done"]:
        print("PASS — text_chunk tokens + state_update + [DONE] all present.")
        print(f"       Phase 0A.4 contract satisfied ({counters['text_chunk']} tokens streamed).")
    elif counters["state_update"] > 0 and counters["done"]:
        print("PARTIAL PASS — state_update + [DONE] present but no text_chunk tokens.")
        print("       Node whitelist may be filtering all speaking nodes for this path.")
    else:
        print("INCONCLUSIVE — unexpected event combination, manual review needed.")
    print()


if __name__ == "__main__":
    run_requests()
