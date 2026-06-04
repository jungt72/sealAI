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
