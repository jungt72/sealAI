#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
# docker-entrypoint-v2.sh — the V2 deploy teeth.
#
# ops/release-backend-v2.sh bakes the gated served tree_hash into the image
# (--build-arg GATE_TREE_HASH → /etc/sealai/gate-tree-hash). A RAW build
# (`docker compose build backend-v2` with no --build-arg) leaves that marker
# EMPTY — current builds already reject missing release identity arguments, and
# this runtime check independently rejects a missing or inconsistent marker.
#
# SEALAI_GATE_MARKER overrides the marker path (tests only; prod uses the default).
# ─────────────────────────────────────────────────────────────────────────────
set -e

MARKER="${SEALAI_GATE_MARKER:-/etc/sealai/gate-tree-hash}"
IDENTITY="${SEALAI_RELEASE_IDENTITY:-/etc/sealai/release-identity.json}"

if [ ! -s "${MARKER}" ]; then
  echo "UNGATED BUILD — refusing to start: no GATE_TREE_HASH baked in." >&2
  echo "Deploy backend-v2 ONLY via ops/release-backend-v2.sh (it gates on an adjudicated eval-REPLAY)." >&2
  exit 1
fi

if ! python -m sealai_v2.config.build_identity verify \
  --identity "${IDENTITY}" --tree-marker "${MARKER}" >/dev/null; then
  echo "INVALID RELEASE IDENTITY — refusing to start." >&2
  exit 1
fi

exec "$@"
