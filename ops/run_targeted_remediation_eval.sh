#!/usr/bin/env bash
# Runs only the owner-approved failed M15 topics. This wrapper cannot degrade into a full replay.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

[[ $# -ge 1 && $# -le 2 ]] || {
  echo "usage: ops/run_targeted_remediation_eval.sh <run-label> [--verify-only]" >&2
  exit 2
}
LABEL="$1"
VERIFY_ONLY="${2:-}"
[[ -z "${VERIFY_ONLY}" || "${VERIFY_ONLY}" == "--verify-only" ]] || {
  echo "unknown option: ${VERIFY_ONLY}" >&2
  exit 2
}
[[ "${LABEL}" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "invalid run label" >&2
  exit 2
}

SCOPE_FILE="backend/sealai_v2/eval/remediation/m15_failed_topics_v1.json"
RUNS_DIR="backend/sealai_v2/eval/runs"

CASE_IDS="$(python3 - "${SCOPE_FILE}" "${RUNS_DIR}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

scope = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
baseline = scope["baseline"]
results = Path(sys.argv[2]) / baseline["run_label"] / "results.json"
if not results.is_file():
    raise SystemExit(f"baseline results missing: {results}")
payload = results.read_bytes()
actual_sha = hashlib.sha256(payload).hexdigest()
if actual_sha != baseline["results_sha256"]:
    raise SystemExit(
        f"baseline results hash mismatch: expected {baseline['results_sha256']}, got {actual_sha}"
    )
data = json.loads(payload)
manifest = data.get("manifest") or {}
if manifest.get("tree_hash") != baseline["tree_hash"]:
    raise SystemExit("baseline tree hash mismatch")
if manifest.get("runtime_profile_hash") != baseline["runtime_profile_hash"]:
    raise SystemExit("baseline runtime profile mismatch")
case_ids = scope.get("failed_topics") or []
if len(case_ids) != len(set(case_ids)) or not case_ids:
    raise SystemExit("failed topic scope must be non-empty and unique")
print(",".join(case_ids))
PY
)"

echo ">> targeted remediation scope: ${CASE_IDS}"
[[ "${VERIFY_ONLY}" == "--verify-only" ]] && exit 0
exec bash ops/run_eval.sh \
  --label "${LABEL}" \
  --case-ids "${CASE_IDS}" \
  --columns flags_off,flags_on
