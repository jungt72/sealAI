"""recall@k eval for the L2 retrieval layer — does the right Fachkarte come back for a naturally
phrased query? SEPARATE from the answer eval (which keeps the in-process keyword retriever as its
deterministic instrument): this measures the PRODUCTION Qdrant path's recall vs the keyword baseline.

Needs fastembed + a running Qdrant (run with ``SEALAI_V2_QDRANT_URL`` + ``SEALAI_V2_QDRANT_COLLECTION``
set; use a throwaway collection). The truth set (``seed_cases/retrieval_recall_v0.json``) is OWNER-
REVIEWED (query→expected-card) — the recall number is provisional until ratified. The pure metric
functions (``recall_at_k`` / ``reciprocal_rank`` / ``ranked_card_ids`` / ``summarize``) are
unit-tested hermetically; the run is an integration measurement, not a CI unit test.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.qdrant_retrieval import (
    QdrantFachkartenRetriever,
    ingest_fachkarten,
)
from sealai_v2.knowledge.retrieval import InProcessRetriever

_TRUTH = Path(__file__).resolve().parent / "seed_cases" / "retrieval_recall_v0.json"
_KS = (1, 3, 5)


def ranked_card_ids(result) -> list[str]:
    """Unique card ids in retrieval rank order (reviewed grounding_facts first, then provisional).
    A card surfaces via several claim-points → dedup to card granularity for recall."""
    out: list[str] = []
    for fact in (*result.grounding_facts, *result.provisional):
        if fact.card_id and fact.card_id not in out:
            out.append(fact.card_id)
    return out


def recall_at_k(ranked: list[str], expected: str, k: int) -> int:
    """1 iff ``expected`` is among the first k ranked card ids. Pure."""
    return int(expected in ranked[:k])


def reciprocal_rank(ranked: list[str], expected: str) -> float:
    """1/rank of ``expected`` (1-based), else 0. Pure."""
    return 1.0 / (ranked.index(expected) + 1) if expected in ranked else 0.0


def summarize(rows) -> dict:
    n = len(rows) or 1
    out: dict = {
        f"recall@{k}": round(sum(r[f"r@{k}"] for r in rows) / n, 3) for k in _KS
    }
    out["mrr"] = round(sum(r["rr"] for r in rows) / n, 3)
    out["n"] = len(rows)
    return out


async def _run(retriever, cases, *, tenant: str, fetch: int) -> list[dict]:
    rows: list[dict] = []
    for c in cases:
        res = await retriever.retrieve(c["query"], tenant_id=tenant, k=fetch)
        ranked = ranked_card_ids(res)
        rows.append(
            {
                "id": c["id"],
                "expected": c["expected_card"],
                "ranked": ranked,
                "rr": reciprocal_rank(ranked, c["expected_card"]),
                **{f"r@{k}": recall_at_k(ranked, c["expected_card"], k) for k in _KS},
            }
        )
    return rows


def run_recall_eval(
    settings: Settings, *, fetch: int = 20, tenant: str = "eval-tenant"
):
    """Ingest the Fachkarten + run the truth set through BOTH retrievers. Returns
    ``(qd_rows, qd_summary, inp_rows, inp_summary)``. Caller owns the collection lifecycle."""
    cases = json.loads(_TRUTH.read_text(encoding="utf-8"))["cases"]
    ingest_fachkarten(settings)
    qd_rows = asyncio.run(
        _run(QdrantFachkartenRetriever(settings), cases, tenant=tenant, fetch=fetch)
    )
    inp_rows = asyncio.run(
        _run(InProcessRetriever(), cases, tenant=tenant, fetch=fetch)
    )
    return qd_rows, summarize(qd_rows), inp_rows, summarize(inp_rows)


def main() -> None:
    s = Settings()
    if not s.qdrant_url:
        raise SystemExit(
            "set SEALAI_V2_QDRANT_URL + SEALAI_V2_QDRANT_COLLECTION (a throwaway) to run"
        )
    qd_rows, qd_sum, inp_rows, inp_sum = run_recall_eval(s)
    print("=== recall@k — PROVISIONAL (truth set is owner-reviewed) ===")
    print("Qdrant (semantic):   ", qd_sum)
    print("In-process (keyword):", inp_sum)
    inp_by_id = {r["id"]: r for r in inp_rows}
    print("\n=== per query: Qdrant r@3 | in-process r@3 ===")
    for r in qd_rows:
        q = "✓" if r["r@3"] else "✗"
        i = "✓" if inp_by_id[r["id"]]["r@3"] else "✗"
        print(
            f"  Q:{q} K:{i}  {r['id']}  erwartet {r['expected']:24s}  Qdrant-top: {r['ranked'][:3]}"
        )
    from sealai_v2.knowledge.qdrant_retrieval import _make_client

    _make_client(s).delete_collection(s.qdrant_collection)
    print(f"\n>> Test-Collection '{s.qdrant_collection}' aufgeräumt")


if __name__ == "__main__":
    main()
