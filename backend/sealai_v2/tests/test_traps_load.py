from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from sealai_v2.core.contracts import HARD_GATES
from sealai_v2.knowledge.traps import (
    TrapCatalog,
    load_traps,
    retrieve_reviewed_trap_facts,
)


def _evidenced(catalog: TrapCatalog) -> TrapCatalog:
    return TrapCatalog(
        entries=tuple(
            replace(entry, sources=("test-source",)) if entry.reviewed else entry
            for entry in catalog.entries
        ),
        version=catalog.version,
        source=catalog.source,
    )


def test_loads_production_catalog():
    cat = load_traps()
    assert cat.reviewed(), "expected reviewed entries"
    assert cat.version == "trap_catalog_v5"


def test_every_entry_well_formed():
    for e in load_traps().entries:
        assert e.id and e.trigger and e.wrong and e.provenance
        assert all(g in HARD_GATES for g in e.gates) and e.gates
        assert e.review_state in ("reviewed", "draft")


def test_reviewed_entries_carry_a_correct_fact():
    # The text remains available to the review queue, but the current production
    # seed is block-only until sources are attached.
    for e in load_traps().reviewed():
        assert e.correct.strip(), f"{e.id}: reviewed entry needs a correct fact"
        assert not e.corrective


def test_reviewed_conflict_fact_is_prefetched_only_on_high_precision_match():
    catalog = _evidenced(load_traps())
    facts = retrieve_reviewed_trap_facts(
        catalog,
        "Aceton, dauerhaft 180 °C und möglichst günstig: welche Dichtung?",
    )
    assert [fact.card_id for fact in facts] == ["CONF-SCHEIN-OPTIMUM"]
    assert facts[0].kind == "trap"
    assert facts[0].sources == ("test-source",)

    assert not retrieve_reviewed_trap_facts(catalog, "Ist EPDM gegen Aceton beständig?")

    uncertainty = retrieve_reviewed_trap_facts(
        catalog, "Ist FKM beständig gegen Essigsäure?"
    )
    assert [fact.card_id for fact in uncertainty] == ["CONF-PAUSCHAL-BESTAENDIG"]

    combo = retrieve_reviewed_trap_facts(
        catalog, "FKM in verdünnter Natronlauge bei 200 °C"
    )
    assert [fact.card_id for fact in combo] == ["TRAP-FKM-AMIN-LAUGE-KETON"]


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Medium ist Synthetiköl, die genaue Sorte weiß ich nicht. Welcher Werkstoff passt?",
            "POLICY-SYNTHETIKOEL-KLASSE-OFFEN",
        ),
        (
            "Schoko-Rührwerk mit taumelnder Welle und CIP: Welche Dichtungslösung ist sinnvoll?",
            "POLICY-SCHOKO-CIP-WERKSTOFF-OFFEN",
        ),
        (
            "Belüftetes Getriebe, Mineralöl bei 80 °C und staubige Umgebung: sinnvoller Ansatz?",
            "POLICY-GETRIEBE-NBR-HNBR-KANDIDATENRAUM",
        ),
        (
            "Passt FKM in normalem Wasser bei Raumtemperatur?",
            "POLICY-FKM-WASSER-KEIN-VERDIKT",
        ),
        (
            "Warum fällt ein RWDR bei zu hoher Umfangsgeschwindigkeit aus?",
            "POLICY-RWDR-GESCHWINDIGKEIT-MECHANISMUS",
        ),
        (
            "Die Dichtung quillt in Mineralöl und wird weich. Was ist die Ursache?",
            "POLICY-DIAG-QUELLUNG-MATERIAL-OFFEN",
        ),
    ],
)
def test_reviewed_solution_policy_is_prefetched_only_for_qualified_context(
    question, expected
):
    facts = retrieve_reviewed_trap_facts(_evidenced(load_traps()), question)
    assert expected in [fact.card_id for fact in facts]


