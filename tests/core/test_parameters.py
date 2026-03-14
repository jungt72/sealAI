"""Tests for ExtractedParameter and RawInputState — CLAUDE.md §5.6 T01–T09."""
import pytest
from pydantic import ValidationError

from core.enums import ExtractionCertainty
from core.parameters import ExtractedParameter, RawInputState


# ---------------------------------------------------------------------------
# T01 – AMBIGUOUS certainty → is_calculable == False
# ---------------------------------------------------------------------------
def test_ambiguous_certainty_not_calculable():
    param = ExtractedParameter[float](
        parsed_value=150.0,
        certainty=ExtractionCertainty.AMBIGUOUS,
    )
    assert param.is_calculable is False


# ---------------------------------------------------------------------------
# T02 – INFERRED + confirmed=False → is_calculable == False
# ---------------------------------------------------------------------------
def test_inferred_unconfirmed_not_calculable():
    param = ExtractedParameter[float](
        parsed_value=95.0,
        certainty=ExtractionCertainty.INFERRED_FROM_CONTEXT,
        confirmed=False,
    )
    assert param.is_calculable is False


# ---------------------------------------------------------------------------
# T03 – INFERRED + confirmed=True → is_calculable == True
# ---------------------------------------------------------------------------
def test_inferred_confirmed_is_calculable():
    param = ExtractedParameter[float](
        parsed_value=95.0,
        certainty=ExtractionCertainty.INFERRED_FROM_CONTEXT,
        confirmed=True,
    )
    assert param.is_calculable is True


# ---------------------------------------------------------------------------
# T04 – EXPLICIT_VALUE + parsed_value=None → is_calculable == False
# ---------------------------------------------------------------------------
def test_explicit_value_none_not_calculable():
    param = ExtractedParameter[float](
        parsed_value=None,
        certainty=ExtractionCertainty.EXPLICIT_VALUE,
    )
    assert param.is_calculable is False


# ---------------------------------------------------------------------------
# T05 – EXPLICIT_VALUE + parsed_value=150.0 → is_calculable == True
# ---------------------------------------------------------------------------
def test_explicit_value_present_is_calculable():
    param = ExtractedParameter[float](
        parsed_value=150.0,
        certainty=ExtractionCertainty.EXPLICIT_VALUE,
    )
    assert param.is_calculable is True


# ---------------------------------------------------------------------------
# T06 – Valid L1 dict with nested ExtractedParameter → parses successfully
# ---------------------------------------------------------------------------
def test_raw_input_state_valid_l1_dict():
    result = RawInputState.model_validate({
        "medium": {
            "raw_text": "Wasser",
            "parsed_value": "Wasser",
            "certainty": "explicit_value",
        }
    })
    assert result.medium is not None
    assert result.medium.parsed_value == "Wasser"
    assert result.medium.certainty == ExtractionCertainty.EXPLICIT_VALUE


# ---------------------------------------------------------------------------
# T07 – Plain string for medium (not ExtractedParameter) → ValidationError
# ---------------------------------------------------------------------------
def test_raw_input_state_plain_string_rejected():
    with pytest.raises(ValidationError):
        RawInputState.model_validate({"medium": "Wasser"})


# ---------------------------------------------------------------------------
# T08 – L2 field pv_value → ValidationError (extra="forbid")
# ---------------------------------------------------------------------------
def test_raw_input_state_l2_field_rejected():
    with pytest.raises(ValidationError):
        RawInputState.model_validate({"pv_value": 42.0})


# ---------------------------------------------------------------------------
# T09 – L4 field hard_stops → ValidationError (extra="forbid")
# ---------------------------------------------------------------------------
def test_raw_input_state_l4_field_rejected():
    with pytest.raises(ValidationError):
        RawInputState.model_validate({"hard_stops": ["too hot"]})
