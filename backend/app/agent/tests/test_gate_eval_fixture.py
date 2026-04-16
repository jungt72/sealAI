from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agent.runtime.gate import LLMGateResult, decide_route


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "gate_eval_cases.json"


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _session(zone: str) -> SimpleNamespace:
    return SimpleNamespace(session_zone=zone)


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


CASES = _load_cases()


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_gate_eval_fixture_cases(case: dict) -> None:
    session = _session(str(case["session_zone"]))
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

    assert decision.route == case["expected_route"], case["why"]
    assert decision.allow_direct_reply is bool(case["expected_allow_direct_reply"]), case["why"]
    if case["expected_allow_direct_reply"]:
        assert decision.direct_reply is not None, case["why"]
    else:
        assert decision.direct_reply is None, case["why"]


def test_gate_eval_fixture_has_broad_runtime_coverage() -> None:
    categories = {str(case["category"]) for case in CASES}
    assert len(CASES) >= 30
    assert {
        "A_conversation_clear",
        "B_conversation_exploration_boundary",
        "C_exploration_clear",
        "D_governed_clear",
        "E_sticky_follow_up",
        "F_fast_path_boundary",
    }.issubset(categories)


def test_gate_eval_fixture_has_fail_closed_cases() -> None:
    fail_closed = [case for case in CASES if case["expected_fail_closed_to_governed"]]
    assert fail_closed, "fixture must contain explicit fail-closed cases"
    assert any(case["expected_route"] == "GOVERNED" for case in fail_closed)
