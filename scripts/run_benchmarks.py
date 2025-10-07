#!/usr/bin/env python3
"""Routing benchmark runner for the unified LangGraph stack."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

try:
    from app.langgraph.graph_chat import compile_chat_graph
except Exception as exc:  # pragma: no cover - script should fail fast in CI
    print(f"[bench] unable to import graph_chat: {exc}", file=sys.stderr)
    sys.exit(2)


def _load_entries(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for path in paths:
        if path.is_dir():
            for file in sorted(path.glob("*.yaml")):
                entries.extend(_read_yaml(file))
        else:
            entries.extend(_read_yaml(path))
    return entries


def _read_yaml(path: Path) -> List[Dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    prompts = data.get("prompts") or []
    results: List[Dict[str, Any]] = []
    for prompt in prompts:
        if not isinstance(prompt, dict):
            continue
        prompt.setdefault("source", str(path))
        results.append(prompt)
    return results


def _percentile(values: List[float], percent: float) -> float:
    if not values:
        return 0.0
    return statistics.quantiles(values, n=100, method="inclusive")[int(percent) - 1]


def run(dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    graph = compile_chat_graph()

    total = len(dataset)
    durations: List[float] = []
    correct_intent = 0
    correct_mode = 0
    rag_used = 0
    rag_violation = 0
    non_fallback = 0

    for entry in dataset:
        prompt = entry.get("prompt", "").strip()
        if not prompt:
            continue

        expected_agent = str(entry.get("expected_agent", "")).strip().lower()
        expected_mode = str(entry.get("expected_mode", "")).strip().lower()
        allow_rag = bool(entry.get("allow_rag", False))

        state = {
            "messages": [{"role": "user", "content": prompt}],
            "parameter_bag": {"items": entry.get("parameters", []) or []},
            "thread_id": f"bench:{entry.get('id', 'unknown')}",
            "user_id": "routing-bench",
        }

        start = time.perf_counter()
        result = graph.invoke(state)
        durations.append((time.perf_counter() - start) * 1000.0)

        final = result.get("final", {})
        classification = final.get("classification") or {}
        handoff = final.get("handoff") or {}

        predicted_agent = str(
            classification.get("intent")
            or classification.get("intent".upper())
            or handoff.get("agent")
            or ""
        ).lower()

        predicted_mode = str(classification.get("routing_modus") or "").lower()
        executed_agents = final.get("executed_agents") or []
        rag_involved = any(
            isinstance(agent, str) and "rag" in agent.lower() for agent in executed_agents
        )

        if predicted_agent == expected_agent:
            correct_intent += 1
        if predicted_mode == expected_mode:
            correct_mode += 1
        if predicted_mode != "fallback":
            non_fallback += 1
        if rag_involved:
            rag_used += 1
            if not allow_rag:
                rag_violation += 1

    accuracy = correct_intent / total if total else 0.0
    mode_accuracy = correct_mode / total if total else 0.0
    rag_rate = rag_used / total if total else 0.0
    rag_compliance = 1.0 - (rag_violation / total) if total else 0.0
    first_pass_rate = non_fallback / total if total else 0.0

    metrics = {
        "total": total,
        "accuracy": round(accuracy, 3),
        "mode_accuracy": round(mode_accuracy, 3),
        "rag_rate": round(rag_rate, 3),
        "rag_compliance": round(rag_compliance, 3),
        "first_pass_rate": round(first_pass_rate, 3),
        "latency_ms_avg": round(sum(durations) / total, 2) if total else 0.0,
        "latency_ms_p95": round(_percentile(durations, 95), 2) if total else 0.0,
    }

    metrics["targets"] = {
        "accuracy": "≥ 0.85",
        "rag_rate": "-30% vs. baseline (enforced via allow_rag)",
        "first_pass_rate": "≥ 0.70",
    }

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run routing benchmarks")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("benchmarks/routing")],
        help="Benchmark YAML files or directories",
    )
    parser.add_argument("--json", action="store_true", help="Emit metrics as JSON")
    args = parser.parse_args()

    dataset = _load_entries(args.paths)
    if not dataset:
        print("[bench] no prompts loaded", file=sys.stderr)
        sys.exit(1)

    metrics = run(dataset)
    if args.json:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    else:
        print("Routing Benchmarks")
        for key, value in metrics.items():
            if key == "targets":
                print("  targets:")
                for tk, tv in value.items():
                    print(f"    - {tk}: {tv}")
            else:
                print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
