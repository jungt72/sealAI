@AGENTS.md

# CLAUDE.md

## Purpose

Claude Code-specific operating rules for the **sealAI / sealing | Intelligence**
repository. `AGENTS.md` is the operating contract and the source of truth for
product scope — this file does not duplicate it.

Project-wide authority, in order:

1. `AGENTS.md` — the main coding-agent contract, and (in it) the **sealingAI
   Leitbild V3** (the binding product doctrine, ten Leitsätze L1–L10).
2. `docs/V2/sealingai_v2_build_spec.md` — the executable build plan for
   `backend/sealai_v2/` (§11 import boundary, §12 agent guardrails).
3. `docs/V2/sealingai_v2_architektur_prinzipien.md` — the trust model + the *why*.
4. `docs/V2/sealingai_v2_1_produkt_konzept.md` /
   `sealingai_v2_1_implementierungs_konzept_cc.md` — the V2.1/V2.2 forward SoT.
5. `docs/V2/sealingai_eval_seed_set_v0.md` — the acceptance ruler (7 axes + hard
   Schranken).
6. this `CLAUDE.md`.

If sources conflict, follow the higher item and fix the lower source/code so
future agents don't inherit ambiguity. When in doubt, `AGENTS.md` wins.

> **The single production backend is `backend/sealai_v2/`** (the `backend-v2`
> Docker service). The former `backend/app/` LangGraph runtime (V1 / V10 / the
> V1.8 "Universal Sealing Lifecycle Platform" blueprint / the RWDR-MVP contract
> set) was **retired 2026-06-28** — gutted to dead weight, container stopped. Do
> **not** build against it and do **not** reintroduce LangGraph anywhere. Anything
> describing that world is historical context only.

---

## Skills (`.claude/skills/`)

Repo-specific, on-demand procedures that Claude Code auto-loads when a task
matches their description. Reach for the matching skill before improvising an
error-prone workflow:

- **`eval-replay-adjudication`** — run the live Eval-REPLAY + fold the owner's
  ticked adjudication worksheet (human-is-oracle, targeted-not-full, secret
  hygiene, cost guardrails).
- **`backend-v2-deploy`** — deploy backend-v2 via `ops/release-backend-v2.sh`; the
  compose-passthrough allow-list invariant; rollback; post-incident HALT.
- **`trust-layer-change`** — change the four-layer trust spine (L1/L3, response
  contract, trap catalog, prompts) without weakening a guard or re-triggering the
  confident_wrong / destructive-hedge failure.
- **`knowledge-fachkarten`** — grow/curate the reviewed-knowledge SSoT (Fachkarten,
  claim `kind`, reviewed-vs-drafts provenance, ingest CLI).
- **`retrieval-rag`** — operate the Qdrant hybrid retrieval stack (OpenAI-API
  embeddings only; score-scale caution). Re-architecture is out of scope.
- **`security-tenant`** — the P0 tenant / untrusted-content / secrets boundary.
- **`frontend-v2-dashboard`** — the product dashboard (Vite/React SPA under
  `/dashboard`); `npm run build` in the VPS checkout IS a deploy (live `dist/`
  bind-mount); projection-of-backend-truth.
- **`frontend-marketing`** — the Next.js marketing site (`frontend/`, ships via
  `ops/release-frontend.sh`); NextAuth/BFF, distinct from V2 OIDC.

A read-only adversarial reviewer for V2 trust-spine / guard / mutation changes
lives at `.claude/agents/v2-doctrine-reviewer.md` (the V1 `doctrine-reviewer` is
retired-scope). See `docs/claude-code-skills.md` for how skills relate to
rules/commands/agents and how to add one.

## Operating rules (`.claude/rules/`)

Enforced operating rules — read them for any non-trivial change:

- `.claude/rules/doctrine.md` — how the product doctrine (AGENTS.md § Safety
  Boundaries + Leitbild V3) is enforced in V2: the four-layer trust model, the
  hard lines (never weaken a guard; the eval hard-Schranken; reviewed-only
  correction).
- `.claude/rules/workflow.md` — per-fix protocol (verify the repro,
  red-before-green), the plan → owner-gate → build → review rhythm, `main`-only
  branch/merge with 3 required checks, blast-radius HALT gating.
- `.claude/rules/ops.md` — pre-deploy gate (pytest exit code authoritative),
  rollback anchor from the running daemon, prod only via
  `ops/release-backend-v2.sh`.
- `.claude/rules/testing.md` — the V2 offline suite + import-purity keystone +
  the Eval-REPLAY milestone instrument; never silence or weaken a test.

These are also enforced by hooks (`ops/hooks/*`) and project permissions
(`.claude/settings.json`).

---

## Startup rule

At the start of any non-trivial task:

1. Read `AGENTS.md` (contract + Leitbild V3).
2. Read the `docs/V2/*` sources `AGENTS.md` points to for the touched area — at
   minimum the build-spec (§11 boundary, §12 guardrails) and, for calibration
   work, the V2.1 Produkt-/Implementierungs-Konzept.
