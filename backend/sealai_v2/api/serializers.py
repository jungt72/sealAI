"""M6c — API serializers: present the pure core's results to the client. The citation serializer
surfaces the OWNER-VERIFIED PRIMARY SOURCE (GroundingFact.sources, e.g. Parker / ISO 3601-2) instead
of the internal card_id (which stays internal for provenance/audit). Presentation only — no domain logic.
"""

from __future__ import annotations

from sealai_v2.core.contracts import (
    ComputedValue,
    DerivedFact,
    GroundingFact,
    NotComputed,
    PipelineResult,
)


def _not_computed(n: NotComputed) -> dict:
    return {"calc_id": n.calc_id, "reason": n.reason}


def _clarification(c) -> dict:
    """A fail-closed unit-recovery hint (binder kernel channel). ``one_click`` is the BACKEND-owned
    'append the canonical is safe' policy — the UI must honor it (never append on one_click=False, or
    the no-silent-rescale guard is bypassed at the panel)."""
    return {
        "feld": c.feld,
        "input_name": c.input_name,
        "raw_value": c.raw_value,
        "raw_unit": c.raw_unit,
        "reason": c.reason,
        "suggested_unit": c.suggested_unit,
        "known_dimension": c.known_dimension,
        "expected_dimension": c.expected_dimension,
        "one_click": c.one_click,
    }


def _computed_value(c: ComputedValue) -> dict:
    """A chat turn's in-band kern result. Same wire shape as a persisted DerivedFact (one frontend
    type); ``parent_fields`` is left empty on the in-band path (the case-state source map is not
    threaded here) — the authoritative dependency view comes from /compute."""
    return {
        "calc_id": c.calc_id,
        "name": c.name,
        "value": c.value,
        "unit": c.unit,
        "formula": c.formula,
        "parent_fields": [],
        "input_origins": list(c.input_origins),
        "provenance": "kernel_computed",
    }


def _derived_fact(d: DerivedFact) -> dict:
    """A persisted kernel_computed value (the /compute read surface). Carries the parent input
    felder it depends on (v ← wellendurchmesser, drehzahl)."""
    return {
        "calc_id": d.calc_id,
        "name": d.name,
        "value": d.value,
        "unit": d.unit,
        "formula": d.formula,
        "parent_fields": list(d.parent_fields),
        "input_origins": list(d.input_origins),
        "provenance": d.provenance,
    }


def compute_response(comp) -> dict:
    """The /compute payload (``DerivedComputation``): persisted kernel values + honest
    'nicht berechenbar' reasons + cross-cutting notes. NO LLM content — kernel channel only."""
    return {
        "computed": [_derived_fact(d) for d in comp.derived],
        "not_computed": [_not_computed(n) for n in comp.calc.not_computed],
        "notes": list(comp.calc.notes),
        # M-unit-binding: structured fail-closed unit-recovery hints (the panel's confirm surface).
        "clarifications": [_clarification(c) for c in comp.clarifications],
    }


def citation(fact: GroundingFact) -> dict:
    """User-facing citation: the claim text + its primary source(s). Never exposes the internal
    card_id; falls back to a neutral 'reviewed' label when a (path-i owner-grounded) claim has no
    external primary source."""
    return {
        "text": fact.text,
        "sources": list(fact.sources)
        if fact.sources
        else ["geprüfte Fachkarte (intern)"],
    }


def chat_response(result: PipelineResult) -> dict:
    return {
        "answer": result.answer.text,
        "model": result.answer.model,
        "grounded": result.grounded,
        "intent": (result.understanding.intent.value if result.understanding else None),
        "citations": [citation(f) for f in result.grounding_facts],
        # M8: surface the turn's in-band kern result so the panel can update without a 2nd
        # round-trip (the authoritative settled read is /compute). Empty when compute is off.
        "computed": [_computed_value(c) for c in result.computed_values],
        "not_computed": [_not_computed(n) for n in result.not_computed],
        # Modus E: deterministic Gegencheck verdict (binary disqualified-or-not) or None when
        # the turn is not a Gegencheck situation. Already a plain dict from the kernel - passed
        # through verbatim so the SPA renders the verdict deterministically, not from L1 prose.
        "gegencheck": result.gegencheck,
        "diagnose": result.diagnose,
        "decode": result.decode,
        "alternativen": result.alternativen,
    }
