"""Hersteller-Fähigkeiten — the §7 Dim. 6 knowledge dimension (Produkt-Konzept §7, Schema §5.3):
who makes what (werkstoffe / bauformen / groessen / zertifikate), owner-reviewed, queryable.
Feeds the **Alternativen/Hersteller** operation (Modus F) and the "Hersteller wählen" step.

NEUTRALITY IS SACRED (Produkt-Konzept §3.9 — no pay-to-rank): selection + ordering are by
CAPABILITY ONLY. The schema has NO payment/ranking/sponsored field, and the query orders by
capability-match completeness then a deterministic alphabetical tie-break — never by anything
that could encode payment. The whole product value rests on the user's trust; pay-to-rank would
destroy it. Non-negotiable, enforced structurally (no rank field exists to set).

Same two-review-state + circularity discipline as the other dimensions (build-spec §8): a
``reviewed`` entry must name an owner/trap provenance or a primary source; a ``draft`` entry is
flag-only. The seed ships EMPTY — manufacturer capability data is OWNER-PROVIDED market truth
(Produkt-Konzept §8), specific + changeable + neutrality-critical, NOT model-generated. Until the
owner curates it, Modus F honestly reports "no grounded manufacturer data" and gives only the
neutral, capability-based selection approach. Pure data + a typed loader — no LLM, no network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.security.tenant import TenantContext, require_tenant

_SEED_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _SEED_DIR / "hersteller_seed.json"
_REVIEW_STATES = ("reviewed", "draft")
_REVIEWED_PROV_PREFIXES = (
    "trap-correct:",
    "trap:",
    "owner:",
    "eval:",
    "fk-",
    "fachkarte:",
)


@dataclass(frozen=True)
class HerstellerFaehigkeit:
    """One reviewed/draft manufacturer-capability entry (Schema §5.3) — NEUTRAL: what the
    manufacturer can make, no payment/ranking field anywhere."""

    id: str
    hersteller: str
    werkstoffe: tuple[str, ...]
    bauformen: tuple[str, ...]
    groessen: str  # qualitative size range, or "" — kept as text (no engineering number claim)
    zertifikate: tuple[str, ...]
    review_state: str
    provenance: tuple[str, ...]
    sources: tuple[str, ...] = ()

    @property
    def reviewed(self) -> bool:
        return self.review_state == "reviewed"


@dataclass(frozen=True)
class HerstellerCatalog:
    faehigkeiten: tuple[HerstellerFaehigkeit, ...]
    version: str = ""
    source: str = ""

    def by_id(self, fid: str) -> HerstellerFaehigkeit | None:
        for f in self.faehigkeiten:
            if f.id == fid:
                return f
        return None


def _is_reviewed_prov(provenance: tuple[str, ...]) -> bool:
    return any(p.lower().startswith(_REVIEWED_PROV_PREFIXES) for p in provenance)


def _entry(raw: dict) -> HerstellerFaehigkeit:
    fid = str(raw["id"])
    state = str(raw.get("review_state", "")).strip()
    if state not in _REVIEW_STATES:
        raise ValueError(f"{fid}: review_state {state!r} not in {_REVIEW_STATES}")
    hersteller = str(raw.get("hersteller", "")).strip()
    if not hersteller:
        raise ValueError(f"{fid}: hersteller is mandatory")
    # neutrality keystone: no payment/ranking field may exist on a capability entry
    for forbidden in (
        "rank",
        "ranking",
        "priority",
        "sponsored",
        "bezahlt",
        "paid",
        "tier",
    ):
        if forbidden in raw:
            raise ValueError(
                f"{fid}: forbidden field {forbidden!r} — Hersteller-Auswahl ist nach Fähigkeit, "
                f"NIE nach Bezahlung (§3.9 kein pay-to-rank)"
            )
    provenance = tuple(str(p) for p in raw.get("provenance", []))
    if not provenance:
        raise ValueError(f"{fid}: provenance is mandatory (owner-grounding audit)")
    sources = tuple(str(s) for s in raw.get("sources", []))
    if state == "reviewed" and not (_is_reviewed_prov(provenance) or sources):
        raise ValueError(
            f"{fid}: reviewed entry has neither reviewed provenance nor a primary source "
            f"('no LLM erdet LLM')"
        )
    return HerstellerFaehigkeit(
        id=fid,
        hersteller=hersteller,
        werkstoffe=tuple(str(w) for w in raw.get("werkstoffe", [])),
        bauformen=tuple(str(b) for b in raw.get("bauformen", [])),
        groessen=str(raw.get("groessen", "")).strip(),
        zertifikate=tuple(str(z) for z in raw.get("zertifikate", [])),
        review_state=state,
        provenance=provenance,
        sources=sources,
    )


def load_hersteller(path: Path | None = None) -> HerstellerCatalog:
    """Load + validate the (possibly EMPTY) Hersteller seed. Raises on schema / neutrality /
    circularity violation."""
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    entries: list[HerstellerFaehigkeit] = []
    seen: set[str] = set()
    for raw in data.get("faehigkeiten", []):
        e = _entry(raw)
        if e.id in seen:
            raise ValueError(f"duplicate hersteller id: {e.id}")
        seen.add(e.id)
        entries.append(e)
    return HerstellerCatalog(
        faehigkeiten=tuple(entries),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )


class InProcessHerstellerStore:
    """Capability-only matching over the file-backed seed. Ordering = match-completeness, then
    ALPHABETICAL by hersteller (a neutral, deterministic tie-break) — NEVER by payment (§3.9).
    Empty seed → empty result → Modus F reports 'no grounded data'. P0 tenant gate."""

    def __init__(self, catalog: HerstellerCatalog | None = None) -> None:
        self._catalog = catalog or load_hersteller()

    @property
    def catalog(self) -> HerstellerCatalog:
        return self._catalog

    def query(
        self,
        *,
        tenant_id: str,
        material: str | None = None,
        bauform: str | None = None,
        k: int = 8,
    ) -> tuple[HerstellerFaehigkeit, ...]:
        require_tenant(TenantContext(tenant_id))  # P0
        scored: list[tuple[int, str, HerstellerFaehigkeit]] = []
        for f in self._catalog.faehigkeiten:
            score = 0
            if material and any(material.lower() == w.lower() for w in f.werkstoffe):
                score += 1
            if bauform and any(bauform.lower() == b.lower() for b in f.bauformen):
                score += 1
            if score > 0:
                scored.append((score, f.hersteller.lower(), f))
        # capability match desc, then alphabetical hersteller (neutral tie-break) — NO payment axis
        scored.sort(key=lambda s: (-s[0], s[1]))
        return tuple(f for _s, _n, f in scored[: max(0, k)])
