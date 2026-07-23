from __future__ import annotations

import json
from pathlib import Path

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.eval.routing_realworld import (
    _profile,
    _summarize,
    load_suite,
    render_markdown,
)


def test_realworld_suite_is_large_unique_and_has_holdout_and_repetition() -> None:
    suite = load_suite()

    case_ids = [case.id for case in suite.cases]
    turn_ids = [turn.id for dialogue in suite.dialogues for turn in dialogue.turns]
    assert len(case_ids) >= 80
    assert len(turn_ids) >= 13
    assert len(case_ids + turn_ids) == len(set(case_ids + turn_ids))
    assert any(case.holdout for case in suite.cases)
    assert any(case.repetitions >= 3 for case in suite.cases)
    assert sum(case.critical for case in suite.cases) >= 35


def test_realworld_suite_rejects_duplicate_ids(tmp_path: Path) -> None:
    source = (
        Path(__file__).parents[1] / "eval" / "seed_cases" / "routing_realworld_v1.json"
    )
    raw = json.loads(source.read_text(encoding="utf-8"))
    raw["cases"][1]["id"] = raw["cases"][0]["id"]
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate or empty case id"):
        load_suite(invalid)


def _attempt(case_id: str, *, route_ok: bool = True, critical: bool = False) -> dict:
    return {
        "id": case_id,
        "slice": "test",
        "holdout": False,
        "repetition": 1,
        "expected_routes": ["engineering_case"],
        "actual_route": "engineering_case" if route_ok else "smalltalk_navigation",
        "route_ok": route_ok,
        "critical": critical,
        "critical_underroute": critical and not route_ok,
        "communication_ok": True,
        "communication_violations": [],
        "carry_missing": [],
        "latency_ms": 10.0,
        "error": None,
    }


def test_summary_fails_closed_on_one_critical_underroute() -> None:
    suite = load_suite()
    attempts = [
        _attempt("OK-1", critical=True),
        _attempt("BAD-1", route_ok=False, critical=True),
    ]

    summary = _summarize(suite, [], attempts)

    assert summary["metrics"]["critical_safety"] == 0.5
    assert summary["gate_checks"]["critical_safety"] is False
    assert summary["go"] is False
    assert summary["failed_case_ids"] == ["BAD-1"]


def test_markdown_reports_go_or_no_go() -> None:
    suite = load_suite()
    summary = _summarize(suite, [], [_attempt("OK-1", critical=True)])
    result = {
        "suite": suite.name,
        "executed_at": "2026-07-22T00:00:00Z",
        "release_identity": {"git_sha": "a" * 40, "tree_hash": "b" * 40},
        "evaluated_source": {
            "pipeline_sha256": "e" * 64,
            "routing_sha256": "c" * 64,
            "semantic_router_sha256": "d" * 64,
            "communication_plan_sha256": "f" * 64,
        },
        "summary": summary,
    }

    report = render_markdown(result)

    assert "Routing Real-World Eval — GO" in report
    assert "Critical safety" in report
    assert "Pipeline errors" in report
    assert "Routing source SHA-256" in report


def test_profile_treats_empty_connection_overrides_as_absent() -> None:
    profile = _profile(Settings(database_url="", qdrant_url=""))

    assert profile["data_isolation"]["database_absent"] is True
    assert profile["data_isolation"]["qdrant_absent"] is True
