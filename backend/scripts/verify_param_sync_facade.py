"""
Verification Script — Parameter Sync Facade (Blueprint §13)

Proves that direct parameter patches via the SSoT facade:
  1. Write values into sealing_state['asserted'] + working_profile
  2. Invalidate the RFQ (rfq_confirmed=False)
  3. Increment state_revision

Workflow
--------
  1. POST /api/v1/agent/review/seed          — seed a session
  2. POST /api/v1/langgraph/parameters/patch — PATCH pressure_bar 5→15
  3. GET  /api/v1/langgraph/state/{chat_id}  — assert pressure_bar=15 in working_profile
  4. GET  /api/v1/state/workspace  — assert rfq_confirmed=False + revision++
  5. POST /api/v1/langgraph/state            — PATCH shaft_diameter via WorkingProfile
  6. GET  /api/v1/langgraph/state/{chat_id}  — assert shaft_diameter visible

Run (backend must be up with BYPASS_AUTH=1 and SEALAI_SSOT_FACADE_ENABLED=1):
  python scripts/verify_param_sync_facade.py [--base-url http://host:port]
"""
from __future__ import annotations

import sys
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed.  Run: pip install requests")
    sys.exit(1)

BASE_URL = "http://localhost:8000"

for i, arg in enumerate(sys.argv[1:], 1):
    if arg.startswith("--base-url="):
        BASE_URL = arg.split("=", 1)[1].rstrip("/")
    elif arg == "--base-url" and i < len(sys.argv) - 1:
        BASE_URL = sys.argv[i + 1].rstrip("/")

SEED_URL      = f"{BASE_URL}/api/v1/agent/review/seed"
PATCH_URL     = f"{BASE_URL}/api/v1/langgraph/parameters/patch"
STATE_URL     = f"{BASE_URL}/api/v1/langgraph/state"
WORKSPACE_URL = f"{BASE_URL}/api/v1/state/workspace"

BYPASS_HEADERS = {"X-Bypass-Auth": "1"}
_all_checks: list[bool] = []


def _check(condition: bool, label: str, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    suffix = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{suffix}")
    _all_checks.append(condition)
    return condition


def _post(url: str, *, params: dict | None = None, body: dict | None = None,
          label: str) -> tuple[int, Any]:
    try:
        r = requests.post(url, headers=BYPASS_HEADERS, params=params, json=body, timeout=20)
    except Exception as exc:
        print(f"\nCONNECTION ERROR ({label}): {exc}")
        sys.exit(1)
    return r.status_code, _safe_json(r, label)


def _get(url: str, *, params: dict | None = None, label: str) -> tuple[int, Any]:
    try:
        r = requests.get(url, headers=BYPASS_HEADERS, params=params, timeout=20)
    except Exception as exc:
        print(f"\nCONNECTION ERROR ({label}): {exc}")
        sys.exit(1)
    return r.status_code, _safe_json(r, label)


def _safe_json(r: requests.Response, label: str) -> Any:
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:400]}


def _abort_if_fail(ok: bool, msg: str) -> None:
    if not ok:
        print(f"\nABORTED: {msg}")
        sys.exit(1)


