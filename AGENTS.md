# AGENTS.md

## Purpose

This repository builds **sealAI / sealing | Intelligence**: a herstellerneutrale
Vorbewertungsinstanz für Dichtungstechnik — grounded knowledge dialogue plus a
deterministic calculation kernel, governed by the **sealingAI Leitbild V3**.

Active target:

```text
Freely explain. Deterministically calculate. Only claim with evidence.
```

The single production backend is **`backend/sealai_v2/`**, deployed as the
`backend-v2` Docker service. `backend/app/` (the former V1/V10 LangGraph
runtime) was **retired 2026-06-28** — the directory is gutted (2 files, dead
weight, kept only as git history) and its container is stopped. Do not build
against it, do not reintroduce LangGraph anywhere in this repo.

## sealingAI Leitbild V3 — the binding product doctrine

This is the normative basis for every architecture and product decision.
sealAI is **not** a final technical release authority. It is a
**herstellerneutrale Vorbewertungsinstanz** (manufacturer-neutral
pre-assessment instance).

Ten Leitsätze bind every decision:

- **L1** Der Kernel entscheidet, das LLM formuliert.
- **L2** Kein Verdikt ohne Quelle, keine Quelle ohne Status, keine Aussage ohne
  Coverage.
- **L3** Unsicherheit ist ein Zustand, kein Textbaustein.
- **L4** Werkstofffamilie orientiert. Compound bewertet. Bauteil wird
  freigegeben — aber nicht von uns.
- **L5** Was das System nicht weiß, sagt es zuerst.
- **L6** Matching folgt dem Verdikt, nie umgekehrt.
- **L7** Felddaten sind Evidenz, kein Autopilot.
- **L8** Das Produkt ist das Entscheidungsdokument.
- **L9** Coverage-Tiefe vor Breite.
- **L10** Die Grenzen des Systems stehen im Produkt — nicht im Kleingedruckten.

Non-negotiable regardless of what else is optimized:

- The deterministic kernel is the only source of numbers. The LLM never
  invents a value.
- No material/compound release is ever phrased as "geeignet"/"freigegeben" —
  only verdict + source + uncertainty.
- No domain fact (material property, limit value, norm) may be
  invented/hallucinated — only cited from reviewed, versioned sources.

Full Leitbild text is held by the owner locally; ask for it when a decision
needs the complete Kernprinzipien (Compound- vs. Familien-Logik, Risikoklassen,
Coverage/Quellenhierarchie/Konfliktlogik/Versionierung).

## Authority Order

1. This file (`AGENTS.md`) is the operating contract for coding agents.
2. The sealingAI Leitbild V3 (above) is the binding product doctrine.
3. `docs/V2/sealingai_v2_build_spec.md` — the executable build plan for
   `backend/sealai_v2/` (§11 boundary, §12 agent guardrails).
4. `docs/V2/sealingai_v2_architektur_prinzipien.md` — the trust model + the
   *why* (§0/§2/§3/§4/§9).
5. `docs/V2/sealingai_v2_1_produkt_konzept.md` /
   `sealingai_v2_1_implementierungs_konzept_cc.md` — the V2.1/V2.2 forward SoT
   (WHAT/HOW) for the current increment work.
6. `docs/V2/sealingai_eval_seed_set_v0.md` — the acceptance ruler (7 axes +
   hard Schranken).
7. Tests in `backend/sealai_v2/tests/` and
   `backend/tests/architecture/test_v2_import_boundary.py` are executable
   contracts.
8. Everything under "Retired: V1 / V10 / V1.8 (historical)" below, plus
   archived docs/audit reports/screenshots, is historical context only.

If sources conflict, follow the higher item and update the lower source or
the code so future agents don't inherit ambiguity.

## Repo Layout

- `backend/sealai_v2/`: the ONLY active backend. Pipeline, L1/L3, Fachkarten
  knowledge, Qdrant retrieval, memory, calc kernel, API, config, eval harness.
- `backend/app/`: **retired** (2026-06-28). Do not add code here.
- `frontend-v2/`: the dashboard (Vite, served under `/dashboard`) — the active
  frontend for `sealai_v2`.
- `frontend/`: marketing site only. Not the product UI.
- `docs/V2/`: the normative V2 sources (see Authority Order above).
- `ops/`: sanctioned deploy scripts (`release-backend-v2.sh`,
  `release-frontend.sh`), backup scripts, disk safeguard.

If a subdirectory contains another `AGENTS.md`, follow the more specific file
for files inside that subtree.

## Four-layer trust model + the thin pipeline

Halluzination-resistance comes from four layers that carry together, not from
control-determinism — this is the concrete implementation of Leitsatz L1/L2:

- **L1 · Generator** — strong LLM + the L1 system prompt; covers the infinite
  answer space, integrated reasoning, the *why*. Must not invent precise
  numbers/norms or rubber-stamp a default.
- **L2 · Grounding** — RAG over the curated knowledge layer (Fachkarten +
  compatibility matrix + Qdrant hybrid retrieval) for specifics (numbers,
  norms, compatibility), **with provenance**. Must not become control logic.
