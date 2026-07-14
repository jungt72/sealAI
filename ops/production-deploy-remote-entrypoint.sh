#!/bin/bash -p
# Root-installed boundary for one exact, two-gate backend-v2 promotion.
#
# This entrypoint never fetches, checks out, or executes the operator-owned live
# checkout.  The separately installed stdlib control first verifies a root-owned
# staged checkout and a one-shot private GATE-08 receipt.  Gate 10 is then run
# without root privileges from that immutable checkout.  Only after both gates
# agree on source/image/evidence does this process acquire the global storage
# lease, consume the receipt, and drop permanently to the deployment account.
set -euo pipefail
umask 077
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

readonly INSTALLED_ROOT=/usr/local/libexec/sealai
readonly INSTALLED_HELPER="${INSTALLED_ROOT}/production-release-gate-check.sh"
readonly INSTALLED_LEASE="${INSTALLED_ROOT}/production-storage-lease.sh"
readonly INSTALLED_CONTROL="${INSTALLED_ROOT}/production_release_control.py"
readonly INSTALLED_DASHBOARD="${INSTALLED_ROOT}/dashboard_release.py"
readonly CONTROL_RELEASES=/var/lib/sealai/release-control/releases
readonly DEPLOY_USER=thorsten

deny() {
  printf '%s\n' \
    "{\"component\":\"sealai-production-remote-entrypoint\",\"allowed\":false,\"reason\":\"$1\"}" >&2
  exit 78
}

usage() {
  printf '%s\n' \
    'usage: production-deploy-remote-entrypoint.sh --control-sha SHA --source-sha SHA --backend-image REF@sha256:DIGEST' >&2
}

[[ "${EUID}" -eq 0 ]] || deny root_required

CONTROL_SHA=""
SOURCE_SHA=""
BACKEND_IMAGE=""
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --control-sha)
      [[ "$#" -ge 2 ]] || { usage; exit 64; }
      CONTROL_SHA="$2"
      shift 2
      ;;
    --source-sha)
      [[ "$#" -ge 2 ]] || { usage; exit 64; }
      SOURCE_SHA="$2"
      shift 2
      ;;
    --backend-image)
      [[ "$#" -ge 2 ]] || { usage; exit 64; }
      BACKEND_IMAGE="$2"
      shift 2
      ;;
    *) usage; exit 64 ;;
  esac
done

[[ "${CONTROL_SHA}" =~ ^[0-9a-f]{40}$ ]] || { usage; exit 64; }
[[ "${SOURCE_SHA}" =~ ^[0-9a-f]{40}$ ]] || { usage; exit 64; }
[[ "${BACKEND_IMAGE}" =~ ^ghcr\.io/jungt72/sealai-backend-v2:[A-Za-z0-9_][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}$ ]] || {
  usage
  exit 64
}

