#!/usr/bin/env python3
"""Stage A measurement harness — per-route first_progress / latency / wall-clock.

Drives governed + knowledge turns IN-PROCESS via the FastAPI ``TestClient`` with a
stubbed auth user (no Keycloak), parses the final ``state_update`` SSE frame for the
server-side ``trace.first_progress_ms`` / ``trace.latency_ms`` that Stage A1 now
persists, and prints a per-route p50/p95 table.

This is the *shared* harness for the whole latency-hardening arc. Per the agreed
methodology (in-process TestClient now, authoritative prod Run-IDs at the end), the
authoritative 5-governed + 5-knowledge baseline / before-after table is produced by
running this INSIDE the deployed backend container at the final post-deploy step:

    docker exec -e PYTHONPATH=/app backend python scripts/perf/measure_turn_timing.py --runs 5

Locally it requires the backend deps (redis/qdrant) and will call the live LLM, so
do not run the full pass against prod LangSmith ad-hoc — use ``--dry-run`` to verify
wiring only.

Usage:
    PYTHONPATH=backend python scripts/perf/measure_turn_timing.py --dry-run
    PYTHONPATH=backend python scripts/perf/measure_turn_timing.py --runs 5 [--json]
"""

from __future__ import annotations

import argparse
import json
import time
from statistics import median
from typing import Any

# (label, message) — governed = concrete RWDR application facts; knowledge = no-case.
GOVERNED_TURNS: list[tuple[str, str]] = [
    (
        "engineering_case_update",
        "Wellendichtring 80mm Welle, Öl ISO VG 68, 1500 U/min, 80°C",
    ),
    ("engineering_case_update", "Medium ist jetzt Wasser-Glykol, Druck 0.5 bar"),
    ("engineering_case_update", "Die Welle dreht mit 3000 U/min, Durchmesser 120mm"),
    ("engineering_case_update", "Temperatur steigt auf 140°C im Dauerbetrieb"),
    (
        "engineering_case_update",
        "Wie ist die Umfangsgeschwindigkeit bei diesen Werten?",
    ),
]
KNOWLEDGE_TURNS: list[tuple[str, str]] = [
    ("knowledge", "Was ist FKM und wofür wird es bei Dichtungen verwendet?"),
    ("knowledge", "Worin unterscheiden sich NBR und EPDM?"),
    ("knowledge", "Was bedeutet die Shore-Härte bei Elastomeren?"),
    ("knowledge", "Wann nimmt man PTFE statt einem Elastomer?"),
    ("knowledge", "Erkläre die Rolle der Dichtlippe beim Radialwellendichtring."),
]


def _build_client():
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.services.auth.dependencies import RequestUser, get_current_request_user

    app = create_app()
    user = RequestUser(
        user_id="perf-user",
        username="perfuser",
        sub="perf-sub",
        roles=["user"],
        tenant_id="perf-tenant",
    )
    app.dependency_overrides[get_current_request_user] = lambda: user
    return TestClient(app)


def _final_state_update(sse_text: str) -> dict[str, Any] | None:
    """Return the last state_update payload from a raw SSE response body."""
    final: dict[str, Any] | None = None
    for block in sse_text.strip().split("\n\n"):
        line = block.strip()
        if not line.startswith("data: "):
            continue
        body = line[len("data: ") :]
        if body == "[DONE]":
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "state_update":
            final = payload
    return final


def _drive(client, session: str, message: str) -> dict[str, Any]:
    t0 = time.monotonic()
    resp = client.post(
        "/api/agent/chat/stream", json={"message": message, "session_id": session}
    )
    wall_ms = int((time.monotonic() - t0) * 1000)
    payload = _final_state_update(resp.text) or {}
    trace = payload.get("trace") or {}
    return {
        "status": resp.status_code,
        "wall_ms": wall_ms,
        "first_progress_ms": trace.get("first_progress_ms"),
        "latency_ms": trace.get("latency_ms"),
        "run_id": (payload.get("run_meta") or {}).get("run_id"),
    }


def _pct(values: list[int], q: float) -> int | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    idx = min(len(vals) - 1, int(round(q * (len(vals) - 1))))
    return vals[idx]


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_route: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_route.setdefault(r["route"], []).append(r)
    out = {}
    for route, rs in by_route.items():
        wall = [r["wall_ms"] for r in rs]
        fp = [r["first_progress_ms"] for r in rs]
        lat = [r["latency_ms"] for r in rs]
        out[route] = {
            "n": len(rs),
            "wall_p50": int(median(wall)) if wall else None,
            "wall_p95": _pct(wall, 0.95),
            "first_progress_p50": int(median([v for v in fp if v is not None]))
            if any(v is not None for v in fp)
            else None,
            "latency_p50": int(median([v for v in lat if v is not None]))
            if any(v is not None for v in lat)
            else None,
            "latency_p95": _pct(lat, 0.95),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=1, help="repeats per turn spec")
    ap.add_argument(
        "--dry-run", action="store_true", help="build wiring only, drive no turns"
    )
    ap.add_argument("--json", action="store_true", help="emit JSON summary")
    args = ap.parse_args()

    client = _build_client()
    if args.dry_run:
        print("wiring OK: app + stub-auth + TestClient constructed; no turns driven.")
        return 0

    specs = [("governed", r, m) for r, m in GOVERNED_TURNS] + [
        ("knowledge", r, m) for r, m in KNOWLEDGE_TURNS
    ]
    rows: list[dict[str, Any]] = []
    with client:  # triggers lifespan/startup
        for run in range(args.runs):
            for kind, route, message in specs:
                res = _drive(
                    client, session=f"perf-{kind}-{route}-{run}", message=message
                )
                res.update({"route": route, "kind": kind, "message": message})
                rows.append(res)
                print(
                    f"[{kind:9}] {route:26} wall={res['wall_ms']:>6}ms "
                    f"first_progress={res['first_progress_ms']} latency={res['latency_ms']} "
                    f"status={res['status']} run_id={res['run_id']}"
                )

    summary = _summarize(rows)
    if args.json:
        print(
            json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False)
        )
    else:
        print("\n=== per-route summary (p50/p95, ms) ===")
        for route, s in summary.items():
            print(
                f"{route:28} n={s['n']:>2} wall p50={s['wall_p50']} p95={s['wall_p95']} "
                f"| first_progress p50={s['first_progress_p50']} "
                f"| latency p50={s['latency_p50']} p95={s['latency_p95']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
