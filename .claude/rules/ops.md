# Ops

Production is gated. These rules are enforced by hooks (`ops/hooks/*.sh`) and
permissions (`.claude/settings.json`); they are also the contract for humans.

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
- Prod changes go **only** through `ops/release-backend.sh` (backend only): build
  → push GHCR → pin `@sha256` in `.env.prod` → recreate backend → health +
  auto-rollback (health-fail) → nginx reload → live pilot smoke.
- The **deploy gate** (`ops/hooks/deploy-gate.sh`) blocks `release-backend.sh`
  until both sentinels above are fresh (< 1h). The project permission then still
  **asks** the human to confirm.
- After deploy: record the new live digest, re-run the smoke, and verify live
  acceptance in the deployed container (`docker exec backend …`).

## Secrets & untouchables
- `.env*` files are never read, printed, or committed (denied in permissions).
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
