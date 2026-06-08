from __future__ import annotations

import json

import pytest

from sealai_v2.core.contracts import HARD_GATES
from sealai_v2.knowledge.traps import load_traps


def test_loads_production_catalog():
    cat = load_traps()
    assert cat.reviewed(), "expected reviewed entries"
    assert cat.version == "trap_catalog_v0"


def test_every_entry_well_formed():
    for e in load_traps().entries:
        assert e.id and e.trigger and e.wrong and e.provenance
        assert all(g in HARD_GATES for g in e.gates) and e.gates
        assert e.review_state in ("reviewed", "draft")


def test_reviewed_entries_carry_a_correct_fact():
    # reviewed entries may CORRECT, so they must have a non-empty correct fact (integrity)
    for e in load_traps().reviewed():
        assert e.correct.strip(), f"{e.id}: reviewed entry needs a correct fact"


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
