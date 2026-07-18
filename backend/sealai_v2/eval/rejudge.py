"""Retry only missing judge results from an existing eval artifact.

The subject answer is immutable input here: this module never builds a pipeline and therefore
cannot call L1, helper, verifier, retrieval or calculation stages. It only replaces failed judge
objects, recomputes rubric scores/summaries, and rewrites the report/worksheet atomically.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from pathlib import Path

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.eval import report
from sealai_v2.eval.cases import (
    Case,
    load_alternativen_cases,
    load_archetype_cases,
    load_beratungs_ux_cases,
    load_calibration_cases,
    load_cases,
    load_decode_cases,
    load_diagnose_cases,
    load_edge_cases,
    load_gegencheck_cases,
    load_injection_cases,
    load_loesungserarbeitung_cases,
)
from sealai_v2.eval.judge import JudgeResult, judge_answer
from sealai_v2.eval.judge_pacing import PacedLlmClient
from sealai_v2.eval.scorer import score_case, summarize_column
from sealai_v2.llm.factory import build_client_for


def _case_index() -> dict[str, Case]:
    suites = (
        load_cases(),
        load_edge_cases(),
        load_injection_cases(),
        load_archetype_cases(),
        load_calibration_cases(),
        load_beratungs_ux_cases(),
        load_loesungserarbeitung_cases(),
        load_gegencheck_cases(),
        load_diagnose_cases(),
        load_decode_cases(),
        load_alternativen_cases(),
    )
    index: dict[str, Case] = {}
    for suite in suites:
        for case in suite:
            if case.id in index:
                raise ValueError(f"duplicate eval case id: {case.id}")
            index[case.id] = case
    return index


def _judge_identity(manifest: dict) -> str | None:
    role = (manifest.get("roles") or {}).get("judge") or {}
    provider, model = role.get("provider"), role.get("model")
    return f"{provider}/{model}" if provider and model else None


def _judge_from_dict(raw: dict) -> JudgeResult:
    return JudgeResult(
        case_id=str(raw.get("case_id") or ""),
        column=str(raw.get("column") or ""),
        must_contain=list(raw.get("must_contain") or []),
        must_catch=dict(raw.get("must_catch") or {}),
        must_avoid=list(raw.get("must_avoid") or []),
        axes={str(k): str(v) for k, v in dict(raw.get("axes") or {}).items()},
        notes=str(raw.get("notes") or ""),
        raw=str(raw.get("raw") or ""),
        parse_ok=bool(raw.get("parse_ok") is True),
    )


async def rejudge_failed(
    run_dir: str | Path,
    settings: Settings,
    *,
    case_ids: frozenset[str] | None = None,
    judge_client=None,
    render_artifacts: bool = True,
) -> dict:
    run_path = Path(run_dir)
    results_path = run_path / "results.json"
    data = json.loads(results_path.read_text(encoding="utf-8"))
    if data.get("adjudication"):
        raise ValueError("cannot rejudge an already adjudicated run")

    manifest = data.get("manifest") or {}
    provider = settings.judge_provider or settings.provider
    configured_identity = f"{provider}/{settings.judge_model}"
    if _judge_identity(manifest) != configured_identity:
        raise ValueError(
            "judge identity mismatch: artifact="
            f"{_judge_identity(manifest)!r}, configured={configured_identity!r}"
        )

    cases = _case_index()
    records = list(data.get("records") or [])
    targets = [
        record
        for record in records
        if record.get("answer_text")
        and not record.get("error")
        and (
            record.get("judge_error")
            or not bool((record.get("judge") or {}).get("parse_ok") is True)
        )
        and (case_ids is None or record.get("case_id") in case_ids)
    ]
    if not targets:
        raise ValueError("no failed judge cells selected")

    unknown = sorted({str(record.get("case_id")) for record in targets} - set(cases))
    if unknown:
        raise ValueError(f"unknown eval case ids in artifact: {unknown}")

    client = judge_client
    if client is None:
        raw_client = build_client_for(
            settings,
            provider,
            max_retries=settings.eval_judge_max_retries,
        )
        client = PacedLlmClient(
            raw_client,
            max_concurrency=settings.eval_judge_concurrency,
            min_interval_s=settings.eval_judge_min_interval_s,
        )
    judge_cfg = ModelConfig(
        model=settings.judge_model,
        temperature=settings.judge_temperature,
        max_output_tokens=settings.eval_judge_max_output_tokens,
        cache_key="sealai-v2-judge",
        stage="judge",
        reasoning_effort=settings.eval_judge_reasoning_effort,
    )

    for record in targets:
        case = cases[str(record["case_id"])]
        judge = await judge_answer(
            client,
            judge_cfg,
            case,
            str(record["answer_text"]),
            str(record["column"]),
        )
        if not judge.parse_ok:
            raise ValueError(f"judge parse failed for {case.id}/{record['column']}")
        record["judge"] = dataclasses.asdict(judge)
        record["score"] = dataclasses.asdict(score_case(case, judge))
        record["judge_error"] = None

    columns = list(manifest.get("columns") or [])
    summaries = {}
    for column in columns:
        scores = []
        for record in records:
            if record.get("column") != column:
                continue
            case = cases.get(str(record.get("case_id")))
            if case is None:
                continue
            scores.append(score_case(case, _judge_from_dict(record.get("judge") or {})))
        summaries[column] = dataclasses.asdict(summarize_column(column, scores))
    data["summaries"] = summaries
    manifest["errors"] = [
        error
        for error in (manifest.get("errors") or [])
        if not str(error).startswith("judge::")
    ]
    manifest["rejudged_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["rejudged_cells"] = sorted(
        f"{record['case_id']}/{record['column']}" for record in targets
    )

    tmp = results_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(results_path)

    if render_artifacts:
        (run_path / "report.md").write_text(
            report._render_report(  # noqa: SLF001 - canonical renderer in the eval package
                manifest,
                summaries,
                records,
                multiturn=data.get("multiturn"),
                edge=data.get("edge"),
                injection=data.get("injection"),
                parametric=data.get("parametric"),
                archetype=data.get("archetype"),
            ),
            encoding="utf-8",
        )
        (run_path / "human_review_worksheet.md").write_text(
            report._render_worksheet(  # noqa: SLF001 - canonical renderer in the eval package
                manifest, records, multiturn=data.get("multiturn")
            ),
            encoding="utf-8",
        )
    return {
        "run_label": manifest.get("run_label"),
        "rejudged_cells": manifest["rejudged_cells"],
        "remaining_errors": manifest["errors"],
    }
