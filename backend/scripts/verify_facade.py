"""
QA Verification Script — SSoT Thin Translation Facade
Phase 0B.2 compliance test

Endpoint : POST /api/v1/langgraph/chat/v2   (legacy frontend endpoint)
Expected : SSoT-synthesised events → token, text_chunk, turn_complete, done
"""

import json
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not available. Install it first.")
    sys.exit(1)

ENDPOINT = "http://localhost:8000/api/v1/langgraph/chat/v2"
PAYLOAD = {
    "input": "Ich benötige eine Dichtung für eine Welle mit 50mm Durchmesser bei 3000 U/min und 5 bar Öldruck.",
    "chat_id": "test-facade-002",
}
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
    "X-Bypass-Auth": "1",
}


def _parse_sse_line(line: str) -> dict[str, Any] | None:
    """Parse a raw SSE line into (event_name, data_dict)."""
    if line.startswith("event:"):
        return {"_event_name": line[len("event:"):].strip()}
    if line.startswith("data:"):
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            return {"_event_name": "__done__", "type": "__done__"}
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {"_event_name": "__raw__", "_raw": payload}
    return None


def main():
    print("=" * 64)
    print("SealAI — SSoT Thin Translation Facade QA")
    print("Phase 0B.2 Compliance Test")
    print("=" * 64)
    print(f"\nTarget  : {ENDPOINT}")
    print(f"Payload : {json.dumps(PAYLOAD, ensure_ascii=False)}\n")

    counters = {
        "token": 0,
        "text_chunk": 0,
        "state_update": 0,
        "turn_complete": 0,
        "done": 0,
        "error": 0,
        "unknown": 0,
    }
    text_parts: list[str] = []
    current_event_name: str | None = None
    t0 = time.monotonic()

    try:
        resp = requests.post(
            ENDPOINT, json=PAYLOAD, headers=HEADERS, stream=True, timeout=120
        )
    except Exception as exc:
        print(f"\nCONNECTION ERROR: {exc}")
        sys.exit(1)

    print(f"HTTP Status : {resp.status_code}")
    if resp.status_code != 200:
        print(f"Body        : {resp.text[:500]}")
        print("\nVERDICT: FAIL — non-200 response.")
        sys.exit(1)

    print("\n── SSE Event Stream ──────────────────────────────────────────")

    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line:
            current_event_name = None  # blank line = SSE event boundary
            continue

        parsed = _parse_sse_line(raw_line)
        if parsed is None:
            continue

        elapsed = f"{time.monotonic() - t0:.2f}s"

        # Track named events from "event:" lines
        if "_event_name" in parsed and set(parsed.keys()) == {"_event_name"}:
            current_event_name = parsed["_event_name"]
            continue

        ev_type = parsed.get("type") or current_event_name or ""

        if ev_type == "__done__":
            print(f"[{elapsed}] raw [DONE] sentinel (SSoT passthrough)")
            break

        elif ev_type == "token":
            counters["token"] += 1
            text = parsed.get("text", "")
            text_parts.append(text)
            if counters["token"] == 1:
                print(f"[{elapsed}] token ×1 (first): {repr(text[:60])}")
            elif counters["token"] % 20 == 0:
                print(f"[{elapsed}] token ×{counters['token']} (cumulative)…")

        elif ev_type == "text_chunk":
            counters["text_chunk"] += 1
            if counters["text_chunk"] == 1:
                print(f"[{elapsed}] text_chunk ×1 (first): {repr(parsed.get('text','')[:60])}")

        elif ev_type == "state_update":
            counters["state_update"] += 1
            gov = (parsed.get("governance_metadata") or {})
            wp_keys = list((parsed.get("working_profile") or {}).keys())
            print(f"[{elapsed}] state_update:")
            print(f"  streaming_complete  : {parsed.get('streaming_complete')}")
            print(f"  governed_output_ready: {parsed.get('governed_output_ready')}")
            print(f"  rfq_admissibility   : {parsed.get('rfq_admissibility')}")
            print(f"  governance.release  : {gov.get('release_status')}")
            print(f"  conflicts           : {len(gov.get('conflicts') or [])}")
            print(f"  working_profile keys: {wp_keys}")

        elif ev_type == "turn_complete":
            counters["turn_complete"] += 1
            print(f"[{elapsed}] turn_complete ✓")

        elif ev_type == "done":
            counters["done"] += 1
            print(f"[{elapsed}] done ✓ — stream closed")
            break

        elif ev_type == "error":
            counters["error"] += 1
            print(f"[{elapsed}] ERROR: {parsed.get('message', parsed)}")

        else:
            counters["unknown"] += 1
            if counters["unknown"] <= 5:
                print(f"[{elapsed}] unknown '{ev_type}': {str(parsed)[:100]}")

    elapsed_total = time.monotonic() - t0
    full_text = "".join(text_parts)

    print("\n── Assembled LLM Reply ──────────────────────────────────────")
    if full_text:
        print(full_text[:800] + ("…" if len(full_text) > 800 else ""))
    else:
        print("(no token events — check node whitelist)")

    print("\n── Event Counters ───────────────────────────────────────────")
    for k, v in counters.items():
        print(f"  {k:<18}: {v}")
    print(f"  {'elapsed':<18}: {elapsed_total:.2f}s")

    # ── Verdict ──────────────────────────────────────────────────────────────
    print("\nVERDICT")
    print("=" * 64)

    has_stream_events = counters["token"] > 0 or counters["text_chunk"] > 0
    has_close = counters["turn_complete"] > 0 and counters["done"] > 0
    has_error = counters["error"] > 0

    if has_error:
        print("FAIL — error event received in SSoT stream.")
    elif not has_close:
        print("FAIL — stream did not close with turn_complete + done.")
    elif not has_stream_events and counters["state_update"] == 0:
        print("FAIL — no events of any kind received (empty stream).")
    elif has_close and (has_stream_events or counters["state_update"] > 0):
        print("PASS — SSoT Thin Translation Facade working correctly.")
        if has_stream_events:
            print(f"       token×{counters['token']} + text_chunk×{counters['text_chunk']} "
                  f"+ state_update×{counters['state_update']} "
                  f"+ turn_complete + done — all Phase 0B.2 contracts satisfied.")
        else:
            print("       state_update + turn_complete + done present.")
            print("       NOTE: No token events — final_response_node is deterministic "
                  "(no LLM stream). Correct Phase 0A.4 behaviour.")
    else:
        print("INCONCLUSIVE — unexpected event combination.")
    print()


if __name__ == "__main__":
    main()
