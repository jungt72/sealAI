"""
Verification Script — RFQ Facade Lifecycle (Blueprint §16)

Tests the full Confirm → Generate PDF → Handover flow through the
SSoT facade in state.py, without touching the LangGraph Postgres checkpointer.

Workflow:
  1. POST /api/v1/agent/review/seed    — inject rfq_ready session
  2. POST /api/v1/agent/review         — approve (sets release_status=rfq_ready)
  3. GET  /api/v1/state/workspace
                                       — assert rfq_package.has_draft=true
  4. POST /api/v1/state/workspace/rfq-confirm
                                       — assert rfq_confirmed=true
  5. POST /api/v1/state/workspace/rfq-generate-pdf
                                       — assert artifact_status.has_rfq_draft=true
                                         AND rfq_status.has_html_report=true
  6. GET  /api/v1/state/workspace/rfq-document
                                       — assert HTTP 200 + HTML body
  7. POST /api/v1/state/workspace/rfq-handover
                                       — assert rfq_status.handover_initiated=true

Run (backend must be up with BYPASS_AUTH=1 and SEALAI_SSOT_FACADE_ENABLED=1):
  python scripts/verify_rfq_facade.py [--base-url http://host:port]
"""
from __future__ import annotations

import json
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
REVIEW_URL    = f"{BASE_URL}/api/v1/agent/review"
WORKSPACE_URL = f"{BASE_URL}/api/v1/state/workspace"
CONFIRM_URL   = f"{BASE_URL}/api/v1/state/workspace/rfq-confirm"
GEN_PDF_URL   = f"{BASE_URL}/api/v1/state/workspace/rfq-generate-pdf"
DOCUMENT_URL  = f"{BASE_URL}/api/v1/state/workspace/rfq-document"
HANDOVER_URL  = f"{BASE_URL}/api/v1/state/workspace/rfq-handover"

BYPASS_HEADERS = {"X-Bypass-Auth": "1"}

# Track overall pass/fail
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
        r = requests.post(
            url, headers=BYPASS_HEADERS,
            params=params,
            json=body,
            timeout=20,
        )
    except Exception as exc:
        print(f"\nCONNECTION ERROR ({label}): {exc}")
        sys.exit(1)
    return r.status_code, _safe_json(r, label)


def _get(url: str, *, params: dict | None = None, label: str,
         accept_html: bool = False) -> tuple[int, Any]:
    headers = dict(BYPASS_HEADERS)
    if accept_html:
        headers["Accept"] = "text/html"
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
    except Exception as exc:
        print(f"\nCONNECTION ERROR ({label}): {exc}")
        sys.exit(1)
    if accept_html:
        return r.status_code, r.text
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


