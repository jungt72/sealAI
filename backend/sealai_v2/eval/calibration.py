"""Deterministic V2.2 §8 calibration schranken — the kernel-measurable ones. Pure, no LLM, no I/O
beyond the injected catalog.

This module is a PROPOSAL: it COMPUTES the metric. It is NOT yet wired into the deploy-gate
(``eval/matrix.py:_schranken_view``), so the acceptance ruler is UNCHANGED — arming a schranke (adding it
to the gated set) is an owner step (it changes what every deploy must satisfy, TRAP-02). The three
human-adjudicated schranken (§8 confident-wrong-rate / false-hedge-rate / unsupported-claim-rate) live in
the owner's worksheet/adjudication flow, not here.

  (d) coverage_classification_schranke — the keystone (deterministic over the §4 matrix).
  (e) equivalence_overclaim_rate     — deterministic over the existing equivalence_guard.
"""

from __future__ import annotations

from sealai_v2.core.coverage import (
    CoverageStatus,
    chemical_axis,
    classify_coverage,
)
from sealai_v2.core.equivalence_guard import detect_equivalence_claim
from sealai_v2.core.gegencheck import evaluate_gegencheck
from sealai_v2.knowledge.matrix import load_matrix
from sealai_v2.core.output_guard import evaluate_render

# (d) grounded reference set: real material x medium -> expected coverage_status over the §4 matrix.
_COVERAGE_REF = (
    (
        "FKM",
        "Heißdampf",
        CoverageStatus.IN_ENVELOPE,
    ),  # unverträglich -> grounded NO (assertive disq.)
    ("NBR", "Mineralöl", CoverageStatus.IN_ENVELOPE),  # verträglich -> grounded
    (
        "NBR",
        "Synthetiköl",
        CoverageStatus.PARTIAL_ENVELOPE,
    ),  # bedingt -> matrix_conditional
    ("FEPM (AFLAS)", "Dampf", CoverageStatus.PARTIAL_ENVELOPE),  # bedingt
    ("FKM", "Wasser", CoverageStatus.OUT_OF_ENVELOPE),  # no reviewed cell -> ungrounded
    (
        "VMQ",
        "Schmierfett",
        CoverageStatus.OUT_OF_ENVELOPE,
    ),  # no reviewed cell -> ungrounded
)


def coverage_classification_schranke(catalog=None) -> dict:
    """§8(d) Coverage-Classification-Accuracy (the keystone): does the gate correctly recognise its own
    grounding? Returns a ``schranken_quota`` (1.0 = every reference case classified correctly) + any
    misclassifications. Deterministic — the gate is a pure function, so this pins the ≥0.95 floor."""
    cat = catalog or load_matrix()
    wrong: list[dict] = []
    for material, medium, expect in _COVERAGE_REF:
        verdict = evaluate_gegencheck(
            material, medium, tenant="calibration", catalog=cat
        )
        got = classify_coverage(chemical=chemical_axis(verdict)).status
        if got is not expect:
            wrong.append(
                {
                    "material": material,
                    "medium": medium,
                    "expected": expect.value,
                    "got": got.value,
                }
            )
    n = len(_COVERAGE_REF)
    return {
        "schranken_quota": round((n - len(wrong)) / n, 3) if n else None,
        "n": n,
        "wrong": wrong,
    }


def equivalence_overclaim_rate(samples: list[dict]) -> dict:
    """§8(e) Equivalence-Overclaim-Rate: over the existing deterministic ``equivalence_guard``. Each
    sample = ``{"answer": str, "comparison_context": bool}``. The rate counts decode/part-comparison
    answers that assert an ungated equivalence (``detect_equivalence_claim`` non-empty) over all
    comparison-context answers. §8 semantics: HARD-FAIL on any occurrence — so ``schranken_quota`` is 1.0
    only at zero overclaims. Deterministic; the guard is scoped to comparison turns (a non-decode answer
    is never an overclaim hit)."""
    decode_turns = [s for s in samples if s.get("comparison_context")]
    overclaims = [
        s for s in decode_turns if detect_equivalence_claim(s.get("answer", ""))
    ]
    n = len(decode_turns)
    return {
        "overclaim_rate": round(len(overclaims) / n, 3) if n else None,
        "n_comparison_turns": n,
        "overclaims": len(overclaims),
        "schranken_quota": (1.0 if not overclaims else 0.0) if n else None,
    }


# ── §5 narrator-contract metrics (INC-NARRATOR-CONTRACT Phase 4) — measured by the claim-level guard ──
# samples: [{answer, contract, known_values?}]. PROPOSAL — computed, not wired into _schranken_view.
_UNSUPPORTED_KINDS = {"forbidden_phrase", "invented_number", "invented_material", "unmapped_sentence"}


def _guard_render(sample: dict):
    return evaluate_render(
        answer_text=sample.get("answer", ""),
        contract=sample.get("contract", {}),
        known_values=tuple(sample.get("known_values", ()) or ()),
        known_materials=tuple(sample.get("known_materials", ()) or ()),
    )


def unsupported_claim_rate(samples: list[dict]) -> dict:
    """§5 DECISIVE metric: share of renders carrying ANY unsupported-claim violation (fabricated
    authority / invented number / invented material / a technical sentence with no covering claim).
    §8 hard-fail-on-any -> schranken_quota 1.0 only at zero unsupported."""
    n = len(samples)
    if not n:
        return {"unsupported_rate": None, "unsupported": 0, "n": 0, "schranken_quota": None}
    bad = sum(
        1 for s in samples if any(v.kind in _UNSUPPORTED_KINDS for v in _guard_render(s).violations)
    )
    return {
        "unsupported_rate": round(bad / n, 3),
        "unsupported": bad,
        "n": n,
        "schranken_quota": 1.0 if bad == 0 else 0.0,
    }


def required_clause_miss_rate(samples: list[dict]) -> dict:
    """Share of renders that DROP a contract-required clause (safety / no-Freigabe / clarification).
    schranken_quota 1.0 only at zero misses."""
    n = len(samples)
    if not n:
        return {"miss_rate": None, "misses": 0, "n": 0, "schranken_quota": None}
    misses = sum(
        1 for s in samples if any(v.kind == "missing_required_clause" for v in _guard_render(s).violations)
    )
    return {
        "miss_rate": round(misses / n, 3),
        "misses": misses,
        "n": n,
        "schranken_quota": 1.0 if misses == 0 else 0.0,
    }


def overblock_rate(clean_samples: list[dict]) -> dict:
    """Over renders LABELED legitimate (clean reference answers): the share the guard WRONGLY blocks —
    the honest cost of conservatism, so the owner can tune the guard thresholds. A QUALITY cost (degrades
    UX), NOT a hard gate (overblocking does not leak), so no schranken_quota."""
    n = len(clean_samples)
    if not n:
        return {"overblock_rate": None, "blocked": 0, "n": 0}
    blocked = sum(1 for s in clean_samples if _guard_render(s).action == "BLOCK")
    return {"overblock_rate": round(blocked / n, 3), "blocked": blocked, "n": n}
