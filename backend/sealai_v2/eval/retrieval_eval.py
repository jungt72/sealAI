"""recall@k eval for the L2 retrieval layer — does the right Fachkarte come back for a naturally
phrased query? SEPARATE from the answer eval (which keeps the in-process keyword retriever as its
deterministic instrument): this measures the PRODUCTION Qdrant path's recall vs the keyword baseline.

The default mode needs fastembed + a running Qdrant (run with ``SEALAI_V2_QDRANT_URL`` +
``SEALAI_V2_QDRANT_COLLECTION`` set; use a throwaway collection). ``--live-read-only`` instead uses
the configured production Qdrant + Postgres ledger without ingest, mutation or collection cleanup.

The truth set (``seed_cases/retrieval_recall_v0.json``) remains a DRAFT query→expected-card mapping
until the owner ratifies it. Technical metrics are therefore useful regression evidence, but never a
substitute for factual adjudication or the release approval. Pure metrics and gates are unit-tested;
the Qdrant runs are explicit integration measurements, not CI unit tests.
"""

from __future__ import annotations

import asyncio
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import time
import uuid

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.qdrant_retrieval import (
    QdrantFachkartenRetriever,
    ingest_fachkarten,
)
from sealai_v2.knowledge.retrieval import InProcessRetriever

_TRUTH = Path(__file__).resolve().parent / "seed_cases" / "retrieval_recall_v0.json"
_KS = (1, 3, 5)
_LIVE_GATES = {
    "recall@3": 0.90,
    "recall@5": 0.95,
    "grounded_query_rate": 1.0,
    "empty_result_count": 0,
    "retrieval_latency_p95_ms_max": 250.0,
}
_HEX_SHA = re.compile(r"^[0-9a-f]{40,64}$")


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


def _percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil((percentile / 100) * len(ordered)) - 1)
    return round(ordered[index], 1)


def summarize_live(rows: list[dict]) -> dict:
    """Summarize the read-only production path without exposing query or claim text."""
    summary = summarize(rows)
    n = len(rows) or 1
    latencies = [float(row["latency_ms"]) for row in rows]
    summary.update(
        {
            "grounded_query_rate": round(
                sum(row["reviewed_fact_count"] > 0 for row in rows) / n, 3
            ),
            "empty_result_count": sum(
                row["reviewed_fact_count"] == 0 and row["provisional_fact_count"] == 0
                for row in rows
            ),
            "public_exception_count": sum(
                bool(row["public_exception"]) for row in rows
            ),
            "latency_ms": {
                "p50": round(statistics.median(latencies), 1) if latencies else None,
                "p95": _percentile(latencies, 95),
                "max": round(max(latencies), 1) if latencies else None,
            },
        }
    )
    return summary


def evaluate_live_gates(summary: dict) -> dict:
    checks = {
        "recall@3": summary["recall@3"] >= _LIVE_GATES["recall@3"],
        "recall@5": summary["recall@5"] >= _LIVE_GATES["recall@5"],
        "grounded_query_rate": summary["grounded_query_rate"]
        >= _LIVE_GATES["grounded_query_rate"],
        "empty_result_count": summary["empty_result_count"]
        <= _LIVE_GATES["empty_result_count"],
        "retrieval_latency_p95_ms_max": summary["latency_ms"]["p95"] is not None
        and summary["latency_ms"]["p95"] <= _LIVE_GATES["retrieval_latency_p95_ms_max"],
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "thresholds": dict(_LIVE_GATES),
        "checks": checks,
    }


def live_exit_code(report: dict) -> int:
    """Reserve success for a genuinely release-eligible report, never a provisional metric pass."""
    if report["retrieval_quality_gate"]["status"] != "PASS":
        return 2
    return 0 if report.get("release_eligible") is True else 3


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


