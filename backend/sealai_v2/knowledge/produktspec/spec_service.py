"""Produktspec entry point. NEUTRAL by construction: the Kandidaten-Spezifikation is a pure function of
(Fall, neutral rules). This module MUST NOT import sealai_v2.knowledge.capability — the §3.9 structural
firewall (enforced by the firewall test). The spec is therefore invariant to any manufacturer/capability
data (proven by the hash-invariance test)."""

from __future__ import annotations

from sealai_v2.knowledge.produktspec.contracts import (
    Fall,
    KandidatenSpec,
    Kritikalitaet,
)
from sealai_v2.knowledge.produktspec.familie_rwdr import RWDR_KERNEL
from sealai_v2.knowledge.produktspec.kernel import resolve

_KERNELS = {"RWDR": RWDR_KERNEL}


def _no_knowledge(familie: str) -> KandidatenSpec:
    """Empty-knowledge: no curated family kernel → NO bauform invention, only an honest defer."""
    return KandidatenSpec(
        familie=familie,
        kritikalitaet=Kritikalitaet.CAUTION,
        bauform_din=None,
        werkstoff=None,
        lippen=None,
        masse=(),
        begruendung=(),
        varianten=(),
        konflikte=(),
        offene_punkte=(
            f"Für die Familie '{familie}' liegt noch kein geprüftes Auswahlwissen vor.",
        ),
        defer_gruende=(
            "Kein kuratiertes Familienwissen — keine Kandidaten-Spezifikation.",
        ),
        teil_screening=True,
        freigegeben=False,
    )


def kandidaten_spezifikation(fall: Fall, familie: str = "RWDR") -> KandidatenSpec:
    kernel = _KERNELS.get(familie)
    if kernel is None:
        return _no_knowledge(familie)
    return resolve(fall, kernel)