- **L3 · Verifier** — an independent critic pass against the trap catalog
  (+ matrix). Must not smooth over correct answers or invent its own source
  of truth.
- **L4 · Human/Manufacturer** — orientation ≠ binding spec; final validation
  and release stays outside the system (Leitsatz L4/L8).

The pipeline is one directed chain, no routing mesh:
**verstehen → grounden → antworten (mit Konfidenz) → verifizieren →
zitieren.** No deterministic intake gate, no slot-binder, no field-envelope
state machine.

## Hard invariants (review criteria for every patch)

- **Eval is the instrument.** The eval seed set (`docs/V2/sealingai_eval_seed_set_v0.md`)
  is the build target *and* the regression guard. Hard Schranken-Quote = 100%
  where the deploy gate applies (see below — currently temporarily disabled,
  owner-authorized, see `ops/release-backend-v2.sh` `###EVAL-GATE###`
  markers).
- **The human is the factual-correctness ORACLE; the agent never
  self-adjudicates.** The agent surfaces divergences as candidates and
  recomputes from the owner's ticked worksheet. It never ticks PASS/FAIL
  itself and never free-corrects a factual verdict.
- **Trap-catalog provenance + reviewed-only correction.** `reviewed` entries
  are owner-grounded and may correct/block; `drafts` are model-proposed and
  flag-only. No fact in `reviewed` is model-sourced.
- **Green-field boundary + import-purity.** No `sealai_v2.* ↔ app.*` imports,
  either direction — enforced by
  `backend/tests/architecture/test_v2_import_boundary.py`. This still applies
  even though `app.*` is retired: it keeps `sealai_v2` cleanly independent.
  Thin adapters, pure `core/` (no I/O); Jinja2 builds prompts + renders
  artifacts, never decides domain content.
- **Deterministic vs. generative.** Calculations are Code with cited formulas
  (never LLM-guessed); artifact rendering is deterministic from grounded
  facts; provenance is visible to the user.
- **Security/Tenant P0.** Server-side tenant filters, untrusted-content
  pipeline, no secrets in logs; cross-tenant leak is a P0 blocker
  (`backend/sealai_v2/security/tenant.py`).
- **A `docker-compose.deploy.yml` field/env-var is an explicit allow-list.**
  A new `SEALAI_V2_*` setting or new bind mount does nothing until it also
  has a line in `docker-compose.deploy.yml`'s `environment:`/`volumes:`
  block, AND the running container is recreated (not just restarted) to pick
  it up. This exact bug class has caused multiple real incidents in this
  repo — always add the compose passthrough in the SAME patch as the settings
  field.
- **Feature work lands flag-gated, default OFF, byte-identical when unset**
  unless the owner explicitly says otherwise. Prove it with a targeted eval
  or an explicit before/after diff against live data before activating.
- **HALT-gate rhythm.** Plan → owner gate → build → review; never auto past a
  gate. A self-caused production incident is itself a HALT point — report and
  stop, do not self-commit a fix to `main` without checking back with the
  owner first, even when the fix is already tested and correct.
- **Secret hygiene.** Offline tests use a fake LLM client — no key needed. A
  live eval REPLAY sources `OPENAI_API_KEY` transiently — never into logs,
  never committed. `.env*` stays never-read/printed/committed.

## Git / branch workflow

- `main` is the single active line for `sealai_v2`/`frontend-v2` work.
  Branch protection on `main` requires a PR with 3 green required checks
  (`backend-contracts`, `v2-contracts`, `secret-scan`) — **`enforce_admins`
  is ON**, so this applies to every push, including agent/admin credentials.
  There is no direct-push bypass anymore.
- Work happens on a short-lived branch off `main`, gets a PR, and merges once
  checks are green. Do not accumulate multiple long-lived parallel feature
  branches for the same piece of work — one active branch per workstream,
  merged (or explicitly closed) before starting the next, keeps "which branch
  is the real one" unambiguous.
- Delete a branch immediately once it's merged (`git branch -d` /
  `git push origin --delete`) — a merged branch left lying around is exactly
  the kind of stale state that causes "wrong branch" mistakes later.
- Production deploys are triggered ONLY via `ops/release-backend-v2.sh`
  (backend) or `ops/release-frontend.sh` (marketing) — both are health-gated
  with smoke tests and an automatic rollback tag. `frontend-v2`/dashboard
  deploys via its live `dist/` bind-mount (`npm run build` = deploy) — a
  different mechanism, be explicit about which one you mean.

## Canonical Backend Entry Points (`backend/sealai_v2/`)

- Pipeline (stages): `pipeline/pipeline.py`, `pipeline/stages.py`
- L1 generator: `core/l1_generator.py` · L3 verifier: `core/l3_verifier.py`
- Core contracts: `core/contracts.py` · shared text matcher: `core/text_match.py`
- Trap catalog: `knowledge/traps.py` + `knowledge/trap_catalog.json`
- Fachkarten knowledge: `knowledge/fachkarten.py`, in-process retrieval
  `knowledge/retrieval.py`, production Qdrant retrieval (dense + hybrid
  sparse/RRF/rerank, flag-gated) `knowledge/qdrant_retrieval.py`
