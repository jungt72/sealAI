# sealingAI production-like retrieval deep dive — 2026-07-23

## Decision

The retrieval defect behind the defensive, repetitive answer behavior is reproduced and corrected
at candidate level. The production Qdrant collection and Postgres claim ledger were exercised
read-only through an isolated source overlay; neither production data nor the running service was
changed.

The candidate passes the **retrieval-quality** thresholds. It is not a production release approval:
the query-to-card truth mapping remains a draft pending owner ratification, query-level expected
facets have not been adjudicated, and the production collection contains no tenant-private fixture
with which a real cross-tenant leak can be tested read-only.

## Root cause

All expected reviewed cards and claim IDs exist in the production index, and the Postgres ledger
resolves their active claims. The failure was ranking, not missing data:

- dense retrieval placed several correct cards only at ranks 94, 100 and 125 of 128 candidates;
- focused seal-type profiles could displace the case-specific evidence instead of augmenting it;
- broad defensive evidence therefore reached the answer contract more reliably than the evidence
  needed to develop a concrete solution.

## Candidate design

- A bounded, deterministic engineering-concept lane ranks reviewed card identities for natural
  variants such as swelling, weathering, tearing, dynamic shaft sealing and preload loss.
- Dense and lexical card ranks are fused by reciprocal-rank fusion; claim points are interleaved by
  card so one verbose card cannot occupy the complete evidence window.
- Lexically fetched candidates use a mandatory server-side
  `tenant_id in {requested tenant, sealai}` filter and at most 16 exact card IDs.
- Qdrant still contributes only candidate identity and order. Every claim is re-resolved through the
  Postgres ledger; retired, rejected or missing claims disappear.
- Focused seal profiles are bounded additive context after case evidence. They no longer suppress
  the case-specific card.
- Failure of either optional augmentation keeps the successful dense/hybrid result. It is logged and
  never converts that result into an empty turn.
- Short abbreviations such as `UV` require a complete-token match; negative controls prevent matches
  inside unrelated tokens such as `SUV`.

## Read-only production-path measurement

Collection: `sealai_v2_knowledge_local_minilm_v1`  
Runtime: Qdrant dense retrieval, hybrid off, rerank off, Postgres ledger active  
Cases: 18 natural-language queries from `retrieval_recall_v0.json`  
Candidate served-tree hash: `d4f7196c0e7aea392feb4165ea21f9b8f47b21ea`

| Measure | Original production path | Candidate |
|---|---:|---:|
| Recall@1 | 0.389 | **0.667** |
| Recall@3 | 0.556 | **0.944** |
| Recall@5 | 0.556 | **1.000** |
| MRR | 0.463 | **0.810** |
| Grounded query rate | 1.000 | **1.000** |
| Retrieval p50 | about 40–49 ms | **86.8 ms** |
| Retrieval p95 / max | about 113–163 ms | **157.5 / 157.5 ms** |
| Misses at 5 | 8 | **0** |

The quality thresholds are Recall@3 ≥ 0.90, Recall@5 ≥ 0.95, grounded-query rate 1.00, no empty
result and retrieval p95 ≤ 250 ms. The candidate passes all five.

The previously reported `facet_coverage=0.357` is not a release metric. Only four expected cards
carry facet metadata and the truth set defines no expected facets per query. The reproducible runner
therefore reports facet adjudication as `NOT_SCORED` until a human-reviewed query-facet truth set
exists.

## Tenant boundary

The production collection contains 601 points, all under the global tenant `sealai`. Comparing two
random absent tenant scopes produced identical global results, but this proves only global-corpus
consistency. It does **not** prove that tenant A cannot see tenant B's private card.

The runner and its exit code now fail closed on this distinction:

- exit 2: retrieval-quality failure;
- exit 3: quality pass, but release remains blocked;
- exit 0 is reserved for a future fully adjudicated, release-eligible report.

A real isolation gate requires two owned tenant fixtures with mutually exclusive private cards in a
disposable staging collection, or equivalent owner-approved fixtures. The server-side filter shape
is covered by regression tests, but a unit test does not replace that integration evidence.

## Verification

- Full `backend/sealai_v2` suite: pass with expected skips and two dependency warnings.
- Full architecture suite: pass.
- Ruff format check across 517 files: pass.
- Ruff check: pass.
- Retrieval, knowledge-answer and live-gate regression suites: pass.
- `git diff --check`: pass.
- Claude Code hostile review: initial **BLOCK** on the misleading tenant-isolation and exit-code
  semantics; after correction, final **APPROVE** with no release blocker in the implementation.
- Production service unchanged; the temporary evaluation overlay was removed after measurement.

## Source identity

| Source | SHA-256 |
|---|---|
| In-process lexical retrieval | `c0f55e9637cb70fe434bc7474bdf093e91ec0bd26532b843a822c7eeee42c986` |
| Production Qdrant retrieval | `80865d968fc8a955f6a4a5981996894eba90a7a1ebdcb7976792c92376260cc9` |
| Reproducible live runner | `122f9719f80a21c7cac8209349cff64d3d610da2fe8b59918c7c6f1896592764` |
| Draft truth set | `423c03e8c7e42718501965ce6477d6dbba48a1fcd9c9575c0331a478bee5159e` |

## Remaining release authority

1. Owner-ratify or correct every query-to-card mapping and define expected facets where applicable.
2. Run the cross-tenant fixture test described above.
3. Re-run and fully adjudicate the answer replay for the exact committed served tree and production
   L1/runtime profile.
4. Accept or remediate the previously measured long-tail generation latency.
5. Merge the reviewed source, promote a signed provenance-attested image, and issue the fresh
   SHA-bound production approval required by the sanctioned release script.

Until all five are complete, the correct state is **retrieval-quality candidate passed; production
release blocked; not deployed**.
