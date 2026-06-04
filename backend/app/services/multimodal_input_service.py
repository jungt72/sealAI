from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class InputType(str, Enum):
    PHOTO = "photo"
    ARTICLE_NUMBER = "article_number"
    DATASHEET_FRAGMENT = "datasheet_fragment"
    DIMENSIONAL_SKETCH = "dimensional_sketch"
    FREE_TEXT = "free_text"


@dataclass(frozen=True, slots=True)
class IntakeExtraction:
    input_type: InputType
    raw_input_reference: str
    extracted_parameters: Mapping[str, object]
    confidence_per_parameter: Mapping[str, float]
    provenance: str
    extraction_model_version: str
    user_verification_required: bool
    clarification_questions: tuple[str, ...] = ()
    notes: str = ""


class MultimodalInputService:
    def process_article_number(self, raw: str) -> IntakeExtraction:
        dims = _dimension_triple(raw)
        params: dict[str, object] = {}
        confidence: dict[str, float] = {}
        if dims is not None:
            params.update({"shaft.diameter_mm": dims[0], "housing.bore_diameter_mm": dims[1], "seal.width_mm": dims[2]})
            confidence.update({"shaft.diameter_mm": 0.8, "housing.bore_diameter_mm": 0.8, "seal.width_mm": 0.8})
        upper = raw.upper()
        if "BAUSL" in upper or " AS" in upper:
            params["seal_type_hint"] = "din_3760_type_as"
            confidence["seal_type_hint"] = 0.65
        return IntakeExtraction(InputType.ARTICLE_NUMBER, raw, params, confidence, "user_article_number", "article-number-v1", True, ("Please confirm decoded dimensions and seal type.",))

    def process_free_text(self, raw: str) -> IntakeExtraction:
        params: dict[str, object] = {}
        confidence: dict[str, float] = {}
        dims = _dimension_triple(raw)
        if dims is not None:
            params["shaft.diameter_mm"] = dims[0]
            params["housing.bore_diameter_mm"] = dims[1]
            params["seal.width_mm"] = dims[2]
            confidence.update({"shaft.diameter_mm": 0.7, "housing.bore_diameter_mm": 0.7, "seal.width_mm": 0.7})
        rpm = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:rpm|u\.?/?min)", raw, re.I)
        if rpm:
            params["operating.shaft_speed.rpm_nom"] = float(rpm.group(1).replace(",", "."))
            confidence["operating.shaft_speed.rpm_nom"] = 0.7
        return IntakeExtraction(InputType.FREE_TEXT, "inline", params, confidence, "user_free_text", "free-text-v1", True)

    def process_photo(self, raw_reference: str) -> IntakeExtraction:
        return IntakeExtraction(InputType.PHOTO, raw_reference, {}, {}, "user_photo", "photo-placeholder-v1", True, ("Please confirm seal type and dimensions; exact compound and dimensions cannot be inferred without evidence.",), "MVP stores photo evidence but does not claim exact visual engineering truth.")

    def process_datasheet_fragment(self, raw_reference: str) -> IntakeExtraction:
        return IntakeExtraction(InputType.DATASHEET_FRAGMENT, raw_reference, {}, {}, "documented", "datasheet-placeholder-v1", True, ("Please confirm visible table values from the datasheet.",))


def _dimension_triple(text: str) -> tuple[float, float, float] | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)\s*[xX]\s*(\d+(?:[.,]\d+)?)", text)
    if not match:
        return None
    return tuple(float(part.replace(",", ".")) for part in match.groups())  # type: ignore[return-value]