- Compatibility matrix: `knowledge/matrix.py`
- Memory (4 layers — session working-window/case-state/derived facts,
  distiller, integrity guard, cross-session durable facts):
  `memory/store.py`, `memory/distiller.py`, `memory/integrity.py`,
  `db/conversation_memory.py`, `db/cross_session_memory.py`
- Response contract + output guard: `core/response_contract.py`,
  claim-level fail-closed guard
- Produktspec / Kandidaten-Spezifikation: `pipeline/produktspec_step.py`,
  `produktspec/kernel.py` (flag-gated, owner-activation-gated)
- Hersteller-Partner (paid pool + leads): `db/hersteller_partner.py`
- Prompt assembly (Jinja2): `prompts/assembler.py`, `prompts/system_l1.jinja`,
  `prompts/verifier_l3.jinja`
- Eval harness + adjudication: `eval/` (`harness.py`, `scorer.py`, `judge.py`,
  `adjudicate.py`, `__main__.py`; runs in `eval/runs/`)
- LLM access (provider-agnostic): `llm/factory.py`, `llm/client.py`
- Security/tenant (P0): `security/tenant.py`
- Observability: `obs/tracing.py` (LangSmith, `wrap_openai` + `@traceable`,
  fail-open)
- API: `api/main.py` · Config (model tiers/flags):
  `config/settings.py`
- Import-purity keystone: `backend/tests/architecture/test_v2_import_boundary.py`

## Test Commands

Run from `backend/` unless stated otherwise.

Full offline suite (fake LLM client — no `OPENAI_API_KEY`, no runtime stack):

```bash
python -m pytest sealai_v2/ -q
```

Import-purity keystone:

```bash
python -m pytest ../backend/tests/architecture/test_v2_import_boundary.py --noconftest
```

Formatting (CI's non-blocking `Backend ruff-format guard` — CI pins
`ruff==0.6.9`, matched by `.venv`; a different local ruff version WILL
disagree on formatting):

```bash
cd .. && .venv/bin/ruff format backend/
```

Live eval REPLAY (needs `OPENAI_API_KEY` transiently from `~/sealai/.env` for
that run only):

```bash
PYTHONPATH=. python -m sealai_v2.eval --label <run-label>
# Owner adjudication recompute (no LLM call — folds the ticked worksheet):
PYTHONPATH=. python -m sealai_v2.eval --adjudicate --label <run-label>
```

Owner directive (2026-06-27): no full eval before every deploy — targeted eval
against the changed dimension + the deterministic Schranken. See
`ops/release-backend-v2.sh` for the current (temporarily owner-disabled) gate.

Do not install new dependencies unless the user explicitly asks.

## Clean-Code Rules

- Prefer canonical runtime modules over compatibility facades.
- Keep adapters thin; they must delegate to canonical contracts.
- Do not add productive prompt strings inside services when a prompt registry
  or Jinja2 template is appropriate.
- Use typed contracts at boundaries: Pydantic on backend, TypeScript
  interfaces/types on frontend.
- Do not generate technical claims in frontend code.
- Do not silence tests, skip critical paths, or catch broad exceptions
  without typed fallback and logging.
- Remove dead imports, dead tests, and obsolete scripts when replacing old
  paths — but don't delete something you haven't verified is genuinely
  unreferenced (check imports/grep first; a stale-looking file may still be
  load-bearing).
- Keep comments short and useful; explain the WHY (a non-obvious constraint,
  a workaround, an invariant), never restate the WHAT.
- No comments in code unless the reasoning genuinely isn't obvious from
  well-named identifiers.

## Safety Boundaries

Never claim:

- final engineering release;
- guaranteed material/product suitability;
- manufacturer approval without manufacturer evidence;
- compliance/certification without licensed rule or expert review;
- product claim from material-family evidence;
- compound claim from material-family evidence;
- current/stale calculation as final proof.

Allowed wording must stay scoped: screening, orientation, current evidence,
calculated value, open point, review required, manufacturer review basis.

## Definition Of Done

- Touched response paths preserve the response contract / guard coverage.
- Backend tests covering the touched contracts pass; full
  `pytest sealai_v2/ -q` stays green.
- No secrets, environment files, database mutations, or dependency changes
  are committed unless explicitly requested.
- A feature that's flag-gated stays byte-identical with the flag unset,
  proven (not assumed) before merge.
- Historical/dead code is removed, or explicitly documented as retired with
  owner and removal criterion — not left ambiguous.

## Retired: V1 / V10 / V1.8 (historical only)

The following describes the **former** `backend/app/` LangGraph runtime
("V10 Conversational Sealing Intelligence", RWDR MVP, V1.8 Universal Sealing
Lifecycle Platform blueprint). It was **retired 2026-06-28** (owner-approved,
`backend/app/` gutted to 2 files, container stopped). Kept here only as
historical context for anyone reading old commits/docs that reference it —
it is **not** authoritative for any current work. Do not resurrect LangGraph,
the V10 topology, or the RWDR-MVP contract set. `backend/sealai_v2/` is the
current and only production backend.
