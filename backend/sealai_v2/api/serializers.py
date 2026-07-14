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
from sealai_v2.pipeline.route_prompt_matrix import plan_for
from sealai_v2.pipeline.routing import RouteName


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


def _display_flags(result: PipelineResult) -> dict:
    """Route-aware chat-UI display flags (the trust-bug fix): decide which optional chat-UI
    sections a given classified route is ELIGIBLE to render, from the one authoritative per-route
    table (pipeline/route_prompt_matrix.py).

    BACKWARD COMPATIBILITY is the whole point of the default: when no route was classified
    (``result.route_name is None`` — route optimization off / first request / no decision) OR the
    value is not a recognized RouteName (an unrecognized or future route), ALL FOUR flags default to
    ``True`` — i.e. today's always-show behavior — so behavior is 100% unchanged whenever route
    classification did not run. Only a recognized classified route narrows what is shown.

    Render-only. ``show_evidence`` is ANDed with the existing non-empty-citations check on the
    client (Citation.tsx keeps its own ``cites.length === 0`` guard), so it can only HIDE the Belege
    section — it never forces citations to appear when there are none.
    """
    plan = None
    if result.route_name is not None:
        try:
            plan = plan_for(RouteName(result.route_name))
        except (ValueError, KeyError):
            plan = None  # unrecognized/future route → fall back to always-show
    return {
        "route_name": result.route_name,
        "show_technical_preassessment": (
            plan.show_technical_preassessment if plan is not None else True
        ),
        "show_evidence": plan.show_evidence if plan is not None else True,
        "show_calculations": plan.show_calculations if plan is not None else True,
        "show_rfq_sections": plan.show_rfq_sections if plan is not None else True,
    }


def chat_response(result: PipelineResult) -> dict:
    turn_state = result.turn_state
    case_state = result.case_state
    response = {
        "answer": result.answer.text,
        "model": result.answer.model,
        "run": (
            {
                "run_id": turn_state.run_id,
                "status": turn_state.status,
                "case_id": turn_state.case_id,
                "case_revision_started": turn_state.case_revision_started,
                "case_revision_current": turn_state.case_revision_current,
                "risk_level": turn_state.risk_level,
                "route_name": turn_state.route_name,
                "execution_class": turn_state.execution_class,
                "model_tier": turn_state.model_tier,
                "verification_mode": turn_state.verification_mode,
                "policy_version": turn_state.policy_version,
                "needs_human_review": turn_state.needs_human_review,
            }
            if turn_state is not None
            else None
        ),
        "case": (
            {
                "case_id": case_state.case_id,
                "revision": case_state.revision,
                "schema_version": case_state.schema_version,
                "fingerprint": case_state.fingerprint,
                "required_missing": list(case_state.required_missing),
                "open_conflicts": len(case_state.open_conflicts),
            }
            if case_state is not None
            else None
        ),
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
        # Mutable Postgres authority that passed the request's final just-before-serve recheck.
        # Empty only for hermetic/offline pipelines that have no database authority.
        "authority_epoch": result.authority_epoch,
        # Legal-by-Design Phase D (Goal 6): deterministic risk-flag terms matched in the question
        # ((), or e.g. ["ATEX", "Sauerstoff"]) — drives the SPA's warning badge. Always present
        # (never flag-gated — see PipelineResult.risk_flags's docstring).
        "risk_flags": list(result.risk_flags),
        # P1.5: surface L3's verdict (verified flag + action/parse_ok/hedged) so the client can
        # distinguish a confidently-verified answer from a hedge or a silently-unverified one.
        # Additive only — existing keys are untouched.
        **_verification(result),
        # Phase 2B routing → render contract: route_name + the four route-aware chat-UI display
        # flags (route_prompt_matrix). Backward-compatible: all four default to True when no route
        # was classified, so existing behavior is unchanged. Fixes "Technische Vorbewertung"/"Belege"
        # showing on smalltalk/off-topic turns. Render-only — never gates L1/L3/kernel/RAG.
        **_display_flags(result),
    }
    # Default-off and additive: when the active interview flag is not enabled the PipelineResult
    # field is None and the legacy JSON remains byte-for-byte key-compatible (no null key added).
    if result.next_question is not None:
        response["next_question"] = result.next_question.to_dict()
    return response
