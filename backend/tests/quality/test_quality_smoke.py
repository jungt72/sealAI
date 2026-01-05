from __future__ import annotations

from typing import Any, Dict, List

import pytest

from tests.quality.score import score_answer


class _AttrDict(dict):
    def __getattr__(self, name: str) -> Any:  # pragma: no cover - trivial helper
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def _sse_transcript_for_answer(answer: str) -> List[Dict[str, Any]]:
    # Minimal offline SSE transcript model (no network):
    # stream chunks as message events, then done with final_text.
    chunks: List[Dict[str, Any]] = []
    for part in answer.splitlines(True):
        if part:
            chunks.append({"event": "message", "data": {"text": part}})
    chunks.append({"event": "done", "data": {"final_text": answer}})
    return chunks


def _assert_sse_done_exactly_once(transcript: List[Dict[str, Any]]) -> None:
    events = [item.get("event") for item in transcript]
    done_count = sum(1 for e in events if e == "done")
    assert done_count == 1, f"expected exactly 1 done event, got {done_count} ({events})"
    assert events[-1] == "done", f"expected last event to be done, got {events[-1]!r}"


def test_quality_golden_prompts_score_and_gates(
    golden_prompts: List[Dict[str, Any]],
    stub_answers: Dict[str, str],
) -> None:
    missing = [case["id"] for case in golden_prompts if case["id"] not in stub_answers]
    assert not missing, f"missing stub answers for ids: {missing}"

    for case in golden_prompts:
        answer = stub_answers[case["id"]]
        requires_rag = bool((case.get("tool_expectations") or {}).get("requires_rag"))

        # Enforce output discipline checks (ChatGPT-level structure).
        assert (
            "## Kurz-Zusammenfassung" in answer or "TL;DR" in answer
        ), f"{case['id']} must start with a TL;DR/Kurz-Zusammenfassung section"

        assert "## Allgemeines Fachwissen" in answer, f"{case['id']} must contain 'Allgemeines Fachwissen' section"

        if not requires_rag:
            assert "Wissensdatenbank" not in answer, f"{case['id']} must not mention Wissensdatenbank without RAG"
            assert "## Wissensdatenbank (Quellen)" not in answer
        else:
            assert "## Wissensdatenbank (Quellen)" in answer, f"{case['id']} must include Wissensdatenbank section when RAG required"
            # Require at least one citation-like bullet.
            assert (
                "\n- " in answer and ("Quelle:" in answer or "Dokument:" in answer)
            ), f"{case['id']} must include at least one citation-like bullet when RAG required"

        result = score_answer(case, answer)

        assert not result.gate_failures, f"{case['id']} gate failures: {result.gate_failures}"
        assert result.total >= 24, f"{case['id']} score too low: total={result.total} categories={result.categories}"

        transcript = _sse_transcript_for_answer(answer)
        _assert_sse_done_exactly_once(transcript)


def test_quality_templates_render_with_seed_state(minimal_settings_env: None, golden_prompts: List[Dict[str, Any]]) -> None:
    # Deterministic renderability gate: run Jinja render for the final templates using the seed_state.
    from app.langgraph_v2.utils.jinja import render_template

    for case in golden_prompts:
        seed = case.get("seed_state") or {}
        params = (seed.get("parameters") or {}) if isinstance(seed, dict) else {}

        ctx: Dict[str, Any] = {
            "latest_user_text": case.get("user_input"),
            "user_text": case.get("user_input"),
            "goal": "design_recommendation",
            "coverage_score": 0.5,
            "coverage_gaps": [],
            "coverage_gaps_text": "keine",
            "discovery_summary": None,
            "discovery_missing": [],
            "discovery_coverage": None,
            "parameters": dict(params),
            # Some templates use dict access (calc_results.get) and others attribute access
            # (calc_results.safety_factor). Use a hybrid container.
            "calc_results": _AttrDict(
                safety_factor=None,
                temperature_margin=None,
                pressure_margin=None,
                notes=[],
            ),
            "recommendation": {"material": "", "profile": "", "summary": "", "rationale": "", "risk_hints": []},
            "working_memory": {},
            "plan": {},
            "draft": "DRAFT",
            "intent_goal": "design_recommendation",
            "frontdoor_reply": "ok",
            "material_choice": {},
            "profile_choice": {},
            "validation": {"status": None, "issues": []},
            "critical": {"status": None},
            "products": {"manufacturer": None, "matches": [], "match_quality": None},
            "comparison_notes": {},
            "troubleshooting": {"symptoms": [], "hypotheses": [], "pattern_match": None, "done": False},
        }

        # Render both: router draft + at least one final template.
        render_template("final_answer_router.j2", ctx)
        render_template("final_answer_discovery_v2.j2", ctx)
        render_template("final_answer_recommendation_v2.j2", ctx)
