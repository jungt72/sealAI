"""Tests for backend/app/services/rag/state.py — WorkingProfile, ErrorInfo, RAGState."""

from __future__ import annotations

import operator
import time

import pytest
from pydantic import ValidationError

from app.services.rag.state import ErrorInfo, RAGState, WorkingProfile


# ═══════════════════════════════════════════════════════════════════════════
# WorkingProfile
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkingProfileConstruction:
    def test_empty_profile(self):
        p = WorkingProfile()
        assert p.medium is None
        assert p.pressure_max_bar is None
        assert p.cyclic_load is False

    def test_full_profile(self):
        p = WorkingProfile(
            medium="steam",
            medium_detail="saturated",
            pressure_max_bar=40.0,
            pressure_min_bar=1.0,
            temperature_max_c=250.0,
            temperature_min_c=20.0,
            flange_standard="EN 1514-1",
            flange_dn=100,
            flange_pn=40,
            flange_class=300,
            bolt_count=8,
            bolt_size="M16",
            cyclic_load=True,
            emission_class="TA-Luft",
            industry_sector="petrochemical",
        )
        assert p.medium == "steam"
        assert p.pressure_max_bar == 40.0
        assert p.flange_class == 300
        assert p.bolt_count == 8
        assert p.cyclic_load is True

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            WorkingProfile(unknown_field="x")


# ═══════════════════════════════════════════════════════════════════════════
# WorkingProfile — Field Validators
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkingProfilePressureValidation:
    def test_negative_pressure_max_rejected(self):
        with pytest.raises(ValidationError, match="pressure_max_bar.*>= 0"):
            WorkingProfile(pressure_max_bar=-1.0)

    def test_negative_pressure_min_rejected(self):
        with pytest.raises(ValidationError, match="pressure_min_bar.*>= 0"):
            WorkingProfile(pressure_min_bar=-5.0)

    def test_zero_pressure_allowed(self):
        p = WorkingProfile(pressure_max_bar=0.0, pressure_min_bar=0.0)
        assert p.pressure_max_bar == 0.0
        assert p.pressure_min_bar == 0.0


class TestWorkingProfileTemperatureValidation:
    def test_below_absolute_zero_max_rejected(self):
        with pytest.raises(ValidationError, match="temperature_max_c.*>= -273.15"):
            WorkingProfile(temperature_max_c=-300.0)

    def test_below_absolute_zero_min_rejected(self):
        with pytest.raises(ValidationError, match="temperature_min_c.*>= -273.15"):
            WorkingProfile(temperature_min_c=-274.0)

    def test_absolute_zero_allowed(self):
        p = WorkingProfile(temperature_min_c=-273.15)
        assert p.temperature_min_c == -273.15


class TestWorkingProfileCrossFieldValidation:
    def test_pressure_min_gt_max_rejected(self):
        with pytest.raises(ValidationError, match="pressure_min_bar.*<= pressure_max_bar"):
            WorkingProfile(pressure_min_bar=50.0, pressure_max_bar=10.0)

    def test_temperature_min_gt_max_rejected(self):
        with pytest.raises(ValidationError, match="temperature_min_c.*<= temperature_max_c"):
            WorkingProfile(temperature_min_c=100.0, temperature_max_c=20.0)

    def test_equal_min_max_allowed(self):
        p = WorkingProfile(pressure_min_bar=10.0, pressure_max_bar=10.0)
        assert p.pressure_min_bar == p.pressure_max_bar

    def test_only_min_set_no_cross_check(self):
        p = WorkingProfile(pressure_min_bar=50.0)
        assert p.pressure_min_bar == 50.0
        assert p.pressure_max_bar is None


class TestWorkingProfileFlangeValidation:
    def test_flange_dn_zero_rejected(self):
        with pytest.raises(ValidationError, match="flange_dn.*> 0"):
            WorkingProfile(flange_dn=0)

    def test_flange_pn_negative_rejected(self):
        with pytest.raises(ValidationError, match="flange_pn.*> 0"):
            WorkingProfile(flange_pn=-10)

    def test_invalid_flange_class_rejected(self):
        with pytest.raises(ValidationError, match="flange_class must be one of"):
            WorkingProfile(flange_class=200)

    def test_valid_flange_classes(self):
        for cls in (150, 300, 600, 900, 1500, 2500):
            p = WorkingProfile(flange_class=cls)
            assert p.flange_class == cls


class TestWorkingProfileBoltValidation:
    def test_odd_bolt_count_rejected(self):
        with pytest.raises(ValidationError, match="bolt_count must be even"):
            WorkingProfile(bolt_count=7)

    def test_zero_bolt_count_rejected(self):
        with pytest.raises(ValidationError, match="bolt_count must be > 0"):
            WorkingProfile(bolt_count=0)

    def test_even_bolt_count_allowed(self):
        p = WorkingProfile(bolt_count=12)
        assert p.bolt_count == 12


# ═══════════════════════════════════════════════════════════════════════════
# WorkingProfile — String-to-Float Coercion
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkingProfileCoercion:
    def test_string_pressure_coerced(self):
        p = WorkingProfile(pressure_max_bar="25.5")
        assert p.pressure_max_bar == 25.5

    def test_german_comma_pressure(self):
        p = WorkingProfile(pressure_max_bar="25,5")
        assert p.pressure_max_bar == 25.5

    def test_string_temperature_coerced(self):
        p = WorkingProfile(temperature_max_c="180")
        assert p.temperature_max_c == 180.0

    def test_empty_string_becomes_none(self):
        p = WorkingProfile(pressure_max_bar="  ")
        assert p.pressure_max_bar is None

    def test_non_numeric_string_rejected(self):
        with pytest.raises(ValidationError, match="must be a number"):
            WorkingProfile(pressure_max_bar="abc")


