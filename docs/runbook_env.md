# Environment Runbook

This guide captures how to start the stack with an explicit env file, keep the secrets in sync, and troubleshoot when things diverge.

## Booting the stack

- **Development**: run `./ops/up-dev.sh`. It first invokes `./ops/check-env-drift.sh dev`, then runs `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up -d --build` from the repository root. The explicit file pair keeps dev-only mounts and `--reload` out of every other mode.
- **Production**: run `./ops/up-prod.sh`. The script validates the local `.env.prod`, rejects placeholder secrets, rejects unpinned images, pulls the pinned images, then runs `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml up -d --remove-orphans backend keycloak`.
  Before the containers are started, the script also prepares the production `backend-data` volume so `/app/data`, `/app/data/uploads`, and `/app/data/models` are owned by the backend runtime user (`1000:1000`). This keeps the image-based production path intact while preventing model-cache permission failures after a fresh volume create or recovery.

## Secret rotation

- The canonical sources for secrets are `.env.dev` and the local, uncommitted `.env.prod`. Use [`.env.prod.example`](/home/thorsten/sealai/.env.prod.example) as the production template and keep real prod values only in `.env.prod`.
- `./ops/check-env-drift.sh` validates that required runtime secrets exist in `.env.dev` / `.env.prod`, rejects placeholder values such as `SET_IN_SECRET_STORE` in production, and enforces pinned prod image references via `BACKEND_IMAGE`, `KEYCLOAK_IMAGE`, and `FRONTEND_IMAGE`.
- The current production baseline uses digest-only GHCR refs in `.env.prod`. If you later adopt release tags, keep the same immutability level by using `tag@digest`, not plain tags.
- When rotating `NEXTAUTH_SECRET`:
  1. Update the value in `.env.dev` and/or `.env.prod`.
  2. Start the stack with the corresponding `ops/up-*.sh` script so the new secret flows into the containers.
  3. Optionally copy the value into `.env` if other helpers still need it; otherwise keep `.env` absent or identical to the target env file to avoid `check-env-drift` failures.

## Troubleshooting

- `./ops/check-env-drift.sh dev|prod`: discovers if `.env` is misaligned before you run any compose commands. Running it manually shows which mode is broken.
- `docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml config | grep -n "NEXTAUTH_SECRET"` confirms the dev merge before launching containers.
- `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml config | grep -n "image:"` confirms the pinned deploy image refs before launching containers.
- `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml config | grep -n "backend-data"` confirms production now persists backend runtime data in a named Docker volume rather than a repo bind mount.
- `docker run --rm --user 0:0 --entrypoint sh -v sealai_backend-data:/app/data postgres:15 -lc 'stat -c "%n %u:%g %a" /app/data /app/data/models /app/data/uploads'` verifies the named production volume is writable for the backend runtime user after `./ops/up-prod.sh`.
- `docker exec frontend env | grep NEXTAUTH_SECRET` helps verify the running frontend process saw the expected secret.
- If the drift checker refuses to run and you only need to start a one-off container from `.env.dev`, temporarily move `.env` out of the way or copy `NEXTAUTH_SECRET` from `.env.dev` into `.env` so they match, then re-run `./ops/up-dev.sh`.
- Backend source edits are live in dev because `docker-compose.dev.yml` mounts `./backend:/app` and starts `uvicorn --reload`. Dependency changes still require `./ops/up-dev.sh` or an explicit image rebuild.
- LangGraph v2 Diagnose (Health, `parameters/patch`, Node-Contract): `docs/runbook_langgraph_v2.md`

## Why Compose Watch Is Not The Primary Dev Loop

- Docker Compose Watch is available on this VPS, but it would add a second long-running dev control loop on top of the already explicit `./ops/up-dev.sh` workflow.
- For this Python/FastAPI stack, `./backend:/app` plus `uvicorn --reload` is the simpler and more observable model: the container sees the real working tree immediately, and the reload mechanism already restarts the process correctly after source edits.
- Dependency changes remain intentionally explicit. Editing `requirements.txt` or `requirements-dev.txt` still requires `./ops/up-dev.sh` so the image is rebuilt and Python packages stay image-based rather than drifting via sync.
- Dev-only cache noise is redirected into `/tmp` inside the container through `PYTEST_ADDOPTS`, `RUFF_CACHE_DIR`, `MYPY_CACHE_DIR`, and `PYTHONDONTWRITEBYTECODE=1`.

Keeping these commands front and center ensures both dev and prod stacks always start with an explicit env file and that `.env` never silently overrides the expected secrets.
