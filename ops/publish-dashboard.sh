#!/bin/bash -p
# ops/publish-dashboard.sh — the gated dashboard (frontend-v2) publisher.
#
# GATE-10 P1 phase 4 follow-up: dashboard_artifact_sha256 (production_release_gate.py)
# proves a CLAIMED hash matches what is sitting in frontend-v2/.build/dashboard-candidate/.
# This script is the missing other half docs/ops/RUNBOOK_V2_CUTOVER.md calls the "gated
# publisher": build candidate -> content-address it -> gate-check the dashboard-publish
# operation -> only THEN promote into the live frontend-v2/dist/ directory nginx
# bind-mounts read-only at /usr/share/nginx/v2-client (docker-compose.deploy.yml).
#
# The gate check happens BEFORE any write to the live directory. A denial (e.g. the
# active production freeze) never touches dist/ at all -- same ordering
# ops/v2-flip.sh already uses for the nginx-config side of a cutover.
#
#   ops/publish-dashboard.sh                # build + verify + gate-check + promote
#   ops/publish-dashboard.sh --check-only   # build + verify + gate-check, never promotes
#
# Known, deliberate limitation: promotion is `rsync -a --delete` directly into the live
# directory, not a symlink blue/green swap -- that would need docker-compose.deploy.yml's
# mount itself redesigned (frontend-v2/dist is mounted directly, not via a symlink target),
# which is a separate, bigger change. A concurrent request during the sync window can in
# principle see a transient mix of old/new files; for this SPA's size that window is well
# under a second. A pre-promotion snapshot gives an instant manual rollback regardless.
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

CHECK_ONLY=0
if [[ "${1:-}" == "--check-only" ]]; then
  CHECK_ONLY=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--check-only]" >&2
  exit 2
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd "${REPO_ROOT}"

# shellcheck source=production-release-gate-check.sh
source "${SCRIPT_DIR}/production-release-gate-check.sh"

CANDIDATE_DIR="${REPO_ROOT}/frontend-v2/.build/dashboard-candidate"
LIVE_DIR="${REPO_ROOT}/frontend-v2/dist"

echo ">> building frontend-v2 candidate (writes only to .build/dashboard-candidate/,"
echo "   enforced by vite.config.ts's own sealai-deny-live-dashboard-build plugin)"
(cd frontend-v2 && npm run build)

echo ">> content-addressing candidate"
DASHBOARD_HASH="$(
  /usr/bin/env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C LC_ALL=C \
    /usr/bin/python3 -I -c \
    "import sys; sys.path.insert(0, 'ops'); from production_release_gate import _dashboard_artifact_sha256; print(_dashboard_artifact_sha256())"
)"
[[ "${DASHBOARD_HASH}" =~ ^[0-9a-f]{64}$ ]] \
  || { echo "!! invalid dashboard_artifact_sha256: ${DASHBOARD_HASH}" >&2; exit 1; }
echo ">> dashboard_artifact_sha256 = ${DASHBOARD_HASH}"

echo ">> gate check: dashboard-publish"
if production_release_gate_check \
  "${SCRIPT_DIR}/production_release_gate.py" dashboard-publish; then
  echo ">> gate ALLOWED (source_git_sha=${PRODUCTION_RELEASE_APPROVED_SOURCE_SHA})"
else
  status=$?
  echo "!! gate DENIED dashboard-publish (exit ${status}) -- candidate built and hashed," >&2
  echo "   live directory NOT touched. This is correct while GATE-10 is frozen/unapproved." >&2
  exit "${status}"
fi

if [[ "${CHECK_ONLY}" == 1 ]]; then
  echo ">> --check-only: not promoting"
  exit 0
fi

[[ -d "${CANDIDATE_DIR}" ]] || { echo "!! candidate directory missing after build" >&2; exit 1; }

TS="$(date -u +%Y%m%d-%H%M%S)"
if [[ -d "${LIVE_DIR}" ]]; then
  ROLLBACK_DIR="${REPO_ROOT}/frontend-v2/dist.rollback-${TS}"
  echo ">> snapshotting current live dashboard: ${ROLLBACK_DIR}"
  cp -a "${LIVE_DIR}" "${ROLLBACK_DIR}"
  echo ">> rollback command if needed:"
  echo "   rm -rf ${LIVE_DIR} && mv ${ROLLBACK_DIR} ${LIVE_DIR}"
fi

echo ">> promoting candidate -> live (rsync -a --delete --checksum)"
mkdir -p "${LIVE_DIR}"
# --checksum: a fresh candidate build can easily produce a file with the same size and
# the same one-second mtime granularity as the file it replaces (verified by hand: rsync's
# default quick-check silently skipped such a file, leaving stale content live). Content
# hashing is exactly what this script already does for dashboard_artifact_sha256 anyway --
# paying for it again here is cheap for a build this size and removes a real correctness
# gap, not a theoretical one.
rsync -a --delete --checksum "${CANDIDATE_DIR}/" "${LIVE_DIR}/"

echo ">> done -- dashboard_artifact_sha256 ${DASHBOARD_HASH} is now live at ${LIVE_DIR}"
