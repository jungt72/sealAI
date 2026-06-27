"""§3.9 STRUCTURAL firewall (Konzept v2 §7) — proven, not promised:
- the produktspec package never imports the capability package (no path for vendor data to reach the spec);
- the Kandidaten-Spezifikation is invariant to capability data (no capability parameter; deterministic);
- a neutral source can never be a vendor claim (SourceType has no vendor member);
- capability data is structurally labelled 'Herstellerangabe' + marketing claims are dropped (claim hygiene)."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import sealai_v2.knowledge.produktspec as produktspec

# An actual import line referencing the capability package (not a doc-comment mention of the word).
_CAP_IMPORT = re.compile(r"^\s*(?:from|import)\s+\S*capability", re.MULTILINE)
from sealai_v2.knowledge.capability.store import (
    CapabilityRecord,
    InProcessCapabilityStore,
    extract_capability,
)
from sealai_v2.knowledge.produktspec.contracts import Fall, SourceType
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation


def test_produktspec_never_imports_capability():
    pkg_dir = Path(produktspec.__path__[0])
    offenders = [
        f.name for f in pkg_dir.glob("*.py") if _CAP_IMPORT.search(f.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"produktspec must not import capability: {offenders}"


def test_spec_is_invariant_to_capability_data():
    # The entry point takes ONLY (fall, familie) — there is no capability input, so manufacturer data
    # cannot influence the neutral spec; the result is deterministic.
    params = list(inspect.signature(kandidaten_spezifikation).parameters)
    assert params == ["fall", "familie"]
    fall = Fall(medium="Öl", temperatur_c=150, druck_bar=0.3, welle_d_mm=50, verschmutzung=True)
    assert kandidaten_spezifikation(fall) == kandidaten_spezifikation(fall)


def test_no_vendor_claim_neutral_source_type():
    # multi_vendor_common (generic across vendors) is fine; a SINGLE-vendor claim must never be a neutral source.
    assert "vendor_claim" not in [s.value for s in SourceType]


def test_capability_record_is_labelled_herstellerangabe():
    rec = CapabilityRecord(hersteller_id="acme", familie="RWDR")
    assert rec.herstellerangabe is True


def test_claim_hygiene_drops_marketing_keeps_numeric():
    rec = extract_capability(
        "acme",
        "RWDR",
        {"druck_bar_max": 0.8, "werbung": "best for all media", "bauform": "AS"},
    )
    assert rec.druck_bar_max == 0.8 and rec.bauform == "AS"
    assert not hasattr(rec, "werbung")  # marketing claim never stored
    assert rec.herstellerangabe is True


def test_capability_store_is_independent():
    store = InProcessCapabilityStore()
    store.add(CapabilityRecord(hersteller_id="acme", familie="RWDR", bauform="AS"))
    assert len(store.list_for("RWDR")) == 1 and store.list_for("O-Ring") == ()
