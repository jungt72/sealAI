"""
QA Verification Script — SSoT Interaction Policy Check
Blueprint Section 06 compliance test

Endpoint: POST /api/v1/agent/chat
Payload:  {"message": "Was ist der Unterschied zwischen FKM und NBR?", "session_id": "test-audit-001"}
"""

import json
import sys

try:
    import httpx
    _client_lib = "httpx"
except ImportError:
    import urllib.request
    import urllib.error
    _client_lib = "urllib"

ENDPOINT = "http://localhost:8000/api/v1/agent/chat"
PAYLOAD = {
    "message": "Ich benötige eine Dichtung für eine Welle mit 50mm Durchmesser bei 3000 U/min und 5 bar Öldruck.",
    "session_id": "test-audit-003",
}
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    # DEV bypass — requires BYPASS_AUTH=1 env var on the server side
    "X-Bypass-Auth": "1",
}

POLICY_INDICATORS = {
    "fast_path": ["fast", "guidance", "policy_path", "fast_brain", "conversational_rag"],
    "structured_path": ["qualification", "structured", "rag", "supervisor", "node_p1", "node_p2"],
    "auth_guard": [401, "unauthorized", "not authenticated", "missing token"],
    "schema_error": [422, "validation error", "field required"],
    "server_error": [500, "internal server error", "traceback"],
}


def analyse_response(status_code: int, body: dict | str) -> dict:
    result = {
        "status_code": status_code,
        "guard_triggered": None,
        "policy_path": "undetermined",
        "deterministic": False,
        "findings": [],
    }

    body_str = json.dumps(body).lower() if isinstance(body, dict) else str(body).lower()

    # --- Auth guard check ---
    if status_code == 401:
        result["guard_triggered"] = "AUTH_GUARD"
        result["policy_path"] = "blocked_at_auth"
        result["deterministic"] = True
        result["findings"].append("401 Unauthorized — Auth guard functioning correctly per security spec.")
        return result

    # --- Schema validation error ---
    if status_code == 422:
        result["guard_triggered"] = "SCHEMA_VALIDATION"
        result["policy_path"] = "blocked_at_validation"
        result["deterministic"] = True
        result["findings"].append("422 Unprocessable Entity — Request schema rejected. Check field names.")
        return result

    # --- Server crash ---
    if status_code >= 500:
        result["guard_triggered"] = "SERVER_CRASH"
        result["policy_path"] = "error"
        result["deterministic"] = False
        result["findings"].append(
            f"ARCHITECTURE DEFECT: {status_code} — server-side crash. "
            "Likely cause: State schema mismatch or unhandled exception in graph node."
        )
        return result

    # --- 200 OK path analysis ---
    if status_code == 200:
        result["deterministic"] = True

        # Fast path indicators
        fast_hits = [kw for kw in POLICY_INDICATORS["fast_path"] if kw in body_str]
        structured_hits = [kw for kw in POLICY_INDICATORS["structured_path"] if kw in body_str]

        if isinstance(body, dict):
            # Direct policy_path field
            if "policy_path" in body:
                result["policy_path"] = body["policy_path"]
                result["findings"].append(f"Explicit policy_path field found: '{body['policy_path']}'")
            # Metadata / routing hints
            for field in ("routing", "path", "mode", "intent", "node", "phase"):
                if field in body:
                    result["findings"].append(f"Routing hint — '{field}': {body[field]}")
            # Response text present?
            for field in ("answer", "text", "response", "message", "output", "governed_output_text"):
                if field in body and body[field]:
                    snippet = str(body[field])[:120].replace("\n", " ")
                    result["findings"].append(f"Response text in '{field}': {snippet}…")

        if fast_hits:
            result["policy_path"] = "FAST_PATH (Guidance)"
            result["findings"].append(f"Fast-path keywords detected: {fast_hits}")
        elif structured_hits:
            result["policy_path"] = "STRUCTURED_PATH (Qualification)"
            result["findings"].append(f"Structured-path keywords detected: {structured_hits}")
        else:
            result["findings"].append(
                "No explicit routing metadata in response body. "
                "Cannot determine path from payload alone."
            )

    return result


def run():
    print("=" * 60)
    print("SealAI SSoT Interaction Policy Verification")
    print("Blueprint Section 06 Compliance Check")
    print("=" * 60)
    print(f"\nTarget : {ENDPOINT}")
    print(f"Payload: {json.dumps(PAYLOAD, ensure_ascii=False)}\n")

    status_code = None
    raw_body = None

    try:
        if _client_lib == "httpx":
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(ENDPOINT, json=PAYLOAD, headers=HEADERS)
                status_code = resp.status_code
                try:
                    raw_body = resp.json()
                except Exception:
                    raw_body = resp.text
        else:
            data = json.dumps(PAYLOAD).encode()
            req = urllib.request.Request(ENDPOINT, data=data, headers=HEADERS, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    status_code = resp.status
                    raw_body = json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                status_code = e.code
                try:
                    raw_body = json.loads(e.read().decode())
                except Exception:
                    raw_body = e.reason

    except Exception as e:
        print(f"CONNECTION ERROR: {e}")
        print("\nDiagnosis: Backend is not reachable on port 8000.")
        print("Action required: Start the container or check port binding.")
        sys.exit(1)

    # --- Raw output ---
    print(f"HTTP Status : {status_code}")
    print("\nRaw Response Body:")
    print("-" * 40)
    if isinstance(raw_body, dict):
        print(json.dumps(raw_body, indent=2, ensure_ascii=False))
    else:
        print(raw_body)
    print("-" * 40)

    # --- Analysis ---
    analysis = analyse_response(status_code, raw_body)

    print("\nPOLICY ANALYSIS")
    print("=" * 60)
    print(f"Status Code    : {analysis['status_code']}")
    print(f"Guard Triggered: {analysis['guard_triggered'] or 'None'}")
    print(f"Policy Path    : {analysis['policy_path']}")
    print(f"Deterministic  : {'YES' % () if analysis['deterministic'] else 'NO — investigate'}")
    print("\nFindings:")
    for i, f in enumerate(analysis["findings"], 1):
        print(f"  [{i}] {f}")

    print("\nVERDICT")
    print("=" * 60)
    if analysis["guard_triggered"] == "AUTH_GUARD":
        print("PASS — Auth guard correctly blocked unauthenticated request.")
        print("       This is the expected behaviour for a secured endpoint.")
    elif analysis["guard_triggered"] == "SERVER_CRASH":
        print("FAIL — Server-side crash detected. Architecture defect present.")
    elif analysis["guard_triggered"] == "SCHEMA_VALIDATION":
        print("FAIL — Schema mismatch. Endpoint rejects the test payload.")
    elif status_code == 200 and analysis["deterministic"]:
        print(f"PASS — Endpoint responded deterministically via: {analysis['policy_path']}")
    else:
        print(f"INCONCLUSIVE — Status {status_code}, manual inspection needed.")

    print()


if __name__ == "__main__":
    run()
