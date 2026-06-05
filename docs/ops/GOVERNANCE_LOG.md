# Governance Activation Log

Append-only logbook for activation and verification of the SealAI governance
gates (doctrine-gate, deploy-gate, branch-guard, read-only reviewer). One entry
per activation/verification event. Newest on top.

---

## 2026-06-05T06:03Z — C10 echo prod deploy + Parked-Items-Closeout COMPLETE

C10 manufacturer-response echo deployed to prod through the standard gates (the HALT in the
05:42Z entry, released on explicit owner go). Pre-deploy gate **re-run** on the deploy
candidate `demo@ccdd4577` (`pytest backend` **EXIT=0**; sentinels not recycled — refreshed);
rollback anchor read from the running daemon, never memory. Deploy via
`ops/release-backend.sh` (build → GHCR push → pin `@sha256` in `.env.prod` → recreate backend
→ health + auto-rollback → nginx reload → live smoke).

- **Deployed digest:**
  `ghcr.io/jungt72/sealai-backend:ccdd4577-20260605-060228@sha256:045c2c2fc4583b1a13890437cd16006e72409ff4d1acf4313a781172adc4a933`
- **Rollback target (prior live, from the daemon):**
  `ghcr.io/jungt72/sealai-backend:2d325acf-20260604-181319@sha256:6d3c38266ccf116a9632b0e7f86974a53fd1b84ca7dc885fee923106fdb64877`
- Health `healthy` (redis / qdrant / agent_runtime); nginx reloaded; **live pilot smoke all
  PASS**; the echo wiring (`manufacturer_echo_notes`) is confirmed present in the running image.
- **Convergence:** `demo→main` carry **PR #86** merged as a merge-commit (`79f3ab66`; no squash;
  demo branch intact) → **main ⊇ demo**. Deploy/Build-Push workflows **did not run** on the main
  push (prod is digest-pinned; deployment happened via `ops/release-backend.sh`). Branch
  protection unchanged.

**Parked-Items-Closeout abgeschlossen 2026-06-05.** Open only:
(i) Keycloak service-account wiring for the admin scripts [documented, undated];
(ii) S5-Mode-Konsolidierung [LOW, deliberate];
(iii) item (d) `.env` `KEYCLOAK_ADMIN_PASSWORD` placeholder [owner-manual, instructions in the runbook].

---

## 2026-06-05T05:42Z — Parked-Items-Closeout (Keycloak cleanup, C10 echo wired, branch strategy decided)

Closeout session taking every parked item to a documented terminal state. Three owner
decisions: **C10 echo → wire**; **branch strategy → keep + codify**;
**`registrationAllowed` → false**. No undocumented open item remains; the one
deliberately-open item (d) is recorded with its reason.

**Phase 1 — Keycloak cleanup (live realm, owner-gated, lockout-safe order).** Owner logged
in interactively (recovery admin `test`); CC ran only read/cleanup `kcadm` against the
cached token — no secrets in the transcript. Read-only status **contradicted runbook item
(b)**: the master-realm `jungt` (`9f0906ab…`) was **not** a credential-less crashed-run row
— it had a valid password + non-admin roles. Surfaced (**HALT, not silent action**); owner
decided to delete it as accidental master-realm clutter. Order honored — **rotation before
recovery-user deletion**: the real admin is **`superadmin`** (there is no `admin` user);
owner rotated `superadmin`'s password (console, Temporary=OFF) + verified login, **then**
the recovery admin `test` (`bae9fa04…`) was deleted. `registrationAllowed=false` on the live
`sealAI` realm (B2B — self-registration only yields locked-out 401 users); realm backed up
first → `~/keycloak-backups/20260605T051149Z/sealAI-realm-export.json`, and both seed exports
updated (`keycloak/realm-export.json`, `keycloak/import/realm-export.json`). **Master-realm
end state verified: only `superadmin`; sealAI `jungt` (`7748ba15…`) untouched.** Closeout
recorded in `docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md`.
**Item (d) — DELIBERATELY OPEN (owner action; CC does not touch `.env*`):** remove the stale
`KEYCLOAK_ADMIN_PASSWORD` from `.env*`, keep exactly one authoritative store (password
manager). The app needs no master-admin password at runtime (bootstrap relic).

