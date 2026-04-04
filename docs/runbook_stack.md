# SealAI Stack Runbook

## Boot persistence
- `sealai-stack.service` is a oneshot unit that waits for `network-online.target`, `docker.service` and `ufw.service`, then delegates to `./ops/up-prod.sh`. That keeps the systemd path aligned with the same secret and image-pin validation used for manual deploys. The dockerized production services remain backend and Keycloak; the public frontend stays host-managed via PM2.
- Install it with `sudo ./ops/install_sealai_stack_service.sh`; the script copies the service file into `/etc/systemd/system`, runs `systemctl daemon-reload`, and enables the unit `--now`.
- If you ever need to stop automatic restarts (for example during maintenance), run `sudo systemctl disable --now sealai-stack.service` and then manually bring the stack up with the compose commands below.

## Stack restart and recovery
- The canonical restart command is `./ops/up-prod.sh`. It validates the local `.env.prod`, enforces pinned image refs, pulls the pinned images, and then starts `backend` and `keycloak`. This keeps manual deploys aligned with the systemd unit and the host-managed frontend setup.
- `./ops/up-prod.sh` also repairs the named `backend-data` volume permissions before starting the backend so `/app/data/models` remains writable for the non-root backend process across recoveries and fresh volume creation.
- After any manual restart you can refresh the service definition with `sudo systemctl restart sealai-stack.service` to let systemd track the new state.

## Smoke tests
- Run `./ops/stack_smoke.sh` to confirm the dockerized production services are running and that the backend responds locally on port 8000. The script exits with diagnostics plus the last 200 log lines on failure.
- `ops/docker_firewall_fix.sh --test` now wraps `ops/stack_smoke.sh` and classifies failures as “services not running”, “listeners missing”, or “curl blocked/timeouts” so firewall fixes only trigger when the network stack is actually blocking traffic.

## Rollback steps
1. Disable the systemd unit: `sudo systemctl disable --now sealai-stack.service`.
2. Take down the containers to avoid stray listeners: `docker compose --env-file /home/thorsten/sealai/.env.prod -f /home/thorsten/sealai/docker-compose.yml -f /home/thorsten/sealai/docker-compose.deploy.yml down --remove-orphans`.
3. Reapply the firewall baseline (if needed) by rerunning `sudo ops/docker_firewall_fix.sh --mode relaxed` or your preferred mode so the DOCKER-USER drop rule plus bridge return rules stay intact.

## Backend Data
- Production backend runtime data is stored in the named Docker volume `backend-data` mounted at `/app/data`.
- This keeps production independent from the repository working tree and avoids hidden host-path coupling.
- The backend container runs as `1000:1000`, so the canonical recovery path is to let `./ops/up-prod.sh` create `/app/data/models` and `/app/data/uploads` and `chown` the volume contents before container startup. Do not rely on `/home/thorsten/sealai/data/backend`; that host path is not the live production mount.
- Backup example: `docker run --rm -v sealai_backend-data:/data -v "$PWD:/backup" alpine tar czf /backup/backend-data.tgz -C /data .`

## Monitoring
- The current pinned production backend image does not expose `/metrics`, so Prometheus backend scraping is intentionally disabled in [monitoring/prometheus.yml](/home/thorsten/sealai/monitoring/prometheus.yml).
- When a future backend release explicitly includes a supported Prometheus endpoint, re-enable the scrape job and restart Prometheus with `docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml up -d prometheus`.

## Releases
- Keep a local `.env.prod` on the VPS, created from [`.env.prod.example`](/home/thorsten/sealai/.env.prod.example). Do not commit real production secrets.
- Pin production images in `.env.prod` as immutable refs. `tag@digest` is preferred when a release tag exists; digest-only refs are acceptable and are the current baseline in this repo.
- Before changing image refs for a release, copy `.env.prod` to a dated local backup such as `.env.prod.rollback-$(date +%Y%m%d-%H%M%S)`.
- Release by updating `BACKEND_IMAGE` and `KEYCLOAK_IMAGE` in `.env.prod`, then run `./ops/up-prod.sh`.
- Roll back by restoring the previous backup copy of `.env.prod` or by restoring the previous pinned image refs in `.env.prod`, then rerunning `./ops/up-prod.sh`.

Keep UFW in default deny (incoming/outgoing/routed) and leave the final DROP in DOCKER-USER; the stack still relies on the return rules and `sealai-stack.service` to keep the two public ports accessible without exposing anything else.
