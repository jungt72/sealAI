from __future__ import annotations

import pytest

from sealai_v2.eval.cases import load_cases
from sealai_v2.eval.harness import _select_primary_cases


def test_case_filter_preserves_canonical_order():
    selected = _select_primary_cases(
        load_cases(), frozenset({"CONFLICT-01", "TRAP-01"}), None
    )
    assert [case.id for case in selected] == ["TRAP-01", "CONFLICT-01"]


def test_case_filter_rejects_unknown_ids():
    with pytest.raises(ValueError, match="unknown primary eval case ids"):
        _select_primary_cases(load_cases(), frozenset({"NOT-A-CASE"}), None)
