"""Calc registry loader — formulas-as-code binding + the reviewed-def discipline."""

from __future__ import annotations

import json

import pytest

from sealai_v2.knowledge.calc_registry import load_calc_registry


def _write(tmp_path, calcs):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"version": "t", "calcs": calcs}), encoding="utf-8")
    return p


def test_seed_loads_three_reviewed_with_bound_code():
    reg = load_calc_registry()
    assert len(reg.defs) == 3 and len(reg.reviewed()) == 3
    for d in reg.reviewed():
        assert d.source.strip(), f"{d.id}: missing source"
        assert d.provenance and d.validity and d.impl is not None


def test_calc_registry_does_not_bypass_human_review_for_gland_fill_guidance():
    calc = load_calc_registry().by_id("verpressung_prozent")
    assert calc is not None
    rendered_contract = " ".join((*calc.assumptions, calc.source))
    assert "Nutfüllung" not in rendered_contract
    assert "60–85" not in rendered_contract
    assert "75 %" not in rendered_contract


def test_cascade_edge_pv_consumes_v():
    reg = load_calc_registry()
    pv = reg.by_id("pv_wert")
    v = reg.by_id("umfangsgeschwindigkeit")
    assert v.output.name in pv.input_names  # PV consumes v's output → a real DAG edge


def test_reviewed_without_source_is_error(tmp_path):
    bad = [
        {
            "id": "umfangsgeschwindigkeit",
            "review_state": "reviewed",
            "provenance": ["owner"],
            "validity": {"d1_mm": [1, 1000], "rpm": [0, 60000]},
            "inputs": [
                {"name": "d1_mm", "unit": "mm"},
                {"name": "rpm", "unit": "1/min"},
            ],
            "output": {"name": "v_m_s", "unit": "m/s"},
            "source": "",
        }
    ]
    with pytest.raises(ValueError, match="source"):
        load_calc_registry(_write(tmp_path, bad))


def test_reviewed_without_bound_impl_is_error(tmp_path):
    bad = [
        {
            "id": "unknown_calc",  # not in FORMULAS → no bound code
            "review_state": "reviewed",
            "provenance": ["owner"],
            "source": "x",
            "validity": {"a": [0, 1]},
            "inputs": [{"name": "a", "unit": ""}],
            "output": {"name": "o", "unit": ""},
        }
    ]
    with pytest.raises(ValueError, match="bound implementation"):
        load_calc_registry(_write(tmp_path, bad))


def test_reviewed_without_validity_is_error(tmp_path):
    bad = [
        {
            "id": "umfangsgeschwindigkeit",
            "review_state": "reviewed",
            "provenance": ["owner"],
            "source": "x",
            "validity": {},
            "inputs": [{"name": "d1_mm", "unit": "mm"}],
            "output": {"name": "v_m_s", "unit": "m/s"},
        }
    ]
    with pytest.raises(ValueError, match="validity"):
        load_calc_registry(_write(tmp_path, bad))


def test_draft_def_needs_no_source(tmp_path):
    ok = [
        {
            "id": "draft_calc",
            "review_state": "draft",
            "provenance": [],
            "inputs": [{"name": "a", "unit": ""}],
            "output": {"name": "o", "unit": ""},
        }
    ]
    reg = load_calc_registry(_write(tmp_path, ok))
    assert reg.by_id("draft_calc").review_state == "draft"
    assert not reg.reviewed()
