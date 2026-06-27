"""Hersteller-PARTNER layer (owner business model) — the paid-membership + company + lead-routing
dimension, DELIBERATELY SEPARATE from the neutral ``HerstellerFaehigkeit`` (capability).

WHY SEPARATE (preserves the §3.9 neutrality keystone): payment/partner status lives HERE, never on a
capability entry (``hersteller.py`` structurally rejects any payment field on a capability — that guard
stays). Membership gates POOL INCLUSION only; the SELECTION RANKING stays capability-by-fit, computed by
the neutral capability store. So "Auswahl unabhängig von der Zahlung" holds: payment decides WHO is in
the pool, never WHO ranks higher (no pay-to-rank). The pool is shown TRANSPARENTLY as paying partners.

Pure data + selection logic — no LLM, no network. The persistence is pluggable behind ``PartnerRegistry``
(an in-process impl here for eval/CI; a Postgres adapter — the dashboard-editable prod store — follows,
mirroring the memory/store config-gated pattern).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sealai_v2.knowledge.hersteller import HerstellerFaehigkeit


@dataclass(frozen=True)
class HerstellerPartner:
    """A manufacturer's PARTNER membership + company profile + lead routing. Linked to the neutral
    capability entries by ``hersteller`` (the company name). ``plan`` is billing metadata ONLY — it is
    NEVER read by the selection (no pay-to-rank). ``aktiv`` gates pool membership."""

    hersteller: str  # links to HerstellerFaehigkeit.hersteller
    firmenname: str
    aktiv: bool  # active paying partner → included in the pool (else hidden)
    lead_email: str  # where the structured RFQ briefing is routed
    website: str = ""
    beschreibung: str = ""
    standort: str = ""
    kontakt_oeffentlich: str = ""
    partner_seit: str = ""
    plan: str = ""  # billing tier — metadata only, NEVER a selection/ranking input


@dataclass(frozen=True)
class PartnerMatch:
    """One selected partner = a neutral capability match (fit-ranked) + its partner record. The order
    of a ``PartnerMatch`` list is the CAPABILITY fit order — payment never reorders it."""

    faehigkeit: HerstellerFaehigkeit
    partner: HerstellerPartner


@runtime_checkable
class PartnerRegistry(Protocol):
    """The partner-membership store seam. ``get`` resolves a company's partner record (or None);
    ``list_active`` lists active partners (for the dashboard / pool overview). Persistence is the
    impl's concern (in-process for CI, Postgres for the dashboard-editable prod path)."""

    def get(self, hersteller: str) -> HerstellerPartner | None: ...
    def list_active(self) -> tuple[HerstellerPartner, ...]: ...


class InProcessPartnerRegistry:
    """In-memory ``PartnerRegistry`` (CI/eval + the deferred-DB fallback). Keyed by company name."""

    def __init__(self, partners: tuple[HerstellerPartner, ...] = ()) -> None:
        self._by_name = {p.hersteller: p for p in partners}

    def get(self, hersteller: str) -> HerstellerPartner | None:
        return self._by_name.get(hersteller)

    def list_active(self) -> tuple[HerstellerPartner, ...]:
        return tuple(p for p in self._by_name.values() if p.aktiv)


def select_partners(
    capability_matches: tuple[HerstellerFaehigkeit, ...],
    registry: PartnerRegistry,
) -> tuple[PartnerMatch, ...]:
    """Given the NEUTRAL, fit-ranked capability matches (from the capability store) + the partner
    registry, return the matches that are ACTIVE partners — PRESERVING the capability fit order.

    Payment NEVER reorders: this only FILTERS to the paying pool, walking ``capability_matches`` in
    their given (capability-by-fit) order. That is the structural no-pay-to-rank guarantee at the
    selection layer (the keystone's analogue for the partner pool)."""
    out: list[PartnerMatch] = []
    for f in capability_matches:  # already fit-ordered by the neutral capability store
        p = registry.get(f.hersteller)
        if p is not None and p.aktiv:
            out.append(PartnerMatch(faehigkeit=f, partner=p))
    return tuple(out)
