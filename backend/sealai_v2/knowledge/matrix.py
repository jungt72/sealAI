"""Verträglichkeitsmatrix — the §4 relational compatibility matrix (build-spec §4: "relational,
abfragbar — Medium × Werkstoff × Bedingung → Bewertung + Quelle. Speist L2 und L3").

A first-class, queryable, provenance-bearing grounding source that complements the Fachkarten: where
a card carries grounded *substance/mechanism* prose, a matrix cell carries a queryable compatibility
VERDICT (werkstoff × medium/bedingung → bewertung) with its reviewed source. It feeds L2 (grounding)
and — Step B — L3 (correction of compatibility claims).

No-fabrication is STRUCTURAL (build-spec §8 "no LLM erdet LLM"): the loader's circularity guard
(mirrors ``fachkarten._claim``) rejects any cell whose ``provenance`` does not name a reviewed source
(``trap-correct:`` / ``owner:`` / ``eval:`` / a reviewed ``FK-…`` id) and that carries no primary
``source``. Every seed cell is a faithful restatement of an existing reviewed verdict — zero
model-generated cells. The seed is GLOBAL reviewed knowledge (git = provenance/version/audit),
canonical for this hop; a Postgres/Qdrant adapter is the deferred prod path behind the
``CompatibilityMatrix`` Protocol. Pure data + a typed loader — no LLM, no network.

DOCTRINE (architektur_prinzipien §2-L2): the matrix GROUNDS/CORRECTS factual compatibility with
sources; it NEVER selects materials, ranks options, or makes suitability statements (no
Steuerlogik). The query returns verdict+source facts only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sealai_v2.core.contracts import (
    _MATRIX_VERDICTS,
    GroundingFact,
    MatrixCell,
)
from sealai_v2.core.text_match import query_tokens, tag_matches
from sealai_v2.security.tenant import TenantContext, require_tenant

_SEED_DIR = Path(__file__).resolve().parent
_DEFAULT_FILE = _SEED_DIR / "matrix_seed.json"
_SCOPE_DIMS = ("material", "medium", "bedingung")
# provenance markers that establish an owner/reviewed grounding (path i — no external source needed)
_REVIEWED_PROV_PREFIXES = (
    "trap-correct:",
    "trap:",
    "owner:",
    "eval:",
    "fk-",
    "fachkarte:",
)
# a cell is retrieved when at least this many of its scope tags appear in the query — two keeps it
# precise (one material + its medium/condition), mirroring the Fachkarten retriever (_MIN_SCOPE_HITS).
_MIN_SCOPE_HITS = 2
# token/tag matching primitives now live in core.text_match (shared with the L3 trap topic-gate).


@dataclass(frozen=True)
class CompatibilityMatrixCatalog:
    cells: tuple[MatrixCell, ...]
    version: str = ""
    source: str = ""

    def by_id(self, cell_id: str) -> MatrixCell | None:
        for c in self.cells:
            if c.id == cell_id:
                return c
        return None

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(c.id for c in self.cells)


def _is_reviewed_prov(provenance: tuple[str, ...]) -> bool:
    return any(p.lower().startswith(_REVIEWED_PROV_PREFIXES) for p in provenance)


def _cell(raw: dict) -> MatrixCell:
    cid = str(raw["id"])
    werkstoff = str(raw.get("werkstoff", "")).strip()
    if not werkstoff:
        raise ValueError(f"{cid}: werkstoff is mandatory")
    bewertung = str(raw.get("bewertung", "")).strip()
    if bewertung not in _MATRIX_VERDICTS:
        raise ValueError(f"{cid}: bewertung {bewertung!r} not in {_MATRIX_VERDICTS}")
    begruendung = str(raw.get("begruendung", "")).strip()
    if not begruendung:
        raise ValueError(f"{cid}: begruendung (grounded verdict text) is mandatory")
    scope = raw.get("scope", {}) or {}
    if not isinstance(scope, dict) or not scope.get("material"):
        raise ValueError(
            f"{cid}: scope.material is mandatory (the werkstoff match-tag)"
        )
    provenance = tuple(str(p) for p in raw.get("provenance", []))
    sources = tuple(str(s) for s in raw.get("sources", []))
    # Circularity guard (build-spec §8): a cell must trace to a reviewed source OR a primary source.
    if not (_is_reviewed_prov(provenance) or sources):
        raise ValueError(
            f"{cid}: cell has neither a reviewed provenance (trap-correct:/owner:/eval:/FK-…) nor a "
            f"primary source — 'no LLM erdet LLM', model-generated cells are forbidden: {begruendung[:60]!r}"
        )
    return MatrixCell(
        id=cid,
        werkstoff=werkstoff,
        medium=str(raw.get("medium", "")).strip(),
        bedingung=str(raw.get("bedingung", "")).strip(),
        bewertung=bewertung,
        begruendung=begruendung,
        scope={d: [str(v) for v in scope.get(d, [])] for d in _SCOPE_DIMS},
        provenance=provenance,
        sources=sources,
    )


def load_matrix(path: Path | None = None) -> CompatibilityMatrixCatalog:
    """Load + validate the matrix seed. Raises on any circularity-guard / schema violation."""
    data = json.loads((path or _DEFAULT_FILE).read_text(encoding="utf-8"))
    cells: list[MatrixCell] = []
    seen: set[str] = set()
    for raw in data.get("cells", []):
        c = _cell(raw)
        if c.id in seen:
            raise ValueError(f"duplicate matrix cell id: {c.id}")
        seen.add(c.id)
        cells.append(c)
    return CompatibilityMatrixCatalog(
        cells=tuple(cells),
        version=str(data.get("version", "")),
        source=str(data.get("source", "")),
    )


class InProcessCompatibilityMatrix:
    """Implements the ``CompatibilityMatrix`` Protocol over the file-backed seed. Deterministic
    scope-tag overlap (≥2 hits: a material tag + a medium/bedingung tag), mirroring the Fachkarten
    retriever — semantic recall is the deferred Qdrant adapter's job, not this hop."""

    def __init__(self, catalog: CompatibilityMatrixCatalog | None = None) -> None:
        self._catalog = catalog or load_matrix()

    @property
    def catalog(self) -> CompatibilityMatrixCatalog:
        """The backing reviewed catalog — exposed so a caller (the Gegencheck stage)
        can recover the bewertung enum via ``by_id()`` that ``query()`` drops onto
        ``GroundingFact``. Read-only accessor; no rebuild, no I/O."""
        return self._catalog

    def query(
        self,
        *,
        tenant_id: str,
        query_text: str,
        case_facts: tuple = (),
        k: int = 6,
    ) -> tuple[GroundingFact, ...]:
        require_tenant(
            TenantContext(tenant_id)
        )  # P0 — server-side scope (seed is global reviewed)
        # match surface = the question + any structured case facts (medium/material) — eval has no
        # case_facts, so the eval delta comes purely from the question tokens.
        q_norm = " ".join(
            [query_text] + [str(getattr(f, "wert", "") or "") for f in case_facts]
        ).lower()
        q_tokens = query_tokens(q_norm)
        scored: list[tuple[int, MatrixCell]] = []
        for c in self._catalog.cells:
            mat_hit = any(
                tag_matches(t, q_tokens, q_norm) for t in c.scope.get("material", [])
            )
            ctx_hits = sum(
                1
                for dim in ("medium", "bedingung")
                for t in c.scope.get(dim, [])
                if tag_matches(t, q_tokens, q_norm)
            )
            total = (1 if mat_hit else 0) + ctx_hits
            # require the material AND at least one medium/condition tag (≥2, and material is one of them)
            if mat_hit and total >= _MIN_SCOPE_HITS:
                scored.append((total, c))
        scored.sort(
            key=lambda sc: (-sc[0], sc[1].id)
        )  # strongest first, deterministic tie-break
        return tuple(
            GroundingFact(
                text=c.begruendung,
                quelle=c.quelle(),
                card_id=c.id,
                sources=c.sources,
                kind="matrix",
            )
            for _s, c in scored[: max(0, k)]
        )
