"""render.ArtifactRenderer — deterministic Jinja2 artifact rendering (build-spec §4, M4b).

A TERMINAL projection: reads a finished-turn ``RenderSnapshot`` and emits stable artifacts
(briefing, calc-report). It NEVER touches L1/L3, so it cannot change the measured answer. Jinja
FORMATS only — no domain logic in template conditionals, no LLM, no network. Same Jinja-env
discipline as ``prompts.assembler`` (StrictUndefined; untrusted content as delimited data).

The claim-boundary frame is OWNER-GROUNDED doctrine wording (§ Safety Boundaries): scoped to
orientation/screening + Hersteller-Prüfgrundlage — never a release/suitability/compliance claim.
It is a working frame; the full liability/warranty review is deferred to pre-public-launch.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from sealai_v2.core.contracts import Artifact, PipelineResult, RenderSnapshot

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Owner-grounded doctrine wording. Allowed scoped vocabulary only (screening, orientation,
# Hersteller-Prüfgrundlage); explicitly disclaims release / suitability / compliance.
CLAIM_BOUNDARY = (
    "**Hinweis (Geltungsrahmen):** Diese Zusammenstellung ist eine technische "
    "**Orientierung/Screening** auf Basis der aktuell vorliegenden Angaben und Richtwerte — "
    "**keine** verbindliche Auslegung, **keine** Freigabe und **keine** Eignungs-, Zulassungs- "
    "oder Konformitätszusage. Sie ist eine **Hersteller-Prüfgrundlage**: die finale Werkstoff- "
    "und Auslegungsentscheidung sowie die Freigabe trifft der Hersteller bzw. die verantwortliche "
    "Fachperson anhand des konkreten Datenblatts."
)


def _provenance(snapshot: RenderSnapshot) -> tuple[str, ...]:
    """Cited sources surfaced in the artifact (computed formula sources + grounded cards)."""
    seen: list[str] = []
    for c in snapshot.computed:
        if c.source and c.source not in seen:
            seen.append(c.source)
    for f in snapshot.grounding_facts:
        q = f.card_id or f.quelle
        if q and q not in seen:
            seen.append(q)
    return tuple(seen)


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        undefined=StrictUndefined,
        autoescape=False,  # plain-text/markdown artifact, not HTML
        keep_trailing_newline=True,
    )


class ArtifactRenderer:
    """Implements the ``Renderer`` Protocol. Stateless + deterministic; templates loaded once."""

    def __init__(self) -> None:
        self._env = _env()

    def calc_report(self, snapshot: RenderSnapshot) -> Artifact:
        body = self._env.get_template("calc_report.jinja").render(
            computed=snapshot.computed,
            not_computed=snapshot.not_computed,
            calc_notes=snapshot.calc_notes,
        )
        return Artifact(
            kind="calc_report",
            title="Berechnete Werte",
            body=body,
            provenance=_provenance(snapshot),
        )

    def briefing(self, snapshot: RenderSnapshot) -> Artifact:
        body = self._env.get_template("briefing.jinja").render(
            question=snapshot.question,
            answer_text=snapshot.answer_text,
            computed=snapshot.computed,
            not_computed=snapshot.not_computed,
            calc_notes=snapshot.calc_notes,
            grounding_facts=snapshot.grounding_facts,
            grounded=snapshot.grounded,
            claim_boundary=CLAIM_BOUNDARY,
        )
        return Artifact(
            kind="briefing",
            title="Technische Orientierung (Screening)",
            body=body,
            provenance=_provenance(snapshot),
        )


def snapshot_from_result(question: str, result: PipelineResult) -> RenderSnapshot:
    """Pure adapter: a finished ``PipelineResult`` → the render input. No I/O, no mutation."""
    return RenderSnapshot(
        question=question,
        answer_text=result.answer.text,
        computed=result.computed_values,
        not_computed=result.not_computed,
        calc_notes=result.calc_notes,
        grounding_facts=result.grounding_facts,
        grounded=result.grounded,
    )
