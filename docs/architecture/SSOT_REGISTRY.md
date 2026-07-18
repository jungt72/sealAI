# sealingAI SSoT Registry

Status: active registry for the ratified SSoT v2.0 and the production V2
runtime. Updated 2026-07-18.

This file is a navigation map, not a competing source of truth. Authority is
defined in `docs/ssot/sealingAI_SSoT_v2.0.md` and summarized in `AGENTS.md`.

## Strategic authority

| Concern | Canonical source |
| --- | --- |
| Product, positioning, horizons, governance, and target architecture | `docs/ssot/sealingAI_SSoT_v2.0.md` |
| Reviewed source artifact | `docs/ssot/sealingAI_SSoT_v2.0.docx` |
| Strategic owner decisions | `docs/ssot/OWNER_DECISION_REGISTER.md` |
| Current hard-gate and M1-M16 status | `docs/ssot/ssot-map.json` |
| Honest product/horizon maturity | `docs/ssot/product-maturity.json` |
| Principle and gate traceability | `docs/ssot/INVARIANT_MAPPING.md` |
| Industry pain evidence | `docs/ssot/PAIN_EVIDENCE_LEDGER.md` |
| Quality operating model | `docs/ssot/QUALITY_ASSURANCE_PLAN.md` |
| External data-contract policy | `docs/ssot/INTEROPERABILITY_CHARTER.md` |

## Current product boundary

- sealingAI is a manufacturer-neutral knowledge, engineering, and sealing-case
  infrastructure, not a general chatbot or price marketplace.
- The current wedge is depth-first H1 knowledge plus the H2 case foundation in
  a limited set of sealing domains.
- H3-H5 are target architecture. They remain planned or in build until their
  own reference sets, expert review, hard gates, and maturity activation exist.
- The final engineering, legal, conformity, and manufacturer release remains
  outside sealingAI.

## Canonical production runtime

| Concern | Canonical source |
| --- | --- |
| Backend package | `backend/sealai_v2/` |
| API composition | `backend/sealai_v2/api/main.py` |
| Chat/SSE boundary | `backend/sealai_v2/api/routes/chat.py`, `backend/sealai_v2/api/sse.py` |
| Pipeline | `backend/sealai_v2/pipeline/pipeline.py`, `backend/sealai_v2/pipeline/stages.py` |
| Core contracts | `backend/sealai_v2/core/contracts.py` |
| Deterministic kernel | `backend/sealai_v2/core/calc/` |
| Technical answer contract | `backend/sealai_v2/core/technical_answer.py` |
| Output guard | `backend/sealai_v2/core/output_guard.py` |
| Case state | `backend/sealai_v2/core/case_state.py` |
| Material-constraint governance (03A immutable snapshots, owner-accepted 03B non-authoritative shadow/pinning, and inert 01A evidence manifests; default-off/sampling zero) | `docs/ssot/MATERIAL_CONSTRAINT_GOVERNANCE.md`, `docs/architecture/ADR_MAT_GOV_03A_PERSISTENCE.md`, `docs/architecture/ADR_MAT_GOV_03B_SHADOW_PINNING.md`, `docs/architecture/ADR_MAT_EVID_01A_PERSISTENCE.md`, `backend/sealai_v2/core/material_rulesets.py`, `backend/sealai_v2/core/material_shadow.py`, `backend/sealai_v2/core/material_evidence.py`; production migrations, runtime evidence binding, activation and MAT-GOV-03C remain NO-GO |
| RWDR adaptive interview (owner-approved limited production scope) | `docs/ssot/RWDR_ADAPTIVE_INTERVIEW_PHASE_0_1.md`, `docs/ssot/RWDR_SHADOW_REVIEW_PROTOCOL.md`, `docs/ssot/reviews/2026-07-14-rwdr-adaptive-interview-cutover/`, `backend/sealai_v2/core/interview/` |
| Knowledge source of record | `backend/sealai_v2/db/models.py`, `backend/sealai_v2/knowledge/ledger.py` |
| Derived retrieval index | `backend/sealai_v2/knowledge/qdrant_retrieval.py` |
| Worker/outbox | `backend/sealai_v2/memory/outbox_daemon.py`, `backend/sealai_v2/knowledge/outbox_worker.py` |
| Auth and tenant boundary | `backend/sealai_v2/security/tenant.py`, `backend/sealai_v2/api/deps.py` |
| Runtime configuration | `backend/sealai_v2/config/settings.py` |
| Database migrations | `backend/sealai_v2/db/migrations/` |
| Dashboard | `frontend-v2/` |
| Marketing | `frontend/` |

`backend/app/` is retired and must not be imported or treated as canonical.

## Subordinate specifications

These documents remain useful where they do not conflict with the strategic
SSoT:

- `docs/V2/sealingai_v2_build_spec.md`
- `docs/V2/sealingai_v2_architektur_prinzipien.md`
- `docs/V2/sealingai_v2_invarianten_charter.md`
- `docs/V2/sealingai_eval_seed_set_v0.md`
- `docs/architecture/2026-07-09-production-architecture.md`

They are implementation and verification specifications, not separate product
strategies. Any incompatible statement is superseded and must be corrected or
explicitly marked historical.

## Systems of record

| Data | System of record |
| --- | --- |
| Claims, sources, review state, cases, decisions, capabilities, jobs, audit | Postgres |
| Original documents, drawings, images, exports | Object storage target; current gap tracked in the implementation audit |
| Retrieval vectors and sparse index | Qdrant, derived and rebuildable |
| Cache, locks, rate limits, short-lived working state | Redis |
| Authentication | Identity provider; authorization remains server-side |

## Release and verification

| Concern | Canonical source |
| --- | --- |
| Backend build | `.github/workflows/build-and-push.yml` |
| Backend deploy | `.github/workflows/deploy.yml`, `ops/release-backend-v2.sh` |
| Served tree hash | `ops/tree-hash.sh` |
| Runtime behavior profile | `backend/sealai_v2/config/runtime_profile.py` |
| Eval and adjudication | `backend/sealai_v2/eval/` |
| Schema validation | `backend/sealai_v2/db/migrate.py` |
| Recovery | `ops/RESTORE.md`, backup and restore scripts under `ops/` |
| Required CI | backend contracts, V2 contracts, secret scan |

A successful candidate smoke is not final-release evidence. Final production
activation requires the SSoT G7/M15 evidence for the exact served artifact.

## Historical material

The following are context only and must not direct current implementation:

- V1, V1.8, V9, V10, LangGraph, and RWDR-MVP runtime concepts under
  `docs/implementation/`, `docs/audits/`, `konzept/`, and old reports.
- Any file naming `backend/app/` as the current runtime.
- Screenshots, browser comments, audit snapshots, and superseded rollout logs.

Historical documents are retained for provenance. They do not regain authority
through recency, detail, or an old `SSoT` label.

## Patch rules

1. Identify the SSoT principle, horizon, hard gate, and maturity affected.
2. Modify only the current runtime and canonical data contracts.
3. Keep new scope default-off until its activation evidence exists.
4. Update `ssot-map.json`, maturity, tests/eval, and rollback in the same change.
5. Never turn draft research, manufacturer self-description, or model output
   into reviewed truth automatically.
6. Never represent planned 360-degree scope as currently available.