**Phase 2 — C10 manufacturer-response echo: WIRED** (PR #84 → demo, merge `9615dd52`). The
intake was live but the projection `manufacturer_response_echo_notes()` had no caller. Wired
the last hop at the single funnel `RWDRCaseOrchestrator.build()`: recorded responses (raw
envelopes) now surface as `rag_supported` notes on
`TechnicalRWDRRFQBrief.manufacturer_echo_notes` + a conditional brief section — never a
confirmed fact, guard-scrubbed to the neutral fallback. **Red-before-green** (2 wiring tests
red→green + 1 invariant guard). **doctrine-reviewer: APPROVE** (four comparative-ranking
repros still block at L1; AC8 no-over-block + AC9; no guard/lexicon/streaming/mutation
touched; purely additive, backend-only). CI green (`agent-bff-guardrails`, `backend
ruff-format`).
**Prod deploy: HELD at 🛑 HALT (owner-gated).** Pre-deploy gate `pytest backend` **EXIT=0**;
sentinels staged (`pytest-green`, `anchor-verified`); rollback anchor read from the running
daemon: `ghcr.io/jungt72/sealai-backend:2d325acf-20260604-181319@sha256:6d3c3826…`
(status=running health=healthy). No `release-backend.sh` run by CC.

**Phase 3 — Branch strategy: DECIDED (was parked).** Keep the demo-integration model and
codify it in `.claude/rules/ops.md`: all PRs target `demo/rwdr-limited-external`; `demo→main`
convergence is owner-gated, per milestone/day, with a carry-over PR per demo merge; matches
existing branch-guard/hooks/CI (no infra change). Trunk-based not adopted; the CI-trigger /
`ruff format` scope questions remain **separately parked**.

**Phase 4 — Ledger:** this entry + the journal (`docs/runtime-audit-fixmap.md`). Docs
(Phases 1 + 3 + 4) ship in one closeout PR → demo; each demo merge gets its `demo→main`
carry-over PR (owner-gated).

---

## 2026-06-04T20:05Z — Legacy cleanup: remove red double-CI + delete dead dirs (NO prod deploy)

Two owner-decided cleanups; no prod deploy; branch protection unchanged; demo→main convergence
held (each via PR → demo → small demo→main carry-over).

**TEIL 1 — removed the legacy `.github/workflows/ci.yml`** (PR #79 → demo, #80 → main). It was a
Sprint-9-origin, **main/master-only** workflow whose `Lint (ruff)` job ran whole-repo
`ruff format --check .` + `ruff check .` and was permanently red on the legacy debt → error mails
on every main push (alarm-deafness); its pytest/docker jobs only ever skipped (`needs: [lint]`).
Canonical CI is now `agent-bff-guardrails` (the required check) + the `backend-ruff-format`
re-debt guard; backend pytest is the local pre-deploy gate, docker build runs in the release
scripts. Lint was never a required check, so branch protection is unchanged. **No more red `CI` runs.**

**TEIL 2 — deleted dead legacy dirs** (PR #81 → demo, carry-over → main; pure deletions, 225 files):
`archive/` (21M, archived legacy frontend `legacy_phase2`) and `langgraph_backup/` (756K, backup
of the removed langgraph). **`seo/` KEPT** (recent `sealai_seo` tool with a systemd service — not
dead legacy). Safety-checked read-only first: **nothing imports either dir**; both recoverable from
git history; the `NON_CANONICAL_TREES` SSoT guardrail test stays green (doc-string check) and the
`check-secret-hygiene` allowlist entry is left vestigial-but-harmless (pure-deletion PR).

**Backlog closed:** the parked "legacy ruff cleanup" follow-up (noted in the 19:05 convergence
entry) is **resolved** — `archive/` + `langgraph_backup/` are gone; the only remaining whole-repo
`ruff format` non-conformance is `seo/`, which is kept as an active standalone tool and is outside
the `backend-ruff-format` guard's scope. Backend is ruff-format-clean and guarded; no further
legacy ruff work pending.

---

## 2026-06-04T19:05Z — demo→main convergence + v1.7.0 release tag (NO prod deploy)

Converged `demo/rwdr-limited-external` → `main` via PR #11 as a **merge-commit** (`bffa2188`;
no squash — the full ~677-commit governance trail is preserved). Production **untouched**
(digest-pinned; the main push's Deploy/Build-Push workflows **skipped**; no `release-*.sh` run).
No force-push, no history rewrite, no branch deletion — demo stays the active integration branch.

**STEP 0 (read-only):** main was **not** an ancestor of demo — main carried **6 unique
CI/CD-stabilization commits** (2026-04-23/24: `e406c705 430ecbf0 56bd8c89 9acf753e 5331a9d9
d846582f`); demo was **+677** ahead. Merge dry-run: the **only** conflicts were 4 CI/ops files —
**zero product-code conflicts**. Merge-base `042810ef`.

**Resolution (owner decision: demo-CI canonical):** merged `origin/main` into demo (`349e10ce`)
resolving the 4 conflicts (+ `ci.yml` / `check_no_langgraph_v1.sh`) to **demo's versions** — the
merged tree is **byte-identical to demo HEAD** (zero tree change; main's April CI content
superseded but preserved as a merge parent). Then PR #11 (demo→main) merged conflict-free.

**CI on main:** `agent-bff-guardrails` **green** (×2). The repo-wide `ruff format --check`
(`Lint (ruff)`, **716 files** — all of `backend/` + `seo/archive/langgraph_backup/...`) is **red**
but **pre-existing / repo-wide / not a V1.7 regression** and never gated demo PRs; accepted as an
out-of-scope follow-up (owner decision). pytest/docker jobs skipped by `ci.yml` conditions.

**Tag + release:** annotated **`v1.7.0`** on `bffa2188` + GitHub release. Verdikt: **V1.7 erreicht
— ja-mit-Amendments** (`docs/audits/2026-06-04_v17_gap_audit_rerun.md`).

**Branch protection on `main` (gh api, set):** PRs required (`required_approving_review_count: 0`);
**`agent-bff-guardrails`** as the **required** status check (the ruff debt deliberately NOT
required); force-pushes + deletions blocked; `enforce_admins: false`.

**Verification:** `git merge-base --is-ancestor 349e10ce origin/main` = true (main ⊇ demo); the
key V1.7 files (enforcer tests, `oring_calc.py`, GOVERNANCE_LOG, both audits, CORE_PACK_BOUNDARY)
exist on main.

---

## 2026-06-04T18:37Z — Frontend Brand/UI-Refresh prod deploy

Frontend-only release of the Codex-authored brand/chat-UI refresh (owner-approved; PR #72 on
`demo/rwdr-limited-external`, checked in verbatim). Not a doctrine/governance change — logged
per the **owner's standing rule (2026-06-04): every prod deploy is recorded here, no exceptions**
(backend, frontend, doctrine or brand).

**Scope:** new PNG logos + `SealAiBrand` (inline SVG → `next/image`); `DashboardShell`
header/sidebar restyle + user-identity card; `ChatComposer` pill/glass restyle; `ChatPane`
empty-start simplified (starter prompts + client-side JWT name greeting removed). 9 files, no
secrets / `.env` / build artifacts.

**Quality gate:** `next build` EXIT=0; `vitest` 198/199 — the only red, `workspaceMapping.test.tsx`,
**proven pre-existing** (fails on the clean tree with the changes stashed); `test:node` 35/35.

**Deploy (`ops/release-frontend.sh`, EXIT=0):** new pinned image
`ghcr.io/jungt72/sealai-frontend:d40d7145-20260604-183558@sha256:fdb5ced64153aee727b1b2eb7ad8d7fda0dec398c5b8d225cfabfb3ff7cc19d6`.
Frontend healthy (`/api/health` → `ok`); nginx reloaded; **live pilot smoke 14/14 PASS**. Rollback
target `…sealai-frontend:7eb3d9f4-20260604-174637@sha256:59e433fd58dba0baf9d9d3179780bc6d7d2fde113f440e2ccae3ab4a66ebc723`
via `.env.prod.rollback-20260604-183558` (read from the running daemon, not memory). Owner does the
visual acceptance check on https://sealingai.com.

---

## 2026-06-04T18:14Z — P1-4 prod deploy (C1/C9/S3 + enforcers)

Follow-up deploy to the demo-merge entry below. HALT-before-prod honoured: the four-part risk
summary presented (behaviour-neutral; all freezes byte-identical; both enforcers synthetic-proven;
L1/L2 + Tier-0 untouched; four comparative-ranking repros still block; two `doctrine-reviewer`
APPROVEs) + explicit operator **go**.

**Pre-deploy gate:** full backend suite `EXIT=0` re-run on the exact deployed commit `2d325acf`
→ fresh `pytest-green`; rollback anchor `…@sha256:05953eda…` (running/healthy from
`docker inspect backend`, never memory) → fresh `anchor-verified`. Confirmed PR6's docs-only merge
did **not** revert PR5b (3-way merge took demo's PR5b versions; `produce_*` + both enforcers
present on HEAD).

**Deploy (`ops/release-backend.sh`, RELEASE-EXIT=0):** new pinned image
`ghcr.io/jungt72/sealai-backend:2d325acf-20260604-181319@sha256:6d3c38266ccf116a9632b0e7f86974a53fd1b84ca7dc885fee923106fdb64877`.
Backend healthy (redis/qdrant collections=2/agent_runtime); nginx reloaded; **live pilot smoke
14/14 PASS**. Rollback target `…@sha256:05953eda…` via `.env.prod.rollback-20260604-181319`.

**Scoped re-verification on the deployed image (`docker exec backend`):**
- **C1 → ERFÜLLT** — seam selectors live in `seal_packs.py`; **zero** `== "rwdr"`/`!= "rwdr"`
  control-flow in the routed core (`reducers`/`challenge_engine`/`case_workspace`/`checks_registry`/
  `calculation_projection`).
- **C9 → closed** — `app/agent/domain/oring_calc.py` present; orchestrator core has **0**
  `_oring_calculations`.
- **S3 → ERFÜLLT** — 3 `produce_*` single-writer helpers live; **zero** governed-layer
  `model_copy` bypass in the routed sites.
- **C10 → ERFÜLLT (deferred, unchanged)** — `manufacturer_response_echo_notes` still caller-less,
  by design.

Re-Run-Doc verdict updated **nein → ja-mit-Amendments**. No guard/lexicon/doctrine test weakened;
no gate bypassed.

---

## 2026-06-04T17:57Z — P1-4 C1/C9/S3 closure + architecture enforcers (demo-merged; HALT-before-prod)

Closes the V1.7 re-run audit's open verdicts (`docs/audits/2026-06-04_v17_gap_audit_rerun.md`):
**C1 TEILWEISE/HIGH → ERFÜLLT**, **C9 LOW-Vorbehalt → closed**, **S3 TEILWEISE → ERFÜLLT**.
Eight small PRs to `demo/rwdr-limited-external`, P1-1 discipline (characterization-freeze
committed before each refactor, zero behaviour change):

- **C1** — routed the three audited core surfaces (`reducers.py` PR1, `challenge_engine.py` PR2,
  `case_workspace.py` PR3) **plus** the decision-A extras the inventory surfaced
  (`checks_registry.py` / `output_contract_assembly.py` / `calculation_projection.py`, PR3.5)
  through the pack seam. The calc_type sites use the new exact `pack_for_calc_type` (a dotted
  `rwdr.<id>` divergence vs `pack_for_calc_id` was red-proven and avoided).
- **C9** — relocated `_oring_calculations` out of the v92 core orchestrator into
  `app/agent/domain/oring_calc.py` (PR4; no `OringPack`).
- **S3** — routed all governed-layer `model_copy` content-syncs (`api/utils.py`,
  `output_contract_assembly.py`, `persistence.py`, `sheet_events.py`) through
  `reducers.produce_governance/produce_decision/produce_normalized` (PR5b).
- **Enforcers (the actual goal)** — `test_core_seal_type_branching.py` (no seal-type branching in
  the core outside a documented allowlist = the heterogeneous `risk_readiness` checks + the
  `normalize_seal_type` classifier) and `test_single_writer_invariant.py` (governed-layer state
  produced only by the reducer chain). Both carry synthetic-violation proofs; CI-effective (PR5a/PR5b).

**Reviews:** `doctrine-reviewer` APPROVE on PR1 (mutation core) and on PR5b (after one
REQUEST-CHANGES round that caught a bare-variable `normalized.model_copy` single-writer gap at
`sheet_events.py:190`, now closed). Boundary doc corrected (the earlier P1-3 "resolved" over-claim);
prior-audit S1/S2 matrix rows reconciled TEILWEISE → ERFÜLLT (stale; detail P1-2 already ERFÜLLT).

**Adjacent owner decisions:**
- **C10** (manufacturer-feedback echo) — **deferred** (not wired). `manufacturer_response_echo_notes`
  is implemented + tested but caller-less; wiring deferred to the Knowledge contract seam
  (`dashboard_contract._knowledge_notes`). AC10 ("als Wissensquelle vorgesehen") stays ERFÜLLT.
- **V1.7 §6.4 off-branch caveat** — `origin/feat/v1.7-blueprint` §6.4 still lists
  `CaseUnderstandingPatch + RFQBriefPatch`; off-branch + non-binding (AGENTS.md: V1.6/RWDR-MVP is
  binding). Noted, unrekonziliert by design.

**Pending:** 🛑 HALT-before-prod — the bundled prod release (full backend pytest exit=0 + fresh
daemon rollback anchor + enforcer proof) and the scoped C1/C9/S3/C10 re-verification → Re-Run
verdict update to "ja-mit-Amendments" are recorded in a follow-up entry at deploy.

---

## 2026-06-04T14:43Z — P2-1 Knowledge-Marker (C5) + Herstellerfeedback (C10) — Sammel-Release

Closes the last two open gap-audit items (`docs/audits/2026-06-03_v17_gap_audit.md`):
**C5 TEILWEISE → ERFÜLLT** and **C10 FEHLT → ERFÜLLT**. Two demo PRs + one fix,
then one combined prod release; HALT-before-prod honoured with the four-deliverable
risk summary and explicit operator go.

**Demo merges (each: full suite EXIT=0 + fast-doctrine green + CI `agent-bff-guardrails` pass):**
- **TEIL B (#59, C10) — doctrine/mutation path:** `manufacturer_response` intake
  (`POST /rfq/rwdr/cases/{id}/manufacturer-feedback`, tenant-scoped, open-point
  candidate under a namespaced key) + guarded `rag_supported` echo + brief-gate
  backstop (`_NEVER_BRIEF_SOURCE_TYPES` short-circuit in `_blocked_reason` **before**
  the origin branches — `_BLOCKING_SOURCE_TYPES` alone leaked via `user_entered`
  origin laundering). **doctrine-reviewer APPROVE**: full 5×5 laundering matrix → 0
  leaks; red-before-green load-bearing; four L1 comparative-ranking repros still
  block (`output_guard.py`/`final_guard.py` untouched); AC8 no over-block; AC9 echo
  is a pure read; zero-FP (no existing fact carries the source_type).
- **TEIL A (#60, C5) — additive, non-doctrine:** `ChunkMetadata.pack_affinity`
  (None=cross-cutting, "rwdr"=pack) + `classify_pack_affinity()` (single SoT
  ingest+backfill); ingest sets it; **retrieval-inert** (not in
  `_SUPPORTED_METADATA_FILTER_KEYS`; payloads read as raw dicts). Backfill script
  (dry-run-default, idempotent, conserved accounting).
- **#61 fix:** backfill default collection → `sealai_knowledge_v3` (live corpus).

**Prod deploy (`ops/release-backend.sh`, RELEASE-EXIT=0):**
- Pre-deploy gate: full backend suite `EXIT=0` → fresh `pytest-green`; rollback
  anchor `…@sha256:afb82cfb…` (running/healthy from `docker inspect backend`, never
  memory) → fresh `anchor-verified`.
- New pinned image
  `ghcr.io/jungt72/sealai-backend:3627b2f7-20260604-144259@sha256:05953eda7885130b8a5cd97021a46742ff497aefe6b4a51480e5349a0d470362`
  (built from demo `3627b2f7`). Backend healthy (redis/qdrant/agent_runtime,
  qdrant collections=2); nginx reloaded; **live pilot smoke 14/14 PASS**. Rollback
  target `…@sha256:afb82cfb…` via `.env.prod.rollback-20260604-144259`.

**Post-deploy backfill + characterization (operator sequence):**
- Backfill `sealai_knowledge_v3` (script `docker cp`-ed in — the image does not ship
  `scripts/`): dry-run = `--apply` accounting **total 83 = 0 already + 7 rwdr + 76
  cross-cutting** (conserved); applied 83 writes, `post_check_missing_marker=0`;
  2nd dry-run `writes=0` (idempotent).
- **Retrieval characterization: identical hit-sets before/after across 5 queries
  (0 result-diff)** — the marker is inert, exactly as designed. Temp script +
  baseline removed from the prod container afterward.

Gap-audit **C5 + C10 → ERFÜLLT**; the P2-1 (last) patch-order item is closed. No
guard/lexicon/doctrine test weakened; no gate bypassed.

---

## 2026-06-04T13:04Z — P1-3 residual rwdr risk branches (closes C1 residual)

Behaviour-neutral follow-up to P1-1 PR3's surfaced residual (`risk_readiness.py`).
Same P1-1 discipline: STEP-0 map → characterization freeze committed before the
refactor → small commits.
- `:527` runout_risk + `:555` surface_risk (clean `== "rwdr"`) → `pack_for_engineering_path`.
- `:499` speed_pv_risk (`{rwdr, ms_pump, unclear_rotary}` — heterogeneous, no 1:1 pack
  equivalence) → **HALT → owner chose: keep as a documented CORE check** (honest core
  check > contorted abstraction). PR #56.
- Proof: characterization freeze green before+after (incl. the `:499` neutrality pin
  that ms_pump/unclear_rotary still emit the risk); full backend suite EXIT=0;
  **doctrine-reviewer APPROVE** (`pack_for_engineering_path(x) ⇔ x=="rwdr"`, 1:1).
- Deploy `…@sha256:afb82cfb…` (operator-approved HALT); live spot-check confirms
  rwdr runout/surface via pack, `:499` set intact for all three paths, tier-0 guard
  still enforced. Gap-audit **C1 → ERFÜLLT** (residual closed).

---

## 2026-06-04T12:41Z — P1-2 Trace/Tier (S1/S2) + prod-deploy chain since P0-2

Prod-deploy continuity since the P0-2 entry (each via `ops/release-backend.sh`,
full-suite `EXIT=0` + fresh `pytest-green`/`anchor-verified` sentinels + live
pilot smoke; HALT-before-prod honoured with explicit operator go each time):
- **P0-3** (pocket `rfq_status` single-source + envelope-stub removal) →
  `…@sha256:6916d557…` + frontend `…@sha256:f27f9b5e…`.
- **P1-1** (Core/Pack boundary — DomainPack protocol, RWDR-only; behaviour-neutral)
  → `…@sha256:d5ff7e08…`.
- **P1-2** (this entry) → `ghcr.io/jungt72/sealai-backend:d582544d-20260604-124056@sha256:808e5cae…`.

**P1-2 — Gap-audit S1 + S2, two PRs, different blast radius:**
- **TEIL A (#53, obs):** one central streaming timing source fills
  `first_progress_ms`/`latency_ms` for all TurnRoutes (`turn_timing.py` contextvar
  timer; `SSEEventBuilder.event()` stamps the final `state_update`). Mobile trace
  byte-identical. Autonomous → demo.
- **TEIL B (#54, enforcement):** fail-closed Tier-0 retrieval guard — `turn_tier.py`
  (`TierViolation`, declared-tier contextvar, kill-switch `SEALAI_TIER0_RETRIEVAL_GUARD`
  default ON / incident-only / logged) + **one** `enforce_retrieval_allowed()` at the
  `hybrid_retrieve` funnel; tier declared in `dispatch.py` from the pre-gate
  classification. Tier-0 = {GREETING, META_QUESTION, BLOCKED} (operator decision,
  strict-safe). Red-before-green + **false-trip proof** (scenario matrix S1-S10 +
  golden + dispatch + full suite + live smoke → 0 TierViolation on legitimate
  paths). **doctrine-reviewer APPROVE.**
- Live acceptance (deployed container): guard default-ON, Tier-0 → `TierViolation`,
  Tier-1 → allowed; timer fills the timing fields.
- Reviewer note recorded: the broad `except` at the 3 call sites catches
  `TierViolation` → a wrongly-Tier-0 retrieval manifests as a logged failure + no
  cards (fail-safe, not a 500). Kill-switch doc: `.claude/rules/ops.md`.

Gap-audit S1+S2 → ERFÜLLT; risk #5 closed. Residual rwdr branches
(`risk_readiness.py:498/:527/:555`) deliberately untouched (own later pass).

---

## 2026-06-04T09:00Z — P0-2 tenant-fallback removal: code + migration + prod deploy

Closes audit **C6** (`docs/audits/2026-06-03_v17_gap_audit.md`) together with P0-1.
Three gated steps, each evidence-backed; HARD HALTs honoured (operator-approved
migration scope and deploy).

- **(A) Code — demo PR #46.** New strict resolver
  `app.services.auth.dependencies.require_tenant_id` → missing/empty tenant claim is
  a hard 401, never `"default"`/`user_id`. Converted request-scoped sites
  `deps.py:23`, `rfq.py:42`, `memory.py:40` (LTM), `rag.py:57` (private RAG),
  `chat_history.py` ×4. Shared-tenant (`RAG_SHARED_TENANT_ID`, Paperless) paths
  untouched — invariant test. Red-before-green
  `backend/tests/unit/services/test_p0_2_strict_tenant_resolver.py` (8 red → green);
  affected + fast-doctrine suites green. No deploy on (A).
- **(B) Migration — prod DB.** `ops/migrations/p0_2_unify_tenant_to_sealai.sql`
  (idempotent, dry-run-default). pg_dump backup first
  (`~/sealai-db-backups/20260604T084655Z/sealai_p0_2_pre_migration.dump`, 40 MB).
  Dry-run + idempotency proof → HARD HALT → operator approved **real-data scope**.
  Applied: **374** cases (353 `default` + 21 real realm-user) + 1337/1337
  `mutation_events`/`outbox` `default` rows → `sealai`. Untouched: 21 test-label
  cases, `rag_documents` (7, shared-tenant), `audit_log` (9, append-only). Per-table
  totals conserved; 2nd pass = `UPDATE 0`.
- **(C) Deploy — prod backend.** Pre-deploy gate: full backend suite exit 0 →
  fresh `pytest-green`; rollback anchor `…@sha256:c0406be9…` running/healthy →
  fresh `anchor-verified`. `ops/release-backend.sh` RELEASE-EXIT=0. New pinned image
  `ghcr.io/jungt72/sealai-backend:f3a8aa20-20260604-090045@sha256:6916d557…`;
  backend healthy (redis/qdrant/agent_runtime); nginx reloaded; live pilot smoke
  passed. **Live acceptance:** in-container `present-claim → "sealai"`,
  `no-claim → 401 missing_tenant_claim`. Rollback target `…@sha256:c0406be9…` via
  `.env.prod.rollback-20260604-090045`.

**Onboarding consequence (logged, accepted):** the realm has
`registrationAllowed=true`, so a new/attribute-less user now gets 401 on
case/RFQ/RAG/memory/chat-history until an admin sets their `tenant_id`. The 6
existing realm users carry `tenant_id=sealai`. Runbook
`docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md` updated with the admin onboarding step.

---

## 2026-06-04T06:00Z — First production deploy through the active deploy gate (P0-1)

P0-1 (LTM tenant scoping) shipped to prod as the **first real release gated by the
active deploy-gate**. The gate passed on two FRESH sentinels, each produced by a
real gate step (never fabricated):
- `pytest-green` — full backend suite `.venv/bin/python -m pytest backend -q -rf`
  exit 0 (chained `&& touch`); 0 failures.
- `anchor-verified` — `docker inspect backend` digest matched the expected rollback
  anchor `…@sha256:d102da88…`, status running/healthy.

Release via `ops/release-backend.sh` (RELEASE-EXIT=0):
- **Rollback anchor (pre-deploy):**
  `ghcr.io/jungt72/sealai-backend:8431dda2-20260603-190217@sha256:d102da8820b9f4c66057d85573a11d55a1e99d2c3359176db4233708fca9f78e`
- **New live image (post-deploy, from daemon):**
  `ghcr.io/jungt72/sealai-backend:89d73ff3-20260604-055825@sha256:c0406be90c136bf73c6e4c746b9fedbe220e380cf922ee34331a79cd7d132127`
  (built from demo `89d73ff3`, which includes P0-1 `d072a892`), status running/healthy,
  started 2026-06-04T05:58:54Z.

Acceptance: `/health` healthy (redis/qdrant/agent_runtime); live pilot smoke 14/14
PASS; `GET /api/v1/memory/export` → 401 (auth boundary intact, no 500). `LTM_ENABLE`
unset live → endpoints early-return, so P0-1 is enforcement-neutral (zero behavior
change for current single-tenant logins), exactly as the pre-deploy HALT analysis
predicted.

The deploy-gate behaved correctly: it required both fresh sentinels and did not
wrongly block. No gate weakened or bypassed; no P0-2 code (awaits the manual
Keycloak `tenant_id` mapper — see `docs/ops/KEYCLOAK_TENANT_ID_MAPPER.md`).

---

## 2026-06-04T05:48Z — Gate hardening F1/F2/F3 + four-quadrant re-verification

Both PreToolUse hooks now match on the executed command only
(`jq -er '.tool_input.command // empty'`), never the whole payload; the deploy
gate fires only on an actual **invocation** of the release script. **Fail-closed**:
jq missing / malformed payload / undeterminable command → BLOCK (validated). The
payload shape was verified live before the change (`.tool_input.command`), and the
new logic was validated out-of-band (16/16 synthetic cases) before an atomic swap,
so a parse bug could not lock the session out. **Session:**
`1b1be06d-dfd9-4cc6-895d-2ec7353181c6`. Branch `proof/gate-harden-reverify` removed;
worktree clean.

| Quadrant | Expectation | Result | Evidence |
|---|---|---|---|
| **FP1** | `git diff` with "git commit" in the **description**, suite RED | **now PASS (not blocked)** | command ran rc=0; no doctrine-gate log entry (gate short-circuited on command-only match) — contrast prior `05:14:24Z BLOCK` |
| **FP2** | real `git commit` whose **message** names `ops/release-backend.sh` | **now PASS (allowed)** | commit `68a3fcd1` succeeded rc=0 (deploy gate saw a mention, not an invocation) |
| **TP1** | real `git commit` with synthetic RED suite | **still BLOCK** | `05:46:32Z BLOCK — guard suite FAILED`; `DOCTRINE GATE (fail-closed): … FAILED` |
| **TP2** | real `bash ops/release-backend.sh` with no sentinel | **still BLOCK, no build** | `DEPLOY GATE (fail-closed): missing sentinel — full backend pytest exit 0` |

Out-of-band fail-closed proofs (all BLOCK): malformed payload, absent command
field, jq unavailable (stripped PATH) — for both hooks. Standard proofs re-run:
branch-guard (`git push origin HEAD:main` → permission denied), reviewer
(`doctrine-reviewer` toolset = Read, Bash only), ops.md ↔ `deploy-gate.sh`
freshness consistent (`<1h` / `MAX_AGE=3600`). No quadrant failed; no gate was
weakened (changes tighten matching and keep fail-closed).

Docs in the same change: `.claude/rules/ops.md` gains a command-parsing +
deliberate-residual-gaps note (`sh -c`/alias/variable constructs not caught — a
discipline anchor, not a sandbox) and the hot-reload activation reality;
`.claude/agents/doctrine-reviewer.md` gains the F3 read-only (Bash-by-convention)
line.

---

## 2026-06-04T05:26Z — Re-verification against the durable (merged) gates

**Governance aktiv ab 2026-06-04T05:07Z**, durable auf `demo` (activation commit
`645e9f62`, merged via PR #38). **Session:** `1b1be06d-dfd9-4cc6-895d-2ec7353181c6`.
Fresh, independent re-run of the six live gate proofs against the
already-committed/merged hooks (not the in-session hot-reload). Throwaway branch
`proof/governance-reverify`; all synthetic artifacts removed, worktree clean.

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | Hooks registered (committed) & live | **PASS** | `git show HEAD:.claude/settings.json` carries the hooks block (`:94-105`); activation commit `645e9f62`; live PASS log entries through 05:25Z |
| 2 | Doctrine-gate RED → commit BLOCKED | **BLOCK ✓** | `05:25:29Z BLOCK — guard suite FAILED`; `DOCTRINE GATE (fail-closed): … FAILED`; `test_synthetic_doctrine_gate_reverify_DELETE_ME` failed; HEAD `e1abae9e` unchanged |
| 3 | Doctrine-gate GREEN → commit ALLOWED | **PASS** | `05:25:52Z PASS`; throwaway commit `d5f19b03` (`rc=0`) after probe removal |
| 4 | Branch-guard → push to `main` denied | **BLOCK ✓** | `git push origin HEAD:main --dry-run` → `Permission … denied` (pre-execution; no real push) |
| 5 | Deploy-gate → release w/o sentinel denied | **BLOCK ✓** | `bash ops/release-backend.sh --help` → `DEPLOY GATE (fail-closed): missing sentinel`; no build started |
| 6 | Reviewer cannot Write/Edit | **PASS** | `doctrine-reviewer` subagent toolset = Read, Bash only |
| 7 | ops.md sentinel docs consistent | **PASS** | `ops.md:12,18,26` ↔ `deploy-gate.sh:24` (`MAX_AGE=3600`) |

Outcome: identical to the first run — gates enforce idempotently from the durable
state. No proof failed. F1/F2 (payload over-match, see prior entry) remain open
and unchanged; no gate was weakened.

---

## 2026-06-04 — Governance activated and mechanically verified

**Governance aktiv ab 2026-06-04T05:07Z** (Hooks hot-reloaded in-session),
durable auf `demo/rwdr-limited-external` via **PR #38** (merge `64f4bcc2`).
**Session:** `1b1be06d-dfd9-4cc6-895d-2ec7353181c6`.

Activation: the reviewed `.claude/settings.json.proposed` was renamed onto the
active `.claude/settings.json`, registering the `PreToolUse → Bash` hooks
(`ops/hooks/doctrine-gate.sh`, `ops/hooks/deploy-gate.sh`) and the tightened
permissions (main-push denies, release-script `ask`-gate). The previously active
settings had **no `hooks` block** — the gates were authored but not loaded. The
machinery, rules, and reviewer were untracked and are now committed
(`f25079d1`, `645e9f62`).

### Gate → Proof → Evidence

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | Hooks registered & live | **PASS** | `.claude/settings.json:94-110` hooks block (merged #38); `doctrine-gate.log` live PASS entries 05:06–05:16Z (one per real `git commit`/`git push`) |
| 2 | Doctrine-gate RED → commit BLOCKED | **BLOCK (correct)** | `05:13:46Z BLOCK — guard suite FAILED`; stderr `DOCTRINE GATE (fail-closed): fast doctrine guard suite FAILED`; synthetic `assert False` probe in `test_comparative_ranking_guard.py`; HEAD unchanged |
| 3 | Doctrine-gate GREEN → commit ALLOWED | **PASS** | `05:15:53Z PASS`; throwaway commit `2a149589` succeeded (`rc=0`) after the probe was removed |
| 4 | Branch-guard → push to `main` denied | **BLOCK (correct)** | `git push origin HEAD:main --dry-run` → `Permission to use Bash … has been denied` (settings deny, pre-execution; no real push) |
| 5 | Deploy-gate → release w/o sentinel denied | **BLOCK (correct)** | `bash ops/release-backend.sh --help` → `DEPLOY GATE (fail-closed): missing sentinel — full backend pytest exit 0`; no build started; `…/sentinels/` absent |
| 6 | Reviewer cannot Write/Edit | **PASS** | `doctrine-reviewer` subagent toolset = Read, Bash only; no `Write`/`Edit` tool to invoke |
| 7 | ops.md sentinel docs present & consistent | **PASS** | `.claude/rules/ops.md:6-19` documents `touch …/sentinels/{pytest-green,anchor-verified}` + <1h freshness, consistent with `deploy-gate.sh:24,50-51` |

Red-before-green integrity: the doctrine-gate proof reproduced a real RED (suite
failing) and a real GREEN (suite passing) on the same throwaway branch. All
synthetic artifacts (probe test, throwaway file, `proof/governance-gates` branch)
were fully removed; no sentinels were created; worktree left clean.

### Findings (surfaced, not auto-fixed — gate changes require their own plan)

- **F1 — Doctrine-gate over-matches the payload.** The hook greps the *whole*
  `PreToolUse` payload (incl. the Bash `description` field), not just
  `tool_input.command`. A benign `git restore` whose description merely contained
  the text "git commit" triggered a full suite run and was blocked
  (`05:14:24Z BLOCK`). Fix direction: parse `jq -r '.tool_input.command'` and
  match only the command.
- **F2 — Deploy-gate over-matches the payload.** It matches `ops/release-backend.sh`
  anywhere in the command string, so a `git commit` whose *message* referenced
  that path was falsely blocked. Same fix direction as F1.
- **F3 (low) — Reviewer has Bash.** The read-only guarantee is enforced for
  `Write`/`Edit` via the tool-list, but file mutation via Bash redirection is not
  tool-blocked; the read-only role for Bash is by convention (Bash is needed to
  run the guard suite).

Neither F1 nor F2 weakens a gate — both cause *over*-blocking (fail-closed in the
safe direction). They are robustness/usability findings, not security gaps.
