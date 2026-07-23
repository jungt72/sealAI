"""Reproducible real-world routing and communication evaluation.

This eval complements the credibility REPLAY.  It measures whether differently
worded user turns reach the intended governed route, whether technical turns are
ever downgraded to a cheap route, whether ambiguous language is stable across
repeated live classifications, and whether the response obeys the deterministic
communication contract.

The runner deliberately uses the real configured pipeline and provider clients.
It never reads or prints credentials and refuses to run with a durable database or
Qdrant URL so an eval cannot mutate production case data.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sealai_v2.config.settings import Settings
from sealai_v2.core.communication_plan import (
    build_communication_plan,
    evaluate_communication,
)
from sealai_v2.core.contracts import SessionContext
from sealai_v2.llm.factory import build_client_factory
from sealai_v2.pipeline.pipeline import build_pipeline
from sealai_v2.pipeline.routing import (
    CHEAP_ROUTES,
    RouteName,
    classify_route_deterministic,
)
from sealai_v2.security.tenant import TenantContext

_DEFAULT_SUITE = (
    Path(__file__).resolve().parent / "seed_cases" / "routing_realworld_v1.json"
)
_VALID_ROUTES = frozenset(route.value for route in RouteName)
_REQUIRED_PROFILE_FLAGS = (
    "execution_policy_enabled",
    "route_optimization_enabled",
    "route_prompt_families_enabled",
    "semantic_router_enabled",
    "structured_answer_enabled",
    "knowledge_mode_enabled",
)


@dataclass(frozen=True)
class CaseSpec:
    id: str
    slice: str
    prompt: str
    expected_routes: tuple[str, ...]
    deterministic_expected_routes: tuple[str, ...]
    critical: bool
    holdout: bool
    repetitions: int
    max_questions: int
    must_contain_all: tuple[str, ...]
    forbidden_fragments: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class TurnSpec:
    id: str
    prompt: str
    expected_routes: tuple[str, ...]
    critical: bool
    max_questions: int
    must_carry: tuple[str, ...]
    forbidden_fragments: tuple[str, ...]


@dataclass(frozen=True)
class DialogueSpec:
    id: str
    slice: str
    holdout: bool
    turns: tuple[TurnSpec, ...]


@dataclass(frozen=True)
class Suite:
    schema_version: int
    name: str
    gates: dict[str, float]
    cases: tuple[CaseSpec, ...]
    dialogues: tuple[DialogueSpec, ...]


def _tuple_of_strings(value: Any, *, field: str, owner: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{owner}: {field} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _routes(value: Any, *, field: str, owner: str) -> tuple[str, ...]:
    routes = _tuple_of_strings(value, field=field, owner=owner)
    if not routes:
        raise ValueError(f"{owner}: {field} cannot be empty")
    unknown = sorted(set(routes) - _VALID_ROUTES)
    if unknown:
        raise ValueError(f"{owner}: unknown routes in {field}: {unknown}")
    return routes


def load_suite(path: Path | None = None) -> Suite:
    source = path or _DEFAULT_SUITE
    raw = json.loads(source.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("routing real-world suite requires schema_version=1")
    defaults = raw.get("slice_policies") or {}
    seen: set[str] = set()
    cases: list[CaseSpec] = []
    for item in raw.get("cases", []):
        cid = str(item.get("id", "")).strip()
        if not cid or cid in seen:
            raise ValueError(f"duplicate or empty case id: {cid!r}")
        seen.add(cid)
        slice_name = str(item.get("slice", "")).strip()
        policy = defaults.get(slice_name) or {}
        prompt = str(item.get("prompt", "")).strip()
        if not slice_name or not prompt:
            raise ValueError(f"{cid}: slice and prompt are required")
        expected = _routes(
            item.get("expected_routes"), field="expected_routes", owner=cid
        )
        deterministic_raw = item.get("deterministic_expected_routes")
        deterministic = (
            expected
            if deterministic_raw is None
            else _routes(
                deterministic_raw,
                field="deterministic_expected_routes",
                owner=cid,
            )
        )
        repetitions = int(item.get("repetitions", 1))
        if repetitions < 1 or repetitions > 5:
            raise ValueError(f"{cid}: repetitions must be between 1 and 5")
        max_questions = int(item.get("max_questions", policy.get("max_questions", 1)))
        if max_questions < 0 or max_questions > 3:
            raise ValueError(f"{cid}: max_questions must be between 0 and 3")
        cases.append(
            CaseSpec(
                id=cid,
                slice=slice_name,
                prompt=prompt,
                expected_routes=expected,
                deterministic_expected_routes=deterministic,
                critical=bool(item.get("critical", policy.get("critical", False))),
                holdout=bool(item.get("holdout", False)),
                repetitions=repetitions,
                max_questions=max_questions,
                must_contain_all=_tuple_of_strings(
                    item.get("must_contain_all", policy.get("must_contain_all", [])),
                    field="must_contain_all",
                    owner=cid,
                ),
                forbidden_fragments=_tuple_of_strings(
                    item.get(
                        "forbidden_fragments",
                        policy.get("forbidden_fragments", []),
                    ),
                    field="forbidden_fragments",
                    owner=cid,
                ),
                tags=_tuple_of_strings(item.get("tags", []), field="tags", owner=cid),
            )
        )

    dialogues: list[DialogueSpec] = []
    for item in raw.get("dialogues", []):
        did = str(item.get("id", "")).strip()
        if not did or did in seen:
            raise ValueError(f"duplicate or empty dialogue id: {did!r}")
        seen.add(did)
        turns: list[TurnSpec] = []
        for index, turn in enumerate(item.get("turns", []), start=1):
            tid = f"{did}-T{index:02d}"
            prompt = str(turn.get("prompt", "")).strip()
            if not prompt:
                raise ValueError(f"{tid}: prompt is required")
            turns.append(
                TurnSpec(
                    id=tid,
                    prompt=prompt,
                    expected_routes=_routes(
                        turn.get("expected_routes"),
                        field="expected_routes",
                        owner=tid,
                    ),
                    critical=bool(turn.get("critical", False)),
                    max_questions=int(turn.get("max_questions", 1)),
                    must_carry=_tuple_of_strings(
                        turn.get("must_carry", []), field="must_carry", owner=tid
                    ),
                    forbidden_fragments=_tuple_of_strings(
                        turn.get("forbidden_fragments", []),
                        field="forbidden_fragments",
                        owner=tid,
                    ),
                )
            )
        if len(turns) < 2:
            raise ValueError(f"{did}: a dialogue needs at least two turns")
        dialogues.append(
            DialogueSpec(
                id=did,
                slice=str(item.get("slice", "multi_turn")).strip() or "multi_turn",
                holdout=bool(item.get("holdout", False)),
                turns=tuple(turns),
            )
        )

    gates = raw.get("gates") or {}
    required_gates = {
        "route_case_accuracy_min",
        "critical_safety_min",
        "communication_min",
        "stability_min",
    }
    if set(gates) != required_gates:
        raise ValueError(f"gates must be exactly {sorted(required_gates)}")
    parsed_gates = {name: float(value) for name, value in gates.items()}
    if any(not 0.0 <= value <= 1.0 for value in parsed_gates.values()):
        raise ValueError("all gates must be within [0, 1]")
    if not cases:
        raise ValueError("routing real-world suite cannot be empty")
    return Suite(
        schema_version=1,
        name=str(raw.get("name", "routing-realworld-v1")),
        gates=parsed_gates,
        cases=tuple(cases),
        dialogues=tuple(dialogues),
    )


def _profile(settings: Settings) -> dict[str, Any]:
    return {
        "provider": settings.provider,
        "l1": [settings.l1_provider or settings.provider, settings.l1_model],
        "standard": [settings.standard_provider, settings.standard_model],
        "verifier": [
            settings.verifier_provider or settings.provider,
            settings.verifier_model,
        ],
        "helper": [
            settings.helper_provider or settings.provider,
            settings.helper_model,
        ],
        "router": [settings.router_provider, settings.router_model],
        "router_confidence_threshold": settings.router_confidence_threshold,
        "router_timeout_s": settings.router_timeout_s,
        "flags": {
            name: bool(getattr(settings, name)) for name in _REQUIRED_PROFILE_FLAGS
        },
        "data_isolation": {
            # Container exec overrides use an empty string to disable a service.
            # Treat falsy endpoints as absent, matching both the safety guard and
            # the pipeline factories that decide whether a connection is built.
            "database_absent": not bool(settings.database_url),
            "qdrant_absent": not bool(settings.qdrant_url),
            "retriever_backend": settings.retriever_backend,
        },
    }


def _assert_safe_profile(settings: Settings) -> None:
    disabled = [name for name in _REQUIRED_PROFILE_FLAGS if not getattr(settings, name)]
    if disabled:
        raise RuntimeError(
            f"required production routing flags are disabled: {disabled}"
        )
    if settings.database_url or settings.qdrant_url:
        raise RuntimeError(
            "real-world routing eval refuses durable database or Qdrant connections"
        )


def _release_identity() -> dict[str, Any]:
    path = Path("/etc/sealai/release-identity.json")
    if not path.exists():
        return {"git_sha": "unknown", "tree_hash": "unknown"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"git_sha": "unknown", "tree_hash": "unknown"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[index], 1)


def _case_blob(result: Any) -> str:
    case_state = getattr(result, "case_state", None)
    if case_state is None:
        return ""
    return " ".join(
        f"{field.key} {field.value or ''}" for field in case_state.fields
    ).casefold()


def _communication_check(
    *,
    prompt: str,
    result: Any,
    max_questions: int,
    must_contain_all: tuple[str, ...],
    forbidden_fragments: tuple[str, ...],
) -> tuple[bool, list[str]]:
    answer = result.answer.text
    case_state = result.case_state
    case_fields = ()
    missing_fields = ()
    conflicts = ()
    if case_state is not None:
        case_fields = tuple(field.key for field in case_state.fields)
        missing_fields = tuple(case_state.required_missing)
        conflicts = tuple(conflict.field_key for conflict in case_state.open_conflicts)
    plan = build_communication_plan(
        question=prompt,
        route_name=result.route_name or "unsupported_or_ambiguous",
        case_fields=case_fields,
        missing_fields=missing_fields,
        conflicts=conflicts,
    )
    violations = list(evaluate_communication(answer, plan).violations)
    if answer.count("?") > max_questions:
        violations.append("eval_question_budget_exceeded")
    folded = answer.casefold()
    for fragment in must_contain_all:
        if fragment.casefold() not in folded:
            violations.append(f"required_fragment_missing:{fragment}")
    for fragment in forbidden_fragments:
        if fragment.casefold() in folded:
            violations.append(f"forbidden_fragment_present:{fragment}")
    return not violations, violations


def _attempt_record(
    *,
    case_id: str,
    slice_name: str,
    holdout: bool,
    prompt: str,
    expected_routes: tuple[str, ...],
    critical: bool,
    repetition: int,
    result: Any,
    elapsed_ms: float,
    max_questions: int,
    must_contain_all: tuple[str, ...] = (),
    forbidden_fragments: tuple[str, ...] = (),
    must_carry: tuple[str, ...] = (),
) -> dict[str, Any]:
    actual_route = result.route_name or ""
    route_ok = actual_route in expected_routes
    communication_ok, communication_violations = _communication_check(
        prompt=prompt,
        result=result,
        max_questions=max_questions,
        must_contain_all=must_contain_all,
        forbidden_fragments=forbidden_fragments,
    )
    case_blob = _case_blob(result)
    carry_missing = [item for item in must_carry if item.casefold() not in case_blob]
    cheap_values = {route.value for route in CHEAP_ROUTES}
    critical_underroute = bool(
        critical
        and actual_route in cheap_values
        and actual_route not in expected_routes
    )
    turn_state = result.turn_state
    return {
        "id": case_id,
        "slice": slice_name,
        "holdout": holdout,
        "repetition": repetition,
        "prompt": prompt,
        "expected_routes": list(expected_routes),
        "actual_route": actual_route,
        "route_ok": route_ok,
        "critical": critical,
        "critical_underroute": critical_underroute,
        "communication_ok": communication_ok,
        "communication_violations": communication_violations,
        "carry_missing": carry_missing,
        "answer": result.answer.text,
        "question_count": result.answer.text.count("?"),
        "execution_class": turn_state.execution_class if turn_state else None,
        "model_tier": turn_state.model_tier if turn_state else None,
        "verification_mode": turn_state.verification_mode if turn_state else None,
        "grounded": bool(result.grounded),
        "cited": bool(result.cited),
        "latency_ms": round(elapsed_ms, 1),
        "error": None,
    }


def _error_record(
    *,
    case_id: str,
    slice_name: str,
    holdout: bool,
    prompt: str,
    expected_routes: tuple[str, ...],
    critical: bool,
    repetition: int,
    error: Exception,
    elapsed_ms: float,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "slice": slice_name,
        "holdout": holdout,
        "repetition": repetition,
        "prompt": prompt,
        "expected_routes": list(expected_routes),
        "actual_route": None,
        "route_ok": False,
        "critical": critical,
        "critical_underroute": critical,
        "communication_ok": False,
        "communication_violations": ["pipeline_error"],
        "carry_missing": [],
        "answer": "",
        "question_count": 0,
        "execution_class": None,
        "model_tier": None,
        "verification_mode": None,
        "grounded": False,
        "cited": False,
        "latency_ms": round(elapsed_ms, 1),
        "error": f"{type(error).__name__}: {error}",
    }


def _summarize(
    suite: Suite,
    deterministic: list[dict[str, Any]],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    case_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for attempt in attempts:
        case_groups[attempt["id"]].append(attempt)
    case_passes = {
        case_id: all(
            attempt["route_ok"]
            and attempt["communication_ok"]
            and not attempt["carry_missing"]
            and not attempt["error"]
            for attempt in group
        )
        for case_id, group in case_groups.items()
    }
    route_case_accuracy = (
        sum(case_passes.values()) / len(case_passes) if case_passes else 0.0
    )
    critical_attempts = [attempt for attempt in attempts if attempt["critical"]]
    critical_safety = (
        sum(
            not attempt["critical_underroute"] and not attempt["error"]
            for attempt in critical_attempts
        )
        / len(critical_attempts)
        if critical_attempts
        else 1.0
    )
    communication = (
        sum(
            attempt["communication_ok"] and not attempt["carry_missing"]
            for attempt in attempts
        )
        / len(attempts)
        if attempts
        else 0.0
    )
    repeated = [group for group in case_groups.values() if len(group) > 1]
    stability = (
        sum(
            len({attempt["actual_route"] for attempt in group}) == 1
            and not any(attempt["error"] for attempt in group)
            for group in repeated
        )
        / len(repeated)
        if repeated
        else 1.0
    )
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for attempt in attempts:
        expected = "|".join(attempt["expected_routes"])
        confusion[expected][attempt["actual_route"] or "ERROR"] += 1
    latencies = [attempt["latency_ms"] for attempt in attempts if not attempt["error"]]
    metrics = {
        "route_case_accuracy": round(route_case_accuracy, 4),
        "critical_safety": round(critical_safety, 4),
        "communication": round(communication, 4),
        "stability": round(stability, 4),
        "pipeline_errors": sum(bool(attempt["error"]) for attempt in attempts),
        "n_cases": len(case_groups),
        "n_attempts": len(attempts),
        "n_repeated_cases": len(repeated),
        "latency_ms": {
            "p50": round(statistics.median(latencies), 1) if latencies else None,
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 1) if latencies else None,
        },
    }
    gate_checks = {
        "route_case_accuracy": metrics["route_case_accuracy"]
        >= suite.gates["route_case_accuracy_min"],
        "critical_safety": metrics["critical_safety"]
        >= suite.gates["critical_safety_min"],
        "communication": metrics["communication"] >= suite.gates["communication_min"],
        "stability": metrics["stability"] >= suite.gates["stability_min"],
        "pipeline_errors": metrics["pipeline_errors"] == 0,
    }
    return {
        "metrics": metrics,
        "gates": suite.gates,
        "gate_checks": gate_checks,
        "go": all(gate_checks.values()),
        "failed_case_ids": sorted(
            case_id for case_id, passed in case_passes.items() if not passed
        ),
        "confusion_matrix": {
            expected: dict(sorted(actual.items()))
            for expected, actual in sorted(confusion.items())
        },
        "deterministic_preflight": {
            "n_cases": len(deterministic),
            "accuracy": round(
                sum(row["route_ok"] for row in deterministic) / len(deterministic),
                4,
            )
            if deterministic
            else None,
            "failed_case_ids": [
                row["id"] for row in deterministic if not row["route_ok"]
            ],
        },
    }


async def run_suite(suite: Suite, settings: Settings) -> dict[str, Any]:
    _assert_safe_profile(settings)
    pipeline = build_pipeline(settings, client_for=build_client_factory(settings))
    deterministic: list[dict[str, Any]] = []
    for case in suite.cases:
        decision = classify_route_deterministic(case.prompt)
        deterministic.append(
            {
                "id": case.id,
                "expected_routes": list(case.deterministic_expected_routes),
                "actual_route": decision.route.value,
                "route_ok": decision.route.value in case.deterministic_expected_routes,
                "reason": decision.reason,
                "forced_full_pipeline": decision.forced_full_pipeline,
                "signal_count": decision.deterministic_signal_count,
            }
        )

    attempts: list[dict[str, Any]] = []
    expected_attempts = sum(case.repetitions for case in suite.cases) + sum(
        len(dialogue.turns) for dialogue in suite.dialogues
    )

    def emit_progress() -> None:
        attempt = attempts[-1]
        print(
            json.dumps(
                {
                    "progress": f"{len(attempts)}/{expected_attempts}",
                    "id": attempt["id"],
                    "repetition": attempt["repetition"],
                    "actual_route": attempt["actual_route"],
                    "route_ok": attempt["route_ok"],
                    "communication_ok": attempt["communication_ok"],
                    "error": bool(attempt["error"]),
                    "latency_ms": attempt["latency_ms"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            flush=True,
        )

    for case in suite.cases:
        for repetition in range(1, case.repetitions + 1):
            started = time.perf_counter()
            try:
                result = await pipeline.run(
                    case.prompt,
                    tenant=TenantContext(f"rw-{case.id.casefold()}-{repetition:02d}"),
                )
                attempts.append(
                    _attempt_record(
                        case_id=case.id,
                        slice_name=case.slice,
                        holdout=case.holdout,
                        prompt=case.prompt,
                        expected_routes=case.expected_routes,
                        critical=case.critical,
                        repetition=repetition,
                        result=result,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                        max_questions=case.max_questions,
                        must_contain_all=case.must_contain_all,
                        forbidden_fragments=case.forbidden_fragments,
                    )
                )
            except Exception as error:  # noqa: BLE001 - errors are measured outcomes
                attempts.append(
                    _error_record(
                        case_id=case.id,
                        slice_name=case.slice,
                        holdout=case.holdout,
                        prompt=case.prompt,
                        expected_routes=case.expected_routes,
                        critical=case.critical,
                        repetition=repetition,
                        error=error,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                    )
                )
            emit_progress()

    for dialogue in suite.dialogues:
        tenant = TenantContext(f"rw-{dialogue.id.casefold()}")
        session = SessionContext(session_id=f"rw-{dialogue.id.casefold()}")
        for turn in dialogue.turns:
            started = time.perf_counter()
            try:
                result = await pipeline.run(
                    turn.prompt,
                    tenant=tenant,
                    session=session,
                )
                if pipeline.memory is not None:
                    await pipeline.flush_memory(
                        tenant_id=tenant.tenant_id, session_id=session.session_id
                    )
                attempts.append(
                    _attempt_record(
                        case_id=turn.id,
                        slice_name=dialogue.slice,
                        holdout=dialogue.holdout,
                        prompt=turn.prompt,
                        expected_routes=turn.expected_routes,
                        critical=turn.critical,
                        repetition=1,
                        result=result,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                        max_questions=turn.max_questions,
                        forbidden_fragments=turn.forbidden_fragments,
                        must_carry=turn.must_carry,
                    )
                )
            except Exception as error:  # noqa: BLE001 - errors are measured outcomes
                attempts.append(
                    _error_record(
                        case_id=turn.id,
                        slice_name=dialogue.slice,
                        holdout=dialogue.holdout,
                        prompt=turn.prompt,
                        expected_routes=turn.expected_routes,
                        critical=turn.critical,
                        repetition=1,
                        error=error,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                    )
                )
            emit_progress()

    return {
        "schema_version": 1,
        "suite": suite.name,
        "executed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release_identity": _release_identity(),
        "evaluated_source": {
            "pipeline_sha256": _sha256(
                Path(__file__).parents[1] / "pipeline" / "pipeline.py"
            ),
            "routing_sha256": _sha256(
                Path(__file__).parents[1] / "pipeline" / "routing.py"
            ),
            "semantic_router_sha256": _sha256(
                Path(__file__).parents[1] / "pipeline" / "semantic_router.py"
            ),
            "communication_plan_sha256": _sha256(
                Path(__file__).parents[1] / "core" / "communication_plan.py"
            ),
        },
        "runtime_profile": _profile(settings),
        "deterministic": deterministic,
        "attempts": attempts,
        "summary": _summarize(suite, deterministic, attempts),
    }


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    metrics = summary["metrics"]
    status = "GO" if summary["go"] else "NO-GO"
    lines = [
        f"# Routing Real-World Eval — {status}",
        "",
        f"- Suite: `{result['suite']}`",
        f"- Executed: `{result['executed_at']}`",
        f"- Release SHA: `{result['release_identity'].get('git_sha', 'unknown')}`",
        f"- Tree hash: `{result['release_identity'].get('tree_hash', 'unknown')}`",
        f"- Pipeline source SHA-256: `{result['evaluated_source']['pipeline_sha256']}`",
        f"- Routing source SHA-256: `{result['evaluated_source']['routing_sha256']}`",
        "- Semantic-router source SHA-256: "
        f"`{result['evaluated_source']['semantic_router_sha256']}`",
        "- Communication-plan source SHA-256: "
        f"`{result['evaluated_source']['communication_plan_sha256']}`",
        f"- Cases: {metrics['n_cases']} ({metrics['n_attempts']} attempts)",
        "",
        "## Gates",
        "",
        "| Gate | Measured | Required | Result |",
        "|---|---:|---:|---|",
    ]
    gate_rows = (
        (
            "Route case accuracy",
            metrics["route_case_accuracy"],
            summary["gates"]["route_case_accuracy_min"],
            summary["gate_checks"]["route_case_accuracy"],
        ),
        (
            "Critical safety",
            metrics["critical_safety"],
            summary["gates"]["critical_safety_min"],
            summary["gate_checks"]["critical_safety"],
        ),
        (
            "Communication",
            metrics["communication"],
            summary["gates"]["communication_min"],
            summary["gate_checks"]["communication"],
        ),
        (
            "Stability",
            metrics["stability"],
            summary["gates"]["stability_min"],
            summary["gate_checks"]["stability"],
        ),
    )
    for name, measured, required, passed in gate_rows:
        lines.append(
            f"| {name} | {measured:.4f} | {required:.4f} | "
            f"{'PASS' if passed else 'FAIL'} |"
        )
    lines.extend(
        [
            f"| Pipeline errors | {metrics['pipeline_errors']} | 0 | "
            f"{'PASS' if summary['gate_checks']['pipeline_errors'] else 'FAIL'} |",
            "",
            "## Latency",
            "",
            f"- p50: {metrics['latency_ms']['p50']} ms",
            f"- p95: {metrics['latency_ms']['p95']} ms",
            f"- max: {metrics['latency_ms']['max']} ms",
            "",
            "## Failures",
            "",
        ]
    )
    if summary["failed_case_ids"]:
        lines.extend(f"- `{case_id}`" for case_id in summary["failed_case_ids"])
    else:
        lines.append("- None")
    lines.extend(["", "## Confusion matrix", ""])
    for expected, actual in summary["confusion_matrix"].items():
        lines.append(f"- `{expected}` → `{actual}`")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the sealAI routing real-world evaluation"
    )
    parser.add_argument("--suite", type=Path, default=_DEFAULT_SUITE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    suite = load_suite(args.suite)
    settings = Settings()
    result = asyncio.run(run_suite(suite, settings))
    result["suite_sha256"] = _sha256(args.suite)
    result["runner_sha256"] = _sha256(Path(__file__))
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output / "report.md").write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result["summary"]["go"] else 2)


if __name__ == "__main__":
    main()
