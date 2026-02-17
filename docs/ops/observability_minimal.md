# Minimal Observability (Patch O1)

We use lightweight shell scripts to monitor critical signals without deploying a full observability stack (Prometheus/ELK).

## Scripts

Location: `scripts/obs/`

### 1. Nginx 429 Watcher
Counts HTTP status codes from Nginx logs.
```bash
# Watch live (every 10s)
bash scripts/obs/nginx_429_watch.sh

# Check last hour once
bash scripts/obs/nginx_429_watch.sh --since 1h --once
```
**Metric**: `rl_429` (Rate Limited requests). High numbers indicate attack or aggressive client.

### 2. Keycloak Auth Watcher
Scans Keycloak logs for login failures.
```bash
# Check last 10m
bash scripts/obs/keycloak_auth_watch.sh --since 10m
```
**Metric**: `invalid_grant` / `LOGIN_ERROR`. Spikes indicate potential credential stuffing or misconfigured clients.

### 3. Redis Token Health
Polls Redis stats for cache efficiency.
```bash
bash scripts/obs/redis_token_health.sh
```
**Metric**: `keyspace_misses` vs `hits`. `evicted_keys` > 0 means the specific memory limit is reached and tokens might be dropping early.

## Integration
These scripts can be:
- Run manually during incidents.
- Added to cron for periodic health checks.
- Piped to a file for simple historical tracking.

### 4. Watch All
Runs all watchers in parallel (Ctrl+C to stop).
```bash
bash scripts/obs/watch_all.sh
```

## Alerting (Patch O2.1)

SealAI supports opt-in webhook alerts.

1. Add to `.env`:
```bash
ALERT_WEBHOOK_URL="https://discord.com/api/webhooks/..."
ALERT_CHANNEL=discord # or slack
```

2. Run watchers:
```bash
bash scripts/obs/watch_all.sh --once
```

Alerts only fire when thresholds are exceeded.
Webhook URLs are never printed.
