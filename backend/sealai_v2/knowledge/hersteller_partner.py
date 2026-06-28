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


@dataclass(frozen=True)
class HerstellerPartner:
    """A manufacturer's PARTNER membership + company profile + lead routing. Linked to the neutral
    capability entries by ``hersteller`` (the company name). ``plan`` is billing metadata ONLY — it is
    NEVER read by the selection (no pay-to-rank). ``aktiv`` gates pool membership."""

    hersteller: str  # stable company key (id)
    firmenname: str
    aktiv: bool  # active paying partner → included in the pool (else hidden)
    lead_email: str  # where the structured RFQ briefing is routed
    website: str = ""
    beschreibung: str = ""
    standort: str = ""
    kontakt_oeffentlich: str = ""
    partner_seit: str = ""
    plan: str = ""  # billing tier — metadata only, NEVER a selection/ranking input
    # Capability (what the partner makes) — on the dashboard-editable record so ONE form per company.
    # The SELECTION ranks ONLY on these (fit), never on ``plan``/``aktiv`` (no pay-to-rank).
    werkstoffe: tuple[str, ...] = ()
    bauformen: tuple[str, ...] = ()
    groessen: str = ""
    zertifikate: tuple[str, ...] = ()


def _fit_score(
    p: HerstellerPartner, *, material: str | None, bauform: str | None
) -> int:
    """Capability-fit score — material + bauform overlap ONLY. Deliberately ignores ``plan``/``aktiv``
    (the structural no-pay-to-rank guarantee at the ranking layer; locked by a test)."""
    ml = (material or "").lower()
    bl = (bauform or "").lower()
    score = 0
    if ml and any(
        ml == w.lower() or ml in w.lower() or w.lower() in ml for w in p.werkstoffe
    ):
        score += 2
    if bl and any(
        bl == b.lower() or bl in b.lower() or b.lower() in bl for b in p.bauformen
    ):
        score += 2
    return score


def rank_partners(
    partners: tuple[HerstellerPartner, ...],
    *,
    material: str | None = None,
    bauform: str | None = None,
) -> tuple[HerstellerPartner, ...]:
    """Rank ACTIVE partners by capability fit to the spec, strongest first (alphabetical tie-break for
    determinism). Payment (``plan``) is NEVER an input — neutrality is structural here too. Partners
    with zero fit are dropped when a spec is given; with no spec, all active partners (alpha order)."""
    active = [p for p in partners if p.aktiv]
    scored = [(_fit_score(p, material=material, bauform=bauform), p) for p in active]
    if material or bauform:
        scored = [(s, p) for s, p in scored if s > 0]
    scored.sort(key=lambda sp: (-sp[0], sp[1].firmenname.lower()))
    return tuple(p for _s, p in scored)


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

    def list_all(self) -> tuple[HerstellerPartner, ...]:
        return tuple(self._by_name.values())

    def upsert(self, p: HerstellerPartner) -> None:
        self._by_name[p.hersteller] = p

    def delete(self, hersteller: str) -> bool:
        return self._by_name.pop(hersteller, None) is not None
