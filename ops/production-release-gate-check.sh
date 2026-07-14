#!/bin/bash -p
# Shared fail-closed invocation contract for production_release_gate.py.
#
# This file is sourced by production entrypoints. It deliberately uses an
# isolated system Python process twice: once for the gate and once to validate
# the complete success document. Caller-controlled Python variables, startup
# hooks, PATH entries, and additional argparse tokens cannot influence either
# process.

production_release_gate_check() {
  if [[ "$#" -lt 2 || "$#" -gt 3 ]]; then
    printf '%s\n' \
      'production release gate invocation: expected GATE_PATH OPERATION [EXPECTED_SOURCE_SHA]' >&2
    return 64
  fi

  local gate_path="$1"
  local operation="$2"
  local expected_source_sha="${3:-}"
  local decision
  local approved_source_sha

  PRODUCTION_RELEASE_GATE_DECISION=""
  PRODUCTION_RELEASE_APPROVED_SOURCE_SHA=""

  case "${operation}" in
    build|pull|deploy|migration|dashboard-publish|recovery-start-existing|remediation-control-install) ;;
    *)
      printf '%s\n' \
        '{"component":"sealai-production-release-gate-invocation","allowed":false,"reason":"invalid_operation"}' >&2
      return 64
      ;;
  esac
  if [[ "${gate_path}" != /* || ! -f "${gate_path}" || -L "${gate_path}" ]]; then
    printf '%s\n' \
      '{"component":"sealai-production-release-gate-invocation","allowed":false,"reason":"unsafe_gate_path"}' >&2
    return 78
  fi
  if [[ -n "${expected_source_sha}" && \
        ! "${expected_source_sha}" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]]; then
    printf '%s\n' \
      '{"component":"sealai-production-release-gate-invocation","allowed":false,"reason":"invalid_expected_source"}' >&2
    return 64
  fi

  # Do not use the caller's Python interpreter, PATH, HOME, or PYTHON* values.
  # `-I` additionally disables user site packages and all PYTHON* processing.
  if decision="$(
    /usr/bin/env -i \
      HOME=/nonexistent \
      PATH=/usr/sbin:/usr/bin:/sbin:/bin \
      LANG=C \
      LC_ALL=C \
      /usr/bin/python3 -I "${gate_path}" check "${operation}"
  )"; then
    :
  else
    local gate_status=$?
    return "${gate_status}"
  fi
  if (( ${#decision} > 65536 )); then
    printf '%s\n' \
      '{"component":"sealai-production-release-gate-invocation","allowed":false,"reason":"oversized_success_decision"}' >&2
    return 78
  fi

  # A zero exit status alone is never authorization. Require the exact JSON
  # schema and values for the requested operation, including the approved
  # source commit for every artifact-mutating Gate-10 operation.
  if approved_source_sha="$(
    printf '%s' "${decision}" | \
      /usr/bin/env -i \
        HOME=/nonexistent \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin \
        LANG=C \
        LC_ALL=C \
        /usr/bin/python3 -I -c '
import hmac
import json
import re
import sys

operation, expected_source = sys.argv[1:]
try:
    value = json.load(sys.stdin)
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit(78)
if not isinstance(value, dict):
    raise SystemExit(78)

base = {"allowed", "operation", "reason", "state_id", "required_gate"}
mutating = {"build", "pull", "deploy", "migration", "dashboard-publish"}
if operation in mutating:
    expected_keys = base | {"source_git_sha"}
    expected_reason = "gate10_approved_manifest_bound"
    expected_gate = "GATE-10"
elif operation == "recovery-start-existing":
    expected_keys = base
    expected_reason = "freeze_recovery_start_existing_only"
    expected_gate = "GATE-10"
else:
    expected_keys = base | {"source_git_sha", "approval_id", "artifact_sha256"}
    expected_reason = "gate08_hash_bound_remediation_control_install"
    expected_gate = "GATE-08"

if (
    set(value) != expected_keys
    or value.get("allowed") is not True
    or value.get("operation") != operation
    or value.get("reason") != expected_reason
    or value.get("required_gate") != expected_gate
    or not isinstance(value.get("state_id"), str)
    or not value["state_id"].strip()
):
    raise SystemExit(78)

source = value.get("source_git_sha", "")
if operation in mutating or operation == "remediation-control-install":
    if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", source):
        raise SystemExit(78)
    if expected_source and not hmac.compare_digest(source, expected_source):
        raise SystemExit(78)
if operation == "remediation-control-install":
    approval_id = value.get("approval_id")
    artifacts = value.get("artifact_sha256")
    if (
        not isinstance(approval_id, str)
        or not approval_id.strip()
        or not isinstance(artifacts, dict)
        or not artifacts
        or any(
            not isinstance(path, str)
            or not path
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for path, digest in artifacts.items()
        )
    ):
        raise SystemExit(78)
print(source, end="")
' "${operation}" "${expected_source_sha}"
  )"; then
    :
  else
    printf '%s\n' \
      '{"component":"sealai-production-release-gate-invocation","allowed":false,"reason":"invalid_success_decision"}' >&2
    return 78
  fi

  PRODUCTION_RELEASE_GATE_DECISION="${decision}"
  PRODUCTION_RELEASE_APPROVED_SOURCE_SHA="${approved_source_sha}"
}
