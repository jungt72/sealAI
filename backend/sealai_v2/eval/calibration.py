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
