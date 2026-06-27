"""§3.9 STRUCTURAL firewall (Konzept v2/v3) — proven, not promised: the produktspec package never imports
the capability package; the Kandidaten-Spezifikation has no capability input (invariant to manufacturer
data); capability records are labelled 'Herstellerangabe' + marketing claims are dropped (claim hygiene)."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import sealai_v2.knowledge.produktspec as produktspec
from sealai_v2.knowledge.capability.store import (
    CapabilityRecord,
    InProcessCapabilityStore,
    extract_capability,
)
from sealai_v2.knowledge.produktspec.contracts import Fall, MediumSource
from sealai_v2.knowledge.produktspec.spec_service import kandidaten_spezifikation

_CAP_IMPORT = re.compile(r"^\s*(?:from|import)\s+\S*capability", re.MULTILINE)


def test_produktspec_never_imports_capability():
    pkg_dir = Path(produktspec.__path__[0])
    offenders = [
        f.name
        for f in pkg_dir.glob("*.py")
        if _CAP_IMPORT.search(f.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"produktspec must not import capability: {offenders}"


def test_spec_is_invariant_to_capability_data():
    # No capability input → manufacturer data cannot influence the neutral spec; deterministic.
    assert list(inspect.signature(kandidaten_spezifikation).parameters) == ["fall"]
    fall = Fall(
        medium="Mineralöl",
        medium_class="mineraloel",
        medium_source=MediumSource.EXACT,
        temperatur_c=90.0,
        druck_bar=0.0,
        geschwindigkeit_ms=11.0,
        verschmutzung=False,
        schmierung_ok=True,
        belueftet=True,
    )
    assert kandidaten_spezifikation(fall) == kandidaten_spezifikation(fall)


def test_capability_record_is_labelled_herstellerangabe():
    assert (
        CapabilityRecord(hersteller_id="acme", familie="RWDR").herstellerangabe is True
    )


def test_claim_hygiene_drops_marketing_keeps_numeric():
    rec = extract_capability(
        "acme",
        "RWDR",
        {"druck_bar_max": 0.8, "werbung": "best for all media", "bauform": "AS"},
    )
    assert rec.druck_bar_max == 0.8 and rec.bauform == "AS"
    assert not hasattr(rec, "werbung") and rec.herstellerangabe is True


def test_capability_store_is_independent():
    store = InProcessCapabilityStore()
    store.add(CapabilityRecord(hersteller_id="acme", familie="RWDR", bauform="AS"))
    assert len(store.list_for("RWDR")) == 1 and store.list_for("O-Ring") == ()
