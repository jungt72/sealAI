"""Capability store (datasheet-derived) — the SEPARATE half of the §3.9 STRUCTURAL firewall. The
``produktspec`` package must NEVER import this module (enforced by the firewall test), so manufacturer
data can never reach the neutral Kandidaten-Spezifikation. Records are MANUFACTURER-STATED
('Herstellerangabe'), reviewed before matching. Claim hygiene: only NUMERIC capability is extracted;
marketing claims (e.g. 'best for all media') are dropped."""

from __future__ import annotations

from dataclasses import dataclass

# Numeric capability fields accepted from a datasheet; everything else (free-text marketing) is dropped.
_NUMERIC = ("druck_bar_max", "geschw_ms_max", "temp_c_max")


@dataclass(frozen=True)
class CapabilityRecord:
    hersteller_id: str
    familie: str
    bauform: str = ""
    werkstoff: str = ""
    druck_bar_max: float | None = None
    geschw_ms_max: float | None = None
    temp_c_max: float | None = None
    quelle: str = ""  # datasheet id
    reifegrad: str = "draft_llm_extracted"
    herstellerangabe: bool = (
        True  # structural label — capability is vendor-stated, NEVER neutral fact
    )


def extract_capability(hersteller_id: str, familie: str, raw: dict) -> CapabilityRecord:
    """Claim hygiene (Konzept v2 §7): take ONLY numeric capability + the structured bauform/werkstoff;
    marketing claims are silently dropped — they never enter the store."""
    nums = {k: float(raw[k]) for k in _NUMERIC if isinstance(raw.get(k), (int, float))}
    return CapabilityRecord(
        hersteller_id=hersteller_id,
        familie=familie,
        bauform=str(raw.get("bauform", "")),
        werkstoff=str(raw.get("werkstoff", "")),
        quelle=str(raw.get("quelle", "")),
        **nums,
    )


class InProcessCapabilityStore:
    def __init__(self) -> None:
        self._recs: list[CapabilityRecord] = []

    def add(self, rec: CapabilityRecord) -> None:
        self._recs.append(rec)

    def list_for(self, familie: str) -> tuple[CapabilityRecord, ...]:
        return tuple(r for r in self._recs if r.familie == familie)
