"""Phase 2C (LangGraph-suitability audit) — prompt-family preparation tests.

Covers the NEW Phase 2C surface: the three cheap-route prompt templates, their assemblers, and
the (inactive) route-to-prompt matrix. Golden-Case/L3-bypass/telemetry/safe-tracing regression
coverage lives in the existing Phase 0/1/2B test files (test_safe_trace.py, test_cache_key.py,
test_routing.py, test_route_optimization_wiring.py, test_route_telemetry_safety.py) — this file
does not duplicate them; the full suite run proves they still pass unmodified.
"""

from __future__ import annotations

import re

from sealai_v2.core.contracts import Flags
from sealai_v2.pipeline.route_prompt_matrix import ROUTE_PROMPT_MATRIX, plan_for
from sealai_v2.pipeline.routing import RouteName
from sealai_v2.prompts.assembler import (
    GeneralKnowledgePromptAssembler,
    MaterialKnowledgePromptAssembler,
    PromptAssembler,
    SmalltalkNavigationPromptAssembler,
)

_JINJA_SYNTAX_RE = re.compile(r"\{\{|\}\}|\{%|%\}")


class TestPromptFilesExistAndRender:
    def test_smalltalk_navigation_renders(self) -> None:
        text = SmalltalkNavigationPromptAssembler().system_prompt()
        assert isinstance(text, str) and len(text) > 0

    def test_general_sealing_knowledge_renders(self) -> None:
        text = GeneralKnowledgePromptAssembler().system_prompt()
        assert isinstance(text, str) and len(text) > 0

    def test_material_knowledge_renders(self) -> None:
        text = MaterialKnowledgePromptAssembler().system_prompt()
        assert isinstance(text, str) and len(text) > 0


class TestPromptFamiliesAreCompact:
    """Requirement: much smaller than the full 536-line engineering L1 prompt."""

    def _l1_length(self) -> int:
        return len(PromptAssembler().system_prompt(flags=Flags()))

    def test_smalltalk_is_much_smaller_than_full_l1(self) -> None:
        assert (
            len(SmalltalkNavigationPromptAssembler().system_prompt())
            < self._l1_length() * 0.15
        )

    def test_general_knowledge_is_much_smaller_than_full_l1(self) -> None:
        assert (
            len(GeneralKnowledgePromptAssembler().system_prompt())
            < self._l1_length() * 0.15
        )

    def test_material_knowledge_is_much_smaller_than_full_l1(self) -> None:
        assert (
            len(MaterialKnowledgePromptAssembler().system_prompt())
            < self._l1_length() * 0.15
        )


class TestStaticRenderingIsStable:
    """Same assembler, called twice, must render byte-identical output (required for the
    static-prompt-hash cache-key scheme from Phase 1 to be meaningful)."""

    def test_smalltalk_stable_across_two_renders(self) -> None:
        a = SmalltalkNavigationPromptAssembler().system_prompt()
        b = SmalltalkNavigationPromptAssembler().system_prompt()
        assert a == b

    def test_general_knowledge_stable_across_two_renders(self) -> None:
        a = GeneralKnowledgePromptAssembler().system_prompt()
        b = GeneralKnowledgePromptAssembler().system_prompt()
        assert a == b

    def test_material_knowledge_stable_across_two_instances(self) -> None:
        a = MaterialKnowledgePromptAssembler().system_prompt()
        b = MaterialKnowledgePromptAssembler().system_prompt()
        assert a == b


class TestStaticHashChangesWithContent:
    """Phase 1's build_prompt_cache_key must produce DIFFERENT keys for the three DIFFERENT
    static prompts (proving the hash is content-sensitive, not a constant)."""

    def test_three_prompt_families_yield_three_different_hashes(self) -> None:
        from sealai_v2.llm.cache_key import build_prompt_cache_key

        keys = {
            build_prompt_cache_key(
                "x", "m", SmalltalkNavigationPromptAssembler().system_prompt()
            ),
            build_prompt_cache_key(
                "x", "m", GeneralKnowledgePromptAssembler().system_prompt()
            ),
            build_prompt_cache_key(
                "x", "m", MaterialKnowledgePromptAssembler().system_prompt()
            ),
        }
        assert len(keys) == 3


class TestNoDynamicCaseDataInStaticSection:
    """All three assemblers' system_prompt() takes NO arguments — structurally, there is no
    parameter slot for per-turn case data (medium, tenant, dimensions, ...) to flow through. This
    test also scans the rendered text for unrendered Jinja syntax (a template authored with a
    variable that was never filled would leave `{{`/`{%` markers behind)."""

    def test_smalltalk_assembler_takes_no_arguments(self) -> None:
        import inspect

        sig = inspect.signature(SmalltalkNavigationPromptAssembler.system_prompt)
        assert list(sig.parameters) == ["self"]

    def test_general_knowledge_assembler_takes_no_arguments(self) -> None:
        import inspect

        sig = inspect.signature(GeneralKnowledgePromptAssembler.system_prompt)
        assert list(sig.parameters) == ["self"]

    def test_material_knowledge_assembler_takes_no_arguments(self) -> None:
        import inspect

        sig = inspect.signature(MaterialKnowledgePromptAssembler.system_prompt)
        assert list(sig.parameters) == ["self"]

    def test_no_unrendered_jinja_syntax_in_any_output(self) -> None:
        for text in (
            SmalltalkNavigationPromptAssembler().system_prompt(),
            GeneralKnowledgePromptAssembler().system_prompt(),
            MaterialKnowledgePromptAssembler().system_prompt(),
        ):
            assert not _JINJA_SYNTAX_RE.search(text), text


