# Rybbit Analytics Runbook

## Current State

- Rybbit is installed on the VPS at `/home/thorsten/rybbit`.
- Version is pinned to `v2.6.1`.
- Containers use unique names: `rybbit_client`, `rybbit_backend`, `rybbit_postgres`, `rybbit_clickhouse`.
- Rybbit client and backend are attached to the existing `sealai_default` Docker network.
- Public exposure is intentionally blocked until DNS and TLS are complete.
- Self-host telemetry is disabled with `DISABLE_TELEMETRY=true`.
- Rybbit signups are currently enabled because the first admin account still needs to be created.

## Architecture

```text
Browser
  -> https://analytics.sealingai.com
  -> nginx container
  -> /api/*      -> rybbit_backend:3001
  -> all other   -> rybbit_client:3002
  -> Rybbit Postgres + ClickHouse volumes
```

## DNS Requirement

Create this DNS record at the authoritative DNS provider:

```text
Type: A
Name: analytics
Value: 49.13.233.145
TTL: 300 or provider default
```

Verify from a machine outside the VPS:

```bash
dig +short A analytics.sealingai.com @1.1.1.1
dig +short A analytics.sealingai.com @8.8.8.8
```

Both should return:

```text
49.13.233.145
```

## Certificate Issuance Without Root LetsEncrypt Access

The VPS user does not currently have passwordless sudo, so do not write to `/etc/letsencrypt`.
Use a repo-local certbot config directory and mount it into nginx.

From `/home/thorsten/sealai`:

```bash
mkdir -p nginx/certs/config nginx/certs/work nginx/certs/logs

certbot certonly \
  --webroot \
  -w /home/thorsten/sealai/nginx/www \
  --config-dir /home/thorsten/sealai/nginx/certs/config \
  --work-dir /home/thorsten/sealai/nginx/certs/work \
  --logs-dir /home/thorsten/sealai/nginx/certs/logs \
  -d analytics.sealingai.com \
  --email mail@thorsten-jung.de \
  --agree-tos \
  --no-eff-email
```

Never commit `nginx/certs/`.

## Nginx Activation

After the certificate exists:

1. Confirm this read-only mount exists on the `nginx` service in the production compose deployment:

```yaml
- ./nginx/certs/config:/etc/letsencrypt-analytics:ro
```

2. Copy the server blocks from `nginx/analytics.rybbit.conf.template` into `nginx/default.conf`.

3. Validate and restart nginx:

```bash
docker exec nginx nginx -t
docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml up -d nginx
docker exec nginx nginx -t
```

## Rybbit Verification

Internal checks:

```bash
docker exec backend curl -fsS http://rybbit_backend:3001/api/health
docker exec backend curl -fsS -I http://rybbit_client:3002/signup
```

Public checks after DNS and TLS:

```bash
curl -fsS -I https://analytics.sealingai.com/signup
curl -fsS https://analytics.sealingai.com/api/health
```

## First Admin And Lockdown

1. Open `https://analytics.sealingai.com/signup`.
2. Create the first admin account.
3. Add the SealingAI site in Rybbit.
4. Copy the generated site ID.
5. Set SealAI production env:

```text
NEXT_PUBLIC_RYBBIT_ENABLED=true
NEXT_PUBLIC_RYBBIT_SITE_ID=<site-id>
NEXT_PUBLIC_RYBBIT_SCRIPT_SRC=https://analytics.sealingai.com/api/script.js
NEXT_PUBLIC_RYBBIT_DASHBOARD_URL=https://analytics.sealingai.com
```

6. Rebuild/restart the frontend.
7. Set `DISABLE_SIGNUP=true` in `/home/thorsten/rybbit/.env`.
8. Restart Rybbit:

```bash
cd /home/thorsten/rybbit
docker compose up -d
```

## Privacy Rules

- Do not track case free text.
- Do not track media names, customer names, manufacturer names, machine details, or uploaded documents.
- Keep dashboard, login, account, and form inputs masked.
- Use only allowlisted metadata events from `frontend/src/lib/analytics/events.ts`.
