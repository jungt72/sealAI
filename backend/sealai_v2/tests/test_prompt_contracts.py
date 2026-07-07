from __future__ import annotations

import inspect
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, meta

from sealai_v2.core import contracts
from sealai_v2.core.fachkarte_extract import FachkarteExtractPrompt
from sealai_v2.core.medium_research import MediumResearchPrompt
from sealai_v2.memory.distiller import DistillPrompt
from sealai_v2.prompts import assembler

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
_RENDER_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "render" / "templates"

_EXPECTED_TEMPLATE_VARS = {
    "distill.jinja": set(),
    "fachkarte_extract.jinja": set(),
    "medium_research.jinja": set(),
    # Phase 2C (LangGraph-suitability audit): prepared cheap-route prompt families — NOT wired
    # into production generation yet (see pipeline/route_prompt_matrix.py, activation_status=
    # "inactive"). Deliberately zero variables, same pattern as distill/medium_research above.
    "general_sealing_knowledge.jinja": set(),
    "material_knowledge.jinja": set(),
    "smalltalk_navigation.jinja": set(),
    "system_l1.jinja": {
        "anrede",
        "archetype_context",
        "baseline_hardening",
        "calc_notes",
        "case_context",
        "compliance_hint",
        "computed_values",
        "contract",
        "conversation_window",
        "correction_note",
        "coverage",
        "durable_context",
        "engineering_flags",
        "grounding_facts",
        "material_params",
        "medium_hint_context",
        "not_computed",
        "pack_suggestion_context",
        "safety_critical",
        "untrusted",
    },
    "understand.jinja": {
        "archetype_keys",
        "known_seal_types",
        "medium_already_known",
    },
    "verifier_l3.jinja": {
        "computed_values",
        "grounding_facts",
        "matrix_facts",
        "traps",
    },
}


def _keyword_params(method) -> set[str]:
    return {name for name in inspect.signature(method).parameters if name != "self"}


def test_active_llm_prompt_templates_have_registered_variables():
    env = Environment(
        loader=FileSystemLoader(str(_PROMPT_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
    )
    actual = {}
    for path in sorted(
        p for p in _PROMPT_DIR.glob("*.jinja") if not p.name.startswith(".")
    ):
        ast = env.parse(path.read_text(encoding="utf-8"))
        actual[path.name] = meta.find_undeclared_variables(ast)
    assert actual == _EXPECTED_TEMPLATE_VARS


def test_active_render_templates_compile():
    env = Environment(
        loader=FileSystemLoader(str(_RENDER_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
    )
    for path in sorted(
        p for p in _RENDER_TEMPLATE_DIR.glob("*.jinja") if not p.name.startswith(".")
    ):
        env.parse(path.read_text(encoding="utf-8"))


def test_prompt_assembler_protocols_match_concrete_signatures():
    assert _keyword_params(
        contracts.SystemPromptAssembler.system_prompt
    ) == _keyword_params(assembler.PromptAssembler.system_prompt)
    assert _keyword_params(
        contracts.VerifierPromptAssembler.verifier_system_prompt
    ) == _keyword_params(assembler.VerifierPromptAssembler.verifier_system_prompt)
    assert _keyword_params(
        contracts.UnderstandPromptAssembler.understand_prompt
    ) == _keyword_params(assembler.UnderstandPromptAssembler.understand_prompt)
    assert _keyword_params(DistillPrompt.distill_prompt) == _keyword_params(
        assembler.DistillPromptAssembler.distill_prompt
    )
    assert _keyword_params(
        MediumResearchPrompt.medium_research_prompt
    ) == _keyword_params(assembler.MediumResearchPromptAssembler.medium_research_prompt)
    assert _keyword_params(
        FachkarteExtractPrompt.fachkarte_extract_prompt
    ) == _keyword_params(
        assembler.FachkarteExtractPromptAssembler.fachkarte_extract_prompt
    )


def test_all_active_prompt_assemblers_render_with_minimal_context():
    assert assembler.PromptAssembler().system_prompt()
    assert assembler.VerifierPromptAssembler().verifier_system_prompt(traps=[])
    assert assembler.DistillPromptAssembler().distill_prompt()
    assert assembler.MediumResearchPromptAssembler().medium_research_prompt()
    assert assembler.FachkarteExtractPromptAssembler().fachkarte_extract_prompt()
    assert assembler.UnderstandPromptAssembler().understand_prompt()
