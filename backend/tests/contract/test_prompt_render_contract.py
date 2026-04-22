from __future__ import annotations

from typing import Any, Dict

import pytest

pytest.skip('legacy LangGraph v2 prompt-render contract imports removed app.langgraph_v2; migrate to app.agent prompt/service contract tests', allow_module_level=True)


def _minimal_prompt_context() -> Dict[str, Any]:
    return {
        "user_input": "Welche Dichtung für Öl bei 80°C?",
        "latest_user_text": "Welche Dichtung für Öl bei 80°C?",
        "user_text": "Vergleiche NBR vs FKM für Öl bei 80°C.",
        "user_text_norm": "welche dichtung fuer oel bei 80c",
        "is_micro_smalltalk": False,
        "goal_descriptions": {
            "smalltalk": "Smalltalk",
            "design_recommendation": "Design recommendation",
            "explanation_or_comparison": "Comparison",
            "troubleshooting_leakage": "Troubleshooting",
            "out_of_scope": "Out of scope",
        },
        "summary": "User fragt nach Empfehlung.",
        "coverage": 0.5,
        "missing_text": "Druck; Wellendurchmesser",
        "parameters": {
            "medium": "öl",
            "temperature_C": 80,
            "pressure_bar": 5,
            "shaft_diameter": 50,
            "speed_rpm": 1200,
        },
        "calc_results": {
            "safety_factor": 1.5,
            "temperature_margin": 140,
            "pressure_margin": 195,
            "notes": ["dummy"],
        },
        "recommendation": {
            "material": "FKM",
            "profile": "Standard",
            "summary": "Vorläufige Empfehlung: FKM.",
            "rationale": "Temperaturreserve und Ölbeständigkeit.",
            "risk_hints": ["Grenzwerte verifizieren."],
        },
        "draft": "DRAFT: (placeholder)",
        "intent_goal": "design_recommendation",
        "coverage_score": 0.5,
        "coverage_gaps": ["pressure_bar", "shaft_diameter"],
        "coverage_gaps_text": "pressure_bar, shaft_diameter",
        "discovery_summary": "Kurz: Öl, 80°C, rotierend.",
        "discovery_missing": ["Druck", "Wellendurchmesser"],
        "discovery_coverage": 0.5,
        "application_category": "pumpe",
        "motion_type": "rotary",
        "seal_family": "radialwellendichtring",
        "plan": {"want_product_recommendation": False},
        "working_memory": {
            "knowledge_material": None,
            "knowledge_lifetime": None,
            "knowledge_generic": None,
            "frontdoor_reply": "Alles klar, ich helfe dir bei der Auswahl.",
        },
        "frontdoor_reply": "Alles klar, ich helfe dir bei der Auswahl.",
        "material_choice": {"material": "FKM"},
        "profile_choice": {"profile": "Standard"},
        "validation": {"status": "ok", "issues": []},
        "critical": {"status": "ok"},
        "products": {"manufacturer": None, "matches": [], "match_quality": None},
        "comparison_notes": {},
        "troubleshooting": {"symptoms": [], "hypotheses": [], "pattern_match": None, "done": False},
        "ask_missing_request": None,
        "response_kind": None,
        "response_text": "",
        "knowledge_material": None,
        "knowledge_lifetime": None,
        "knowledge_generic": None,
        "error": None,
        "pattern": "assembly_error",
        "symptoms": "Leckage nach 2 Wochen",
        "current_date": "Heute",
        "default_text": "Basis-Empfehlung: NBR für Standard-Anwendungen.",
        "standards_used": "ASTM/EN",
        "original_query": "dummy",
        "key_result": "dummy",
    }


@pytest.mark.parametrize(
    ("template_name", "assertions"),
    [
        ("frontdoor_discovery_prompt.jinja2", ["reinem, gültigem JSON-Format"]),
        ("discovery_summarize.j2", ['{"summary": str, "coverage": float, "missing": list[str]}']),
        ("confirm_gate.j2", ["SUMMARY:", "COVERAGE:", "MISSING:"]),
        ("material_comparison.j2", ["Vergleiche Materialien"]),
        ("leakage_troubleshooting.j2", ["Troubleshooting Spezialist"]),
        ("troubleshooting_explainer.j2", ["Fehlerbild:"]),
        ("response_router.j2", ["Status-Update:", "Live-Physik-Engine"]),
        ("final_answer_router.j2", ["## Annahmen & Randbedingungen", "## Technische Mechanismen"]),
        ("final_answer_discovery_v2.j2", ["Erste Einordnung (vorläufig):", "Top-Rückfragen (priorisiert):"]),
        ("final_answer_recommendation_v2.j2", ["TL;DR:", "Sicherheitsfaktor:"]),
        ("final_answer_smalltalk_v2.j2", ["Du bist SealAI, ein freundlicher technischer Gesprächspartner"]),
        ("final_answer_explanation_v2.j2", ["## Erklaerung / Vergleich"]),
        ("final_answer_troubleshooting_v2.j2", ["## Troubleshooting"]),
        ("final_answer_out_of_scope_v2.j2", ["## Hinweis"]),
        ("final_answer_v2.j2", ["Empfehlung zur Dichtungsauswahl", "1) Kurz-Zusammenfassung"]),
    ],
)
def test_all_audit_templates_render_without_undefined_errors(
    template_name: str, assertions: list[str]
) -> None:
    from app.langgraph_v2.utils.jinja import render_template

    text = render_template(template_name, _minimal_prompt_context())
    assert isinstance(text, str)
    assert text.strip(), f"{template_name} rendered empty output"
    for needle in assertions:
        assert needle in text, f"{template_name} output missing expected marker: {needle!r}"


