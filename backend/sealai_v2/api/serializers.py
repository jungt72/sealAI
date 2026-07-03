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
    VerifierAction,
    VerifierVerdict,
)


def _verification(result: PipelineResult) -> dict:
    """P1.5 — surface L3's verdict so a client can tell a CONFIDENTLY-verified answer from a
    hedge or a silently-unverified one. Without this block the chat payload drops the verdict
    and every answer looks equally trustworthy.

    ``verified`` is the honest, conservative signal: True only when L3 actually ran, parsed its
    own output, AND the outcome is one we stand behind — PASS / FLAG (advisory, draft unchanged)
    / CORRECTED (regenerated against a REVIEWED correction → clean, contracts §VerifierAction).
    A BLOCKED_HEDGE (safe hedge substituted) or a parse failure (fail-open) is NOT ``verified``;
    a missing verdict (L3 absent/disabled) is NOT ``verified`` either.

    The nested object keeps the raw signals so the SPA can render a precise badge:
      - ``action``   : the VerifierAction value (``"pass"``/``"flag"``/…) or None if L3 absent.
      - ``parse_ok`` : did L3's output parse (bool), or None if L3 absent.
      - ``hedged``   : True only when the draft was blocked and a safe hedge was substituted.
      - ``ran``      : whether L3 ran at all (the pipeline's own ``verified`` flag) — lets a
                       client distinguish "ran but hedged/unparsed" from "never checked".
    """
    verdict: VerifierVerdict | None = result.verifier
    if verdict is None:
        return {
            "verified": False,
            "verification": {
                "action": None,
                "parse_ok": None,
                "hedged": False,
                "ran": bool(result.verified),
            },
        }
    hedged = verdict.action is VerifierAction.BLOCKED_HEDGE
    verified = verdict.parse_ok and verdict.action in (
        VerifierAction.PASS,
        VerifierAction.FLAG,
        VerifierAction.CORRECTED,
    )
    return {
        "verified": bool(verified),
        "verification": {
            "action": verdict.action.value,
            "parse_ok": bool(verdict.parse_ok),
            "hedged": hedged,
            "ran": bool(result.verified),
        },
    }


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


def _medium_intelligence(mi) -> dict | None:
    """Medium Intelligence (Phase 2) → the MEDIUM tab payload, or None when absent/empty. 'vorläufig'
    is intrinsic (helper-LLM knowledge, never reviewed); the SPA renders the badge accordingly."""
    if mi is None or mi.empty:
        return None
    return {
        "medium": mi.medium,
        "kategorie": mi.kategorie,
        "eigenschaften": list(mi.eigenschaften),
        "herausforderungen": list(mi.herausforderungen),
        "werkstoff_tendenz": list(mi.werkstoff_tendenz),
        "unsicher": mi.unsicher,
        "vorlaeufig": True,
    }


def _memory_context(bundle) -> dict | None:
    """sealingAI Memory Architecture V1.0 (Patch 8) → the ``context_sources`` payload, or None when
    absent/empty. Render/serializer surface only in this patch — NOT injected into L1/L3 yet (the
    prompt-text injection step is deliberately separate, see memory/context_assembler.py)."""
    if bundle is None or bundle.is_empty:
        return None
    return {
        "context_sources": list(bundle.context_sources),
        "total_estimated_tokens": bundle.total_estimated_tokens,
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
        # V2.2 INC-COVERAGE-GATE: deterministic coverage_status + per-axis grounding, or None when off.
        # Render surface only — passed through verbatim; the status bounds the L1 mode, never L1 prose.
        "coverage": result.coverage,
        "contract": result.contract,
        "guard": result.guard,
        "diagnose": result.diagnose,
        "decode": result.decode,
        "alternativen": result.alternativen,
        # Medium Intelligence (Phase 2): provisional researched medium properties + challenges for the
        # MEDIUM tab, or None. Render/serializer surface only — never injected into L1/L3.
        "medium_intelligence": _medium_intelligence(result.medium_intelligence),
        # sealingAI Memory Architecture V1.0 (Patch 8): the bounded curated-memory context bundle's
        # context_sources, or None when off/empty/failed. Render/serializer surface only in this
        # patch — NOT injected into L1/L3 yet (see memory/context_assembler.py's module docstring).
        "memory_context": _memory_context(result.memory_context),
        # Kandidaten-Spezifikation (Produktspec v3.1): the candidate Bauform/Werkstoff/DIN render dict
        # (structurally capped, always "vorläufig"), or None when off / non-RWDR / no basis. Already a
        # plain dict from the pipeline adapter — passed through verbatim. Never from L1/L3.
        "kandidaten_spec": result.kandidaten_spec,
        # P3 (audit §4.3 Versionierung): the knowledge-catalog state this answer was grounded
        # against, or "" when no catalogs were wired. Passed through verbatim.
        "wissensstand": result.wissensstand,
        # P1.5: surface L3's verdict (verified flag + action/parse_ok/hedged) so the client can
        # distinguish a confidently-verified answer from a hedge or a silently-unverified one.
        # Additive only — existing keys are untouched.
        **_verification(result),
    }