3. Read the relevant implementation files and tests
   (`AGENTS.md § Canonical Backend Entry Points`).
4. For dashboard/frontend work, read `frontend-v2/`.
5. Check repository state:

```bash
cd /home/thorsten/sealai && git status --short
```

If the worktree is dirty, stop and report the open changes unless the task
explicitly concerns them.

---

## Operating mode

Default mode:

- Audit first. Patch second. Keep patches small.
- Preserve existing seams unless there is clear evidence they are wrong.
- Do not invent parallel architecture.
- Do not implement later-phase / flag-gated features unless explicitly tasked.
- **HALT-gate rhythm:** plan → owner gate → build → review; never auto past a
  gate. A self-caused production incident is itself a HALT point — report and
  stop, do not self-commit a fix to `main`.

---

## Claude Code behavior

When working in this repo:

- Prefer read-only investigation before changing files; cite concrete files,
  functions, and line ranges.
- Make the smallest useful patch; do not rewrite broad areas without a scoped
  task, and do not create new workflows when an existing seam can be tightened.
- Keep the frontend a **projection of backend truth** — do not let it compute or
  generate authoritative engineering claims.
- The deterministic kernel is the only source of numbers; the LLM never invents a
  value, norm, or compound fact — grounding (L2) carries specifics with
  provenance.
- Respect Keycloak user/tenant scoping. Do not expose or invent secrets;
  `.env*` is never read/printed/committed.
- Feature work lands **flag-gated, default OFF, byte-identical when unset** unless
  the owner says otherwise — proven, not assumed.
- Report validation commands and results; never hide a failing test.

---

## Repository map

- `backend/sealai_v2/` — **the only active backend.** Pipeline
  (`pipeline/pipeline.py`, `pipeline/stages.py`), trust layers
  (`core/l1_generator.py`, `core/l3_verifier.py`, `core/response_contract.py`),
  knowledge (`knowledge/`: Fachkarten, matrix, traps, Qdrant retrieval), memory
  (`memory/`, `db/*_memory.py`), eval (`eval/`), prompts (`prompts/`, Jinja2),
  security (`security/tenant.py`), LLM factory (`llm/`), API (`api/main.py`),
  config (`config/settings.py`), observability (`obs/tracing.py`).
- `backend/app/` — **retired 2026-06-28.** Do not add code here.
- `frontend-v2/` — the dashboard (Vite, served under `/dashboard`) — the active
  product UI. Deploys via its live `dist/` bind-mount (`npm run build` = deploy).
- `frontend/` — marketing site only. Not the product UI.
- `docs/V2/` — the normative V2 sources (see Authority Order above).
- `ops/` — sanctioned deploy scripts (`release-backend-v2.sh`,
  `release-frontend.sh`), backup scripts, disk safeguard, ingest CLIs.
- `_archive/` — local backups (gitignored, do not touch).
- **No `sealai_v2.* ↔ app.*` imports**, either direction — enforced by
  `backend/tests/architecture/test_v2_import_boundary.py`.

---

## Safety language

sealAI is a **herstellerneutrale Vorbewertungsinstanz**, not a final technical
release authority. Never claim: final engineering release; guaranteed
material/product suitability; manufacturer approval without manufacturer evidence;
compliance/certification without a licensed rule or expert review; a product claim
from material-family evidence; a compound claim from material-family evidence; a
current/stale calculation as final proof.

Allowed wording stays scoped: screening, orientation, current evidence,
calculated value, open point, review required, manufacturer review basis. Make
uncertainty, provenance, missing data, and manufacturer-review needs visible
(Leitsätze L2/L3/L5/L10).

Final principle: **SealingAI does not decide the seal — it makes the inquiry
decidable.** AI extracts. User confirms. SealingAI structures. Manufacturer or
responsible engineer evaluates.

---

## Validation

Prefer focused tests first. Never hide failing tests — report the exact command
and failure summary. Run from `backend/` unless stated.

```bash
# Full offline suite (fake LLM client — no OPENAI_API_KEY, no runtime stack)
python -m pytest sealai_v2/ -q

# Import-purity keystone (hard-red gate)
python -m pytest ../backend/tests/architecture/test_v2_import_boundary.py --noconftest

# Formatting (CI pins ruff==0.6.9 — a different local version WILL disagree)
cd .. && .venv/bin/ruff format backend/
```

Live Eval-REPLAY + owner adjudication (needs `OPENAI_API_KEY` transiently from
`~/sealai/.env` for that run only) — see the `eval-replay-adjudication` skill and
`AGENTS.md § Test Commands`:

```bash
PYTHONPATH=. python -m sealai_v2.eval --label <run-label>
PYTHONPATH=. python -m sealai_v2.eval --adjudicate --label <run-label>
```

Owner directive: no full eval before every deploy — targeted eval on the touched
dimension + the deterministic Schranken.

Frontend (dashboard) from `frontend-v2/`: `npm run build` is a deploy (live
`dist/` bind-mount), not just a type-check — do not run it casually.

---

## Final rule

When in doubt, follow `AGENTS.md`.
