"""Phase 2C (LangGraph-suitability audit) — the documented route-to-prompt-family matrix.

INACTIVE / READ-ONLY: nothing here is consumed by ``Pipeline.run()``. This module exists to make
the intended target architecture from the LangGraph-suitability audit's Section 10 explicit and
reviewable in code (not just prose), and to give a later activation phase (Phase 2D+) a single,
already-agreed-upon place to read from instead of re-deriving the mapping. Changing what this
table SAYS is a design decision; changing what the pipeline DOES with it is a separate, much later,
separately-reviewed step.

Nothing in ``pipeline/pipeline.py`` imports or reads this module today. The prompt-family/model/
rag/kernel/l3/streaming columns remain purely documentary INTENT. The four ``show_*`` display-flag
columns are the ONE exception that IS live: ``api/serializers.py::chat_response()`` reads them (via
:func:`plan_for`) to decide which render-only chat-UI sections a given classified route may show
(Technische Vorbewertung / Belege / …). They are render-only and never gate L1/L3/kernel/RAG.
"""

from __future__ import annotations

from dataclasses import dataclass

from sealai_v2.pipeline.routing import RouteName


@dataclass(frozen=True)
class RoutePromptPlan:
    route: RouteName
    prompt_family: str  # the assembler class name this route WOULD use, once activated
    model_class: str  # "cheapest" | "mid" | "strong" — an intent, not a pinned model id
    rag: bool
    kernel: bool
    l3: bool
    streaming: bool
    cache_strategy: str
    activation_status: str  # "inactive" (Phase 2C) | future: "shadow" | "active"
    # --- Render-only chat-UI display flags (LIVE, unlike the columns above) ------------------
    # These decide, per classified route, which optional chat-UI sections are ELIGIBLE to render.
    # Consumed by api/serializers.py::chat_response(); never gate L1/L3/kernel/RAG or any pipeline
    # behavior. Fixes the trust bug where "Technische Vorbewertung"/"Belege" showed on smalltalk.
    # the collapsed "Technische Vorbewertung" meta block
    show_technical_preassessment: bool = True
    # NOTE: show_evidence=True means "eligible to show the Belege/citations section IF real reviewed
    # citations exist" — it is ANDed with the existing non-empty-citations check, NOT a standalone
    # override. It never forces citations to appear when there are none.
    show_evidence: bool = True  # the "Belege" (citations) section
    show_calculations: bool = True  # calculation-derived sections
    show_rfq_sections: bool = True  # RFQ-manufacturer-brief-specific sections


