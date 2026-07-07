---
name: knowledge-fachkarten
description: >-
  Grow or curate the sealingAI reviewed-knowledge SSoT — the seed-JSON knowledge
  under backend/sealai_v2/knowledge/ (fachkarten_seed.json,
  material_parameters_seed.json, versagensmodi_seed.json, matrix_seed.json,
  archetypes_seed.json, calc_seed.json, hersteller_seed.json), the claim `kind`
  taxonomy, and reviewed-vs-drafts provenance. Use when a task asks to add/edit a
  Fachkarte, edit material parameters or failure modes, ingest domain knowledge,
  tag claims, adjust the compatibility matrix, promote a draft, or grow what the
  system is allowed to cite. Encodes the reviewed-only-may-correct rule and the
  owner-curation workflow.
---

# Curate the reviewed-knowledge SSoT (`backend/sealai_v2/knowledge/`)

The **reviewed seed-JSON Fachkarten are the ONE knowledge SSoT.** No domain fact
(material property, limit value, norm) may be invented/hallucinated — only cited
from reviewed, versioned sources (Leitsatz L2). This skill is how that knowledge
is grown safely.

## Where it lives

- Seed-JSON (the SSoT): `knowledge/fachkarten_seed.json`,
  `material_parameters_seed.json`, `versagensmodi_seed.json`, `matrix_seed.json`,
  `archetypes_seed.json`, `calc_seed.json`, `hersteller_seed.json`.
- Loaders: `knowledge/fachkarten.py`, `knowledge/matrix.py`.
- In-process retrieval: `knowledge/retrieval.py`. Production Qdrant retrieval
  (flag-gated): `knowledge/qdrant_retrieval.py` (see the `retrieval-rag` skill).
- Trap catalog (used by L3, distinct from Fachkarten):
  `knowledge/traps.py` + `knowledge/trap_catalog.json`.
- Drafts staging: `ops/fachkarten_drafts/*.json`.
- Sanctioned tooling (prefer over hand-editing JSON):
  `ops/ingest_fachkarte.py` (grow a card), `ops/promote_fachkarte.py` +
  `knowledge/promote.py` (draft → reviewed), `ops/promote_seed.py` (seed promotion).

## Provenance is the whole point

- **`reviewed`** entries are **owner-grounded** and may correct/block a model
  answer. **No fact in `reviewed` is model-sourced.**
- **`drafts`** are model-proposed and are **flag-only** — they surface, they never
  correct.
- The claim `kind` taxonomy (expanded 4→8 in a prior rework) tags each claim by
  type; a re-tag touches many claims/cards at once — do it deliberately and
  re-run the eval on affected dimensions.

## Owner-curation workflow

The owner has no domain expertise and **deepens cards via multi-LLM challenge at
the END of a batch — not per-card.** So:

- Do not pause for owner sign-off on every single card; assemble the batch, then
  surface it for the challenge/adjudication pass.
- The human remains the factual-correctness oracle — a card graduating to
  `reviewed` is an owner decision, not the agent's.

## Discipline

1. Prefer the ingest/promotion CLIs over hand-editing seed-JSON.
2. Keep provenance + version on every claim; never let a `reviewed` claim carry a
   model-sourced fact.
3. After a card/matrix change, run the offline suite
   (`python -m pytest sealai_v2/ -q`) and a **targeted** REPLAY on the affected
   knowledge dimension (see `eval-replay-adjudication`).
4. Coverage-depth before breadth (Leitsatz L9): a few deeply-covered cards beat
   many shallow ones. The Gold-Pfad (RWDR) is the flagship — prioritize reviewed
   coverage there.
5. A live knowledge promotion outside the image can go via the Qdrant-interim
   path, but the image deploy still runs the eval-REPLAY gate.
