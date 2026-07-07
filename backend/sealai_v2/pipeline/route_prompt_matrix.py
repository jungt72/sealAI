"""Phase 2C (LangGraph-suitability audit) — the documented route-to-prompt-family matrix.

INACTIVE / READ-ONLY: nothing here is consumed by ``Pipeline.run()``. This module exists to make
the intended target architecture from the LangGraph-suitability audit's Section 10 explicit and
reviewable in code (not just prose), and to give a later activation phase (Phase 2D+) a single,
already-agreed-upon place to read from instead of re-deriving the mapping. Changing what this
table SAYS is a design decision; changing what the pipeline DOES with it is a separate, much later,
separately-reviewed step.

Nothing in ``pipeline/pipeline.py`` imports or reads this module today.
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
        streaming=False,
        cache_strategy="static-hash (build_prompt_cache_key)",
        activation_status="inactive",
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
    ),
)


def plan_for(route: RouteName) -> RoutePromptPlan:
    """Read-only lookup — raises if the matrix is ever missing an entry for a real RouteName
    (a completeness guard the tests exercise; nothing production-facing calls this yet)."""
    for plan in ROUTE_PROMPT_MATRIX:
        if plan.route is route:
            return plan
    raise KeyError(f"no RoutePromptPlan documented for {route!r}")
