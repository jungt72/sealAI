#!/bin/bash
# Disk-space safeguard (ops hardening, 2026-07-03) — prevents a repeat of the 2026-07-02 incident
# (/dev/sdb hit 100% full from accumulated docker build cache + dangling images, crashed Postgres,
# broke Keycloak login; fixed manually via `docker builder/image prune`, ~14GB freed, no data touched).
#
# SAFE by construction: `docker builder prune` / `docker image prune` only remove UNUSED build cache
# and dangling (untagged) images — never a running container, never a named volume, never live data.
# This script never touches `docker volume prune` or `docker system prune -a` (which WOULD risk
# removing images still referenced by a stopped-but-wanted container) — only the two safe subcommands.
#
# Threshold-gated: does nothing below WARN_PCT (default 80%), so it doesn't churn the build cache on
# every run (image layers are reused across deploys — pruning too eagerly just makes the next build
# slower for no benefit). Above CRITICAL_PCT even after cleanup, this is a loud, visible failure in the
# log (and cron's own mail-on-error, if configured) — there is no automated escalation/alerting beyond
# that today (a known gap, see the ops/security sweep report).
set -uo pipefail

VOLUME=${VOLUME:-/mnt/sealai-data}
WARN_PCT=${WARN_PCT:-80}
CRITICAL_PCT=${CRITICAL_PCT:-90}
LOG_FILE=${LOG_FILE:-"$HOME/sealai-backups/disk_safeguard.log"}
mkdir -p "$(dirname "$LOG_FILE")"

STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
USAGE_BEFORE=$(df --output=pcent "$VOLUME" | tail -1 | tr -d ' %')

if [[ "$USAGE_BEFORE" -lt "$WARN_PCT" ]]; then
  echo "${STAMP} disk_safeguard: ${VOLUME} at ${USAGE_BEFORE}% (below ${WARN_PCT}% threshold) — no action" >>"$LOG_FILE"
  exit 0
fi

echo "${STAMP} disk_safeguard: ${VOLUME} at ${USAGE_BEFORE}% (>= ${WARN_PCT}%) — pruning unused docker build cache + dangling images (safe: no running container, named volume, or live data is touched)" >>"$LOG_FILE"
docker builder prune -f >>"$LOG_FILE" 2>&1
docker image prune -f >>"$LOG_FILE" 2>&1

USAGE_AFTER=$(df --output=pcent "$VOLUME" | tail -1 | tr -d ' %')
echo "${STAMP} disk_safeguard: ${VOLUME} now at ${USAGE_AFTER}% (was ${USAGE_BEFORE}%)" >>"$LOG_FILE"

if [[ "$USAGE_AFTER" -ge "$CRITICAL_PCT" ]]; then
  echo "${STAMP} disk_safeguard: CRITICAL — still at ${USAGE_AFTER}% after cleanup, needs human attention (no more safe automated cleanup available; consider log rotation, old backups, or a volume resize)" >>"$LOG_FILE"
  exit 1
fi
exit 0