async def _run_live(retriever, cases, *, tenant: str, fetch: int) -> list[dict]:
    rows: list[dict] = []
    for case in cases:
        started = time.perf_counter()
        exception_type = ""
        try:
            # Exercise the public production wrapper users actually hit. It deliberately converts an
            # exhausted dependency failure to an empty result; empty_result_count, grounded rate and
            # recall therefore catch that user-visible degradation without bypassing the wrapper.
            result = await retriever.retrieve(case["query"], tenant_id=tenant, k=fetch)
        except Exception as exc:  # noqa: BLE001 — an eval row records, rather than hides, failure
            from sealai_v2.core.contracts import RetrievalResult

            result = RetrievalResult()
            exception_type = type(exc).__name__
        elapsed_ms = (time.perf_counter() - started) * 1000
        ranked = ranked_card_ids(result)
        expected = case["expected_card"]
        rows.append(
            {
                "id": case["id"],
                "expected": expected,
                "ranked_card_ids": ranked,
                "reviewed_fact_count": len(result.grounding_facts),
                "provisional_fact_count": len(result.provisional),
                "public_exception": exception_type,
                "latency_ms": round(elapsed_ms, 1),
                "rr": reciprocal_rank(ranked, expected),
                **{f"r@{k}": recall_at_k(ranked, expected, k) for k in _KS},
            }
        )
    return rows


def _load_truth() -> tuple[dict, list[dict], str]:
    raw = _TRUTH.read_bytes()
    truth = json.loads(raw)
    cases = truth.get("cases") or []
    ids = [str(case.get("id") or "") for case in cases]
    if not cases or any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        raise RuntimeError("retrieval truth set must contain unique non-empty case ids")
    if any(not case.get("query") or not case.get("expected_card") for case in cases):
        raise RuntimeError("every retrieval truth case needs query and expected_card")
    return truth, cases, hashlib.sha256(raw).hexdigest()


async def run_live_read_only_eval(
    settings: Settings,
    *,
    source_git_sha: str,
    source_tree_hash: str,
    fetch: int = 20,
) -> dict:
    """Measure production Qdrant+ledger read-only for two random, absent tenant scopes.

    Comparing absent tenant scopes verifies stable GLOBAL-corpus behavior only. It is deliberately
    not called a tenant-isolation test: proving cross-tenant isolation requires owned tenant fixture
    cards (or a write-enabled disposable staging collection), neither of which this read-only runner
    may invent.
    """
    if not _HEX_SHA.fullmatch(source_git_sha) or not _HEX_SHA.fullmatch(
        source_tree_hash
    ):
        raise RuntimeError(
            "source_git_sha/source_tree_hash must be full lowercase hex identities"
        )
    if not settings.database_url or not settings.qdrant_url:
        raise RuntimeError("live eval requires configured Postgres and Qdrant")
    if getattr(settings, "retriever_backend", "") != "qdrant":
        raise RuntimeError("live eval requires retriever_backend=qdrant")

    from sealai_v2.pipeline.pipeline import _build_retriever

    retriever = _build_retriever(settings)
    if not isinstance(retriever, QdrantFachkartenRetriever):
        raise RuntimeError(
            "production Qdrant+Postgres-ledger retriever was not constructed"
        )
    truth, cases, truth_sha256 = _load_truth()
    token = uuid.uuid4().hex
    tenant_a = f"release-eval-a-{token}"
    tenant_b = f"release-eval-b-{token}"
    rows_a = await _run_live(retriever, cases, tenant=tenant_a, fetch=fetch)
    rows_b = await _run_live(retriever, cases, tenant=tenant_b, fetch=fetch)
    mismatches = [
        left["id"]
        for left, right in zip(rows_a, rows_b, strict=True)
        if left["ranked_card_ids"] != right["ranked_card_ids"]
        or left["reviewed_fact_count"] != right["reviewed_fact_count"]
        or left["provisional_fact_count"] != right["provisional_fact_count"]
        or left["public_exception"] != right["public_exception"]
    ]
    summary = summarize_live(rows_a)
    gates = evaluate_live_gates(summary)
    return {
        "schema_version": 1,
        "mode": "read_only_public_retrieve_production_qdrant_postgres_ledger",
        "source_identity": {
            "git_sha": source_git_sha,
            "tree_hash": source_tree_hash,
            "truth_set_sha256": truth_sha256,
        },
        "runtime": {
            "qdrant_collection": settings.qdrant_collection,
            "hybrid_enabled": settings.qdrant_hybrid_enabled,
            "rerank_enabled": settings.qdrant_rerank_enabled,
            "fetch": fetch,
        },
        "truth_set": {
            "status": "DRAFT_OWNER_RATIFICATION_REQUIRED",
            "case_count": len(cases),
            "doc": truth.get("_doc", ""),
        },
        "facet_adjudication": {
            "status": "NOT_SCORED",
            "reason": "truth set has no owner-ratified expected_facets per query",
        },
        "summary": summary,
        "global_scope_consistency": {
            "status": "PASS" if not mismatches else "FAIL",
            "random_absent_tenants_compared": 2,
            "mismatch_count": len(mismatches),
            "mismatch_case_ids": mismatches,
            "does_not_prove": "cross-tenant isolation without owned tenant fixtures",
        },
        "retrieval_quality_gate": gates,
        "release_status": "BLOCKED",
        "release_blockers": [
            "retrieval truth mappings require owner ratification",
            "cross-tenant isolation requires owned tenant fixtures or disposable staging seed",
            "query-level expected facets require human adjudication",
        ],
        # A draft truth mapping can pass the quality threshold but cannot authorize a release. This
        # field deliberately never infers owner adjudication from a metric or an exit code.
        "release_eligible": False,
        "misses_at_5": [row["id"] for row in rows_a if not row["r@5"]],
        "rows": rows_a,
    }