# ═══════════════════════════════════════════════════════════════════════════
# WorkingProfile — Helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkingProfileHelpers:
    def test_as_dict_excludes_none(self):
        p = WorkingProfile(medium="water", pressure_max_bar=10.0)
        d = p.as_dict()
        assert "medium" in d
        assert "pressure_max_bar" in d
        assert "temperature_max_c" not in d
        # cyclic_load is False (non-None) so it should be present
        assert "cyclic_load" in d

    def test_coverage_ratio_empty(self):
        p = WorkingProfile()
        assert p.coverage_ratio() == 0.0

    def test_coverage_ratio_partial(self):
        p = WorkingProfile(medium="oil", pressure_max_bar=10.0, temperature_max_c=80.0)
        ratio = p.coverage_ratio()
        # 3 out of 15 fields filled (cyclic_load=False is default, not counted)
        assert ratio == pytest.approx(3.0 / 15.0)

    def test_coverage_ratio_full(self):
        p = WorkingProfile(
            medium="steam",
            medium_detail="saturated",
            pressure_max_bar=40.0,
            pressure_min_bar=1.0,
            temperature_max_c=250.0,
            temperature_min_c=20.0,
            flange_standard="EN 1514-1",
            flange_dn=100,
            flange_pn=40,
            flange_class=300,
            bolt_count=8,
            bolt_size="M16",
            cyclic_load=True,
            emission_class="TA-Luft",
            industry_sector="petrochemical",
        )
        assert p.coverage_ratio() == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════════════
# ErrorInfo
# ═══════════════════════════════════════════════════════════════════════════


class TestErrorInfo:
    def test_defaults(self):
        before = time.time()
        err = ErrorInfo(code="NODE_TIMEOUT", message="Node timed out")
        after = time.time()

        assert err.code == "NODE_TIMEOUT"
        assert err.message == "Node timed out"
        assert err.node is None
        assert err.recoverable is True
        assert err.details == {}
        assert before <= err.timestamp <= after

    def test_full_construction(self):
        err = ErrorInfo(
            code="RAG_EMPTY",
            message="No chunks found",
            node="rag_support_node",
            recoverable=False,
            details={"collection": "sealai_knowledge", "query": "NBR"},
            timestamp=1000.0,
        )
        assert err.node == "rag_support_node"
        assert err.recoverable is False
        assert err.details["collection"] == "sealai_knowledge"
        assert err.timestamp == 1000.0

    def test_round_trip(self):
        err = ErrorInfo(code="TEST", message="test error", node="test_node")
        d = err.model_dump()
        err2 = ErrorInfo(**d)
        assert err2.code == err.code
        assert err2.message == err.message
        assert err2.node == err.node

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError, match="extra"):
            ErrorInfo(code="X", message="x", severity="high")


# ═══════════════════════════════════════════════════════════════════════════
# RAGState (TypedDict)
# ═══════════════════════════════════════════════════════════════════════════


class TestRAGStateTypeStructure:
    """Verify that RAGState annotations have operator.add reducers on list fields."""

    def test_list_fields_have_operator_add(self):
        import typing
        hints = typing.get_type_hints(RAGState, include_extras=True)
        for field_name in ("messages", "sources", "sealing_type_results", "errors"):
            annotation = hints[field_name]
            # Annotated types expose __metadata__
            assert hasattr(annotation, "__metadata__"), f"{field_name} should be Annotated"
            assert operator.add in annotation.__metadata__, (
                f"{field_name} should have operator.add reducer"
            )

    def test_scalar_fields_present(self):
        hints = RAGState.__annotations__
        for field_name in ("calculation_result", "error_state", "session_id", "tenant_id", "profile"):
            assert field_name in hints, f"{field_name} missing from RAGState"

    def test_operator_add_concatenation(self):
        """Simulate the reducer behavior: operator.add on lists."""
        existing = ["msg1"]
        update = ["msg2", "msg3"]
        result = operator.add(existing, update)
        assert result == ["msg1", "msg2", "msg3"]

    def test_rag_state_as_dict_literal(self):
        """RAGState can be used as a plain dict (TypedDict contract)."""
        state: RAGState = {
            "messages": ["hello"],
            "sources": [],
            "sealing_type_results": [],
            "errors": [],
            "calculation_result": None,
            "error_state": None,
            "session_id": "sess-1",
            "tenant_id": "tenant-a",
            "profile": None,
        }
        assert state["session_id"] == "sess-1"
        assert state["messages"] == ["hello"]

    def test_rag_state_with_models(self):
        """RAGState works with WorkingProfile and ErrorInfo instances."""
        profile = WorkingProfile(medium="water", pressure_max_bar=10.0)
        error = ErrorInfo(code="TEST", message="test")
        state: RAGState = {
            "messages": [],
            "sources": [],
            "sealing_type_results": [],
            "errors": [error],
            "calculation_result": {"safety_factor": 2.5},
            "error_state": error,
            "session_id": "s1",
            "tenant_id": "t1",
            "profile": profile,
        }
        assert state["profile"].medium == "water"
        assert state["errors"][0].code == "TEST"
        assert state["calculation_result"]["safety_factor"] == 2.5
