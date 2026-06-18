# V1.8 Wave 0 — Manufacturer-matching containment + log hygiene (report)

**Date:** 2026-06-06
**Branch:** `feat/v18-wave0-mfr-guard` (PR target: `demo/rwdr-limited-external`)
**Decisions executed:** C (guard dormant mfr-match infra) · the (b) verify-then-branch of
the live matching path · B4 (logs carry prompt hashes only).
**Method:** read-only investigation (path+line) → smallest patch (a default-OFF flag + a
source-based architecture test) → no refactor of any matching code (per the CONTAINED
branch rule).

---

## 1. C2 show-me — what the manufacturer infra is, and where it lives

### 1a. The dormant trio (P4 groundwork, **no live caller**)
| Module | Purpose | Provenance |
|---|---|---|
| `app/services/capability_service.py` | `CapabilityService` + `ManufacturerCapabilityClaim`/`Profile` dataclasses; capability claim CRUD over the capability tables (CAPABILITY_TYPES, SOURCE_TYPES incl. `datasheet_extracted`, CLAIM_STATUSES). | `7623b61e` "Add typed manufacturer capability profiles"; `59c5abb5` "Add partner capability eligibility projection" |
| `app/services/manufacturer_fit_matrix_service.py` | `ManufacturerFitMatrixService` → `ManufacturerFitMatrix` with **`fit_score`** ranking rows; carries `PARTNER_NETWORK_DISCLOSURE`. | `a657e8d4` "Add manufacturer fit matrix backend" |
| `app/services/problem_first_matching_service.py` | `ProblemFirstMatchingService` — capability requirement → coverage scoring. | (with the above) |
| `alembic/versions/91f0c2d4a6b8_create_manufacturer_capability_tables.py` | `manufacturer_profiles` + `manufacturer_capability_claims` tables. Migration docstring (Create Date 2026-04-20): *"Sprint 3 Patch 3.2 … The capability service, CRUD/API surfaces, seed import, and matching behavior are **intentionally left to later Sprint 3/4 patches.**"* | `91f0c2d4a6b8` |
| `app/domain/artifact_type.py:19,103` | `ArtifactType.manufacturer_fit_matrix` enum entry + metadata. | — |

**All references (non-test):** the three services import **each other** only; the migration
comment references `capability_service`; `artifact_type.py` holds the string enum entry. The
user-facing scan (api / dispatch / graph / composer / semantic_intent_router) is **empty**.
→ a self-contained dormant island.

### 1b. The live matching path (separate, pre-existing — the audit-gap, see §3)
`graph/nodes/matching_node.py` ("Phase G Block 1", deterministic, no LLM) sets
`matchability_status = "ready_for_matching"` (`:434`) and builds, via
`run_manufacturer_rfq_specialist` (`agent/domain/manufacturer_rfq.py`), a
`ManufacturerCapabilityPackage` carrying `match_candidates`, **`winner_candidate_id`**,
**`recommendation_identity`** (`matching_node.py:~444-450`). The default data source is
`DummyDomainDataProvider` (`agent/domain/governed_data.py:204`) seeding **"Acme"/"SealTech"**
(`:136,:157`); nothing calls `set_default_domain_data_provider`, so Dummy is the prod default.

---

## 2. Verify-then-branch (V1–V4) → verdict **CONTAINED**

| # | Check | Evidence | Result |
|---|---|---|---|
| **V1** | Does the browser-bound DTO serialize the matching-identity fields? | `endpoints/state.py:110` `GET /state/workspace` → `response_model=CaseWorkspaceProjection`; matching exposed only via `partner_matching: PartnerMatchingSummary` (`schemas/case_workspace.py:978`). `PartnerMatchingSummary` is **`extra="forbid"`** (`:281`) and declares only `matching_ready/shortlist_ready/inquiry_ready/…/material_fit_items/selected_partner_id/data_source` (`data_source` default `"candidate_derived"` = "no real partner database connected"). `winner_candidate_id`/`recommendation_identity`/`match_candidates`/`matched_primary_candidate` are **not declared → stripped at the wire.** | **Stripped** |
| **V2** | Frontend rendering? | The exact field names are **not** consumed in `frontend/src`. `ManufacturerFitPanel.tsx` (renders `fitScore`/`manufacturerId`) is referenced **only** by its own export + a copy-lint spec — **not mounted** in any screen. Its data source `workspace.matching.manufacturerFitMatrix` maps from `projection.partner_matching.manufacturer_fit_matrix \|\| projection.manufacturer_fit_matrix` (`mapping/workspace.ts:1630`). | **Not mounted; reads a field that doesn't exist** |
| **V1-decisive** | Does the backend ever emit `manufacturer_fit_matrix`? | grep `backend/app/api` + `backend/app/agent` (non-test) for `manufacturer_fit_matrix`/`fit_score`/`eligible_partner_count`/`no_suitable_partner` → **empty**; absent from the schema. | **Never produced** → panel always shows its dormant "*Partner können später sichtbar werden*" fallback |
| **V3** | Is the Dummy provider prod-default; can "Acme"/"SealTech" surface? | Dummy is the module default (`governed_data.py:204`); nothing swaps it. But per V1+V1-decisive the seeded names cannot reach a user surface (identity fields stripped; fit-matrix never produced). | **Prod-default but unreachable** |
| **V4** | Doctrine gating | Not required for the verdict — structural containment (V1) + never-produced matrix (V1-decisive) + unmounted panel (V2) is dispositive. The L1/L2 manufacturer/recommendation/comparative-ranking guard is an **additional** backstop on ChatReply text. | n/a (backstop only) |

