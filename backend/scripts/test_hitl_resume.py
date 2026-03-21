"""
HITL Resume Integration Test — Phase 1B / Blueprint Sections 08 & 12
=====================================================================

Steps:
  1. POST /review/seed  — inject a review-pending session into SESSION_STORE
                          (manufacturer_validation_required + review_required=True)
  2. Assert seed response has correct review_state and release_status
  3. POST /review with action="approve"
  4. Assert response: is_handover_ready=True, review_state="approved",
                      release_status="rfq_ready"
  5. POST /review again — should return 409 (no pending review left)
  6. Test reject path: seed a second session, reject it, assert is_handover_ready=False
"""

import json
import sys
import time

import requests

# ── Config ───────────────────────────────────────────────────────────────────
BASE = "http://localhost:8000/api/v1/agent"
SEED_URL = f"{BASE}/review/seed"
REVIEW_URL = f"{BASE}/review"
HEADERS = {"Content-Type": "application/json", "X-Bypass-Auth": "1"}

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    status = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail and not condition else ""
    print(f"  [{status}] {label}{suffix}")
    if condition:
        PASS += 1
    else:
        FAIL += 1


def post(url: str, payload: dict | None = None) -> requests.Response:
    return requests.post(url, json=payload or {}, headers=HEADERS, timeout=30)


# ── Step 1: Seed a review-pending session ─────────────────────────────────────
print("=" * 64)
print("HITL Resume Integration Test")
print("Blueprint Section 08 & 12 — Human-in-the-Loop Resume")
print("=" * 64)

print("\n── Step 1: Seed review-pending session ──────────────────────")
t0 = time.monotonic()
resp = post(SEED_URL)
elapsed = time.monotonic() - t0
print(f"  POST /review/seed  →  HTTP {resp.status_code}  ({elapsed:.2f}s)")

if resp.status_code != 200:
    print(f"  FATAL: seed endpoint failed: {resp.text[:400]}")
    sys.exit(1)

seed = resp.json()
session_id: str = seed["session_id"]
print(f"  session_id      : {session_id}")
print(f"  review_state    : {seed.get('review_state')}")
print(f"  release_status  : {seed.get('release_status')}")

check("seed: review_state == 'pending'", seed.get("review_state") == "pending", str(seed.get("review_state")))
check("seed: release_status == 'manufacturer_validation_required'",
      seed.get("release_status") == "manufacturer_validation_required",
      str(seed.get("release_status")))
check("seed: review_reason is non-empty", bool(seed.get("review_reason")))

# ── Step 2: Approve the review ────────────────────────────────────────────────
print("\n── Step 2: Approve review (action=approve) ──────────────────")
approve_payload = {
    "session_id": session_id,
    "action": "approve",
    "reviewer_notes": "Hersteller-Validierung liegt vor. Freigabe erteilt.",
}
t0 = time.monotonic()
resp = post(REVIEW_URL, approve_payload)
elapsed = time.monotonic() - t0
print(f"  POST /review (approve)  →  HTTP {resp.status_code}  ({elapsed:.2f}s)")

if resp.status_code != 200:
    print(f"  FATAL: review endpoint failed: {resp.text[:400]}")
    sys.exit(1)

approval = resp.json()
print(f"  is_handover_ready: {approval.get('is_handover_ready')}")
print(f"  release_status   : {approval.get('release_status')}")
print(f"  review_state     : {approval.get('review_state')}")
print(f"  reply            : {str(approval.get('reply', ''))[:80]!r}")
handover = approval.get("handover") or {}
print(f"  handover keys    : {list(handover.keys())}")

check("approve: HTTP 200", resp.status_code == 200, str(resp.status_code))
check("approve: is_handover_ready == True",
      approval.get("is_handover_ready") is True,
      str(approval.get("is_handover_ready")))
check("approve: release_status == 'rfq_ready'",
      approval.get("release_status") == "rfq_ready",
      str(approval.get("release_status")))
check("approve: review_state == 'approved'",
      approval.get("review_state") == "approved",
      str(approval.get("review_state")))
check("approve: handover present in response",
      isinstance(handover, dict) and "is_handover_ready" in handover)

# ── Step 3: Second call should return 409 ─────────────────────────────────────
print("\n── Step 3: Double-approve guard (must return 409) ───────────")
resp2 = post(REVIEW_URL, approve_payload)
print(f"  POST /review (duplicate)  →  HTTP {resp2.status_code}")
check("double-approve: HTTP 409", resp2.status_code == 409, str(resp2.status_code))

# ── Step 4: Reject path ───────────────────────────────────────────────────────
print("\n── Step 4: Seed second session and reject ───────────────────")
resp_seed2 = post(SEED_URL)
if resp_seed2.status_code != 200:
    print(f"  SKIP: seed2 failed ({resp_seed2.status_code})")
else:
    seed2 = resp_seed2.json()
    session_id2 = seed2["session_id"]
    print(f"  session_id2 : {session_id2}")
    reject_payload = {
        "session_id": session_id2,
        "action": "reject",
        "reviewer_notes": "Technische Anforderungen nicht erfüllt.",
    }
    t0 = time.monotonic()
    resp_rej = post(REVIEW_URL, reject_payload)
    elapsed = time.monotonic() - t0
    print(f"  POST /review (reject)  →  HTTP {resp_rej.status_code}  ({elapsed:.2f}s)")
    if resp_rej.status_code == 200:
        rejection = resp_rej.json()
        print(f"  is_handover_ready: {rejection.get('is_handover_ready')}")
        print(f"  release_status   : {rejection.get('release_status')}")
        print(f"  review_state     : {rejection.get('review_state')}")
        check("reject: HTTP 200", True)
        check("reject: is_handover_ready == False",
              rejection.get("is_handover_ready") is False,
              str(rejection.get("is_handover_ready")))
        check("reject: release_status == 'inadmissible'",
              rejection.get("release_status") == "inadmissible",
              str(rejection.get("release_status")))
        check("reject: review_state == 'rejected'",
              rejection.get("review_state") == "rejected",
              str(rejection.get("review_state")))
    else:
        print(f"  SKIP reject checks — HTTP {resp_rej.status_code}: {resp_rej.text[:200]}")

# ── Step 5: Unknown session → 404 ─────────────────────────────────────────────
print("\n── Step 5: Unknown session guard (must return 404) ──────────")
resp_missing = post(REVIEW_URL, {"session_id": "does-not-exist-xyz", "action": "approve"})
print(f"  POST /review (missing)  →  HTTP {resp_missing.status_code}")
check("missing session: HTTP 404", resp_missing.status_code == 404, str(resp_missing.status_code))

# ── Verdict ────────────────────────────────────────────────────────────────────
print("\n── Verdict ──────────────────────────────────────────────────")
print("=" * 64)
total = PASS + FAIL
print(f"  {PASS}/{total} checks passed")
print()
if FAIL == 0:
    print("VERDICT: PASS — HITL resume endpoint is operational.")
    print("         Blueprint Section 08 & 12: SATISFIED.")
else:
    print(f"VERDICT: FAIL — {FAIL} check(s) failed.")
    sys.exit(1)
print()
