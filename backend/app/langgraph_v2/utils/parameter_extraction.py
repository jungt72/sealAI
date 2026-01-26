# backend/app/langgraph_v2/utils/parameter_extraction.py
from __future__ import annotations

import re
from typing import Dict, Union

Number = Union[float, str]

# Matches standard references like:
# - DIN 3761
# - DIN EN 3761
# - ISO 1234
# - EN 10204
# - VDI 2230
# - ASTM D2000
_STANDARD_REF_RE = re.compile(
    r"\b(?:din|iso|en|vdi|astm)(?:\s+en)?\s*[a-z]?\s*[-/]?\s*\d{2,6}\b",
    re.IGNORECASE,
)

# Basic number pattern: 12, 12.3, 12,3
_NUM_RE = r"(-?\d+(?:[.,]\d+)?)"


def _to_float(raw: str) -> float:
    raw = (raw or "").strip().replace(",", ".")
    return float(raw)


def _mask_standard_references(text: str) -> str:
    # Replace standard refs with placeholder tokens to prevent accidental numeric extraction
    return _STANDARD_REF_RE.sub(" STANDARD_REF ", text or "")


def extract_parameters_from_text(text: str) -> Dict[str, Number]:
    """
    Best-effort extraction of technical parameters from user text.

    Key rule:
    - Never treat standard numbers like "DIN 3761" as numeric parameters.

    Currently extracted:
    - pressure_bar
    - temperature_C
    - speed_rpm

    Notes:
    - speed_rpm is extracted ONLY if unit context (rpm/u/min/1/min) exists
      or explicit speed context keywords exist ("Drehzahl", "n=").
    """
    params: Dict[str, Number] = {}
    if not text:
        return params

    original = text
    masked = _mask_standard_references(original)
    lowered = masked.lower()

    # -------------------------
    # pressure_bar
    # -------------------------
    # Priority 1: "Druck ging von 10 auf 7" / "von 10 bis 7"
    # -> take the target value after "auf/bis"
    if "druck" in lowered:
        m_range = re.search(
            rf"\bdruck\b.*?\bvon\b\s*{_NUM_RE}\s*(?:bar)?\s*.*?\b(?:auf|bis)\b\s*{_NUM_RE}\s*(?:bar)?\b",
            lowered,
        )
        if m_range:
            try:
                # group(2) is the target number (after auf/bis)
                params["pressure_bar"] = _to_float(m_range.group(2))
            except ValueError:
                pass
        else:
            # Priority 2: explicit "7 bar"
            m = re.search(rf"{_NUM_RE}\s*(?:bar)\b", lowered)
            if m:
                try:
                    params["pressure_bar"] = _to_float(m.group(1))
                except ValueError:
                    pass
            else:
                # Priority 3: phrases like "Betriebsdruck auf 7" / "Druck ... auf 7"
                # IMPORTANT: do NOT include "von" here (otherwise "von 10 auf 7" would capture 10).
                m2 = re.search(rf"\b(?:auf|bei|ist|liegt|war)\s+{_NUM_RE}\b", lowered)
                if m2:
                    try:
                        params["pressure_bar"] = _to_float(m2.group(1))
                    except ValueError:
                        pass
    else:
        # Even without explicit "druck" keyword, accept explicit "7 bar"
        m = re.search(rf"{_NUM_RE}\s*(?:bar)\b", lowered)
        if m:
            try:
                params["pressure_bar"] = _to_float(m.group(1))
            except ValueError:
                pass

    # -------------------------
    # temperature_C
    # -------------------------
    # explicit: "80°C" / "80 C"
    mt = re.search(rf"{_NUM_RE}\s*°?\s*c\b", lowered)
    if mt:
        try:
            params["temperature_C"] = _to_float(mt.group(1))
        except ValueError:
            pass

    # -------------------------
    # speed_rpm
    # -------------------------
    # 1) Unit-based extraction (preferred)
    # e.g. "3761 rpm", "1500 u/min", "1500 1/min"
    ms = re.search(
        rf"{_NUM_RE}\s*(?:rpm|u/min|1/min|1\s*/\s*min|umdrehungen(?:\s*/\s*min)?)\b",
        lowered,
    )
    if ms:
        try:
            params["speed_rpm"] = _to_float(ms.group(1))
        except ValueError:
            pass
    else:
        # 2) Context-based extraction without explicit unit
        # Only if there is an explicit speed keyword in the text.
        # Examples:
        # - "Drehzahl 1500"
        # - "n=1500"
        # But NOT: "DIN 3761" (masked already)
        has_speed_context = bool(
            re.search(r"\bdrehzahl\b", lowered)
            or re.search(r"\bn\s*=\s*-?\d", lowered)
            or re.search(r"\bnmax\b|\bn_min\b|\bnenn\b", lowered)
        )
        if has_speed_context:
            # Try to capture the first plausible number after the speed cue.
            ms2 = re.search(rf"(?:\bdrehzahl\b|\bn\s*=\s*)(?:\D{{0,10}}){_NUM_RE}\b", lowered)
            if not ms2:
                ms2 = re.search(rf"\bdrehzahl\b\D{{0,20}}{_NUM_RE}\b", lowered)
            if ms2:
                try:
                    params["speed_rpm"] = _to_float(ms2.group(1))
                except ValueError:
                    pass

    return params


__all__ = ["extract_parameters_from_text"]
