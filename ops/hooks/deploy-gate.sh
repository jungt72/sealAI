#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Deploy gate — Claude Code PreToolUse hook (matcher: Bash). FAIL-CLOSED.
#
# Blocks `ops/release-backend.sh` unless BOTH sentinels exist and are fresh
# (< MAX_AGE seconds):
#   (i)  full backend pytest exit 0       → .claude/.gate-logs/sentinels/pytest-green
#   (ii) rollback anchor verified via      → .claude/.gate-logs/sentinels/anchor-verified
#        docker inspect (running daemon)
#
# The sentinels are written by the operator/agent immediately after performing
# each gate step, e.g.:
#   .venv/bin/python -m pytest backend -q -rf  && touch <pytest-green>
#   docker inspect backend ...                 && touch <anchor-verified>
#
# A passing gate exits 0 → the call still hits the project "ask" permission on
# release-backend.sh, so the human confirms every real deploy. Missing/stale
# sentinel → exit 2 (block). Schema verified against Claude Code 2.1.161.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/home/thorsten/sealai}"
SENT_DIR="${PROJECT_DIR}/.claude/.gate-logs/sentinels"
MAX_AGE="${SEALAI_DEPLOY_SENTINEL_MAX_AGE:-3600}"   # default 1h

deny() {  # $1 = reason (single line)
  echo "DEPLOY GATE (fail-closed): $1" >&2
  exit 2
}

payload="$(cat || true)"

# Only gate the production release script.
case "${payload}" in
  *"ops/release-backend.sh"*) : ;;
  *) exit 0 ;;
esac

check_sentinel() {  # $1 = file, $2 = human label
  local f="$1" label="$2" now age mtime
  [ -f "${f}" ] || deny "missing sentinel — ${label}. Run the gate step, then re-attempt."
  now="$(date +%s)"
  mtime="$(stat -c %Y "${f}" 2>/dev/null || echo 0)"
  age=$(( now - mtime ))
  if [ "${age}" -lt 0 ] || [ "${age}" -gt "${MAX_AGE}" ]; then
    deny "stale sentinel — ${label} (age ${age}s > ${MAX_AGE}s). Re-run the gate step."
  fi
}

check_sentinel "${SENT_DIR}/pytest-green"     "full backend pytest exit 0"
check_sentinel "${SENT_DIR}/anchor-verified"  "rollback anchor verified via docker inspect"

# Both sentinels fresh → defer to the normal "ask" permission (human confirms).
exit 0