# The 8 routes classify_route() can produce, each mapped to its intended target treatment. Every
# entry's `activation_status` is "inactive" in Phase 2C — this table documents INTENT, it does not
# grant it. Engineering/leakage/comparison/RFQ keep the exact current full-pipeline treatment
# (rag=kernel=l3=True, streaming=False — no unverified engineering content ever streams) even in
# this table, because Phase 2C changes nothing about them.
ROUTE_PROMPT_MATRIX: tuple[RoutePromptPlan, ...] = (
    RoutePromptPlan(
        route=RouteName.SMALLTALK_NAVIGATION,
        prompt_family="SmalltalkNavigationPromptAssembler",
        model_class="cheapest",
        rag=False,
        kernel=False,
        l3=False,
        # Phase 3A: the ONE route that streams (smalltalk-only token streaming). Documentary INTENT
        # like every other column here; the ACTUAL gate is settings.smalltalk_token_streaming_enabled
        # + the smalltalk_prompt_active boolean in pipeline.py, never this field. Every other row's
        # `streaming` stays False -- no unverified engineering content ever streams.
        streaming=True,
        cache_strategy="static-hash (build_prompt_cache_key)",
        activation_status="inactive",
        # smalltalk/navigation: no technical UI sections at all — the core of the trust-bug fix.
        show_technical_preassessment=False,
        show_evidence=False,
        show_calculations=False,
        show_rfq_sections=False,
    ),
    RoutePromptPlan(
        route=RouteName.GENERAL_SEALING_KNOWLEDGE,
        prompt_family="GeneralKnowledgePromptAssembler",
        model_class="mid",
        rag=True,
        kernel=False,
        # L3 stays True here even in the DOCUMENTED target plan: Phase 2B's own stress-test
        # finding (real eval questions under-detected by keyword signals, incl. injection
        # fixtures) is why this route does not yet get an L3 exemption anywhere, on paper or in
        # code — see pipeline/pipeline.py's skip_l3_for_route (smalltalk_navigation-only).
        l3=True,
        streaming=False,
        cache_strategy="static-hash (build_prompt_cache_key)",
        activation_status="inactive",
        # knowledge Q&A: citations if any exist, but no pre-assessment / calc / RFQ scaffolding.
        show_technical_preassessment=False,
        show_evidence=True,
        show_calculations=False,
        show_rfq_sections=False,
    ),
    RoutePromptPlan(
        route=RouteName.MATERIAL_KNOWLEDGE,
        prompt_family="MaterialKnowledgePromptAssembler",
        model_class="mid",
        rag=True,
        kernel=False,
        l3=True,  # same rationale as general_sealing_knowledge above
        streaming=False,
        cache_strategy="static-hash (build_prompt_cache_key)",
        activation_status="inactive",
        # same treatment as general_sealing_knowledge.
        show_technical_preassessment=False,
        show_evidence=True,
        show_calculations=False,
        show_rfq_sections=False,
    ),
    RoutePromptPlan(
        route=RouteName.MATERIAL_COMPARISON,
        prompt_family="PromptAssembler",  # unchanged — the full L1 prompt, on purpose
        model_class="strong",
        rag=True,
        kernel=True,
        l3=True,
        streaming=False,
        cache_strategy="literal (unchanged this phase)",
        activation_status="inactive",
        # material_comparison: evidence-eligible; L3 stays True above (unchanged). No calc/RFQ/pre-assessment.
        show_technical_preassessment=False,
        show_evidence=True,
        show_calculations=False,
        show_rfq_sections=False,
    ),
    RoutePromptPlan(
        route=RouteName.ENGINEERING_CASE,
        prompt_family="PromptAssembler",
        model_class="strong",
        rag=True,
        kernel=True,
        l3=True,
        streaming=False,
        cache_strategy="static-hash (build_prompt_cache_key) — already live for L1, Phase 1",
        activation_status="inactive",
        # engineering_case: full existing behavior — every section eligible.
        show_technical_preassessment=True,
        show_evidence=True,
        show_calculations=True,
        show_rfq_sections=True,
    ),
    RoutePromptPlan(
        route=RouteName.LEAKAGE_TROUBLESHOOTING,
        prompt_family="PromptAssembler",
        model_class="strong",
        rag=True,
        kernel=True,
        l3=True,
        streaming=False,
        cache_strategy="static-hash (build_prompt_cache_key) — already live for L1, Phase 1",
        activation_status="inactive",
        # leakage_troubleshooting: pre-assessment + evidence + calculations, but no RFQ sections.
        show_technical_preassessment=True,
        show_evidence=True,
        show_calculations=True,
        show_rfq_sections=False,
    ),
    RoutePromptPlan(
        route=RouteName.RFQ_MANUFACTURER_BRIEF,
        prompt_family="PromptAssembler",  # + the deterministic ArtifactRenderer, unchanged
        model_class="strong",
        rag=True,
        kernel=True,
        l3=True,
        streaming=False,
        cache_strategy="static-hash (build_prompt_cache_key) — already live for L1, Phase 1",
        activation_status="inactive",
        # rfq_manufacturer_brief: full existing behavior — every section eligible, incl. RFQ.
        show_technical_preassessment=True,
        show_evidence=True,
        show_calculations=True,
        show_rfq_sections=True,
    ),
    RoutePromptPlan(
        route=RouteName.UNSUPPORTED_OR_AMBIGUOUS,
        prompt_family="PromptAssembler",  # doubt -> the full, safest path, unchanged
        model_class="strong",
        rag=True,
        kernel=True,
        l3=True,
        streaming=False,
        cache_strategy="static-hash (build_prompt_cache_key) — already live for L1, Phase 1",
        activation_status="inactive",
        # unsupported/ambiguous is the off-topic / navigation catch-all: no technical sections.
        # (Note: L1/L3/kernel/RAG still take the full, safest path above — display flags are
        # render-only and do NOT change that; a doubt-route answer is still fully verified.)
        show_technical_preassessment=False,
        show_evidence=False,
        show_calculations=False,
        show_rfq_sections=False,
    ),
)


def plan_for(route: RouteName) -> RoutePromptPlan:
    """Read-only lookup — raises if the matrix is ever missing an entry for a real RouteName
    (a completeness guard the tests exercise; nothing production-facing calls this yet)."""
    for plan in ROUTE_PROMPT_MATRIX:
        if plan.route is route:
            return plan
    raise KeyError(f"no RoutePromptPlan documented for {route!r}")
