"""Tests for KB Knowledge Services: FactCardStore, CompoundDecisionMatrix, GateChecker."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ---------------------------------------------------------------------------
# Helpers — build minimal in-memory KB files
# ---------------------------------------------------------------------------

def _make_factcard_kb(tmp_path: Path) -> Path:
    data = {
        "schema_version": "1.3",
        "factcards": [
            {
                "id": "FC-TEST-001",
                "title": "Test PTFE Virgin",
                "material_family": "PTFE",
                "compound_id": "ptfe_virgin",
                "topic_tags": ["chemical_resistance", "food_grade"],
                "properties": {
                    "temp_min_c": -200,
                    "temp_max_c": 260,
                    "pressure_max_bar": 200,
                },
                "chemical_resistance": {"acids_weak": "excellent"},
                "applications": ["static_sealing"],
                "limitations": ["cold_flow"],
                "standards": ["DIN 3869"],
                "food_grade": True,
                "fda_approved": True,
                "answer_template": "PTFE virgin ist chemisch universal beständig.",
                "deterministic_triggers": ["chemical_resistance_query", "food_grade_query"],
            },
            {
                "id": "FC-TEST-002",
                "title": "Test PTFE + 25% Glass",
                "material_family": "PTFE",
                "compound_id": "ptfe_25_glass",
                "topic_tags": ["creep_resistance"],
                "properties": {
                    "temp_min_c": -70,
                    "temp_max_c": 250,
                    "pressure_max_bar": 350,
                },
                "food_grade": False,
                "fda_approved": False,
                "answer_template": "PTFE + 25% Glasfaser verbessert Kriechfestigkeit.",
                "deterministic_triggers": ["high_pressure_static_query"],
            },
        ],
        "gates": [
            {
                "id": "GATE-TEMP-MAX",
                "type": "temperature_max",
                "condition_field": "temperature_max_c",
                "condition_op": "gt",
                "condition_value": 260,
                "action": "hard_block",
                "severity": "critical",
                "message": "PTFE überschreitet 260°C.",
                "applies_to_compounds": ["ptfe_virgin", "ptfe_25_glass"],
            },
            {
                "id": "GATE-FOOD-GRADE",
                "type": "compliance",
                "condition_field": "food_grade_required",
                "condition_op": "eq",
                "condition_value": True,
                "action": "filter",
                "severity": "info",
                "message": "Nur food-grade Typen.",
                "applies_to_compounds": ["ptfe_25_glass"],
                "allowed_compounds": ["ptfe_virgin"],
            },
        ],
    }
    path = tmp_path / "factcards.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _make_matrix_kb(tmp_path: Path) -> Path:
    data = {
        "schema_version": "1.3",
        "matrix": [
            {
                "id": "CDM-001",
                "filler_id": "ptfe_virgin",
                "compound_name": "PTFE virgin",
                "screening_conditions": {
                    "temp_max_c": {"lte": 260},
                    "temp_min_c": {"gte": -200},
                    "pressure_max_bar": {"lte": 200},
                },
                "hard_exclusions": {
                    "medium_ids": ["hf_acid"],
                    "reason": "HF excluded",
                },
                "score": 90,
                "food_grade": True,
                "rationale": "Universal.",
            },
            {
                "id": "CDM-002",
                "filler_id": "ptfe_25_glass",
                "compound_name": "PTFE + 25% Glass",
                "screening_conditions": {
                    "temp_max_c": {"lte": 250},
                    "temp_min_c": {"gte": -70},
                    "pressure_max_bar": {"lte": 350},
                },
                "hard_exclusions": {
                    "medium_ids": ["hf_acid"],
                    "reason": "HF excluded for glass too",
                },
                "score": 82,
                "food_grade": False,
                "rationale": "High pressure.",
            },
        ],
    }
    path = tmp_path / "matrix.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# FactCardStore
# ---------------------------------------------------------------------------

class TestFactCardStore:
    def test_load_from_file(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        assert store.is_loaded
        assert len(store.all_cards()) == 2
        assert len(store.all_gates()) == 2

    def test_missing_file_does_not_crash(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        store = FactCardStore(kb_path=tmp_path / "nonexistent.json")
        assert not store.is_loaded
        assert store.all_cards() == []
        assert store.all_gates() == []

    def test_get_by_id(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        card = store.get_by_id("FC-TEST-001")
        assert card is not None
        assert card["compound_id"] == "ptfe_virgin"

    def test_get_by_id_not_found(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        assert store.get_by_id("NONEXISTENT") is None

    def test_get_by_compound_id(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        card = store.get_by_compound_id("ptfe_25_glass")
        assert card is not None
        assert card["id"] == "FC-TEST-002"

    def test_search_by_topic(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        results = store.search_by_topic("food_grade")
        assert len(results) == 1
        assert results[0]["id"] == "FC-TEST-001"

    def test_search_by_trigger(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        results = store.search_by_trigger("chemical_resistance_query")
        assert len(results) == 1
        assert results[0]["compound_id"] == "ptfe_virgin"

    def test_lookup_property(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        val = store.lookup_property("ptfe_virgin", "temp_max_c")
        assert val == 260

    def test_lookup_property_missing_compound(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        assert store.lookup_property("nonexistent", "temp_max_c") is None

    def test_match_query_to_cards_chemical_keyword(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        results = store.match_query_to_cards("welche chemisch beständigen Werkstoffe gibt es?")
        assert any(c["compound_id"] == "ptfe_virgin" for c in results)

    def test_match_query_food_grade_filter(self, tmp_path: Path):
        from app.services.knowledge.factcard_store import FactCardStore

        path = _make_factcard_kb(tmp_path)
        store = FactCardStore(kb_path=path)
        # food_grade=True must exclude ptfe_25_glass
        results = store.match_query_to_cards(
            "fda zugelassener werkstoff für lebensmittel",
            food_grade=True,
        )
        ids = [c["compound_id"] for c in results]
        assert "ptfe_25_glass" not in ids

    def test_singleton_get_instance(self):
        from app.services.knowledge.factcard_store import FactCardStore

        FactCardStore.reset_instance()
        a = FactCardStore.get_instance()
        b = FactCardStore.get_instance()
        assert a is b
        FactCardStore.reset_instance()


# ---------------------------------------------------------------------------
# CompoundDecisionMatrix
# ---------------------------------------------------------------------------

class TestCompoundDecisionMatrix:
    def test_load_from_file(self, tmp_path: Path):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        path = _make_matrix_kb(tmp_path)
        matrix = CompoundDecisionMatrix(matrix_path=path)
        assert matrix.is_loaded
        assert len(matrix.all_entries()) == 2

    def test_missing_file_returns_empty(self, tmp_path: Path):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        matrix = CompoundDecisionMatrix(matrix_path=tmp_path / "nope.json")
        assert not matrix.is_loaded
        assert matrix.screen({}) == []

    def test_screen_all_pass_when_no_conditions(self, tmp_path: Path):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        path = _make_matrix_kb(tmp_path)
        matrix = CompoundDecisionMatrix(matrix_path=path)
        results = matrix.screen({})
        assert len(results) == 2

    def test_screen_filters_by_temp(self, tmp_path: Path):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        path = _make_matrix_kb(tmp_path)
        matrix = CompoundDecisionMatrix(matrix_path=path)
        # 255°C — exceeds ptfe_25_glass limit (250) but within ptfe_virgin (260)
        results = matrix.screen({"temp_max_c": 255})
        filler_ids = [r["filler_id"] for r in results]
        assert "ptfe_virgin" in filler_ids
        assert "ptfe_25_glass" not in filler_ids

    def test_screen_hard_exclusion_hf_acid(self, tmp_path: Path):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        path = _make_matrix_kb(tmp_path)
        matrix = CompoundDecisionMatrix(matrix_path=path)
        results = matrix.screen({"medium_id": "hf_acid"})
        assert results == []

    def test_screen_sorted_by_score(self, tmp_path: Path):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        path = _make_matrix_kb(tmp_path)
        matrix = CompoundDecisionMatrix(matrix_path=path)
        results = matrix.screen({})
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_screen_specific_filler_id(self, tmp_path: Path):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        path = _make_matrix_kb(tmp_path)
        matrix = CompoundDecisionMatrix(matrix_path=path)
        results = matrix.screen({}, filler_id="ptfe_virgin")
        assert len(results) == 1
        assert results[0]["filler_id"] == "ptfe_virgin"

    def test_singleton(self):
        from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

        CompoundDecisionMatrix.reset_instance()
        a = CompoundDecisionMatrix.get_instance()
        b = CompoundDecisionMatrix.get_instance()
        assert a is b
        CompoundDecisionMatrix.reset_instance()


# ---------------------------------------------------------------------------
# GateChecker
# ---------------------------------------------------------------------------

class TestGateChecker:
    def _make_gates(self) -> List[Dict]:
        return [
            {
                "id": "GATE-TEMP-MAX",
                "condition_field": "temperature_max_c",
                "condition_op": "gt",
                "condition_value": 260,
                "action": "hard_block",
                "severity": "critical",
                "message": "Über 260°C nicht erlaubt.",
                "applies_to_compounds": ["ptfe_virgin"],
            },
            {
                "id": "GATE-FOOD",
                "condition_field": "food_grade_required",
                "condition_op": "eq",
                "condition_value": True,
                "action": "filter",
                "severity": "info",
                "message": "Nur food-grade.",
                "allowed_compounds": ["ptfe_virgin"],
                "applies_to_compounds": ["ptfe_25_glass"],
            },
            {
                "id": "GATE-WARN",
                "condition_field": "temperature_max_c",
                "condition_op": "gt",
                "condition_value": 240,
                "action": "soft_warn",
                "severity": "warning",
                "message": "Über 240°C: Kriechfestigkeit prüfen.",
                "applies_to_compounds": [],
            },
        ]

    def test_no_triggers_below_threshold(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        results = checker.check_all({"temperature_max_c": 200})
        assert all(not r.triggered for r in results)

    def test_hard_block_triggered(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        results = checker.check_all({"temperature_max_c": 280})
        hard = [r for r in results if r.is_hard_block()]
        assert len(hard) == 1
        assert hard[0].gate_id == "GATE-TEMP-MAX"

    def test_warning_triggered(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        results = checker.check_all({"temperature_max_c": 250})
        warnings = [r for r in results if r.is_warning()]
        assert len(warnings) == 1
        assert warnings[0].gate_id == "GATE-WARN"

    def test_has_hard_blockers_true(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        assert checker.has_hard_blockers({"temperature_max_c": 280})

    def test_has_hard_blockers_false(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        assert not checker.has_hard_blockers({"temperature_max_c": 200})

    def test_get_excluded_compounds(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        excluded = checker.get_excluded_compounds({"temperature_max_c": 280})
        assert "ptfe_virgin" in excluded

    def test_get_allowed_compounds_from_filter_gate(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        allowed = checker.get_allowed_compounds({"food_grade_required": True})
        assert "ptfe_virgin" in allowed

    def test_check_gate_by_id(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        result = checker.check_gate("GATE-TEMP-MAX", {"temperature_max_c": 270})
        assert result is not None
        assert result.triggered
        assert result.is_hard_block()

    def test_check_gate_not_found_returns_none(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        assert checker.check_gate("NONEXISTENT", {}) is None

    def test_empty_context_triggers_nothing(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        results = checker.check_all({})
        assert all(not r.triggered for r in results)

    def test_gate_result_to_dict(self):
        from app.services.knowledge.gate_checker import GateChecker

        checker = GateChecker(gates=self._make_gates())
        result = checker.check_gate("GATE-TEMP-MAX", {"temperature_max_c": 270})
        d = result.to_dict()
        assert d["gate_id"] == "GATE-TEMP-MAX"
        assert d["triggered"] is True
        assert d["action"] == "hard_block"


# ---------------------------------------------------------------------------
# Integration: bundled KB files exist and load successfully
# ---------------------------------------------------------------------------

def test_bundled_kb_factcards_load():
    """Bundled factcard KB file must be valid JSON and load at least 3 cards."""
    from app.services.knowledge.factcard_store import FactCardStore

    FactCardStore.reset_instance()
    store = FactCardStore()  # loads from default path
    assert store.is_loaded, "Bundled KB factcard file not found or invalid"
    assert len(store.all_cards()) >= 3
    assert len(store.all_gates()) >= 3


def test_bundled_kb_matrix_loads():
    """Bundled compound matrix KB must load at least 3 entries."""
    from app.services.knowledge.compound_matrix import CompoundDecisionMatrix

    CompoundDecisionMatrix.reset_instance()
    matrix = CompoundDecisionMatrix()  # loads from default path
    assert matrix.is_loaded, "Bundled KB matrix file not found or invalid"
    assert len(matrix.all_entries()) >= 3
