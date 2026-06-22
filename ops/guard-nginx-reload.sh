#!/usr/bin/env bash
# ops/guard-nginx-reload.sh — cutover drift guard (runbook Phase 3 step 6).
#
# The worktree file nginx/default.conf IS the prod nginx config (bind-mounted); the release
# scripts reload nginx at the end of every deploy. If the worktree sits on a branch WITHOUT the
# V2 include line while V2 routing is live, that reload would silently revert the cutover.
# This guard refuses exactly that case: V2 routing loaded in nginx, absent from the file.
#
# Override (deliberate un-flip goes through ops/v2-flip.sh --revert, not this): ALLOW_V2_ROUTE_DROP=1
set -euo pipefail

CONTAINER="${NGINX_CONTAINER:-nginx}"
FILE="${NGINX_CONF:-nginx/default.conf}"
INCLUDE_RE='^[[:space:]]*include snippets/v2_dashboard\.conf;'

# Nothing running → nothing to drop.
docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" || exit 0

loaded="$(docker exec "$CONTAINER" nginx -T 2>/dev/null | grep -cE "$INCLUDE_RE" || true)"
in_file="$(grep -cE "$INCLUDE_RE" "$FILE" 2>/dev/null || true)"

if [[ "${loaded:-0}" -gt 0 && "${in_file:-0}" -eq 0 ]]; then
  if [[ "${ALLOW_V2_ROUTE_DROP:-0}" == "1" ]]; then
    echo ">> WARNING: reload will DROP live V2 routing (ALLOW_V2_ROUTE_DROP=1 override)" >&2
    exit 0
  fi
  cat >&2 <<'EOF'
!! BLOCKED: live nginx serves V2 routing (include snippets/v2_dashboard.conf) but the worktree
!! nginx/default.conf does NOT contain it — reloading now would silently revert the V2 cutover.
!! Likely cause: worktree on a branch without the flip commit. Fix the branch (or run
!! ops/v2-flip.sh --revert for a DELIBERATE un-flip). Override: ALLOW_V2_ROUTE_DROP=1.
EOF
  exit 1
fi
exit 0