**Verdict: CONTAINED.** The live path computes a winner/recommendation **internally** (RFQ
handover) but it is walled off from every user surface on three independent layers. The
frontend mapper + `ManufacturerFitPanel` are **latent P4 capability** wired to a wire field
the backend never feeds.

---

## 3. Audit-gap note (formal)

The V1.8 deep audit (`v18_audit_report.md`) scanned the **dormant trio** but **missed the
live `matching_node` → `manufacturer_rfq` path** that computes `winner_candidate_id` /
`recommendation_identity`. The verdict (CONTAINED) does not change the audit conclusions, but
the gap is recorded here and guarded by the new test family so it survives the session.

---

## 4. What shipped (smallest patch — no matching code refactored)

1. **Default-OFF activation gate** — `Settings.SEALAI_ENABLE_MANUFACTURER_MATCHING: bool = False`
   (`app/core/config.py`), the single sanctioned gate for any future P4 activation.
2. **Containment architecture test** — `tests/architecture/test_mfr_match_dormant.py`
   (source-based AST, runs with and without conftest / `--noconftest`):
   - dormant trio has **no live importer** (only intra-trio imports allowed);
   - the wire schema **does not declare** any of `winner_candidate_id`,
     `recommendation_identity`, `match_candidates`, `matched_primary_candidate`,
     `manufacturer_fit_matrix`; `PartnerMatchingSummary` stays `extra="forbid"`;
   - `manufacturer_fit_matrix` is **never** a wire field (the panel can't light up);
   - the activation flag is **default-OFF** (env-independent);
   - **B4:** `PromptTrace` carries `rendered_prompt_hash` only, no raw-prompt field, `extra="forbid"`;
   - two synthetic-violation companion tests (anti-false-pass).
3. **No removal** (C4) — the trio, tables, artifact entry, and latent frontend panel are
   preserved as P4 groundwork; dormancy is now enforced, not deleted.

**B4 log hygiene — verified clean.** A comprehensive scan of `backend/app` for log/print
calls emitting `prompt`/`messages`/`content`/`completion` found **one** match,
`agent/cli.py:100` (`print(final_output["messages"][-1].content)`) — the developer CLI
printing the **final answer** to stdout, not a server log sink and not a prompt. No structlog
kwarg leaks; `langsmith_capture_llm_content=False`. No fix required.

---

## 5. Compliance / No-Go entry — **ACCEPTED**

The internal RFQ-handover (`matching_node` → `manufacturer_rfq`) is **ACCEPTED** as
non-surfacing internal structure for the RWDR MVP, on the V1–V4 evidence above, with the
containment now test-enforced. Re-exposing any matching identity to a user surface, or wiring
the dormant trio without `SEALAI_ENABLE_MANUFACTURER_MATCHING`, trips
`test_mfr_match_dormant.py`. Removal of the dormant infra remains a later product decision
(C4), to be taken on this evidence.

---

## 6. Tests

```
cd backend && ../.venv/bin/python -m pytest tests/architecture -q          → 20 passed (exit 0)
cd backend && ../.venv/bin/python -m pytest tests/architecture/test_mfr_match_dormant.py -q --noconftest → 7 passed (exit 0)
doctrine fast suite (comparative-ranking guard + leak golden + final-guard backstop) → green (exit 0)
```

§7.10 prohibition check: additive only — no write-tool, no state mutation outside the gate,
no LLM calculation, no per-seal-type graph, no checkpointer business read. The matching code
is untouched (no refactor).
