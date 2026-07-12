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

SCOPE_FILE="backend/sealai_v2/eval/remediation/m15_failed_topics_v2.json"
RUNS_DIR="backend/sealai_v2/eval/runs"

SCOPE_OUTPUT="$(python3 - "${SCOPE_FILE}" "${RUNS_DIR}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

scope = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if scope.get("schema_version") != 2:
    raise SystemExit("targeted wrapper requires remediation scope schema v2")
runs = Path(sys.argv[2])
root = json.loads((Path(sys.argv[1]).parent / scope["root_scope"]).read_text(encoding="utf-8"))
baseline = root["baseline"]
baseline_results = runs / baseline["run_label"] / "results.json"
baseline_payload = baseline_results.read_bytes()
if hashlib.sha256(baseline_payload).hexdigest() != baseline["results_sha256"]:
    raise SystemExit("root baseline results hash mismatch")
baseline_manifest = (json.loads(baseline_payload).get("manifest") or {})
if baseline_manifest.get("tree_hash") != baseline["tree_hash"]:
    raise SystemExit("root baseline tree hash mismatch")
if baseline_manifest.get("runtime_profile_hash") != baseline["runtime_profile_hash"]:
    raise SystemExit("root baseline runtime profile mismatch")

parent = scope["parent_run"]
parent_results = runs / parent["run_label"] / "results.json"
parent_data = json.loads(parent_results.read_text(encoding="utf-8"))
parent_projection = dict(parent_data)
parent_projection.pop("adjudication", None)
parent_hash = hashlib.sha256(
    json.dumps(
        parent_projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()
if parent_hash != parent["evaluation_payload_sha256"]:
    raise SystemExit("parent evaluation payload hash mismatch")
parent_manifest = parent_data.get("manifest") or {}
if parent_manifest.get("tree_hash") != parent["tree_hash"]:
    raise SystemExit("parent tree hash mismatch")
if parent_manifest.get("runtime_profile_hash") != parent["runtime_profile_hash"]:
    raise SystemExit("parent runtime profile mismatch")
case_ids = scope.get("failed_topics") or []
if len(case_ids) != len(set(case_ids)) or not case_ids:
    raise SystemExit("failed topic scope must be non-empty and unique")
print(",".join(case_ids) + "\t" + scope["target"]["tree_hash"])
PY
)"
IFS=$'\t' read -r CASE_IDS EXPECTED_TREE <<< "${SCOPE_OUTPUT}"
ACTUAL_TREE="$(bash ops/tree-hash.sh)"
[[ "${ACTUAL_TREE}" == "${EXPECTED_TREE}" ]] || {
  echo "target tree mismatch: expected ${EXPECTED_TREE}, got ${ACTUAL_TREE}" >&2
  exit 2
}

echo ">> targeted remediation scope: ${CASE_IDS}"
[[ "${VERIFY_ONLY}" == "--verify-only" ]] && exit 0
exec bash ops/run_eval.sh \
  --label "${LABEL}" \
  --case-ids "${CASE_IDS}" \
  --columns flags_off,flags_on
