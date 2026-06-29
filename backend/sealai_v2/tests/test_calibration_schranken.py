"""Deterministic V2.2 §8 calibration-schranken tests — the two kernel-measurable schranken (d) + (e).
These validate the MEASUREMENT functions; arming them in the deploy-gate is a separate owner step."""

from sealai_v2.eval.calibration import (
    coverage_classification_schranke,
    equivalence_overclaim_rate,
)


# ── §8(d) Coverage-Classification-Accuracy (the keystone) ────────────────────────────────────────


def test_coverage_classification_quota_is_one_on_the_reference_set():
    r = coverage_classification_schranke()
    assert r["schranken_quota"] == 1.0
    assert r["wrong"] == []
    assert r["n"] == 6


# ── §8(e) Equivalence-Overclaim-Rate (over the deterministic guard) ──────────────────────────────


def test_overclaim_clean_comparison_corpus_is_zero():
    samples = [
        {
            "answer": "Diese Nennmaße und Werkstoffklasse sind erkennbar; Compound/Eignung beim Hersteller bestätigen.",
            "comparison_context": True,
        },
        {
            "answer": "Ein normaler Antworttext ohne Vergleich.",
            "comparison_context": False,
        },
    ]
    r = equivalence_overclaim_rate(samples)
    assert r["overclaim_rate"] == 0.0
    assert r["schranken_quota"] == 1.0
    assert r["n_comparison_turns"] == 1


def test_overclaim_detected_hard_fails():
    samples = [
        {
            "answer": "Teil X ist baugleich und 1:1 austauschbar mit Teil Y.",
            "comparison_context": True,
        }
    ]
    r = equivalence_overclaim_rate(samples)
    assert r["overclaims"] == 1
    assert r["overclaim_rate"] == 1.0
    assert r["schranken_quota"] == 0.0  # §8: hard-fail on ANY occurrence


def test_negated_equivalence_is_not_an_overclaim():
    # the doctrine-correct "nicht 1:1 austauschbar" must NOT count (the guard skips negated forms)
    samples = [
        {
            "answer": "Die Teile sind nicht 1:1 austauschbar — Compound prüfen.",
            "comparison_context": True,
        }
    ]
    r = equivalence_overclaim_rate(samples)
    assert r["overclaims"] == 0
    assert r["schranken_quota"] == 1.0


def test_overclaim_outside_comparison_context_is_not_counted():
    # the schranke is scoped to comparison/decode turns — an equivalence phrase elsewhere is not a hit
    samples = [
        {"answer": "baugleich und 1:1 austauschbar", "comparison_context": False}
    ]
    r = equivalence_overclaim_rate(samples)
    assert r["n_comparison_turns"] == 0
    assert r["overclaim_rate"] is None
    assert r["schranken_quota"] is None


def test_overclaim_rate_mixed_corpus():
    samples = [
        {
            "answer": "Vergleichsbasis sauber, Hersteller bestätigt.",
            "comparison_context": True,
        },
        {"answer": "problemlos direkt ersetzen", "comparison_context": True},
        {"answer": "Teil X ist 100% identisch.", "comparison_context": True},
    ]
    r = equivalence_overclaim_rate(samples)
    assert r["n_comparison_turns"] == 3
    assert r["overclaims"] == 2
    assert r["overclaim_rate"] == round(2 / 3, 3)
    assert r["schranken_quota"] == 0.0
