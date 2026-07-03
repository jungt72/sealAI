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
from sealai_v2.core.framing import GELTUNGSRAHMEN

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Owner-grounded doctrine wording — single-sourced from core.framing (byte-identical to the
# pre-cutover literal; re-exported under the established name).
CLAIM_BOUNDARY = GELTUNGSRAHMEN


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


def _offene_punkte(result: PipelineResult) -> tuple[str, ...]:
    """P5 (audit L8, 'offene Punkte fehlen strukturell'): consolidate the open/unresolved signals
    that are ALREADY live on ``result`` — nothing new is computed here, this only gathers what
    exists into one flat list for a single clearly-labelled briefing section, instead of leaving
    it scattered/implicit across the calc report and (previously) nowhere at all for Gegencheck.

    - ``not_computed`` reasons (fail-closed calc gaps — already shown inline in calc_report.jinja
      too; the duplication is accepted, see commit message, rather than touching the shared
      calc_report template that another artifact also renders standalone).
    - ``calc_notes`` (cross-cutting calc advisories).
    - the Gegencheck ``condition`` text, but ONLY for a ``matrix_conditional`` verdict — a
      disqualification is NOT an "open point" (it is a hard verdict) and E4-1 forbids ever
      surfacing anything for the non-disqualifying/non-conditional bases (matrix_compatible/
      no_matrix_data/no_medium) as an affirmative claim, so those never contribute here either.
    - the flag-gated Produktspec's own ``offene_punkte`` when the turn ran it (inert/empty list
      while ``produktspec_enabled`` stays OFF in prod).
    """
    items: list[str] = [f"{n.calc_id}: {n.reason}" for n in result.not_computed]
    items.extend(result.calc_notes)
    gc = result.gegencheck
    if gc and not gc.get("disqualified") and gc.get("basis") == "matrix_conditional":
        condition = gc.get("condition")
        if condition:
            items.append(condition)
    ks = result.kandidaten_spec
    if ks:
        items.extend(ks.get("offene_punkte") or ())
    return tuple(items)


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
            wissensstand=snapshot.wissensstand,
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
            offene_punkte=snapshot.offene_punkte,
            claim_boundary=CLAIM_BOUNDARY,
        )
        return Artifact(
            kind="briefing",
            title="Technische Orientierung (Screening)",
            body=body,
            provenance=_provenance(snapshot),
            wissensstand=snapshot.wissensstand,
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
        wissensstand=result.wissensstand,
        offene_punkte=_offene_punkte(result),
    )