for directory in / /usr /usr/local /usr/local/libexec "${INSTALLED_ROOT}"; do
  [[ ! -L "${directory}" ]] || deny installed_control_ancestor_symlink
  [[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- "${directory}" 2>/dev/null || true)" == \
      'directory:755:root:root' ]] || deny installed_control_ancestor_unsafe
done
for specification in \
  "${INSTALLED_HELPER}:regular file:755:root:root" \
  "${INSTALLED_LEASE}:regular file:644:root:root" \
  "${INSTALLED_CONTROL}:regular file:755:root:root" \
  "${INSTALLED_DASHBOARD}:regular file:755:root:root"; do
  installed="${specification%%:*}"
  expected="${specification#*:}"
  [[ ! -L "${installed}" ]] || deny installed_control_symlink
  [[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- "${installed}" 2>/dev/null || true)" == \
      "${expected}" ]] || deny installed_control_unsafe
done

DEPLOY_PASSWD="$(/usr/bin/getent passwd "${DEPLOY_USER}" || true)"
IFS=: read -r DEPLOY_NAME _ DEPLOY_UID DEPLOY_GID _ DEPLOY_HOME DEPLOY_SHELL <<< "${DEPLOY_PASSWD}"
[[ "${DEPLOY_NAME:-}" == "${DEPLOY_USER}" && "${DEPLOY_UID:-}" =~ ^[0-9]+$ && \
   "${DEPLOY_GID:-}" =~ ^[0-9]+$ && "${DEPLOY_UID}" -ne 0 && \
   "${DEPLOY_HOME:-}" == /home/thorsten ]] || deny deployment_identity_unsafe

CONTROL_CHECKOUT="${CONTROL_RELEASES}/${CONTROL_SHA}"
STAGED_GATE="${CONTROL_CHECKOUT}/ops/production_release_gate.py"
STAGED_RELEASE="${CONTROL_CHECKOUT}/ops/release-backend-v2.sh"

# This is a data-only verification by already-installed root code.  No staged
# file is executed until every path component, Git object, lineage, manifest,
# and private receipt binding has passed.
"${INSTALLED_CONTROL}" verify-stage \
  --control-sha "${CONTROL_SHA}" \
  --source-sha "${SOURCE_SHA}" \
  --backend-image "${BACKEND_IMAGE}" >/dev/null \
  || deny staged_release_control_invalid

# Run the source-bound Gate-10 program after a permanent privilege drop in the
# child.  The root shell only captures its bounded JSON decision.
if GATE10_DECISION="$(
  /usr/bin/setpriv \
    --reuid="${DEPLOY_UID}" \
    --regid="${DEPLOY_GID}" \
    --init-groups \
    --reset-env \
    /usr/bin/env -i \
      HOME="${DEPLOY_HOME}" \
      PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
      LANG=C \
      LC_ALL=C \
      /bin/bash -p -c '
        set -euo pipefail
        # shellcheck source=/dev/null
        source "$1"
        production_release_gate_check "$2" deploy "$3"
        printf "%s" "$PRODUCTION_RELEASE_GATE_DECISION"
      ' sealai-gate10 "${INSTALLED_HELPER}" "${STAGED_GATE}" "${SOURCE_SHA}"
)"; then
  :
else
  GATE10_STATUS=$?
  exit "${GATE10_STATUS}"
fi
(( ${#GATE10_DECISION} <= 65536 )) || deny gate10_decision_oversized

DECISION_FILE="$(/usr/bin/mktemp /run/sealai-gate10-decision.XXXXXX)"
trap '/bin/rm -f -- "${DECISION_FILE}"' EXIT
chmod 0600 "${DECISION_FILE}"
printf '%s' "${GATE10_DECISION}" > "${DECISION_FILE}"

# The installed control compares the independently validated Gate-10 decision
# against the staged manifest, fixed evidence bundle, requested registry digest,
# and exact private GATE-08 deployment receipt.
AUTHORIZATION="$(
  "${INSTALLED_CONTROL}" authorize \
    --control-sha "${CONTROL_SHA}" \
    --source-sha "${SOURCE_SHA}" \
    --backend-image "${BACKEND_IMAGE}" \
    --gate10-decision-file "${DECISION_FILE}"
)" || deny exact_deployment_authorization_failed
RECEIPT_SHA256="$(
  printf '%s' "${AUTHORIZATION}" | \
    /usr/bin/env -i \
      HOME=/nonexistent \
      PATH=/usr/sbin:/usr/bin:/sbin:/bin \
      LANG=C \
      LC_ALL=C \
      /usr/bin/python3 -I -c '
import json
import re
import sys

value = json.load(sys.stdin)
if set(value) != {"authorized", "backend_image_digest", "receipt_sha256", "source_git_sha"}:
    raise SystemExit(78)
if value.get("authorized") is not True:
    raise SystemExit(78)
receipt = value.get("receipt_sha256")
if not isinstance(receipt, str) or re.fullmatch(r"[0-9a-f]{64}", receipt) is None:
    raise SystemExit(78)
print(receipt, end="")
'
)" || deny authorization_output_invalid

# shellcheck source=/dev/null
source "${INSTALLED_LEASE}"
declare -F acquire_production_storage_lease >/dev/null || deny storage_lease_unavailable
acquire_production_storage_lease

# Single-use is consumed under the same global mutation lease.  A failed
# deployment requires a new, explicitly scoped receipt; silent replay is denied.
CONSUMPTION="$("${INSTALLED_CONTROL}" consume \
  --control-sha "${CONTROL_SHA}" \
  --source-sha "${SOURCE_SHA}" \
  --backend-image "${BACKEND_IMAGE}" \
  --expected-receipt-sha256 "${RECEIPT_SHA256}")" \
  || deny gate08_receipt_consumption_failed
APPROVAL_ID="$(
  printf '%s' "${CONSUMPTION}" | \
    /usr/bin/env -i \
      HOME=/nonexistent \
      PATH=/usr/sbin:/usr/bin:/sbin:/bin \
      LANG=C \
      LC_ALL=C \
      /usr/bin/python3 -I -c '
import json
import re
import sys

value = json.load(sys.stdin)
if set(value) != {"approval_id", "consumed"} or value.get("consumed") is not True:
    raise SystemExit(78)
approval_id = value.get("approval_id")
if not isinstance(approval_id, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", approval_id) is None:
    raise SystemExit(78)
print(approval_id, end="")
'
)" || deny consumption_output_invalid
CONSUMED_RECORD="/var/lib/sealai/deployment-receipts/consumed/${APPROVAL_ID}.json"
[[ ! -L "${CONSUMED_RECORD}" ]] || deny consumed_receipt_symlink
[[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- "${CONSUMED_RECORD}" 2>/dev/null || true)" == \
    'regular file:600:root:root' ]] || deny consumed_receipt_unsafe
exec 8<"${CONSUMED_RECORD}" || deny consumed_receipt_unavailable
[[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- /proc/self/fd/8 2>/dev/null || true)" == \
    'regular file:600:root:root' ]] || deny inherited_receipt_capability_unsafe

# FD 9 (the storage lease) is intentionally inherited.  No root privilege and
# no caller-controlled environment reaches the staged release implementation.
if /usr/bin/setpriv \
  --reuid="${DEPLOY_UID}" \
  --regid="${DEPLOY_GID}" \
  --init-groups \
  --reset-env \
  /usr/bin/env -i \
    HOME="${DEPLOY_HOME}" \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C \
    LC_ALL=C \
    BACKEND_V2_IMAGE="${BACKEND_IMAGE}" \
    /bin/bash -p "${STAGED_RELEASE}" --final; then
  :
else
  BACKEND_STATUS=$?
  exit "${BACKEND_STATUS}"
fi

# Backend and existing frontend exposure are now verified. The installed root
# control revalidates both gates and the consumed one-shot receipt, then moves
# only the dashboard `current` symlink atomically to the exact Gate-10 artifact.
# Its activation primitive restores the prior `current` target on any failure.
"${INSTALLED_CONTROL}" activate-dashboard \
  --control-sha "${CONTROL_SHA}" \
  --source-sha "${SOURCE_SHA}" \
  --backend-image "${BACKEND_IMAGE}" \
  --gate10-decision-file "${DECISION_FILE}" >/dev/null \
  || deny dashboard_gate10_activation_failed

/bin/rm -f -- "${DECISION_FILE}"
trap - EXIT
printf '%s\n' \
  '{"component":"sealai-production-remote-entrypoint","allowed":true,"result":"backend_and_dashboard_promoted"}'