def main() -> None:
    print("=" * 68)
    print("SealAI — RFQ Facade Lifecycle QA  (Blueprint §16)")
    print("=" * 68)
    print(f"\nBase URL : {BASE_URL}\n")

    # ──────────────────────────────────────────────────────────────────────
    # Step 1 — Seed a session in rfq_ready state
    # ──────────────────────────────────────────────────────────────────────
    print("── Step 1: Seed SSoT session ────────────────────────────────────")
    status, data = _post(SEED_URL, label="seed")
    print(f"  HTTP {status}")
    _abort_if_fail(status == 200, f"Seed returned {status}: {data}")

    session_id: str = data.get("session_id", "")
    _check(bool(session_id), "session_id returned", session_id)
    _abort_if_fail(bool(session_id), "No session_id from seed — cannot continue.")
    print(f"  session_id: {session_id}")

    # ──────────────────────────────────────────────────────────────────────
    # Step 2 — Approve via HITL review (sets release_status=rfq_ready)
    # ──────────────────────────────────────────────────────────────────────
    print(f"\n── Step 2: Approve session {session_id} ─────────────────────────")
    status, data = _post(
        REVIEW_URL,
        body={"session_id": session_id, "action": "approve"},
        label="review/approve",
    )
    print(f"  HTTP {status}")
    if status not in (200, 409):  # 409 = already approved — still ok for testing
        print(f"  Body: {data}")
        _abort_if_fail(False, f"Review endpoint returned {status}")

    release_status: str = data.get("release_status", "?")
    _check(
        release_status == "rfq_ready" or status == 409,
        "release_status == rfq_ready after approve",
        release_status,
    )

    # ──────────────────────────────────────────────────────────────────────
    # Step 3 — GET workspace → has_draft should be true
    # ──────────────────────────────────────────────────────────────────────
    print(f"\n── Step 3: GET workspace projection ─────────────────────────────")
    status, ws = _get(WORKSPACE_URL, params={"thread_id": session_id}, label="workspace")
    print(f"  HTTP {status}")
    _check(status == 200, "GET workspace returns 200", str(status))
    if status == 200:
        has_draft = (ws.get("rfq_package") or {}).get("has_draft", False)
        gov_status = (ws.get("governance_status") or {}).get("release_status", "?")
        _check(has_draft, "rfq_package.has_draft == true", str(has_draft))
        _check(gov_status == "rfq_ready", "governance_status.release_status == rfq_ready", gov_status)
    else:
        print(f"  Body: {ws}")

    # ──────────────────────────────────────────────────────────────────────
    # Step 4 — POST rfq-confirm
    # ──────────────────────────────────────────────────────────────────────
    print(f"\n── Step 4: POST rfq-confirm ─────────────────────────────────────")
    status, ws = _post(CONFIRM_URL, params={"thread_id": session_id}, label="rfq-confirm")
    print(f"  HTTP {status}")
    _check(status == 200, "rfq-confirm returns 200", str(status))
    if status == 200:
        rfq_confirmed = (ws.get("rfq_status") or {}).get("rfq_confirmed", False)
        _check(rfq_confirmed, "rfq_status.rfq_confirmed == true", str(rfq_confirmed))
    elif status == 409:
        code = (ws.get("detail") or {}).get("code", "?")
        print(f"  → 409 conflict: {code}")
        print("    (Acceptable if session was pre-confirmed — continuing.)")
    else:
        print(f"  Body: {ws}")

    # ──────────────────────────────────────────────────────────────────────
    # Step 5 — POST rfq-generate-pdf
    # ──────────────────────────────────────────────────────────────────────
    print(f"\n── Step 5: POST rfq-generate-pdf ────────────────────────────────")
    status, ws = _post(GEN_PDF_URL, params={"thread_id": session_id}, label="rfq-generate-pdf")
    print(f"  HTTP {status}")
    _check(status == 200, "rfq-generate-pdf returns 200", str(status))
    if status == 200:
        has_html = (ws.get("rfq_status") or {}).get("has_html_report", False)
        has_doc  = (ws.get("artifact_status") or {}).get("has_rfq_draft", False)
        _check(has_html, "rfq_status.has_html_report == true", str(has_html))
        _check(has_doc,  "artifact_status.has_rfq_draft == true", str(has_doc))
    else:
        print(f"  Body: {ws}")

    # ──────────────────────────────────────────────────────────────────────
    # Step 6 — GET rfq-document (HTML download)
    # ──────────────────────────────────────────────────────────────────────
    print(f"\n── Step 6: GET rfq-document (HTML) ──────────────────────────────")
    status, html_body = _get(
        DOCUMENT_URL, params={"thread_id": session_id},
        label="rfq-document", accept_html=True,
    )
    print(f"  HTTP {status}")
    _check(status == 200, "rfq-document returns 200", str(status))
    if status == 200:
        is_html = isinstance(html_body, str) and "<html" in html_body.lower()
        _check(is_html, "response body contains HTML", f"len={len(html_body)}")
        if is_html:
            print(f"  HTML length   : {len(html_body)} bytes")
            print(f"  Title snippet : {html_body[html_body.lower().find('<title'):][:60]}...")
    else:
        print(f"  Body: {str(html_body)[:200]}")

    # ──────────────────────────────────────────────────────────────────────
    # Step 7 — POST rfq-handover
    # ──────────────────────────────────────────────────────────────────────
    print(f"\n── Step 7: POST rfq-handover ────────────────────────────────────")
    status, ws = _post(HANDOVER_URL, params={"thread_id": session_id}, label="rfq-handover")
    print(f"  HTTP {status}")
    _check(status == 200, "rfq-handover returns 200", str(status))
    if status == 200:
        initiated = (ws.get("rfq_status") or {}).get("handover_initiated", False)
        _check(initiated, "rfq_status.handover_initiated == true", str(initiated))
    elif status == 409:
        code = (ws.get("detail") or {}).get("code", "?")
        print(f"  → 409 conflict: {code}")
        if code == "handover_not_ready":
            print("  NOTE: handover_not_ready usually means rfq not confirmed + html not generated.")
            print("  Re-run after Steps 4+5 succeed end-to-end.")
        elif code == "handover_already_initiated":
            print("  (Acceptable — handover was already completed in a prior run.)")
    else:
        print(f"  Body: {ws}")

    # ──────────────────────────────────────────────────────────────────────
    # Step 8 — Double-confirm gate: rfq-confirm on already-confirmed session
    # ──────────────────────────────────────────────────────────────────────
    print(f"\n── Step 8: Gate check — re-confirm must return 409 ──────────────")
    status, ws = _post(CONFIRM_URL, params={"thread_id": session_id}, label="rfq-confirm-2nd")
    print(f"  HTTP {status}")
    code = (ws.get("detail") or {}).get("code", "?") if isinstance(ws, dict) else "?"
    _check(
        status == 409 and code == "rfq_already_confirmed",
        "second rfq-confirm blocked with rfq_already_confirmed",
        f"status={status} code={code}",
    )

    # ──────────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────────
    passed = sum(_all_checks)
    total  = len(_all_checks)
    failed = total - passed

    print()
    print("=" * 68)
    if failed == 0:
        print(f"VERDICT: ALL {total} CHECKS PASSED")
    else:
        print(f"VERDICT: {failed}/{total} CHECKS FAILED")
    print("=" * 68)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
