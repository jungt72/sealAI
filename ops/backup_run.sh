#!/bin/bash
# Nightly backup orchestrator (ops hardening, 2026-07-03) — runs backup_postgres.sh + backup_qdrant.sh,
# logs a one-line summary per run to $LOG_FILE (append-only; rotated by size via `logrotate`-style
# truncation is NOT set up here — the log is tiny, one line/day). Scheduled via the invoking user's own
# crontab (no root needed): `crontab -e` -> `0 3 * * * $HOME/sealai/ops/backup_run.sh`.
#
# Each backup script is independent + fail-closed (a failure in one does not skip the other, and does
# NOT delete any existing good backup) — this script's job is only orchestration + a durable log trail
# a human (or a future monitoring hook) can check.
set -uo pipefail  # NOT -e: one script failing must not skip the other

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE=${LOG_FILE:-"$HOME/sealai-backups/backup.log"}
mkdir -p "$(dirname "$LOG_FILE")"

STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PG_OK=1
QD_OK=1

if "$DIR/backup_postgres.sh" >>"$LOG_FILE" 2>&1; then PG_OK=0; fi
if "$DIR/backup_qdrant.sh" >>"$LOG_FILE" 2>&1; then QD_OK=0; fi

if [[ "$PG_OK" -eq 0 && "$QD_OK" -eq 0 ]]; then
  echo "${STAMP} backup_run: OK (postgres + qdrant)" >>"$LOG_FILE"
  exit 0
fi
echo "${STAMP} backup_run: FAILED (postgres_ok=$([[ $PG_OK -eq 0 ]] && echo yes || echo NO) qdrant_ok=$([[ $QD_OK -eq 0 ]] && echo yes || echo NO)) — see log above" >>"$LOG_FILE"
exit 1
