from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


PERCENT_RE = re.compile(r"(?<!\\d)(\\d{1,3})\\s*%")
FORBIDDEN_OVERCLAIM_RE = re.compile(r"\\b(garantiert|100%\\s*sicher)\\b", re.IGNORECASE)


@dataclass
class ScoreResult:
    total: int
    categories: Dict[str, int]
    gate_failures: List[str]


def _contains_any(haystack: str, needles: List[str]) -> List[str]:
    found: List[str] = []
    for needle in needles:
        if needle and needle in haystack:
            found.append(needle)
    return found


def _gate_percent_claims(answer: str) -> List[str]:
    if PERCENT_RE.search(answer):
        return ["G1: contains percentage claim (forbidden by default policy)"]
    return []


def _gate_overclaims(answer: str) -> List[str]:
    if FORBIDDEN_OVERCLAIM_RE.search(answer):
        return ["G5: contains guarantee/overclaim wording"]
    return []


def _gate_tool_hallucination(answer: str, requires_rag: bool) -> List[str]:
    # Heuristic: claiming to have used knowledge base / tools requires citations (or requires_rag).
    lowered = answer.lower()
    claims_tool = any(
        phrase in lowered
        for phrase in (
            "ich habe in der wissensdatenbank",
            "ich habe in qdrant",
            "ich habe recherchiert",
            "ich habe nachgeschlagen",
        )
    )
    has_sources = ("## quellen" in lowered) or ("quelle:" in lowered) or ("dokument:" in lowered)
    if claims_tool and not has_sources:
        return ["G2: tool/knowledge claim without sources"]
    if requires_rag and not has_sources:
        return ["RAG: requires_rag=true but no sources section/citations found"]
    if not requires_rag and ("dokument:" in lowered or "## quellen" in lowered):
        # Not a hard gate, but indicates potential discipline issue; keep as gate to enforce strictness.
        return ["Tool discipline: requires_rag=false but sources/citations present"]
    return []


def score_answer(prompt_case: Dict[str, Any], answer: str) -> ScoreResult:
    tool_exp = prompt_case.get("tool_expectations") or {}
    requires_rag = bool(tool_exp.get("requires_rag"))

    gate_failures: List[str] = []
    gate_failures.extend(_gate_percent_claims(answer))
    gate_failures.extend(_gate_overclaims(answer))
    gate_failures.extend(_gate_tool_hallucination(answer, requires_rag=requires_rag))

    must_not = prompt_case.get("must_not_contain") or []
    forbidden_hits = _contains_any(answer, must_not)
    if forbidden_hits:
        gate_failures.append(f"must_not_contain hit: {forbidden_hits}")

    expected_sections = prompt_case.get("expected_sections") or []
    lowered = answer.lower()
    missing_sections = [s for s in expected_sections if s and s.lower() not in lowered]

    # Simple 0–5 heuristics per category
    categories: Dict[str, int] = {}

    categories["UX/Structure"] = 5 if not missing_sections else max(0, 5 - min(5, len(missing_sections)))

    completeness_markers = ("fehlende", "bitte", "benötige")
    categories["Completeness"] = 5 if any(m in lowered for m in completeness_markers) else 3

    transparency_markers = ("annahmen", "unsicher", "grenze", "grenzen")
    categories["Transparency"] = 5 if any(m in lowered for m in transparency_markers) else 3

    actionability_markers = ("nächste schritte", "checkliste", "1)")
    categories["Actionability"] = 5 if any(m in lowered for m in actionability_markers) else 3

    categories["Tool Usage Discipline"] = 5 if not any("Tool discipline" in g for g in gate_failures) else 2

    categories["RAG Grounding"] = 5 if (requires_rag and ("## quellen" in lowered or "dokument:" in lowered)) else (3 if not requires_rag else 1)

    categories["Safety/Compliance"] = 5 if not gate_failures else 2

    # Correctness/Engineering Validity is not reliably auto-scored; keep conservative.
    categories["Correctness/Engineering Validity"] = 3

    total = sum(categories.values())
    return ScoreResult(total=total, categories=categories, gate_failures=gate_failures)


def _load_golden(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline heuristic scorer for SealAI answers.")
    parser.add_argument("--golden", type=Path, required=True, help="Path to golden_prompts.json")
    parser.add_argument("--answer-file", type=Path, required=True, help="Path to a text file containing the answer")
    parser.add_argument("--id", dest="case_id", required=True, help="Golden prompt id to score against")
    args = parser.parse_args(argv)

    golden = _load_golden(args.golden)
    case = next((c for c in golden if c.get("id") == args.case_id), None)
    if case is None:
        raise SystemExit(f"Unknown id: {args.case_id}")

    answer = args.answer_file.read_text(encoding="utf-8")
    result = score_answer(case, answer)

    print(f"id={args.case_id} total={result.total}")
    for k, v in sorted(result.categories.items()):
        print(f"{k}: {v}/5")
    if result.gate_failures:
        print("Gate failures:")
        for g in result.gate_failures:
            print(f"- {g}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

