#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Doctrine gate — Claude Code PreToolUse hook (matcher: Bash). FAIL-CLOSED.
#
# Blocks `git commit` / `git push` unless the fast doctrine guard suite passes.
# Reads the PreToolUse JSON payload on stdin; only gates Bash commands that
# contain `git commit` or `git push`. Everything else is neutral (exit 0 →
# normal permission flow continues).
#
# Block mechanism: exit code 2 (Claude Code feeds stderr back to the model and
# blocks the tool call). Chosen over the JSON deny form because a non-zero exit
# is unambiguous and any internal error path also denies — i.e. FAIL-CLOSED.
#
# Emergency override: SEALAI_DOCTRINE_GATE_BYPASS=1 — allowed but LOGGED, never
# silent. Use only when the gate itself is broken, not to ship a doctrine leak.
#
# Schema verified against Claude Code 2.1.161.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-/home/thorsten/sealai}"
LOG_DIR="${PROJECT_DIR}/.claude/.gate-logs"
mkdir -p "${LOG_DIR}" 2>/dev/null || true
LOG="${LOG_DIR}/doctrine-gate.log"
LAST="${LOG_DIR}/doctrine-gate.last"

deny() {  # $1 = reason (single line)
  echo "DOCTRINE GATE (fail-closed): $1" >&2
  exit 2
}
log() { printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "${LOG}" 2>/dev/null || true; }

payload="$(cat || true)"

# Only gate git history mutations. matcher already restricts this to Bash.
case "${payload}" in
  *"git commit"*|*"git push"*) : ;;
  *) exit 0 ;;
esac

# Emergency override — allowed, but always recorded.
if [ "${SEALAI_DOCTRINE_GATE_BYPASS:-}" = "1" ]; then
  log "BYPASS used (SEALAI_DOCTRINE_GATE_BYPASS=1) — doctrine gate skipped"
  echo "DOCTRINE GATE: BYPASS active (logged)." >&2
  exit 0
fi

cd "${PROJECT_DIR}" 2>/dev/null || deny "cannot enter project dir ${PROJECT_DIR}"
PY="${PROJECT_DIR}/.venv/bin/python"
[ -x "${PY}" ] || deny "venv python missing (${PY}) — cannot run guard suite"

# Fast doctrine guard suite (the executable contract for the output doctrine).
if "${PY}" -m pytest \
      backend/app/agent/tests/test_comparative_ranking_guard.py \
      backend/app/agent/tests/test_rwdr_comparative_leak_golden.py \
      backend/app/agent/tests/v92/test_final_guard_knowledge_backstop.py \
      -q > "${LAST}" 2>&1; then
  log "PASS — guard suite green; commit/push allowed to proceed to normal permissions"
  exit 0
fi

log "BLOCK — guard suite FAILED; commit/push denied"
deny "fast doctrine guard suite FAILED — commit/push blocked. See ${LAST}"
