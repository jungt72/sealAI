# Ops

Production is gated. These rules are enforced by hooks (`ops/hooks/*.sh`) and
permissions (`.claude/settings.json`); they are also the contract for humans.

## Branch model (2026-06-04; branch strategy decided 2026-06-05)

`main` is the **converged truth** as of 2026-06-04 (demo→main via PR #11, tag `v1.7.0`).

**Branch strategy — DECIDED (2026-06-05, Parked-Items-Closeout; was "parked").**
Keep the current model and treat it as the standing rule, not a temporary state:
- Integration happens on `demo/rwdr-limited-external`. **All PRs target demo.**
  Direct pushes to `main` stay denied.
- The `demo→main` convergence is a deliberate, **owner-gated** step, run **per
  milestone / per day** — never the routine per-commit flow. Every merge into demo
  gets a small `demo→main` **carry-over PR** that the owner merges.
- This matches the existing branch-guard, hooks, and CI triggers, so **no
  infrastructure change is needed** (that was the point of keeping it).

The broader trunk-based alternative was considered and **not** adopted today; if it
is ever revisited it must be scoped as its own arc (branch-guard, CI triggers,
rules). The **CI-trigger / `ruff format` scope questions remain separately parked**
— do not change branch-guard, hooks, or CI triggers as part of routine work.

## Pre-deploy gate (authoritative)
- Run the **full backend suite** before any deploy:
  `cd /home/thorsten/sealai && .venv/bin/python -m pytest backend -q -rf`.
- The **exit code is authoritative** — the summary line is unreliable under `\r`
  rendering. Only `EXIT=0` clears the gate.
- After it passes, write the sentinel the deploy gate checks:
  `touch .claude/.gate-logs/sentinels/pytest-green`.

## Rollback anchor (from the running daemon, never memory)
- Before deploy, read the live image from the daemon:
  `docker inspect backend --format '{{.Config.Image}}'` — this `@sha256:…` digest
  is the rollback target. Confirm `status=running health=healthy`.
- Then write the sentinel: `touch .claude/.gate-logs/sentinels/anchor-verified`.
- Never quote a rollback anchor from memory or from a prior turn.

## Production deploy
- Prod changes go **only** through the sanctioned release scripts: backend via
  `ops/release-backend.sh`, frontend via `ops/release-frontend.sh`. Both: build →
  push GHCR → pin `@sha256` in `.env.prod` → recreate the one service → health +
  auto-rollback (health-fail) → nginx reload → live pilot smoke.
- The **deploy gate** (`ops/hooks/deploy-gate.sh`) blocks `release-backend.sh`
  until both sentinels above are fresh (< 1h); the project permission then still
  **asks** the human to confirm. The frontend script is **not** sentinel-gated by the
  hook — its pre-deploy gate is a green `next build` + frontend tests (the known
  pre-existing `workspaceMapping` vitest fail is the only tolerated red; nothing new
  may break) + the rollback anchor read from the running daemon.
- After deploy: record the new live digest, re-run the smoke, and verify live
  acceptance in the deployed container (`docker exec … `).
- **Every prod deploy is logged in `docs/ops/GOVERNANCE_LOG.md` — no exceptions**
  (backend, frontend, doctrine or brand; owner rule 2026-06-04). One entry per
  deploy with: the new pinned `@sha256` digest, the rollback target (read from the
  running daemon, never memory), the pre-deploy gate result, and the live-smoke
  outcome.

## Secrets & untouchables
- `.env*` files are never read, printed, or committed (denied in permissions).
- **V2 eval key hygiene:** V2 offline tests use a **fake LLM client (no key)**. A
  **live eval REPLAY** (`python -m sealai_v2.eval`) sources `OPENAI_API_KEY`
  **transiently from `~/sealai/.env` for that run only** — never persisted into the
  agent env, never echoed to logs, never committed.
- Never push to `main`; never `git push --force`, `git clean`, or
  `docker compose down/rm` against prod (denied).
- `.claude/.gate-logs/` holds runtime gate logs and sentinels — gitignored, not
  committed.

## Gate mechanics — command-parsing & deliberate residual gaps
- The PreToolUse gates (`ops/hooks/doctrine-gate.sh`, `ops/hooks/deploy-gate.sh`)
  match on the executed command only (`jq -r '.tool_input.command'`), never the
  whole payload — a Bash `description` or a commit message that merely mentions
  `git commit` / `git push` / `ops/release-backend.sh` no longer triggers a gate
  (audit F1/F2). The deploy gate fires only on an actual **invocation** of the
  release script (command position), not a prose mention.
- Parsing is **fail-closed**: jq missing, malformed payload, or an undeterminable
  command field → BLOCK. Parse ambiguity is never waved through.
- **Deliberate residual gaps** (a *discipline anchor, not a sandbox*): command-text
  matching does not see through `sh -c "…"`, shell aliases/functions, variable
  expansion, or the literal path chained mid-line inside a quoted string. Accepted —
  the gates enforce the habit, not an airtight boundary.
- **Activation reality:** the hooks load from project settings and **hot-reload
  in-session** — no session restart needed (verified 2026-06-04; see
  `docs/ops/GOVERNANCE_LOG.md`). Renaming a `.proposed` settings file onto
  `.claude/settings.json` makes the gates live for the next tool call.

## Runtime kill-switches (incident-only, default = enforced)
- **`SEALAI_TIER0_RETRIEVAL_GUARD`** (P1-2 TEIL B) — fail-closed guard at the RAG
  retrieval funnel (`rag_orchestrator.hybrid_retrieve`): a turn declared **Tier-0**
  (GREETING / META_QUESTION / BLOCKED — no-retrieval fast routes) that reaches
  retrieval raises `TierViolation`. **Default ON** (unset or any value not in
  `{0,false,no,off}` = enforced).
  - **Set `=0` ONLY during an incident** where the guard is wrongly blocking a
    legitimate retrieval (a suspected false-trip), to restore service while the
    real cause is fixed. The bypass is **logged** (`tier0_retrieval_guard_BYPASS`),
    never silent.
  - It is **not a steady state**: a bypass means a tier-label-vs-behaviour
    contradiction is live → open a finding, fix the label or the route, re-enforce.
  - Toggling it is an env change on the running service (`.env.prod` is operator-
    owned; never read/printed by agents) — re-enforce as soon as the incident is
    resolved.

## V2.0 track: live `backend-v2`, deployed under Gap #1/#2 discipline

`backend/sealai_v2/` is **de-facto live in prod** — the `sealai-backend-v2` container runs and nginx
routes `/api/v2` → `sealai-backend-v2:8001` (Gap #1/#2 shipped there; durable `sealai_v2` Postgres,
restart-survival proven; see the 2026-06-17 `GOVERNANCE_LOG`). It does **NOT** go through the V1 release
path: `ops/release-backend.sh`, the deploy gate, the pre-deploy pytest sentinel, and the rollback anchor
all still target the **V1** runtime (`backend/app/`) unchanged. A V2 change deploys with **Gap #1/#2
discipline** instead: **eval-gate green first** → read the **rollback image from the running daemon**
(`docker inspect sealai-backend-v2 --format '{{.Config.Image}}'`, never memory) → rebuild + recreate
**only** `backend-v2` surgically (`up -d --no-deps backend-v2`) → **restart-survival** check (durable
`sealai_v2` Postgres; catalog/code are file-backed in the image, no DB migration) → live `/api/v2` smoke
→ **`GOVERNANCE_LOG` entry** (new pinned `@sha256`, rollback target, eval-gate result, smoke). The full
**demo→main convergence and the V1→V2 cutover remain owner-gated**. (V2 CI: `.github/workflows/v2-contracts.yml`;
V2 doctrine: `AGENTS.md § "V2.0 green-field track"`.)

**V2.1 deploys per-increment under this same Gap #1/#2 discipline** — each increment is a coherent,
testable, deployable unit, gated by an owner plan-review *before* and an owner deploy-review *after*;
the 8 hard eval Schranken hold **1.000** through every increment. See
`docs/V2/sealingai_v2_1_implementierungs_konzept_cc.md §7` (deploy) + §1.3 (the four owner-HALTs).
The public `/api/v2` nginx flip (`ops/v2-flip.sh`) stays owner-gated — these deploys only update the
backend image.