def test_solution_policy_does_not_fire_on_single_generic_keyword():
    catalog = _evidenced(load_traps())
    ids = {
        fact.card_id
        for fact in retrieve_reviewed_trap_facts(catalog, "Was ist Synthetiköl?")
    }
    assert "POLICY-SYNTHETIKOEL-KLASSE-OFFEN" not in ids
    ids = {
        fact.card_id
        for fact in retrieve_reviewed_trap_facts(catalog, "Erkläre mir ein Getriebe.")
    }
    assert "POLICY-GETRIEBE-NBR-HNBR-KANDIDATENRAUM" not in ids


def test_draft_trap_cannot_define_prefetch_terms(tmp_path):
    p = tmp_path / "draft-prefetch.json"
    p.write_text(
        json.dumps(
            {
                "draft_for_review": [
                    {
                        "id": "D",
                        "trigger": "t",
                        "wrong": ["w"],
                        "correct": "c",
                        "gates": ["confident_wrong"],
                        "provenance": ["model:unreviewed"],
                        "retrieval_terms": ["Aceton"],
                        "retrieval_min_hits": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_traps(p)


def test_review_state_is_stamped_from_the_block_not_the_entry(tmp_path):
    # an entry that *claims* reviewed inside the draft block stays draft (discipline can't be faked)
    p = tmp_path / "cat.json"
    p.write_text(
        json.dumps(
            {
                "version": "t",
                "reviewed": [],
                "draft_for_review": [
                    {
                        "id": "X",
                        "trigger": "t",
                        "wrong": ["w"],
                        "correct": "c",
                        "gates": ["confident_wrong"],
                        "provenance": ["model_knowledge:UNREVIEWED"],
                        "review_state": "reviewed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cat = load_traps(p)
    assert cat.by_id("X").review_state == "draft"  # block wins over the self-claim
    assert not cat.reviewed() and len(cat.drafts()) == 1


def test_epdm_entry_encodes_the_non_polar_fact_and_divergence_provenance():
    e = load_traps().by_id("TRAP-EPDM-MINERALOEL")
    assert e is not None and e.reviewed
    assert "unpolar" in e.correct.lower()
    assert any("EPDM ist polar" in w or "polar" in w.lower() for w in e.wrong)
    # provenance is the owner-specified triple — NOT "owner confirmed in M1 adjudication"
    assert "divergence:m1-baseline" in e.provenance
    assert any("eval:TRAP-02" in p for p in e.provenance)
    assert "principles:§2" in e.provenance


def test_calc_umfang_entry_is_kern_referenced_not_self_computed():
    """M8 owner reword (boundary review 2026-06-11): the M2-era entry instructed the ANSWER to
    compute v itself — post-M8 the kern computes; the entry must instruct kern-referencing and
    must no longer carry the plugged worked example."""
    e = load_traps().by_id("CALC-UMFANGSGESCHWINDIGKEIT")
    assert e is not None and e.reviewed
    assert "berechnen lassen" in e.correct
    assert "nie selbst" in e.correct
    assert "keinen Zahlenwert" in e.correct  # fail-closed half is part of the fact
    assert "12,6" not in e.correct  # the plugged example is gone
    # kern-fix-01: the entry is echoed verbatim into the user-facing build_hedge; a plugged speed
    # number (the missed "~14 m/s") then trips detect_parametric_leaks on the hedge → multi-turn
    # parametric Schranke. The reviewed fact must carry NO asserted speed number.
    assert not re.search(r"\d+\s*m/s", e.correct)
    assert any("owner:boundary-review-2026-06-11" in p for p in e.provenance)


def test_validation_rejects_unknown_gate(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {
                "reviewed": [
                    {
                        "id": "B",
                        "trigger": "t",
                        "wrong": ["w"],
                        "correct": "c",
                        "gates": ["not_a_gate"],
                        "provenance": ["eval:X"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_traps(p)


def test_validation_rejects_reviewed_without_correct(tmp_path):
    p = tmp_path / "bad2.json"
    p.write_text(
        json.dumps(
            {
                "reviewed": [
                    {
                        "id": "B",
                        "trigger": "t",
                        "wrong": ["w"],
                        "correct": "  ",
                        "gates": ["confident_wrong"],
                        "provenance": ["eval:X"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_traps(p)
