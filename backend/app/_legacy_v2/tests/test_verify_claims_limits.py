"""Tests für _check_limits_claims() — Material × Temp/Druck Post-Check."""
from app._legacy_v2.nodes.answer_subgraph.node_verify_claims import (
    _check_limits_claims,
)


def test_nbr_temp_exceeded_creates_span():
    draft = "NBR ist bei 160°C einsetzbar."
    spans = _check_limits_claims(draft)
    assert len(spans) == 1
    assert spans[0]["reason"] == "material_temp_exceeded"
    assert "120" in spans[0]["expected_value"]  # temp_max_c für NBR


def test_fkm_temp_ok_no_span():
    draft = "FKM ist bei 180°C geeignet."
    spans = _check_limits_claims(draft)
    assert len(spans) == 0  # 180 < 200 → ok


def test_vmq_pressure_exceeded():
    draft = "VMQ bei 120 bar Betriebsdruck."
    spans = _check_limits_claims(draft)
    assert len(spans) == 1
    assert spans[0]["reason"] == "material_pressure_exceeded"
