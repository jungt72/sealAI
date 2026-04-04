"""
Verification Script — SSoT State Facade (Blueprint §12)

Tests the GET /api/v1/langgraph/state/{chat_id} endpoint which the frontend
calls after an F5 page reload to rehydrate its UI state.

Workflow:
  1. POST /api/v1/agent/review/seed   — inject a review-pending session
  2. GET  /api/v1/langgraph/state/{chat_id}  — retrieve state via facade
  3. Assert HTTP 200 + working_profile contains the seeded parameters

Run:
  BYPASS_AUTH=1 python scripts/verify_state_facade.py
  (or add --base-url http://host:port to target a different server)
"""

import json
import sys
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed.  Run: pip install requests")
    sys.exit(1)

BASE_URL = "http://localhost:8000"

# Parse optional --base-url argument
for i, arg in enumerate(sys.argv[1:], 1):
    if arg.startswith("--base-url="):
        BASE_URL = arg.split("=", 1)[1].rstrip("/")
    elif arg == "--base-url" and i < len(sys.argv) - 1:
        BASE_URL = sys.argv[i + 1].rstrip("/")

SEED_URL = f"{BASE_URL}/api/v1/agent/review/seed"
STATE_URL_TEMPLATE = f"{BASE_URL}/api/v1/langgraph/state/{{chat_id}}"

BYPASS_HEADERS = {
    "X-Bypass-Auth": "1",
}


def _check(condition: bool, label: str, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{suffix}")
    return condition


def main() -> None:
    print("=" * 64)
    print("SealAI — SSoT State Facade QA (Blueprint §12)")
    print("=" * 64)
    print(f"\nBase URL : {BASE_URL}")
    print(f"Seed URL : {SEED_URL}\n")

    # ------------------------------------------------------------------
    # Step 1 — Seed a review-pending session via POST /review/seed
    # ------------------------------------------------------------------
    print("── Step 1: Seed SSoT session ─────────────────────────────────")
    try:
        seed_resp = requests.post(SEED_URL, headers=BYPASS_HEADERS, timeout=15)
    except Exception as exc:
        print(f"\nCONNECTION ERROR (seed): {exc}")
        print("Is the backend running?  BYPASS_AUTH=1 set in the server env?")
        sys.exit(1)

    print(f"  HTTP {seed_resp.status_code}")
    if seed_resp.status_code != 200:
        print(f"  Body: {seed_resp.text[:400]}")
        print("\nVERDICT: FAIL — seed endpoint returned non-200.")
        sys.exit(1)

    try:
        seed_data: dict[str, Any] = seed_resp.json()
    except Exception:
        print(f"  Body (non-JSON): {seed_resp.text[:400]}")
        print("\nVERDICT: FAIL — seed response is not JSON.")
        sys.exit(1)

    session_id: str = seed_data.get("session_id", "")
    review_state: str = seed_data.get("review_state", "")
    print(f"  session_id   : {session_id}")
    print(f"  review_state : {review_state}")

    seed_ok = _check(bool(session_id), "session_id present")
    _check(review_state == "pending", "review_state == 'pending'", review_state)
    if not seed_ok:
        print("\nVERDICT: FAIL — seed did not return a session_id.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 2 — Fetch state via GET /langgraph/state/{chat_id}
    # ------------------------------------------------------------------
    state_url = STATE_URL_TEMPLATE.format(chat_id=session_id)
    print(f"\n── Step 2: GET {state_url} ────────────────")
    try:
        state_resp = requests.get(state_url, headers=BYPASS_HEADERS, timeout=15)
    except Exception as exc:
        print(f"\nCONNECTION ERROR (state): {exc}")
        sys.exit(1)

    print(f"  HTTP {state_resp.status_code}")
    if state_resp.status_code == 404:
        print("  → 404 means the session was not found in SESSION_STORE.")
        print("    Check that SEALAI_SSOT_FACADE_ENABLED=1 and the seed")
        print("    endpoint and this endpoint share the same process.")
        print("\nVERDICT: FAIL — 404 from state endpoint.")
        sys.exit(1)

    if state_resp.status_code != 200:
        print(f"  Body: {state_resp.text[:400]}")
        print("\nVERDICT: FAIL — state endpoint returned non-200.")
        sys.exit(1)

    try:
        state_data: dict[str, Any] = state_resp.json()
    except Exception:
        print(f"  Body (non-JSON): {state_resp.text[:400]}")
        print("\nVERDICT: FAIL — state response is not JSON.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 3 — Assert response shape
    # ------------------------------------------------------------------
    print("\n── Step 3: Assert response fields ───────────────────────────")

    checks: list[bool] = []

    working_profile: dict[str, Any] = state_data.get("working_profile") or {}
    checks.append(_check(bool(working_profile), "working_profile present", str(list(working_profile.keys()))))

    expected_keys = {"shaft_diameter_mm", "rpm", "medium", "pressure_bar"}
    missing = expected_keys - set(working_profile.keys())
    checks.append(_check(not missing, "working_profile contains seeded params", f"missing={missing}"))

    gov_meta: dict[str, Any] = state_data.get("governance_metadata") or {}
    checks.append(_check(bool(gov_meta), "governance_metadata present"))
    checks.append(_check("release_status" in gov_meta, "governance_metadata.release_status present",
                          gov_meta.get("release_status")))

    checks.append(_check("rfq_admissibility" in state_data, "rfq_admissibility field present",
                          str(state_data.get("rfq_admissibility"))))

    state_inner: dict[str, Any] = state_data.get("state") or {}
    conv: dict[str, Any] = state_inner.get("conversation") or {}
    messages = conv.get("messages") or []
    checks.append(_check(len(messages) > 0, "messages list non-empty", f"{len(messages)} message(s)"))

    wp_inner: dict[str, Any] = (state_inner.get("working_profile") or {}).get("engineering_profile") or {}
    checks.append(_check(bool(wp_inner), "state.working_profile.engineering_profile present"))

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n── Payload preview ───────────────────────────────────────────")
    print(f"  working_profile keys  : {sorted(working_profile.keys())}")
    print(f"  rfq_admissibility     : {state_data.get('rfq_admissibility')}")
    print(f"  governance.release    : {gov_meta.get('release_status')}")
    print(f"  is_handover_ready     : {state_data.get('is_handover_ready')}")
    print(f"  messages count        : {len(messages)}")

    all_passed = all(checks)
    print("\nVERDICT")
    print("=" * 64)
    if all_passed:
        print("PASS — GET /state/{chat_id} correctly hydrates from SSoT SESSION_STORE.")
        print("       Frontend F5-reload will receive a valid working_profile.")
    else:
        failed = sum(1 for c in checks if not c)
        print(f"FAIL — {failed}/{len(checks)} checks failed.  See details above.")
    print()


if __name__ == "__main__":
    main()
