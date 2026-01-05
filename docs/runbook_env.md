# Environment Runbook

This guide captures how to start the stack with an explicit env file, keep the secrets in sync, and troubleshoot when things diverge.

## Booting the stack

- **Development**: run `./ops/up-dev.sh`. It first invokes `./ops/check-env-drift.sh dev`, then runs `docker compose --env-file .env.dev up -d --build` from the repository root. The explicit `--env-file` flag guarantees Docker Compose never falls back to the root `.env`.
- **Production**: run `./ops/up-prod.sh`. The script mirrors the deploy workflow (`docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml up -d --build`) after validating `.env` via `./ops/check-env-drift.sh prod`.

## Secret rotation

- The canonical sources for secrets are `.env.dev` and `.env.prod`. `NEXTAUTH_SECRET` (and any other values needed during build/runtime) must be updated there.
- `./ops/check-env-drift.sh` prevents the root `.env` from drifting. It fails whenever `.env` exists and `NEXTAUTH_SECRET` differs from the chosen mode so that the explicit env files stay authoritative.
- When rotating `NEXTAUTH_SECRET`:
  1. Update the value in `.env.dev` and/or `.env.prod`.
  2. Start the stack with the corresponding `ops/up-*.sh` script so the new secret flows into the containers.
  3. Optionally copy the value into `.env` if other helpers still need it; otherwise keep `.env` absent or identical to the target env file to avoid `check-env-drift` failures.

## Troubleshooting

- `./ops/check-env-drift.sh dev|prod`: discovers if `.env` is misaligned before you run any compose commands. Running it manually shows which mode is broken.
- `docker compose --env-file .env.dev config | grep -n "NEXTAUTH_SECRET"` (or the prod equivalent) confirms what value Compose injects for a given mode before launching containers.
- `docker exec frontend env | grep NEXTAUTH_SECRET` helps verify the running frontend process saw the expected secret.
- If the drift checker refuses to run and you only need to start a one-off container from `.env.dev`, temporarily move `.env` out of the way or copy `NEXTAUTH_SECRET` from `.env.dev` into `.env` so they match, then re-run `./ops/up-dev.sh`.
- LangGraph v2 Diagnose (Health, `parameters/patch`, Node-Contract): `docs/runbook_langgraph_v2.md`

Keeping these commands front and center ensures both dev and prod stacks always start with an explicit env file and that `.env` never silently overrides the expected secrets.
