from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.runtime.gate import LLMGateResult, decide_route

FIXTURE_PATH = ROOT / "app" / "agent" / "tests" / "fixtures" / "gate_eval_cases.json"


def _llm_result_from_case(case: dict) -> LLMGateResult | None:
    raw = case.get("llm_result")
    if not isinstance(raw, dict):
        return None
    return LLMGateResult(
        route=raw.get("route", "GOVERNED"),
        confidence=float(raw.get("confidence", 0.0)),
        parse_error=bool(raw.get("parse_error", False)),
        timeout=bool(raw.get("timeout", False)),
        allow_direct_reply=bool(raw.get("allow_direct_reply", False)),
        direct_reply=raw.get("direct_reply"),
        reason_code=str(raw.get("reason_code", "")),
    )


def main() -> int:
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    route_counter: Counter[str] = Counter()
    direct_reply_counter = 0
    failures: list[str] = []

    for case in cases:
        session = SimpleNamespace(session_zone=str(case["session_zone"]))
        llm_result = _llm_result_from_case(case)
        enable_direct_reply = bool(case.get("enable_direct_reply", False))

        if llm_result is None:
            with patch("app.agent.runtime.gate._ENABLE_GATE_DIRECT_REPLY", enable_direct_reply):
                decision = decide_route(str(case["input_text"]), session)
        else:
            with (
                patch("app.agent.runtime.gate._ENABLE_GATE_DIRECT_REPLY", enable_direct_reply),
                patch("app.agent.runtime.gate._call_gate_llm", return_value=llm_result),
            ):
                decision = decide_route(str(case["input_text"]), session)

        route_counter[decision.route] += 1
        if decision.allow_direct_reply:
            direct_reply_counter += 1

        if decision.route != case["expected_route"]:
            failures.append(f"{case['id']}: route={decision.route} expected={case['expected_route']}")
        if decision.allow_direct_reply != bool(case["expected_allow_direct_reply"]):
            failures.append(
                f"{case['id']}: allow_direct_reply={decision.allow_direct_reply} expected={case['expected_allow_direct_reply']}"
            )

    print(f"fixture={FIXTURE_PATH}")
    print(f"cases={len(cases)}")
    print(f"routes={dict(route_counter)}")
    print(f"direct_reply_cases={direct_reply_counter}")
    if failures:
        print("status=FAIL")
        for item in failures[:20]:
            print(item)
        return 1
    print("status=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
