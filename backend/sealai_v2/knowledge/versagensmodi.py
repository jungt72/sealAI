"""Versagensmodi — the §7 Dim. 5 knowledge dimension (Produkt-Konzept §7/§8, Schema §5.3):
symptom → ursache → fix, owner-reviewed, queryable. Feeds the **Diagnose** operation (Modus D)
AND sharpens the Challenge in the recommend flow (the typical failure modes of an archetype ARE
the risks to raise).

Same two-review-state + circularity discipline as the Fachkarten/Matrix (build-spec §8 "no LLM
erdet LLM"): a ``reviewed`` Versagensmodus must name an owner/trap provenance OR a primary source;
a ``draft`` entry is FLAG-ONLY — never authoritative, never the basis of a confident diagnosis,
surfaced as "vorläufig — gegen Hersteller verifizieren" until the owner reviews it. The CC-drafted
seed lands as ``draft`` (no source constraint); the owner flips entries to ``reviewed`` (then the
circularity guard applies). Pure data + a typed loader — no LLM, no network.

DOCTRINE: this dimension GROUNDS a diagnosis (symptom→cause→fix) with provenance; it NEVER invents
a number, never makes a final suitability/release statement (L4 stays with the manufacturer). A
diagnosis is a grounded, verified CLAIM like a recommendation (Produkt-Konzept §9.1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.security.tenant import TenantContext, require_tenant
from sealai_v2.core.text_match import query_tokens, tag_matches

_SEED_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _SEED_DIR / "versagensmodi_seed.json"
_REVIEW_STATES = ("reviewed", "draft")
_SCOPE_DIMS = ("symptom", "material", "medium")
# provenance markers that establish an owner/reviewed grounding (path i — no external source needed)
_REVIEWED_PROV_PREFIXES = (
    "trap-correct:",
    "trap:",
    "owner:",
    "eval:",
    "fk-",
    "fachkarte:",
)
# a mode is retrieved when ≥1 symptom tag matches AND ≥2 scope tags total (symptom + context),
# mirroring the matrix retriever — symptom is mandatory (a diagnosis needs the reported symptom).
_MIN_SCOPE_HITS = 2


@dataclass(frozen=True)
class Versagensmodus:
    """One reviewed/draft failure-mode entry (Schema §5.3): symptom → ursache → fix + the archetypes
    it affects. ``scope`` are synonym match-tags (the queryable mechanism, mirroring a Fachkarte).
    A ``reviewed`` entry MUST trace to an owner/trap provenance or a primary source (circularity
    guard); a ``draft`` entry is flag-only (provisional, never authoritative)."""

    id: str
    symptom: str
    ursache: str
    fix: str
    betrifft_archetypen: tuple[str, ...]
    review_state: str  # "reviewed" | "draft"
    scope: dict  # {symptom:[...], material:[...], medium:[...]} — synonym match-tags
    provenance: tuple[str, ...]
    sources: tuple[str, ...] = ()

    @property
    def reviewed(self) -> bool:
        return self.review_state == "reviewed"

    @property
    def owner_grounded(self) -> bool:
        return any(
            p.lower().startswith(_REVIEWED_PROV_PREFIXES) for p in self.provenance
        )

    def quelle(self) -> str:
        tag = (
            "reviewed"
            if self.reviewed
            else "draft — vorläufig, gegen Hersteller verifizieren"
        )
        return f"Versagensmodi · {self.id} ({tag}; {', '.join(self.provenance)})"


@dataclass(frozen=True)
class VersagensmodiCatalog:
    modes: tuple[Versagensmodus, ...]
    version: str = ""
    source: str = ""

    def by_id(self, mode_id: str) -> Versagensmodus | None:
        for m in self.modes:
            if m.id == mode_id:
                return m
        return None

    @property
    def reviewed(self) -> tuple[Versagensmodus, ...]:
        return tuple(m for m in self.modes if m.reviewed)

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(m.id for m in self.modes)


def _is_reviewed_prov(provenance: tuple[str, ...]) -> bool:
    return any(p.lower().startswith(_REVIEWED_PROV_PREFIXES) for p in provenance)


def _mode(raw: dict) -> Versagensmodus:
    mid = str(raw["id"])
    state = str(raw.get("review_state", "")).strip()
    if state not in _REVIEW_STATES:
        raise ValueError(f"{mid}: review_state {state!r} not in {_REVIEW_STATES}")
    symptom = str(raw.get("symptom", "")).strip()
    ursache = str(raw.get("ursache", "")).strip()
    fix = str(raw.get("fix", "")).strip()
    if not (symptom and ursache and fix):
        raise ValueError(f"{mid}: symptom, ursache und fix sind Pflicht")
    scope = raw.get("scope", {}) or {}
    if not isinstance(scope, dict) or not scope.get("symptom"):
        raise ValueError(f"{mid}: scope.symptom is mandatory (the symptom match-tags)")
    provenance = tuple(str(p) for p in raw.get("provenance", []))
    if not provenance:
        raise ValueError(f"{mid}: provenance is mandatory (owner-grounding audit)")
    sources = tuple(str(s) for s in raw.get("sources", []))
    # Circularity guard (build-spec §8): a REVIEWED mode must trace to a reviewed source OR a
    # primary source. A DRAFT mode is flag-only — never authoritative — so it carries no constraint.
    if state == "reviewed" and not (_is_reviewed_prov(provenance) or sources):
        raise ValueError(
            f"{mid}: reviewed mode has neither a reviewed provenance (trap-correct:/owner:/eval:/FK-…) "
            f"nor a primary source — 'no LLM erdet LLM', model-generated reviewed modes are forbidden"
        )
    return Versagensmodus(
        id=mid,
        symptom=symptom,
        ursache=ursache,
        fix=fix,
        betrifft_archetypen=tuple(str(a) for a in raw.get("betrifft_archetypen", [])),
        review_state=state,
        scope={d: [str(v) for v in scope.get(d, [])] for d in _SCOPE_DIMS},
        provenance=provenance,
        sources=sources,
    )


def load_versagensmodi(path: Path | None = None) -> VersagensmodiCatalog:
    """Load + validate the Versagensmodi seed. Raises on any circularity-guard / schema violation."""
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    modes: list[Versagensmodus] = []
    seen: set[str] = set()
    for raw in data.get("modes", []):
        m = _mode(raw)
        if m.id in seen:
            raise ValueError(f"duplicate versagensmodus id: {m.id}")
        seen.add(m.id)
        modes.append(m)
    return VersagensmodiCatalog(
        modes=tuple(modes),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )


class InProcessVersagensmodiStore:
    """Deterministic symptom-tag retrieval over the file-backed seed (≥1 symptom tag + ≥2 scope tags),
    mirroring the matrix/Fachkarten retrievers. Returns the matched modes strongest-first; the Diagnose
    operation folds reviewed-vs-draft (reviewed → grounded; draft → 'vorläufig'). P0 tenant gate."""

    def __init__(self, catalog: VersagensmodiCatalog | None = None) -> None:
        self._catalog = catalog or load_versagensmodi()

    @property
    def catalog(self) -> VersagensmodiCatalog:
        return self._catalog

    def query(
        self,
        *,
        tenant_id: str,
        query_text: str,
        k: int = 6,
    ) -> tuple[Versagensmodus, ...]:
        require_tenant(TenantContext(tenant_id))  # P0 — server-side scope
        q_norm = query_text.lower()
        q_tokens = query_tokens(q_norm)
        scored: list[tuple[int, Versagensmodus]] = []
        for m in self._catalog.modes:
            sym_hit = any(
                tag_matches(t, q_tokens, q_norm) for t in m.scope.get("symptom", [])
            )
            ctx_hits = sum(
                1
                for dim in ("material", "medium")
                for t in m.scope.get(dim, [])
                if tag_matches(t, q_tokens, q_norm)
            )
            total = (1 if sym_hit else 0) + ctx_hits
            if sym_hit and total >= _MIN_SCOPE_HITS:
                scored.append((total, m))
        # symptom-only match (no context tags) still retrieves — a bare symptom is a valid diagnosis
        # entry; context only sharpens ranking. Fall back to symptom-only when no ≥2 match exists.
        if not scored:
            for m in self._catalog.modes:
                if any(
                    tag_matches(t, q_tokens, q_norm) for t in m.scope.get("symptom", [])
                ):
                    scored.append((1, m))
        scored.sort(key=lambda sc: (-sc[0], sc[1].id))
        return tuple(m for _s, m in scored[: max(0, k)])