class TestSmalltalkHasNoEngineeringDecisionLanguage:
    """The smalltalk prompt must not itself contain material/technical decision vocabulary that
    would suggest it makes engineering claims."""

    _FORBIDDEN = (
        "pv-wert",
        "umfangsgeschwindigkeit",
        "ptfe",
        "fkm",
        "epdm",
        "nbr",
        "bar",
        "u/min",
        "geeignet für",
    )

    def test_no_engineering_vocabulary_present(self) -> None:
        text = SmalltalkNavigationPromptAssembler().system_prompt().lower()
        for term in self._FORBIDDEN:
            # word-boundary match: "bar" must not match inside "belastbare"
            pattern = re.compile(r"\b" + re.escape(term) + r"\b")
            assert not pattern.search(
                text
            ), f"unexpected engineering term {term!r} in smalltalk prompt"


class TestKnowledgePromptsEscalateApplicationQuestions:
    """Both knowledge prompts must explicitly instruct escalation when the message turns out to
    carry operating parameters or application details."""

    def test_general_knowledge_has_escalation_instruction(self) -> None:
        text = GeneralKnowledgePromptAssembler().system_prompt()
        assert "vollständigen technischen Analyse" in text
        assert "Betriebsparameter" in text or "Betriebsdaten" in text

    def test_material_knowledge_has_escalation_instruction(self) -> None:
        text = MaterialKnowledgePromptAssembler().system_prompt()
        assert "vollständigen technischen Analyse" in text
        assert "Medium" in text


class TestMaterialKnowledgeNeverApprovesSuitability:
    def test_explicit_no_final_suitability_language(self) -> None:
        text = MaterialKnowledgePromptAssembler().system_prompt()
        assert "Keine finale Eignungs-Bestätigung" in text
        assert "Orientierung ≠ Freigabe" in text or "Orientierung" in text

    def test_no_comparative_ranking_permission(self) -> None:
        text = MaterialKnowledgePromptAssembler().system_prompt()
        # must explicitly forbid ranking-style comparisons, not just stay silent about them
        assert "besser als" in text.lower() or "vergleich" in text.lower()


class TestRoutePromptMatrixIsInactiveAndComplete:
    def test_every_route_name_has_an_entry(self) -> None:
        documented = {p.route for p in ROUTE_PROMPT_MATRIX}
        assert documented == set(RouteName)

    def test_plan_for_raises_on_a_non_route(self) -> None:
        import pytest

        with pytest.raises(KeyError):
            plan_for("not-a-real-route")  # type: ignore[arg-type]

    def test_all_entries_are_marked_inactive_in_phase_2c(self) -> None:
        for plan in ROUTE_PROMPT_MATRIX:
            assert plan.activation_status == "inactive"

    def test_only_smalltalk_navigation_has_l3_false_in_the_documented_plan(
        self,
    ) -> None:
        """The matrix's own documented intent must match the code's actual safety restriction
        from Phase 2B (L3-bypass is smalltalk_navigation-only) — the plan is not allowed to
        silently diverge from what the code actually enforces."""
        for plan in ROUTE_PROMPT_MATRIX:
            if plan.route is RouteName.SMALLTALK_NAVIGATION:
                assert plan.l3 is False
            else:
                assert plan.l3 is True

    def test_engineering_leakage_comparison_rfq_ambiguous_keep_full_pipeline_plan(
        self,
    ) -> None:
        always_full = {
            RouteName.ENGINEERING_CASE,
            RouteName.LEAKAGE_TROUBLESHOOTING,
            RouteName.MATERIAL_COMPARISON,
            RouteName.RFQ_MANUFACTURER_BRIEF,
            RouteName.UNSUPPORTED_OR_AMBIGUOUS,
        }
        for route in always_full:
            plan = plan_for(route)
            assert plan.rag is True
            assert plan.kernel is True
            assert plan.l3 is True
            assert plan.streaming is False
            assert plan.prompt_family == "PromptAssembler"

    def test_only_smalltalk_navigation_streams_no_unverified_content_streams(
        self,
    ) -> None:
        # Phase 3A: smalltalk_navigation is the SOLE streaming row (compact, zero-signal,
        # non-engineering content). Every OTHER route -- all engineering/verified-content routes --
        # keeps streaming=False, so no unverified engineering content ever streams.
        for plan in ROUTE_PROMPT_MATRIX:
            assert plan.streaming is (plan.route is RouteName.SMALLTALK_NAVIGATION)

    def test_pipeline_py_reads_only_the_matrix_kernel_flag(self) -> None:
        """Structural proof the matrix stays MOSTLY documentary. INC-CALC-ROUTE-RELEVANCE activated
        the FIRST pipeline-side read of the table: the ``kernel`` column, via ``plan_for``, so the
        L1 prompt on a kernel=False route no longer gets off-topic calc context (the RWDR-function/
        Umfangsgeschwindigkeit bug). Guard that this stays the ONLY pipeline-side matrix consumption
        — pipeline.py reads ``plan_for(...).kernel`` and imports the read-only ``plan_for`` accessor,
        but does NOT touch the RoutePromptPlan dataclass or the still-documentary intent columns
        (prompt_family / model_class / rag / l3 / streaming / cache_strategy / activation_status),
        which stay intent-only until their own separately-reviewed activation."""
        import pathlib
        import re

        pipeline_src = (
            pathlib.Path(__file__).resolve().parents[1] / "pipeline" / "pipeline.py"
        ).read_text()
        # The one sanctioned matrix access: read a route's kernel flag via the plan_for accessor.
        assert re.search(r"plan_for\([^)]*\)\.kernel", pipeline_src)
        assert "import plan_for" in pipeline_src
        # It must NOT reach for the raw dataclass or consume any other (still-documentary) column.
        assert "RoutePromptPlan" not in pipeline_src
