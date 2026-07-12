from __future__ import annotations

import asyncio
import json

import pytest

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import LlmResult
from sealai_v2.eval.rejudge import rejudge_failed


class _Judge:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        return LlmResult(
            text=json.dumps(
                {
                    "must_contain": [],
                    "must_catch": {"named": True, "evidence": "bounded"},
                    "must_avoid": [
                        {
                            "point": "pauschales 'ja, beständig' oder 'nein'",
                            "violated": False,
                        }
                    ],
                    "axes": {
                        "1": "human_required",
                        "2": "pass",
                        "3": "pass",
                        "5": "pass",
                    },
                    "notes": "ok",
                }
            ),
            model=kwargs["model_config"].model,
        )


def _artifact(tmp_path, settings: Settings):
    run = tmp_path / "run"
    run.mkdir()
    provider = settings.judge_provider or settings.provider
    data = {
        "manifest": {
            "run_label": "targeted",
            "columns": ["flags_on"],
            "roles": {"judge": {"provider": provider, "model": settings.judge_model}},
            "errors": [
                "judge::UNCERT-03/flags_on::RuntimeError: judge quota unavailable"
            ],
        },
        "summaries": {},
        "records": [
            {
                "case_id": "UNCERT-03",
                "column": "flags_on",
                "answer_text": "Keine belastbare Eignung ohne Konzentration und Temperatur.",
                "error": None,
                "judge_error": "RuntimeError: judge quota unavailable",
                "judge": {
                    "case_id": "UNCERT-03",
                    "column": "flags_on",
                    "parse_ok": False,
                },
                "score": {},
            }
        ],
    }
    (run / "results.json").write_text(json.dumps(data), encoding="utf-8")
    return run


def test_rejudge_reuses_stored_answer_and_clears_only_judge_error(tmp_path):
    settings = Settings()
    run = _artifact(tmp_path, settings)
    judge = _Judge()

    result = asyncio.run(
        rejudge_failed(run, settings, judge_client=judge, render_artifacts=False)
    )

    data = json.loads((run / "results.json").read_text(encoding="utf-8"))
    record = data["records"][0]
    assert judge.calls == 1
    assert record["answer_text"].startswith("Keine belastbare Eignung")
    assert record["judge_error"] is None
    assert record["judge"]["parse_ok"] is True
    assert record["score"]["provisional_gate_clean"] is True
    assert data["manifest"]["errors"] == []
    assert result["rejudged_cells"] == ["UNCERT-03/flags_on"]


def test_rejudge_refuses_model_or_provider_drift(tmp_path):
    settings = Settings()
    run = _artifact(tmp_path, settings)
    data = json.loads((run / "results.json").read_text(encoding="utf-8"))
    data["manifest"]["roles"]["judge"]["model"] = "different-judge"
    (run / "results.json").write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="judge identity mismatch"):
        asyncio.run(
            rejudge_failed(
                run,
                settings,
                judge_client=_Judge(),
                render_artifacts=False,
            )
        )
