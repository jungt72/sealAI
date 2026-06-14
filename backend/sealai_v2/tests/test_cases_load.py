from __future__ import annotations

from sealai_v2.core.contracts import HARD_GATES
from sealai_v2.eval.cases import load_cases


def test_loads_25_cases():
    assert len(load_cases()) == 25


def test_ten_classes_present():
    prefixes = {c.id.split("-")[0] for c in load_cases()}
    assert prefixes == {
        "TRAP",
        "COMBO",
        "UNCERT",
        "UNDER",
        "CONFLICT",
        "DEFAULT",
        "LIMIT",
        "SAFETY",
        "CALC",
        "APP",
    }


def test_each_case_well_formed():
    for c in load_cases():
        assert c.input and c.must_catch and c.must_contain
        assert all(1 <= a <= 7 for a in c.primary_axes)
        assert all(g in HARD_GATES for g in c.hard_gates)


def test_full_set_no_holdout_at_m1():
    # decision #3: full set at M1; the holdout split is introduced from M2.
    assert all(c.holdout is False for c in load_cases())


def test_has_both_gate_and_nongate_cases():
    cases = load_cases()
    gate = [c for c in cases if c.hard_gates]
    nongate = [c for c in cases if not c.hard_gates]
    assert len(gate) >= 15  # the set is dominated by hard cases (build-spec §9)
    assert nongate  # e.g. UNDER-01/02/03, DEFAULT-02, APP-01
