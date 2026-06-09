@AGENTS.md

# CLAUDE.md

## Purpose

This file contains Claude Code-specific operating rules for the SealAI repository.

Project-wide authority, in order:

1. `AGENTS.md` — the main coding-agent contract.
2. The active target blueprint named in `AGENTS.md § "Active target blueprint"`:
   `docs/sealing_intelligence_v1_8_universal_sealing_lifecycle_platform_blueprint.md`
   (V1.8). It is the binding architecture & orchestration layer, with precedence
   `V1.8 > V1.7 > V1.6` (V1.6 still wins on the contract level except where V1.8
   §5/§6 differs).
3. The current product & architecture concept files named in `AGENTS.md`
   (currently `docs/implementation/SEALAI_RWDR_MVP_PRODUCT_CONCEPT.md` and the
   architecture concept it references).
4. `frontend/DESIGN.md` — for UI/frontend work.
5. this `CLAUDE.md`.

`AGENTS.md` is the source of truth for product scope. Do not duplicate the full
product concept here.

> **Precedence:** `AGENTS.md` describes the current runtime as
> **V10 Conversational Sealing Intelligence**, product focus **RWDR MVP**, with
> **V1.8 (Universal Sealing Lifecycle Platform)** as the binding architecture &
> orchestration layer on top of V1.6/V1.7. If any wording below (e.g. legacy
> "Phase-1" framing) conflicts with `AGENTS.md`, `AGENTS.md` wins.

> **V1.8 is audit-first.** Before any V1.8 implementation patch, run the
> read-only deep audit in V1.8 §10.1 against the Annex A checklist
> (evidence = `path + line`) and produce the audit report. Only patch after the
> report is reviewed — one dimension per patch, each with tests, each checked
> against the V1.8 §7.10 prohibition list and §11 acceptance criteria; Golden
> REPLAY stays green after every patch.

> **V2.0 green-field track (`backend/sealai_v2/`).** For work **inside
> `backend/sealai_v2/`**, the binding doctrine + canonical entry points + test
> commands live in **`AGENTS.md § "V2.0 green-field track"`** (single source of
> truth — derived from `docs/V2/*`). V2 is on the `feat/v2*` line and is **not cut
> over** to demo/main; the V1 runtime (`backend/app/`, frontend) stays governed
> **unchanged** by V1.8 and everything else here until cutover. Inside the v2 tree
> only: precedence is **V2.0 > V1.8 > V1.7**, the audit standard is the V2 build-spec
> + the eval seed set, the human is the factual ORACLE (the agent never
> self-adjudicates eval verdicts), and the `sealai_v2.* ↔ app.*` import boundary is
> a hard CI gate. Read `docs/V2/*` first when the task touches that tree.

---

## Operating rules (`.claude/rules/`)

Detailed, enforced operating rules live in `.claude/rules/` — read them for any
non-trivial change:

- `.claude/rules/doctrine.md` — how the output doctrine (AGENTS.md § Safety
  Boundaries) is enforced; the hard lines (never weaken a guard; the four repros
  always block; AC8/AC9).
- `.claude/rules/workflow.md` — per-fix protocol (verify the repro, red-before-
  green), PRs only on `demo/rwdr-limited-external`, blast-radius HALT gating, no
  doctrine/guard/streaming/mutation merge without a `doctrine-reviewer` approval.
- `.claude/rules/ops.md` — pre-deploy gate (pytest exit code authoritative),
  rollback anchor from the running daemon, prod only via `ops/release-backend.sh`.
- `.claude/rules/testing.md` — the fast doctrine guard suite + full gate; never
  silence or weaken a test.

These rules are also enforced by hooks (`ops/hooks/doctrine-gate.sh`,
`ops/hooks/deploy-gate.sh`) and project permissions (`.claude/settings.json`).
A read-only reviewer lives at `.claude/agents/doctrine-reviewer.md`.

---

## Startup rule

At the start of any non-trivial task:

1. Read `AGENTS.md`.
2. Read the active target blueprint
   `docs/sealing_intelligence_v1_8_universal_sealing_lifecycle_platform_blueprint.md`
   (V1.8) — at minimum §7 (orchestration), §10 (implementation discipline +
   read-only audit prompt), §11 (acceptance criteria), and Annex A (audit
   checklist). It layers on top of V1.6/V1.7.
3. Read the concept files `AGENTS.md` points to.
4. Read relevant implementation files and tests.
5. For UI/frontend work, also read `frontend/DESIGN.md`.
6. Check repository state:

```bash
cd /home/thorsten/sealai && git status --short
```

If the worktree is dirty, stop and report the open changes unless the task explicitly concerns those changes.

---

## Operating mode

Default mode:

- Audit first.
- Patch second.
- Keep patches small.
- Preserve existing seams unless there is clear evidence they are wrong.
- Do not invent parallel architecture.
- Do not implement later-phase features unless explicitly tasked.

Current product lens (per `AGENTS.md`): **RWDR MVP / Technical RWDR RFQ Brief**.
Stay focused on chat intake, pre-gate routing, governed case-state, field
envelopes, provenance, unit normalization, conflict/stale handling, lightweight
calculations, readiness, Decision Understanding, cockpit projection, RFQ
preview/export, RFQ freeze/consent, and upload evidence candidates.

Do not treat matching, Seal Passport, reorder, FEM, payment, ERP/CRM
integration, or manufacturer dashboards as in-scope unless explicitly instructed.

---

## Claude Code behavior

When working in this repo:

- Prefer read-only investigation before changing files.
- Cite concrete files, functions, and line ranges in audit output.
- Make the smallest useful patch.
- Do not rewrite broad areas without a scoped task.
- Do not create new workflows when existing seams can be tightened.
- Keep frontend as a projection of backend truth.
- Do not let frontend compute authoritative engineering truth.
- Respect Keycloak user/tenant scoping.
- Do not expose or invent secrets.
- Report validation commands and results.

---

## Repository map

- `backend/app/agent/` — agent runtime: `api/` (dispatch, routes, streaming),
  `communication/` (runtime, governed answer composer).
- `backend/app/{api,domain,llm,mcp,services,schemas,core,observability}/` —
  governed runtime, domain logic, LLM + MCP integration.
- `backend/app/tests/` and `backend/tests/` — backend tests.
- `frontend/src/{app,components,lib,hooks}/` — Next.js app (App Router).
- `keycloak/`, `nginx/`, `paperless/` — infrastructure/auth/ingest.
- `_archive/` — local backups (gitignored, do not touch).
- `backend/sealai_v2/` — **V2.0 green-field tree** (`feat/v2*`, not cut over): the
  thin pipeline (`pipeline/`), the trust layers (`core/l1_generator.py`,
  `core/l3_verifier.py`), grounding (`knowledge/`), `eval/`, `prompts/`, `render/`,
  `security/tenant.py`. Governed by `AGENTS.md § "V2.0 green-field track"`. **No
  `sealai_v2.* ↔ app.*` imports** (keystone: `backend/tests/architecture/test_v2_import_boundary.py`).

---

## Safety language

SealAI must not claim final engineering approval, manufacturer release,
guaranteed suitability, compliance approval without evidence, validated
operation before post-RFQ feedback exists, or current reorder price without
manufacturer confirmation.

Use cautious technical language. Make uncertainty, provenance, missing data, and
manufacturer-review needs visible.

Final product principle (RWDR): SealingAI does not decide the seal — it makes the
inquiry decidable. AI extracts. User confirms. SealingAI structures. Manufacturer
or responsible engineer evaluates.

---

## Validation

Prefer focused tests first. Never hide failing tests — report the exact command
and failure summary.

Backend (pytest config lives in `backend/pytest.ini`, `testpaths = tests`):

```bash
cd /home/thorsten/sealai/backend && pytest -q                    # full suite
cd /home/thorsten/sealai/backend && pytest tests/<file>.py -q    # focused
```

Frontend (from `frontend/`):

```bash
cd /home/thorsten/sealai/frontend && npm run test:run    # vitest (CI mode)
cd /home/thorsten/sealai/frontend && npm run test:node   # node/tsx unit tests
cd /home/thorsten/sealai/frontend && npm run test:all    # node + vitest
cd /home/thorsten/sealai/frontend && npm run lint        # eslint
cd /home/thorsten/sealai/frontend && npm run build       # next build (type-check)
```

V2.0 (`backend/sealai_v2/` — offline = fake LLM client, no key, no runtime stack):

```bash
PYTHONPATH=backend python -m pytest backend/sealai_v2 --noconftest -q          # V2 offline suite
python -m pytest backend/tests/architecture/test_v2_import_boundary.py --noconftest  # import-purity keystone
```

For the live eval REPLAY + owner adjudication, see `AGENTS.md § "V2.0 green-field
track" → V2 test commands` (secret hygiene: key transient from `~/sealai/.env`).

---

## Final rule

When in doubt, follow `AGENTS.md`.
