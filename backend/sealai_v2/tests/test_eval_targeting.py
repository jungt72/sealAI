from __future__ import annotations

import asyncio

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.eval import harness
from sealai_v2.eval.cases import Case


def _case(case_id: str) -> Case:
    return Case(
        id=case_id,
        klass="targeted",
        input=f"input {case_id}",
        must_contain=(),
        must_catch="",
        must_avoid=(),
        primary_axes=(),
        hard_gates=(),
    )


def test_auxiliary_runner_executes_only_requested_case_ids(monkeypatch) -> None:
    cases = [_case("KEEP"), _case("SKIP")]
    seen: list[str] = []

    async def fake_run_unit(_pipeline, _judge_cfg, case, *_args, **_kwargs):
        seen.append(case.id)
        return case.id

    monkeypatch.setattr(harness, "load_calibration_cases", lambda: cases)
    monkeypatch.setattr(harness, "_run_unit", fake_run_unit)

    records, errors = asyncio.run(
        harness._run_calibration(
            object(),
            ModelConfig("judge"),
            case_ids=frozenset({"KEEP"}),
        )
    )

    assert records == ["KEEP"]
    assert errors == []
    assert seen == ["KEEP"]


def test_unknown_target_case_fails_before_client_or_model_setup(tmp_path) -> None:
    with pytest.raises(ValueError, match="unknown eval case ids"):
        asyncio.run(
            harness.run_eval(
                Settings(),
                run_dir=tmp_path,
                run_label="targeted",
                git_sha="test",
                timestamp="2026-07-12T00:00:00Z",
                case_ids=frozenset({"DOES-NOT-EXIST"}),
            )
        )