def run_recall_eval(
    settings: Settings, *, fetch: int = 20, tenant: str = "eval-tenant"
):
    """Ingest the Fachkarten + run the truth set through BOTH retrievers. Returns
    ``(qd_rows, qd_summary, inp_rows, inp_summary)``. Caller owns the collection lifecycle."""
    if settings.database_url:
        raise RuntimeError(
            "retrieval scratch eval refuses a configured production database"
        )
    if not settings.qdrant_collection.startswith("sealai_eval_"):
        raise RuntimeError("retrieval eval collection must start with 'sealai_eval_'")
    cases = json.loads(_TRUTH.read_text(encoding="utf-8"))["cases"]
    ingest_fachkarten(settings)
    qd_rows = asyncio.run(
        _run(QdrantFachkartenRetriever(settings), cases, tenant=tenant, fetch=fetch)
    )
    inp_rows = asyncio.run(
        _run(InProcessRetriever(), cases, tenant=tenant, fetch=fetch)
    )
    return qd_rows, summarize(qd_rows), inp_rows, summarize(inp_rows)


def _run_scratch_main() -> None:
    s = Settings()
    if not s.qdrant_url:
        raise SystemExit(
            "set SEALAI_V2_QDRANT_URL and a SEALAI_V2_QDRANT_COLLECTION starting "
            "with sealai_eval_ to run"
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=(
            "live exit codes: 2 = retrieval-quality failure; 3 = quality pass but release blocked; "
            "0 is reserved for a future fully adjudicated release-eligible report"
        ),
    )
    parser.add_argument("--live-read-only", action="store_true")
    parser.add_argument("--source-git-sha")
    parser.add_argument("--source-tree-hash")
    parser.add_argument("--fetch", type=int, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.live_read_only:
        _run_scratch_main()
        return
    if not args.source_git_sha or not args.source_tree_hash:
        parser.error(
            "--live-read-only requires --source-git-sha and --source-tree-hash"
        )
    if args.fetch < 5 or args.fetch > 128:
        parser.error("--fetch must be between 5 and 128")
    report = asyncio.run(
        run_live_read_only_eval(
            Settings(),
            source_git_sha=args.source_git_sha,
            source_tree_hash=args.source_tree_hash,
            fetch=args.fetch,
        )
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    exit_code = live_exit_code(report)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
