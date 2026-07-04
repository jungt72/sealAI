"""L1 system-prompt assembly (Jinja2, StrictUndefined).

Prinzipien §4.1 / build-spec §12: Jinja **assembles** context (anrede, grounding facts,
case context, flags); it **never decides** domain content. StrictUndefined makes a missing
variable a hard error rather than a silent gap.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sealai_v2.core.contracts import Flags, GroundingFact

_TEMPLATE_DIR = Path(__file__).resolve().parent
_TEMPLATE_NAME = "system_l1.jinja"
_VERIFIER_TEMPLATE_NAME = "verifier_l3.jinja"
_DISTILL_TEMPLATE_NAME = "distill.jinja"
_MEDIUM_RESEARCH_TEMPLATE_NAME = "medium_research.jinja"
_FACHKARTE_EXTRACT_TEMPLATE_NAME = "fachkarte_extract.jinja"


def _env(template_dir: Path | None) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(template_dir or _TEMPLATE_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


class PromptAssembler:
    """Renders ``system_l1.jinja`` into the L1 system prompt. Template file read happens once
    here (at construction) — keeping the pure ``core`` generator I/O-free."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template = _env(template_dir).get_template(_TEMPLATE_NAME)

    def system_prompt(
        self,
        *,
        anrede: str = "du",
        grounding_facts: list[GroundingFact] | None = None,
        case_context: list[dict] | None = None,
        durable_context: list[dict] | None = None,
        flags: Flags | None = None,
        correction_note: str | None = None,
        computed_values: list[dict] | None = None,
        not_computed: list[dict] | None = None,
        calc_notes: list[str] | None = None,
        conversation_window: list[dict] | None = None,
        untrusted: list[dict] | None = None,
        archetype_context: dict | None = None,
        pack_suggestion_context: dict | None = None,
        medium_hint_context: dict | None = None,
        coverage: dict | None = None,
        contract: dict | None = None,
        baseline_hardening: bool = False,
        material_params: list | None = None,
    ) -> str:
        flags = flags or Flags()
        gf = [{"text": f.text, "quelle": f.quelle} for f in (grounding_facts or [])]
        return self._template.render(
            anrede=anrede,
            grounding_facts=gf,
            case_context=case_context or [],
            durable_context=durable_context or [],
            conversation_window=conversation_window or [],
            compliance_hint=flags.compliance_hint,
            safety_critical=flags.safety_critical,
            correction_note=correction_note or "",
            computed_values=computed_values or [],
            not_computed=not_computed or [],
            calc_notes=calc_notes or [],
            untrusted=untrusted or [],
            archetype_context=archetype_context or None,
            pack_suggestion_context=pack_suggestion_context or None,
            medium_hint_context=medium_hint_context or None,
            coverage=coverage or None,
            contract=contract or None,
            baseline_hardening=baseline_hardening,
            material_params=material_params or None,
        )


class VerifierPromptAssembler:
    """Renders ``verifier_l3.jinja`` into the L3 verifier system prompt. The trap catalog is
    injected as delimited DATA (build-spec §4.1 — Jinja assembles, it never decides content)."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template = _env(template_dir).get_template(_VERIFIER_TEMPLATE_NAME)

    def verifier_system_prompt(
        self,
        *,
        traps: list[dict],
        grounding_facts: list[dict] | None = None,
        computed_values: list[dict] | None = None,
        matrix_facts: list[dict] | None = None,
    ) -> str:
        return self._template.render(
            traps=traps or [],
            grounding_facts=grounding_facts or [],
            computed_values=computed_values or [],
            matrix_facts=matrix_facts or [],
        )


class DistillPromptAssembler:
    """Renders ``distill.jinja`` into the memory distillation system prompt (build-spec §7, M5).
    Static instruction — no domain logic in the template; it only instructs CONSERVATIVE,
    user-stated-only extraction (the distilled case-state never gates/routes)."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template = _env(template_dir).get_template(_DISTILL_TEMPLATE_NAME)

    def distill_prompt(self) -> str:
        return self._template.render()


class MediumResearchPromptAssembler:
    """Renders ``medium_research.jinja`` into the Medium-Intelligence (Phase 2) research prompt.
    Static doctrine instruction (vorläufig only, no fabricated numbers, honest "unsicher"); the
    helper LLM's output enters the case as PROVISIONAL facts, never authoritative."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template = _env(template_dir).get_template(_MEDIUM_RESEARCH_TEMPLATE_NAME)

    def medium_research_prompt(self) -> str:
        return self._template.render()


class FachkarteExtractPromptAssembler:
    """Renders ``fachkarte_extract.jinja`` into the Fachkarten-ingestion prompt (Paperless path).
    Static doctrine: extract ONLY doc-grounded claims as a DRAFT card for owner review — never
    authoritative, no fabrication, no added general knowledge."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template = _env(template_dir).get_template(
            _FACHKARTE_EXTRACT_TEMPLATE_NAME
        )

    def fachkarte_extract_prompt(self) -> str:
        return self._template.render()