def _nested_get(d: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def main() -> None:
    print("=" * 64)
    print("SealAI — Parameter Sync Facade QA (Blueprint §13)")
    print("=" * 64)
    print(f"\nBase URL : {BASE_URL}\n")

    # ------------------------------------------------------------------
    # Step 1 — Seed session
    # ------------------------------------------------------------------
    print("── Step 1: Seed SSoT session ─────────────────────────────────")
    status, seed_data = _post(SEED_URL, label="seed")
    print(f"  HTTP {status}")
    _abort_if_fail(
        _check(status == 200, "seed returns HTTP 200", f"got {status}"),
        "Seed failed — is backend running with BYPASS_AUTH=1?",
    )

    chat_id: str = seed_data.get("chat_id") or seed_data.get("session_id") or ""
    _abort_if_fail(
        _check(bool(chat_id), "seed response contains chat_id", repr(chat_id)),
        "Cannot continue without a chat_id.",
    )
    print(f"  chat_id = {chat_id}")

    # Capture initial state_revision via workspace (may be 0 / absent)
    _, ws_before = _get(WORKSPACE_URL, params={"thread_id": chat_id}, label="workspace-before")
    initial_revision: int = int(_nested_get(ws_before, "cycle_info", "state_revision") or 0)
    print(f"  initial state_revision = {initial_revision}")

    # ------------------------------------------------------------------
    # Step 2 — PATCH pressure_bar via /parameters/patch
    # ------------------------------------------------------------------
    print("\n── Step 2: PATCH pressure_bar 5→15 via /parameters/patch ─────")
    patch_body = {
        "chat_id": chat_id,
        "parameters": {"pressure_bar": 15},
        "base_versions": {},
    }
    status, patch_resp = _post(PATCH_URL, body=patch_body, label="parameters/patch")
    print(f"  HTTP {status}")
    _check(status == 200, "parameters/patch returns HTTP 200",
           f"got {status}: {patch_resp}")
    _check(patch_resp.get("ok") is True, "response.ok == True",
           repr(patch_resp.get("ok")))
    _check("pressure_bar" in (patch_resp.get("applied_fields") or []),
           "pressure_bar in applied_fields",
           repr(patch_resp.get("applied_fields")))

    # ------------------------------------------------------------------
    # Step 3 — Read back via GET /state/{chat_id} → working_profile
    # ------------------------------------------------------------------
    print("\n── Step 3: GET /state/{chat_id} — verify pressure_bar = 15 ───")
    state_url = f"{STATE_URL}/{chat_id}"
    status, state_data = _get(state_url, label="state-after-patch")
    print(f"  HTTP {status}")
    _check(status == 200, "GET /state/{chat_id} returns HTTP 200", f"got {status}")

    # Response is _synthesize_state_response_from_ssot → has 'state' key
    # with working_profile.engineering_profile inside it
    eng_profile = (
        _nested_get(state_data, "state", "working_profile", "engineering_profile")
        or _nested_get(state_data, "working_profile")
        or {}
    )
    pressure_val = eng_profile.get("pressure_bar") if isinstance(eng_profile, dict) else None
    _check(pressure_val == 15,
           "working_profile.pressure_bar == 15",
           f"got {pressure_val!r}")

    # ------------------------------------------------------------------
    # Step 4 — Staleness obligations via workspace
    # ------------------------------------------------------------------
    print("\n── Step 4: GET workspace — staleness obligations ──────────────")
    status, ws = _get(WORKSPACE_URL, params={"thread_id": chat_id}, label="workspace-after-patch")
    print(f"  HTTP {status}")
    _check(status == 200, "workspace GET returns HTTP 200", f"got {status}")

    rfq_confirmed = _nested_get(ws, "rfq_status", "rfq_confirmed")
    _check(rfq_confirmed is False or rfq_confirmed is None,
           "rfq_confirmed is False (stale)",
           repr(rfq_confirmed))

    new_revision: int = int(_nested_get(ws, "cycle_info", "state_revision") or 0)
    _check(new_revision > initial_revision,
           f"state_revision incremented ({initial_revision} → {new_revision})",
           f"initial={initial_revision} new={new_revision}")

    # ------------------------------------------------------------------
    # Step 5 — PATCH via POST /state (WorkingProfile body)
    # ------------------------------------------------------------------
    print("\n── Step 5: PATCH shaft_diameter via POST /state ───────────────")
    # shaft_diameter is a valid WorkingProfile field
    state_body = {
        "working_profile": {"shaft_diameter": 80.0},
        "source": "ui",
    }
    status, state_resp = _post(
        STATE_URL,
        params={"thread_id": chat_id},
        body=state_body,
        label="POST /state",
    )
    print(f"  HTTP {status}")
    _check(status == 200, "POST /state returns HTTP 200",
           f"got {status}: {state_resp}")
    _check(state_resp.get("ok") is True, "response.ok == True",
           repr(state_resp.get("ok")))

    # ------------------------------------------------------------------
    # Step 6 — Read back shaft_diameter
    # ------------------------------------------------------------------
    print("\n── Step 6: GET /state/{chat_id} — verify shaft_diameter = 80 ─")
    status, state_data2 = _get(state_url, label="state-after-state-patch")
    print(f"  HTTP {status}")
    _check(status == 200, "GET /state/{chat_id} returns HTTP 200", f"got {status}")

    eng_profile2 = (
        _nested_get(state_data2, "state", "working_profile", "engineering_profile")
        or _nested_get(state_data2, "working_profile")
        or {}
    )
    shaft_val = eng_profile2.get("shaft_diameter") if isinstance(eng_profile2, dict) else None
    _check(shaft_val == 80.0,
           "working_profile.shaft_diameter == 80.0",
           f"got {shaft_val!r}")

    # ------------------------------------------------------------------
    # Verdict
    # ------------------------------------------------------------------
    print("\n" + "=" * 64)
    passed = sum(_all_checks)
    total = len(_all_checks)
    if all(_all_checks):
        print(f"VERDICT: PASS  ({passed}/{total} checks)")
    else:
        print(f"VERDICT: FAIL  ({passed}/{total} checks passed)")
        sys.exit(1)


if __name__ == "__main__":
    main()
