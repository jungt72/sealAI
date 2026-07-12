#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# v2-deploy-deny — Claude Code PreToolUse hook (matcher: Bash).
#
# Blocks a RAW backend-v2 deploy inside CC and points at the sanctioned wrapper.
# It denies an (up|build) verb that EITHER names the backend-v2 service OR
# activates the v2 profile — covering all the bypass shapes:
#   docker compose up -d --build backend-v2          (named service, NO profile flag)
#   docker compose --profile v2 up backend-v2        (--profile v2)
#   docker compose --profile=v2 up backend-v2        (--profile=v2)
#   COMPOSE_PROFILES=v2 docker compose up backend-v2 (env-var profile)
#   docker compose --profile v2 up                   (profile-wide, no service name)
# The wrapper pass is ANCHORED to a genuine invocation at the START of the command,
# so a trailing-comment injection (`… up --build backend-v2  # release-backend-v2.sh`)
# cannot smuggle past it.
#
# This is the in-CC counterpart to the image TEETH (backend/docker-entrypoint-v2.sh),
# which catches a raw build run OUTSIDE CC (empty GATE_TREE_HASH → refuse to start).
#
# FAIL-OPEN by design: a missing jq / unparseable payload → exit 0 (neutral). This
# hook only ADDS a specific deny; it is NOT a global fail-closed. NOTE: the sibling
# deploy-gate.sh is also NOT a global gate — it is a no-op for every command except
# an ops/release-backend.sh invocation, and ITS parse-fail path fail-closes only that
# narrow case. So the out-of-CC and parse-fail backstop for V2 is the entrypoint
# marker (the TEETH), not this hook. Residual (accepted, like the other gates): a
# `wrapper ; <raw deploy>` chain starts with the wrapper and is exempted; aliases /
# `sh -c "…"` / variable-built commands are not introspected.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

deny() {  # $1 = reason (single line)
  echo "V2 DEPLOY DENY: $1" >&2
  exit 2
}

payload="$(cat || true)"
command -v jq >/dev/null 2>&1 || exit 0
cmd="$(printf '%s' "${payload}" | jq -er '.tool_input.command // empty' 2>/dev/null)" || exit 0

m() { printf '%s' "${cmd}" | grep -Eq -- "$1"; }

# Wrapper pass — anchored to a real invocation at the START of the command (not substring).
m '^[[:space:]]*(bash[[:space:]]+)?(\./)?ops/release-backend-v2\.sh([[:space:]]|$)' && exit 0

# Deny: an up/build verb that targets backend-v2 OR activates the v2 profile.
if m '(^|[[:space:]])(up|build)([[:space:]]|$)' \
   && { m '(^|[[:space:]])backend-v2([[:space:]]|$)' \
        || m '--profile[[:space:]=]+v2([[:space:]]|$)' \
        || m 'COMPOSE_PROFILES=([^[:space:]]*,)?v2([,[:space:]]|$)'; }; then
  deny "raw backend-v2 deploy is gated — use ops/release-backend-v2.sh --candidate, --final or --owner-waiver (bakes identity and runs release controls)."
fi

exit 0