def test_final_answer_router_does_not_emit_hardcoded_improvement_percentages() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    text = render_template("final_answer_router.j2", _minimal_prompt_context())
    assert "25%" not in text, "final_answer_router.j2 must not emit hard-coded '25%' claims"
    assert "30%" not in text, "final_answer_router.j2 must not emit hard-coded '30%' claims"


def test_final_answer_router_does_not_claim_rag_or_db_when_no_rag_artifacts() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    ctx = _minimal_prompt_context()
    ctx["comparison_notes"] = {}
    ctx["working_memory"] = dict(ctx.get("working_memory") or {})
    ctx["working_memory"]["comparison_notes"] = {"rag_context": None, "rag_reference": None}

    text = render_template("final_answer_router.j2", ctx)
    assert "RAG-basiert" not in text, "final_answer_router.j2 must not claim RAG usage without artifacts"
    assert "SealAI-DB" not in text, "final_answer_router.j2 must not claim DB usage without artifacts"


def test_discovery_and_smalltalk_templates_require_tldr_marker() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    ctx = _minimal_prompt_context()
    discovery = render_template("final_answer_discovery_v2.j2", ctx)
    smalltalk = render_template("final_answer_smalltalk_v2.j2", ctx)

    # We enforce an explicit TL;DR section marker (not just mentioning the word).
    assert "TL;DR:" in discovery or "## Kurz-Zusammenfassung" in discovery
    assert "TL;DR:" in smalltalk or "## Kurz-Zusammenfassung" in smalltalk


def test_smalltalk_micro_branch_is_short_and_not_technical() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    ctx = _minimal_prompt_context()
    ctx["latest_user_text"] = "Hallo"
    ctx["user_text_norm"] = "hallo"
    ctx["is_micro_smalltalk"] = True
    text = render_template("final_answer_smalltalk_v2.j2", ctx)

    assert "Womit kann ich dir helfen" in text
    assert "Medium" not in text
    assert "Temperatur" not in text
    assert "Druck" not in text


def test_smalltalk_non_micro_includes_light_context_and_draft() -> None:
    from app.langgraph_v2.utils.jinja import render_template

    ctx = _minimal_prompt_context()
    ctx["latest_user_text"] = "Kannst du mir bei einem Radialwellendichtring helfen?"
    ctx["user_text_norm"] = "kannst du mir bei einem radialwellendichtring helfen"
    ctx["is_micro_smalltalk"] = False
    text = render_template("final_answer_smalltalk_v2.j2", ctx)

    assert "Stell mir kurz den Kontext" in text
    assert "DRAFT" in text


def test_final_answer_router_must_not_claim_db_or_rag_without_citations() -> None:
    """
    Gate G2 enforceable: even if a RAG tool ran (rag_context present), the prompt must not
    claim DB/RAG usage unless there are citation-like artifacts (rag_reference).
    """
    from app.langgraph_v2.utils.jinja import render_template

    ctx = _minimal_prompt_context()
    ctx["comparison_notes"] = {"rag_context": "Tool ran but returned no usable sources.", "rag_reference": None}

    text = render_template("final_answer_router.j2", ctx)
    assert "SealAI-DB" not in text
    assert "RAG-basiert" not in text
    assert "bias-frei" not in text


def test_rag_support_node_does_not_hardcode_rag_reference_on_empty_or_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from langchain_core.messages import HumanMessage

    # Avoid circular import: load graph module first (defines log_state_debug),
    # then import nodes_flows (which imports log_state_debug from the graph module).
    from app.langgraph_v2 import sealai_graph_v2 as _graph  # noqa: F401
    from app.langgraph_v2.nodes import nodes_flows
    from app.langgraph_v2.state import SealAIState, WorkingMemory

    # Simulate a tool run that did not yield usable sources.
    class _DummyTool:
        @staticmethod
        def invoke(*_args: Any, **_kwargs: Any) -> str:
            return "Keine relevanten Informationen in der Wissensdatenbank gefunden."

    monkeypatch.setattr(nodes_flows, "search_knowledge_base", _DummyTool())

    state = SealAIState(
        user_id="u1",
        thread_id="t1",
        messages=[HumanMessage(content="Bitte mit Quellen aus der Wissensdatenbank.")],
        working_memory=WorkingMemory(comparison_notes={}),
    )

    out = nodes_flows.rag_support_node(state)
    wm = out.get("working_memory")
    assert wm is not None
    notes = getattr(wm, "comparison_notes", None) or {}
    assert not notes.get("rag_reference"), "rag_reference must be empty/None when no sources were extracted"
