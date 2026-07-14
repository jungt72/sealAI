#!/bin/bash -p
# ─────────────────────────────────────────────────────────────────────────────
# Deploy gate — Claude Code PreToolUse hook (matcher: Bash). FAIL-CLOSED.
#
# Blocks an actual INVOCATION of `ops/release-backend.sh` unless BOTH sentinels
# exist and are fresh (< MAX_AGE seconds):
#   (i)  full backend pytest exit 0       → .claude/.gate-logs/sentinels/pytest-green
#   (ii) rollback anchor verified via      → .claude/.gate-logs/sentinels/anchor-verified
#        docker inspect (running daemon)
#
# Matching is on the executed command (`.tool_input.command`), and only when the
# release script is actually invoked at a command position — so a commit message
# or any prose that merely mentions the path no longer triggers the gate (F2).
#
# FAIL-CLOSED command parsing: jq unavailable / payload not valid JSON /
# command not determinable → BLOCK. Parse ambiguity is NEVER waved through.
# Residual gaps (`sh -c`, aliases, variable expansion, or the literal path
# chained mid-line inside a quoted message) are a discipline anchor, not
# sandboxing — see .claude/rules/ops.md.
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

# Extract ONLY the executed command — fail closed on any parse ambiguity.
command -v jq >/dev/null 2>&1 || deny "jq unavailable — cannot parse tool_input.command"
cmd="$(printf '%s' "${payload}" | jq -er '.tool_input.command // empty' 2>/dev/null)" \
  || deny "tool_input.command not determinable (payload malformed or command absent)"

# Only gate an actual INVOCATION of the release script (command position):
# start-of-line or a shell separator, optional bash/sh/./ prefix — so a mere
# mention in a commit message or prose does not trigger.
RELEASE_RE='(^|[;&|])[[:space:]]*((/bin/)?(bash|sh)([[:space:]]+-p)?[[:space:]]+)?(\./)?ops/release-backend\.sh([[:space:]]|;|&|\||$)'
printf '%s' "${cmd}" | grep -Eq "${RELEASE_RE}" || exit 0

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
