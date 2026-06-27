"""Produktspec v3.1 entry. NEUTRAL by construction: the Kandidaten-Spezifikation is a pure function of the
Fall + the neutral RWDR rules. MUST NOT import sealai_v2.knowledge.capability (firewall test); the entry
takes no capability input, so the result is invariant to any manufacturer data."""

from __future__ import annotations

from sealai_v2.knowledge.produktspec.contracts import Fall, KandidatenSpec
from sealai_v2.knowledge.produktspec.kernel import resolve


def kandidaten_spezifikation(fall: Fall) -> KandidatenSpec:
    return resolve(fall)
