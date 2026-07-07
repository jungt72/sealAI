---
name: retrieval-rag
description: >-
  Operate the existing sealingAI V2 Qdrant retrieval stack — dense + hybrid
  (sparse / RRF / rerank), flag-gated — and its OpenAI-API embeddings. Use when a
  task touches knowledge/qdrant_retrieval.py, embeddings, Qdrant collections, or
  retrieval scoring/ranking. Encodes the never-use-a-local-embedder rule (it OOM'd
  the host) and the score-scale caution (a mismatch caused a ~6-min prod
  incident). RAG re-architecture is out of scope for this skill.
---

# Operate the RAG / retrieval stack (`backend/sealai_v2/knowledge/qdrant_retrieval.py`)

This skill is for **operating and safely tweaking the existing** retrieval stack.
Larger RAG **re-architecture** is deliberately out of scope here (it is reserved
for a heavier, owner-directed workstream). If the task is architectural, say so
and stop rather than reshaping the stack under a small-patch pretext.

## The stack

- Dense retrieval + a flag-gated **hybrid** path: dense + sparse + **RRF** fusion
  + **rerank**. Lives in `knowledge/qdrant_retrieval.py`.
- **Dense** embeddings: **OpenAI API** `text-embedding-3-small` (RAM-safe), live in
  prod. **Sparse** embeddings + the reranker are **local by design** (FastEmbed
  ONNX) — that is why the ~1.1GB runtime-download footgun exists.
- In-process fallback retrieval: `knowledge/retrieval.py`.

## Two hard-won rules

1. **Never swap the dense embedder for a local model.** A local *dense* model
   (e5-large) OOM'd the host and took chat down — it had to be rolled back. The
   dense path must stay on the OpenAI API. Note `embed_provider` defaults to
   `"fastembed"` in code — prod overrides it to OpenAI; do not "simplify" that
   back to a local dense model. There is **no code guard** named for this — the
   OpenAI dense embedder in `qdrant_retrieval.py` (+ the fail-fast dimension check)
   *is* the invariant. (Do not confuse this with **§9.2**, which is the L3
   equivalence-claim edge in `core/l3_verifier.py`, unrelated to embeddings.)
2. **Score-scale mismatch is a real incident class.** The first hybrid activation
   caused a ~6-minute production incident because dense and reranker scores are on
   **different scales** — fusing/thresholding them naively broke retrieval. When
   you touch fusion, thresholds, or the rerank step, verify the score scales agree
   (or are normalized) **before** activating, and watch the first live window.

## `retrieve()` must not crash the turn

`retrieve()` was fixed to **not crash on embed-failure** — it degrades instead.
Preserve that: a retrieval/embedding failure is fail-open (degrade + surface the
gap), never an exception that takes down the answer path. Do not catch broad
exceptions without a typed fallback and logging.

## Activation discipline

- The hybrid path is **flag-gated**. Land changes default-OFF, byte-identical when
  unset; prove it before flipping (see the `backend-v2-deploy` skill for the
  compose-passthrough + flag rules).
- Remember the runtime-cost footgun: the reranker downloads a ~1.1GB model at
  **runtime** — pre-bake heavy assets, or a flip crash-loops the service.
- After any change: offline suite green, then a **targeted** REPLAY on a
  retrieval-sensitive dimension (PTFE grounding is a known probe;
  see `eval-replay-adjudication`).

## Observability

`obs/tracing.py` (LangSmith, fail-open, observation-only) is the place to confirm
what was actually retrieved for a given turn — root-cause from a **real trace**,
not a guess.
