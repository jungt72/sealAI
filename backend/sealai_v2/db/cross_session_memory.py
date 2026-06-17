"""``PostgresCrossSessionMemory`` — durable layer-4 cross-session memory (build-spec §7.4).

Wires the cross-session seam to a real persistent store: ``remember_durable`` persists per-tenant
durable facts (survive a restart); ``relevant_facts`` returns them by a DETERMINISTIC relevance
(token overlap between the query and a fact's ``feld``/``wert``) — so the seam no longer hard-returns
nothing. Tenant scope (P0) is a mandatory filter on BOTH operations: a different tenant can never see
tenant A's durable facts.

Doctrine (build-spec §7.4): these are REMEMBERED facts from EARLIER conversations, not verified —
the pipeline surfaces them under the honest "aus früheren Gesprächen — bei Bedarf bestätigen" frame
(``prompts/system_l1.jinja``) and they do NOT feed the deterministic calc binder. Relevance is
conservative (no recency fallback): an unrelated query surfaces nothing rather than leaking noise.
The broader CURATED cross-session sub-gate (what to promote, vector retrieval) stays deferred —
this lands the durable store + a transparent, deterministic relevance.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from sealai_v2.core.contracts import RememberedFact
from sealai_v2.db.models import V2DurableFact
from sealai_v2.security.tenant import TenantContext, require_tenant

_TOKEN_RE = re.compile(r"[^0-9a-zA-ZäöüßÄÖÜ]+")


def _tokens(*values: str) -> set[str]:
    out: set[str] = set()
    for v in values:
        for t in _TOKEN_RE.split((v or "").lower()):
            if len(t) >= 3:
                out.add(t)
    return out


class PostgresCrossSessionMemory:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._sf = session_factory

    def relevant_facts(
        self, *, tenant_id: str, query: str, k: int = 5
    ) -> tuple[RememberedFact, ...]:
        require_tenant(
            TenantContext(tenant_id)
        )  # P0 — tenant-scoped, never cross-tenant
        with self._sf() as s:
            rows = (
                s.execute(
                    select(V2DurableFact).where(V2DurableFact.tenant_id == tenant_id)
                )
                .scalars()
                .all()
            )
        if not rows:
            return ()
        q = _tokens(query)
        if not q:
            return ()
        matched = [r for r in rows if q & _tokens(r.feld, r.wert)]
        matched.sort(key=lambda r: r.as_of_turn, reverse=True)  # freshest first
        return tuple(
            RememberedFact(
                feld=r.feld,
                wert=r.wert,
                provenance=r.provenance,
                as_of_turn=r.as_of_turn,
            )
            for r in matched[:k]
        )

    def remember_durable(
        self, *, tenant_id: str, facts: tuple[RememberedFact, ...]
    ) -> None:
        require_tenant(TenantContext(tenant_id))  # P0
        if not facts:
            return
        with self._sf.begin() as s:
            for f in facts:
                row = s.get(V2DurableFact, (tenant_id, f.feld))
                if row is None:
                    s.add(
                        V2DurableFact(
                            tenant_id=tenant_id,
                            feld=f.feld,
                            wert=f.wert,
                            provenance=f.provenance,
                            as_of_turn=f.as_of_turn,
                        )
                    )
                else:  # last value wins (curation is conservative, not append-everything)
                    row.wert = f.wert
                    row.provenance = f.provenance
                    row.as_of_turn = f.as_of_turn
