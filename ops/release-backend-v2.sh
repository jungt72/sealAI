#!/bin/bash -p
# ─────────────────────────────────────────────────────────────────────────────
# ops/release-backend-v2.sh — THE ONLY sanctioned V2 (`backend-v2`) deploy.
#
# Closes the bypass found in the deploy-gate audit: the V1 deploy-gate hook only
# watches ops/release-backend.sh and checks V1 sentinels, so a raw
# `docker compose … --profile v2 up --build backend-v2` shipped UNGATED. This
# wrapper supports explicit release stages and bakes a start-time marker so
# a raw build refuses to run: `candidate` is restricted to explicitly declared
# non-production environments and `final` binds production to an adjudicated replay.
#
# Gate chain:
#   1. TREE_HASH = ops/tree-hash.sh backend/sealai_v2   (served-runtime content)
#   2. Pull the immutable candidate, verify its signed SLSA provenance + SPDX
#      SBOM, then derive its secret-free runtime-profile hash.
#   3. final: ops/v2_deploy_gate.py -> a complete, final-adjudicated full replay
#      with that exact tree, L1 and runtime profile; all gated axes are clean.
#      Targeted/chained evidence and owner waivers cannot authorize promotion.
#   4. Rollback rung, verified pre-migration backup and Alembic migration,
#      idempotent knowledge-ledger bootstrap + derived-index drain, then recreate
#      backend-v2 + its durable worker from the same image.
#   5. Smoke: health (internal+public) · worker · kern one-shot (PV=50.0 / v=16,755) ·
#      restart-survival. RED at any point → HALT, NO ledger line, print rollback.
#   6. Ledger: append ops/deploy-ledger.jsonl (machine-readable commit→deploy
#      index) + print a ready GOVERNANCE_LOG paste-block (prose stays owner-authored).
#
# This script is a DEPLOY: do not run it as part of a build/review. Only the gate
# logic (step 2, ops/v2_deploy_gate.py) is unit-tested offline.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
readonly GIT_CONFIG_NOSYSTEM=1
readonly GIT_CONFIG_GLOBAL=/dev/null
readonly GIT_TERMINAL_PROMPT=0
readonly GIT_OPTIONAL_LOCKS=0
export GIT_CONFIG_NOSYSTEM GIT_CONFIG_GLOBAL GIT_TERMINAL_PROMPT GIT_OPTIONAL_LOCKS

usage() {
  cat <<'EOF'
usage: ops/release-backend-v2.sh [--candidate|--final]

  --candidate  Deploy an explicitly unvalidated candidate only when APP_ENV is
               development, test, or staging. Never accepted for production.
  --final      Deploy a final release. Requires a fully adjudicated eval replay.
               This is the default when no option is supplied.
EOF
}

RELEASE_STAGE="final"
case "${1:-}" in
  --candidate) RELEASE_STAGE="candidate"; shift ;;
  --final)     shift ;;
  "")         ;;
  --help|-h)   usage; exit 0 ;;
  *)           usage >&2; echo "release-backend-v2: unknown option: $1" >&2; exit 2 ;;
esac
[[ $# -eq 0 ]] || { usage >&2; echo "release-backend-v2: unexpected arguments: $*" >&2; exit 2; }

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
# shellcheck source=production-release-gate-check.sh
source "${SCRIPT_DIR}/production-release-gate-check.sh"
production_release_gate_check "${SCRIPT_DIR}/production_release_gate.py" deploy
RELEASE_GATE_DECISION="${PRODUCTION_RELEASE_GATE_DECISION}"
APPROVED_SOURCE_SHA="${PRODUCTION_RELEASE_APPROVED_SOURCE_SHA}"
[[ "${APPROVED_SOURCE_SHA}" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]] || {
  echo "release-backend-v2: release gate did not return an approved source parent" >&2
  exit 2
}
release_hash() {
  local name="$1"
  printf '%s' "${RELEASE_GATE_DECISION}" | \
    /usr/bin/env -i \
      HOME=/nonexistent \
      PATH=/usr/sbin:/usr/bin:/sbin:/bin \
      LANG=C \
      LC_ALL=C \
      /usr/bin/python3 -I -c '
import json
import re
import sys

name = sys.argv[1]
value = json.load(sys.stdin)
hashes = value.get("release_hashes")
expected = {
    "served_tree_sha256",
    "backend_image_digest",
    "frontend_image_digest",
    "dashboard_artifact_sha256",
    "database_migration_sha256",
    "rollback_plan_sha256",
    "evidence_manifest_sha256",
}
if not isinstance(hashes, dict) or set(hashes) != expected or name not in expected:
    raise SystemExit(78)
item = hashes[name]
pattern = r"sha256:[0-9a-f]{64}" if name.endswith("_image_digest") else r"[0-9a-f]{64}"
if not isinstance(item, str) or re.fullmatch(pattern, item) is None:
    raise SystemExit(78)
print(item, end="")
' "${name}"
}
APPROVED_BACKEND_IMAGE_DIGEST="$(release_hash backend_image_digest)" || {
  echo "release-backend-v2: could not extract the approved backend image digest" >&2
  exit 2
}
APPROVED_FRONTEND_IMAGE_DIGEST="$(release_hash frontend_image_digest)" || exit 2
APPROVED_DASHBOARD_ARTIFACT_SHA256="$(release_hash dashboard_artifact_sha256)" || exit 2
APPROVED_SERVED_TREE_SHA256="$(release_hash served_tree_sha256)" || exit 2
APPROVED_DATABASE_MIGRATION_SHA256="$(release_hash database_migration_sha256)" || exit 2
APPROVED_ROLLBACK_PLAN_SHA256="$(release_hash rollback_plan_sha256)" || exit 2
APPROVED_EVIDENCE_MANIFEST_SHA256="$(release_hash evidence_manifest_sha256)" || exit 2
# shellcheck source=production-storage-lease.sh
source /usr/local/libexec/sealai/production-storage-lease.sh
acquire_production_storage_lease

cd "${REPO_ROOT}"

SERVICE="backend-v2"
WORKER_SERVICE="backend-v2-worker"
readonly PRODUCTION_CONTROL_ROOT=/var/lib/sealai/release-control/releases
readonly PRODUCTION_ENV_FILE=/home/thorsten/sealai/.env.prod
readonly PROMOTION_EVIDENCE_FILE=/var/lib/sealai/release-evidence/promotion-evidence.json
readonly ROLLBACK_PLAN_FILE=/var/lib/sealai/release-evidence/rollback-plan.json
readonly RUNS_DIR=/var/lib/sealai/release-evidence/runs
if [[ "${RELEASE_STAGE}" == "final" ]]; then
  ENV_FILE="${PRODUCTION_ENV_FILE}"
else
  ENV_FILE="${REPO_ROOT}/.env.prod"
fi
COMPOSE=(docker compose --project-name sealai --env-file "${ENV_FILE}" -f docker-compose.yml -f docker-compose.deploy.yml --profile v2)
/bin/bash -p "${SCRIPT_DIR}/validate-production-compose-security.sh" "${ENV_FILE}"
BACKEND_IMAGE_REF="${BACKEND_V2_IMAGE:-}"
LOCAL_BACKEND_IMAGE="sealai-backend-v2:local"
ROLLBACK_IMAGE_OVERRIDE="${SEALAI_V2_ROLLBACK_IMAGE:-}"

die() { echo "release-backend-v2: $*" >&2; exit 1; }
env_prod() { sed -n "s/^$1=//p" "${ENV_FILE}" | tail -n1; }
verify_repo_digest() {
  local reference="$1"
  local repo_digests_json="$2"
  printf '%s' "${repo_digests_json}" | \
    /usr/bin/python3 -I -c '
import json
import re
import sys

reference = sys.argv[1]
repository_with_tag, digest = reference.rsplit("@", 1)
last_slash = repository_with_tag.rfind("/")
last_colon = repository_with_tag.rfind(":")
repository = (
    repository_with_tag[:last_colon]
    if last_colon > last_slash
    else repository_with_tag
)
try:
    repo_digests = json.load(sys.stdin)
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit(78)
if (
    not isinstance(repo_digests, list)
    or not repo_digests
    or any(not isinstance(item, str) for item in repo_digests)
    or f"{repository}@{digest}" not in repo_digests
    or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
):
    raise SystemExit(78)
' "${reference}"
}

[[ -f "${ENV_FILE}" && ! -L "${ENV_FILE}" ]] || die "fixed environment file is unavailable or symlinked"

DEPLOY_ENV="$(env_prod APP_ENV)"
DEPLOY_ENV="${DEPLOY_ENV:-production}"

echo ">> release stage = ${RELEASE_STAGE}"
if [[ "${RELEASE_STAGE}" == "candidate" ]]; then
  case "${DEPLOY_ENV}" in
    development|test|staging) ;;
    *) die "candidate releases are forbidden for APP_ENV=${DEPLOY_ENV}; production requires --final" ;;
  esac
  echo "!! CANDIDATE: paid eval replay intentionally deferred; this is not final release approval." >&2
fi
if [[ "${RELEASE_STAGE}" == "final" && -z "${BACKEND_IMAGE_REF}" ]]; then
  die "final releases require BACKEND_V2_IMAGE=tag@sha256:digest; local unsigned builds are forbidden"
fi
if [[ "${RELEASE_STAGE}" == "final" ]]; then
  [[ "${BACKEND_IMAGE_REF}" =~ ^ghcr\.io/jungt72/sealai-backend-v2:[A-Za-z0-9_][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}$ ]] \
    || die "final BACKEND_V2_IMAGE must be the canonical backend-v2 tag@sha256:digest"
  [[ "${BACKEND_IMAGE_REF##*@}" == "${APPROVED_BACKEND_IMAGE_DIGEST}" ]] \
    || die "BACKEND_V2_IMAGE digest does not match the Gate-10 release manifest"

  COMPOSE_BACKEND_IMAGE="$(
    "${COMPOSE[@]}" config --format json | \
      /usr/bin/python3 -I -c 'import json,sys; print(json.load(sys.stdin)["services"][sys.argv[1]]["image"], end="")' "${SERVICE}"
  )"
  COMPOSE_WORKER_IMAGE="$(
    "${COMPOSE[@]}" config --format json | \
      /usr/bin/python3 -I -c 'import json,sys; print(json.load(sys.stdin)["services"][sys.argv[1]]["image"], end="")' "${WORKER_SERVICE}"
  )"
  COMPOSE_FRONTEND_IMAGE="$(
    "${COMPOSE[@]}" config --format json | \
      /usr/bin/python3 -I -c 'import json,sys; print(json.load(sys.stdin)["services"][sys.argv[1]]["image"], end="")' frontend
  )"
  [[ "${COMPOSE_BACKEND_IMAGE}" == "${BACKEND_IMAGE_REF}" ]] \
    || die "compose ${SERVICE} image is not the Gate-10-approved immutable reference"
  [[ "${COMPOSE_WORKER_IMAGE}" == "${BACKEND_IMAGE_REF}" ]] \
    || die "compose ${WORKER_SERVICE} image is not the Gate-10-approved immutable reference"
  [[ "${COMPOSE_FRONTEND_IMAGE}" =~ ^[^@[:space:]]+@sha256:[0-9a-f]{64}$ ]] \
    || die "compose frontend image is not one immutable registry reference"
  [[ "${COMPOSE_FRONTEND_IMAGE##*@}" == "${APPROVED_FRONTEND_IMAGE_DIGEST}" ]] \
    || die "compose frontend image does not match the Gate-10 frontend digest"
fi

# Production is an artifact promotion. Never deploy bytes from an uncommitted
# worktree because the content hash would no longer describe the served code.
GIT=(/usr/bin/git -c "safe.directory=${REPO_ROOT}" -C "${REPO_ROOT}")
if [[ -n "$("${GIT[@]}" status --porcelain)" ]]; then
  die "worktree is dirty; commit and deploy the exact reviewed commit"
fi
GATE_CONTROL_GIT_SHA="$("${GIT[@]}" rev-parse HEAD)"
SOURCE_GIT_SHA="${APPROVED_SOURCE_SHA}"
[[ "$("${GIT[@]}" rev-parse HEAD^)" == "${SOURCE_GIT_SHA}" ]] \
  || die "Gate-10 source parent changed after release authorization"
if [[ "${RELEASE_STAGE}" == "final" ]]; then
  [[ "${REPO_ROOT}" == "${PRODUCTION_CONTROL_ROOT}/${GATE_CONTROL_GIT_SHA}" ]] \
    || die "final release is not executing from the exact root-staged control checkout"
  [[ "$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- /proc/self/fd/8 2>/dev/null || true)" == \
      'regular file:600:root:root' ]] \
    || die "inherited one-shot GATE-08 deployment capability is unavailable"
  RELEASE_MANIFEST_SHA256="$(
    /usr/bin/python3 -I -c '
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest(), end="")
' "${REPO_ROOT}/ops/production-release-manifest.json"
  )"
  /usr/bin/python3 -I - \
    "${GATE_CONTROL_GIT_SHA}" \
    "${SOURCE_GIT_SHA}" \
    "${APPROVED_BACKEND_IMAGE_DIGEST}" \
    "${APPROVED_EVIDENCE_MANIFEST_SHA256}" \
    "${RELEASE_MANIFEST_SHA256}" <<'PY' || die "one-shot GATE-08 deployment capability does not match this release"
import json
import os
import re
import stat
import sys

metadata = os.fstat(8)
if (
    not stat.S_ISREG(metadata.st_mode)
    or metadata.st_uid != 0
    or stat.S_IMODE(metadata.st_mode) != 0o600
):
    raise SystemExit(78)
raw = os.read(8, 65537)
if not raw or len(raw) > 65536:
    raise SystemExit(78)
value = json.loads(raw)
expected_keys = {
    "approval_id",
    "backend_image_digest",
    "control_git_sha",
    "operation",
    "promotion_evidence_sha256",
    "receipt_sha256",
    "release_manifest_sha256",
    "source_git_sha",
}
if set(value) != expected_keys:
    raise SystemExit(78)
control, source, image, evidence, manifest = sys.argv[1:]
if value != {
    "approval_id": value.get("approval_id"),
    "backend_image_digest": image,
    "control_git_sha": control,
    "operation": "backend-v2-promote",
    "promotion_evidence_sha256": evidence,
    "receipt_sha256": value.get("receipt_sha256"),
    "release_manifest_sha256": manifest,
    "source_git_sha": source,
}:
    raise SystemExit(78)
if not isinstance(value["approval_id"], str) or re.fullmatch(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value["approval_id"]
) is None:
    raise SystemExit(78)
if not isinstance(value["receipt_sha256"], str) or re.fullmatch(
    r"[0-9a-f]{64}", value["receipt_sha256"]
) is None:
    raise SystemExit(78)
PY
fi
RUNTIME_DIR=/home/thorsten/.local/state/sealai
LEDGER="${RUNTIME_DIR}/deploy-ledger.jsonl"
mkdir -p "${RUNTIME_DIR}"

# ── 1. served-runtime content hash (single source of truth) ──────────────────
TREE_HASH="$(/bin/bash -p ops/tree-hash.sh)"
[ -n "${TREE_HASH}" ] || die "empty tree_hash from ops/tree-hash.sh"
SERVED_TREE_SHA256="$(/usr/bin/python3 -I ops/served-tree-sha256.py "${TREE_HASH}")"
[[ "${SERVED_TREE_SHA256}" =~ ^[0-9a-f]{64}$ ]] \
  || die "invalid SHA-256 projection for served tree ${TREE_HASH}"
[[ "${SERVED_TREE_SHA256}" == "${APPROVED_SERVED_TREE_SHA256}" ]] \
  || die "served runtime tree does not match the Gate-10 release manifest"
DATABASE_MIGRATION_SHA256="$(
  /usr/bin/python3 -I ops/database-migration-sha256.py "${SOURCE_GIT_SHA}"
)"
[[ "${DATABASE_MIGRATION_SHA256}" == "${APPROVED_DATABASE_MIGRATION_SHA256}" ]] \
  || die "database migration program does not match the Gate-10 release manifest"
echo ">> served tree_hash = ${TREE_HASH}"
echo ">> served tree SHA-256 = ${SERVED_TREE_SHA256}"
echo ">> database migration SHA-256 = ${DATABASE_MIGRATION_SHA256}"

# Preserve the running rollback artifact BEFORE a local build can replace the service image tag.
# Docker/BuildKit may remove an untagged manifest-list record while its container keeps running;
# reading/tagging it after the build is therefore too late. If that metadata is already missing,
# accept only an explicit, secret-free reconstructed image whose baked revision + served-tree hash
# exactly match the running container labels. Never `docker commit` a production container: its
# Config includes runtime environment values and can therefore contain secrets.
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROLLBACK_STAMP="$(date -u +%Y%m%d-%H%M%S)"
RUNNING_IMAGE_REF="$(docker inspect "${SERVICE}" --format '{{.Image}}' 2>/dev/null || true)"
[[ -n "${RUNNING_IMAGE_REF}" ]] || die "cannot read running ${SERVICE} image from the daemon"
RUNNING_REVISION="$(docker inspect "${SERVICE}" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || true)"
RUNNING_TREE_HASH="$(docker inspect "${SERVICE}" --format '{{index .Config.Labels "io.sealai.served-tree-hash"}}' 2>/dev/null || true)"
ROLLBACK_SOURCE="${RUNNING_IMAGE_REF}"
if ! docker image inspect "${ROLLBACK_SOURCE}" >/dev/null 2>&1; then
  [[ -n "${ROLLBACK_IMAGE_OVERRIDE}" ]] || die "running image metadata ${RUNNING_IMAGE_REF} is missing; rebuild that exact revision/tree as a secret-free image and retry with SEALAI_V2_ROLLBACK_IMAGE=<image>"
  docker image inspect "${ROLLBACK_IMAGE_OVERRIDE}" >/dev/null 2>&1 \
    || die "rollback override image does not exist: ${ROLLBACK_IMAGE_OVERRIDE}"
  OVERRIDE_REVISION="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "${ROLLBACK_IMAGE_OVERRIDE}")"
  OVERRIDE_TREE_HASH="$(docker image inspect --format '{{index .Config.Labels "io.sealai.served-tree-hash"}}' "${ROLLBACK_IMAGE_OVERRIDE}")"
  [[ -n "${RUNNING_REVISION}" && "${OVERRIDE_REVISION}" == "${RUNNING_REVISION}" ]] \
    || die "rollback override revision ${OVERRIDE_REVISION:-<missing>} does not match running revision ${RUNNING_REVISION:-<missing>}"
  [[ -n "${RUNNING_TREE_HASH}" && "${OVERRIDE_TREE_HASH}" == "${RUNNING_TREE_HASH}" ]] \
    || die "rollback override tree ${OVERRIDE_TREE_HASH:-<missing>} does not match running tree ${RUNNING_TREE_HASH:-<missing>}"
  ROLLBACK_SOURCE="${ROLLBACK_IMAGE_OVERRIDE}"
  echo "!! running image metadata missing; using identity-matched rollback override ${ROLLBACK_SOURCE}" >&2
fi
ROLLBACK_HOLD_TAG="sealai-backend-v2:rollback-hold-${RUNNING_REVISION:0:8}-${ROLLBACK_STAMP}"
preserve_rollback_artifact() {
  docker run --rm --entrypoint python "${ROLLBACK_SOURCE}" \
    -m sealai_v2.config.build_identity verify >/dev/null \
    || die "rollback source failed immutable identity verification: ${ROLLBACK_SOURCE}"
  docker tag "${ROLLBACK_SOURCE}" "${ROLLBACK_HOLD_TAG}"
  ROLLBACK_FROM="$(docker image inspect --format '{{.Id}}' "${ROLLBACK_HOLD_TAG}")"
  [[ "${ROLLBACK_FROM}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || die "rollback source has no immutable image config ID"
  echo ">> rollback artifact preserved: ${ROLLBACK_HOLD_TAG} -> ${ROLLBACK_FROM}"
}
if [[ "${RELEASE_STAGE}" == "candidate" ]]; then
  # A local candidate build can replace the mutable local tag, so preserve its
  # rollback before building. Production uses an immutable pull and waits until
  # the exact RC gate passes before creating any rollback tag.
  preserve_rollback_artifact
fi

# ── 1b. served L1 id (P1.6): the SAME runtime config the container reads. tree_hash binds the CODE
# but not the model, so an .env-only L1 swap would otherwise ship on a stale eval. The container reads
# .env.prod (SEALAI_V2_ prefix); resolve provider/model with the settings.py defaults (provider→openai,
# model→gpt-5.5) — pure config, no models.list() (the gate stays network-free). Read directly from
# .env.prod (the file --env-file feeds the container) rather than the shell env. ──────────────────
SERVED_L1_PROVIDER="$(env_prod SEALAI_V2_L1_PROVIDER)"; SERVED_L1_PROVIDER="${SERVED_L1_PROVIDER:-openai}"
SERVED_L1_MODEL="$(env_prod SEALAI_V2_L1_MODEL)";       SERVED_L1_MODEL="${SERVED_L1_MODEL:-gpt-5.5}"
SERVED_L1="${SERVED_L1_PROVIDER}/${SERVED_L1_MODEL}"
[ -n "${SERVED_L1_PROVIDER}" ] && [ -n "${SERVED_L1_MODEL}" ] || die "could not resolve served L1 from .env.prod"
echo ">> served L1 = ${SERVED_L1}"

# ── 2. prepare immutable candidate (no live state changes) ───────────────────
PREPARED_IMAGE_ID=""
if [[ -n "${BACKEND_IMAGE_REF}" ]]; then
  [[ "${BACKEND_IMAGE_REF}" =~ ^[^@[:space:]]+@sha256:[0-9a-f]{64}$ ]] \
    || die "BACKEND_V2_IMAGE must be pinned as one exact tag@sha256:digest reference"
  echo ">> pulling immutable backend-v2 image ${BACKEND_IMAGE_REF}"
  docker pull "${BACKEND_IMAGE_REF}" >/dev/null
  PREPARED_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${BACKEND_IMAGE_REF}" 2>/dev/null || true)"
  [[ "${PREPARED_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || die "could not resolve the prepared immutable backend image ID"
  REPO_DIGESTS_JSON="$(docker image inspect --format '{{json .RepoDigests}}' "${BACKEND_IMAGE_REF}" 2>/dev/null || true)"
  verify_repo_digest "${BACKEND_IMAGE_REF}" "${REPO_DIGESTS_JSON}" \
    || die "pulled image RepoDigests do not contain the exact Gate-10 registry manifest"
  IMAGE_TREE_HASH="$(docker image inspect --format '{{index .Config.Labels "io.sealai.served-tree-hash"}}' "${BACKEND_IMAGE_REF}" 2>/dev/null || true)"
  IMAGE_REVISION="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "${BACKEND_IMAGE_REF}" 2>/dev/null || true)"
  [[ "${IMAGE_TREE_HASH}" == "${TREE_HASH}" ]] || die "image tree hash ${IMAGE_TREE_HASH:-<missing>} does not match served tree ${TREE_HASH}"
  [[ "${IMAGE_REVISION}" == "${SOURCE_GIT_SHA}" ]] || die "image revision ${IMAGE_REVISION:-<missing>} does not match approved source ${SOURCE_GIT_SHA}"
  /bin/bash -p ops/verify-image-attestations.sh \
    "${BACKEND_IMAGE_REF}" "${SOURCE_GIT_SHA}" ".github/workflows/build-and-push.yml" \
    || die "candidate image provenance or SBOM attestation verification failed"
  PREPARED_IMAGE="${BACKEND_IMAGE_REF}"
else
  echo "!! non-production local candidate has no signed registry attestations" >&2
  echo ">> building ${SERVICE} with GATE_TREE_HASH=${TREE_HASH}"
  "${COMPOSE[@]}" build --build-arg "GATE_TREE_HASH=${TREE_HASH}" --build-arg "SOURCE_GIT_SHA=${SOURCE_GIT_SHA}" "${SERVICE}"
  PREPARED_IMAGE="$(docker image inspect --format '{{.Id}}' "${LOCAL_BACKEND_IMAGE}" 2>/dev/null || true)"
  [[ "${PREPARED_IMAGE}" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || die "could not resolve locally built candidate image"
  PREPARED_IMAGE_ID="${PREPARED_IMAGE}"
fi

echo ">> deriving secret-free runtime behavior profile from candidate image"
RUNTIME_PROFILE_JSON="$("${COMPOSE[@]}" run --rm --no-deps --entrypoint python "${SERVICE}" \
  -m sealai_v2.config.runtime_profile)"
RUNTIME_PROFILE_HASH="$(
  printf '%s' "${RUNTIME_PROFILE_JSON}" | /usr/bin/python3 -I -c '
import hashlib
import json
import sys

value = json.load(sys.stdin)
canonical = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
print(hashlib.sha256(canonical.encode("utf-8")).hexdigest(), end="")
'
)"
[[ "${RUNTIME_PROFILE_HASH}" =~ ^[0-9a-f]{64}$ ]] || die "invalid runtime profile hash: ${RUNTIME_PROFILE_HASH:-<empty>}"
AUTHORITY_EPOCH="$(
  printf '%s' "${RUNTIME_PROFILE_JSON}" | /usr/bin/python3 -I -c '
import json
import re
import sys

value = json.load(sys.stdin)
authority = (value.get("behavior") or {}).get("knowledge_authority_epoch")
if not isinstance(authority, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", authority) is None:
    raise SystemExit(78)
print(authority, end="")
'
)" || {
  [[ "${RELEASE_STAGE}" != "final" ]] \
    || die "production runtime has no canonical knowledge Authority Epoch"
  AUTHORITY_EPOCH=""
}
PROFILE_SERVED_L1="$(
  printf '%s' "${RUNTIME_PROFILE_JSON}" | /usr/bin/python3 -I -c '
import json
import sys

behavior = (json.load(sys.stdin).get("behavior") or {})
provider = (behavior.get("role_providers") or {}).get("l1")
model = behavior.get("l1_model")
if not isinstance(provider, str) or not provider or not isinstance(model, str) or not model:
    raise SystemExit(78)
print(f"{provider}/{model}", end="")
'
)" || die "candidate runtime profile does not contain the served L1 identity"
[[ "${PROFILE_SERVED_L1}" == "${SERVED_L1}" ]] \
  || die "environment-derived and candidate-derived served L1 identities disagree"
echo ">> runtime profile = ${RUNTIME_PROFILE_HASH}"
[[ -z "${AUTHORITY_EPOCH}" ]] || echo ">> Authority Epoch = ${AUTHORITY_EPOCH}"

# ── 3. RELEASE STAGE: candidate defers; final proves ────────────────────────────
if [[ "${RELEASE_STAGE}" == "final" ]]; then
  [[ -f "${PROMOTION_EVIDENCE_FILE}" && ! -L "${PROMOTION_EVIDENCE_FILE}" ]] \
    || die "fixed promotion evidence is missing or symlinked"
  [[ -f "${ROLLBACK_PLAN_FILE}" && ! -L "${ROLLBACK_PLAN_FILE}" ]] \
    || die "fixed rollback plan is missing or symlinked"
  ACTUAL_ROLLBACK_PLAN_SHA256="$(
    /usr/bin/python3 -I -c '
import hashlib
import pathlib
import sys

print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest(), end="")
' "${ROLLBACK_PLAN_FILE}"
  )"
  [[ "${ACTUAL_ROLLBACK_PLAN_SHA256}" == "${APPROVED_ROLLBACK_PLAN_SHA256}" ]] \
    || die "fixed rollback plan does not match the Gate-10 release manifest"
  if ! MATCH="$(
    /usr/bin/python3 -I ops/v2_deploy_gate.py \
      "${RUNS_DIR}" \
      "${TREE_HASH}" \
      "${SERVED_L1}" \
      "${RUNTIME_PROFILE_HASH}" \
      --rc-evidence "${PROMOTION_EVIDENCE_FILE}" \
      --rc-evidence-sha256 "${APPROVED_EVIDENCE_MANIFEST_SHA256}" \
      --candidate-image-digest "${APPROVED_BACKEND_IMAGE_DIGEST}" \
      --candidate-image-config-digest "${PREPARED_IMAGE_ID}" \
      --served-tree-sha256 "${SERVED_TREE_SHA256}" \
      --database-migration-sha256 "${DATABASE_MIGRATION_SHA256}" \
      --authority-epoch "${AUTHORITY_EPOCH}" \
      --source-git-sha "${SOURCE_GIT_SHA}"
  )"; then
    echo "!! refusing FINAL deploy — no complete, final-adjudicated full replay for tree ${TREE_HASH}, L1 ${SERVED_L1}, runtime profile ${RUNTIME_PROFILE_HASH}" >&2
    echo "!! provide a complete, final-adjudicated full replay under this exact production profile; targeted/chained remediation and owner waivers cannot authorize promotion." >&2
    exit 2
  fi
  RUN_LABEL="$(printf '%s' "${MATCH}" | /usr/bin/python3 -I -c 'import json,sys; print(json.load(sys.stdin)["run_label"])')"
  EVAL_GIT_SHA="$(printf '%s' "${MATCH}" | /usr/bin/python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("git_sha") or "")')"
  EVAL_DIRTY="$(printf '%s' "${MATCH}" | /usr/bin/python3 -I -c 'import json,sys; print(str(json.load(sys.stdin).get("dirty")).lower())')"
  EVAL_EVIDENCE_TYPE="$(printf '%s' "${MATCH}" | /usr/bin/python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("evidence_type") or "full_replay")')"
  EVAL_STATUS="passed"
  echo ">> final gate PASS — ${EVAL_EVIDENCE_TYPE} run '${RUN_LABEL}' (eval git ${EVAL_GIT_SHA}, dirty=${EVAL_DIRTY}, L1=${SERVED_L1}, profile=${RUNTIME_PROFILE_HASH})"
  FRONTEND_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "${COMPOSE_FRONTEND_IMAGE}" 2>/dev/null || true)"
  LIVE_FRONTEND_IMAGE_ID="$(docker inspect frontend --format '{{.Image}}' 2>/dev/null || true)"
  [[ "${FRONTEND_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ && \
     "${LIVE_FRONTEND_IMAGE_ID}" == "${FRONTEND_IMAGE_ID}" ]] \
    || die "live frontend exposure is not running the Gate-10-approved image config"
  FRONTEND_REPO_DIGESTS_JSON="$(docker image inspect --format '{{json .RepoDigests}}' "${COMPOSE_FRONTEND_IMAGE}" 2>/dev/null || true)"
  verify_repo_digest "${COMPOSE_FRONTEND_IMAGE}" "${FRONTEND_REPO_DIGESTS_JSON}" \
    || die "live frontend exposure is not backed by the Gate-10-approved registry digest"
  NGINX_MOUNTS_JSON="$(docker inspect nginx --format '{{json .Mounts}}' 2>/dev/null || true)"
  printf '%s' "${NGINX_MOUNTS_JSON}" | /usr/bin/python3 -I -c '
import json
import sys

try:
    mounts = json.load(sys.stdin)
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit(78)
expected = [
    item
    for item in mounts
    if isinstance(item, dict)
    and item.get("Destination") == "/usr/share/nginx/dashboard-releases"
]
if len(expected) != 1 or expected[0].get("Type") != "bind":
    raise SystemExit(78)
if expected[0].get("Source") != "/var/lib/sealai/dashboard-releases":
    raise SystemExit(78)
if expected[0].get("RW") is not False:
    raise SystemExit(78)
' || die "nginx does not expose the fixed read-only Gate-10 dashboard release root"
  echo ">> live frontend Gate-10 image = ${LIVE_FRONTEND_IMAGE_ID} (${APPROVED_FRONTEND_IMAGE_DIGEST})"
  preserve_rollback_artifact
else
  RUN_LABEL="candidate-no-eval-${SOURCE_GIT_SHA:0:8}"
  EVAL_GIT_SHA=""
  EVAL_DIRTY=""
  EVAL_EVIDENCE_TYPE="candidate"
  EVAL_STATUS="pending"
  echo ">> candidate gate PASS — paid eval deferred; deterministic release controls remain active"
fi

# ── 4. rollback rung: promote the artifact preserved before candidate preparation ───────────────
ROLLBACK_TAG="sealai-backend-v2:rollback-pre-${RUN_LABEL}-$(date -u +%Y%m%d-%H%M%S)"
docker tag "${ROLLBACK_HOLD_TAG}" "${ROLLBACK_TAG}"
docker image rm "${ROLLBACK_HOLD_TAG}" >/dev/null 2>&1 || true
echo ">> rollback rung: ${ROLLBACK_TAG} -> ${ROLLBACK_FROM}"

echo ">> creating verified pre-migration backup"
MIGRATION_BACKUP="$(ENV_FILE="${ENV_FILE}" /bin/bash -p ops/backup_v2_database.sh)"
[[ -f "${MIGRATION_BACKUP}" ]] || die "pre-migration backup was not created"
echo ">> pre-migration backup = ${MIGRATION_BACKUP}"

echo ">> applying V2 Alembic migrations with the gated image"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint python "${SERVICE}" \
  -m sealai_v2.db.migrate upgrade
"${COMPOSE[@]}" run --rm --no-deps --entrypoint python "${SERVICE}" \
  -m sealai_v2.db.migrate check

echo ">> reconciling governed knowledge states into Postgres system-of-record"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint python "${SERVICE}" \
  -m sealai_v2.knowledge.bootstrap
echo ">> synchronizing the ledger-derived knowledge index before traffic switch"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint python "${SERVICE}" \
  -m sealai_v2.knowledge.outbox_worker drain-all --batch-size 50

rollback_hint() {
  echo "!! ACTIVATION/SMOKE RED — NOT writing the ledger. Rollback path:" >&2
  echo "   pre-migration database backup: ${MIGRATION_BACKUP:-<not-created>}" >&2
  echo "   BACKEND_V2_IMAGE=${ROLLBACK_TAG:-<not-created>} ${COMPOSE[*]} up -d --no-build --no-deps --force-recreate ${SERVICE} ${WORKER_SERVICE}" >&2
}
smoke_fail() { rollback_hint; exit 1; }

"${COMPOSE[@]}" up -d --no-build --no-deps --force-recreate "${SERVICE}" "${WORKER_SERVICE}"
IMAGE_SHA="$(docker inspect "${SERVICE}" --format '{{.Image}}' 2>/dev/null || true)"
WORKER_IMAGE_SHA="$(docker inspect "${WORKER_SERVICE}" --format '{{.Image}}' 2>/dev/null || true)"
[[ "${IMAGE_SHA}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "!! live ${SERVICE} has no valid immutable image ID" >&2
  smoke_fail
}
[[ "${WORKER_IMAGE_SHA}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "!! live ${WORKER_SERVICE} has no valid immutable image ID" >&2
  smoke_fail
}
[[ "${IMAGE_SHA}" == "${PREPARED_IMAGE_ID}" ]] || {
  echo "!! live ${SERVICE} image ${IMAGE_SHA} is not prepared image ${PREPARED_IMAGE_ID}" >&2
  smoke_fail
}
[[ "${WORKER_IMAGE_SHA}" == "${PREPARED_IMAGE_ID}" ]] || {
  echo "!! live ${WORKER_SERVICE} image ${WORKER_IMAGE_SHA} is not prepared image ${PREPARED_IMAGE_ID}" >&2
  smoke_fail
}
echo ">> live ${SERVICE} image = ${IMAGE_SHA}"
echo ">> live ${WORKER_SERVICE} image = ${WORKER_IMAGE_SHA}"

# ── 5. smoke — RED anywhere → HALT, no ledger, print the rollback path ────────
echo ">> smoke: health"
for i in $(seq 1 30); do
  h="$(docker inspect "${SERVICE}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' 2>/dev/null || true)"
  [ "${h}" = "healthy" ] && break
  [ "${i}" -eq 30 ] && { echo "!! health never reached healthy (last=${h})" >&2; smoke_fail; }
  sleep 2
done
docker exec "${SERVICE}" curl -fsS http://127.0.0.1:8001/health >/dev/null || { echo "!! internal /health failed" >&2; smoke_fail; }
curl -fsS -m 8 https://sealingai.com/api/v2/health >/dev/null || { echo "!! public /api/v2/health failed" >&2; smoke_fail; }

echo ">> smoke: durable outbox worker"
for i in $(seq 1 30); do
  worker_health="$(docker inspect "${WORKER_SERVICE}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' 2>/dev/null || true)"
  [ "${worker_health}" = "healthy" ] && break
  [ "${i}" -eq 30 ] && { echo "!! ${WORKER_SERVICE} is not healthy (last=${worker_health})" >&2; smoke_fail; }
  sleep 2
done
docker exec "${WORKER_SERVICE}" python -m sealai_v2.memory.outbox_daemon --healthcheck || {
  echo "!! outbox worker readiness probe failed" >&2
  smoke_fail
}

echo ">> smoke: immutable image identity"
docker exec "${SERVICE}" python -m sealai_v2.config.build_identity verify >/dev/null || smoke_fail

echo ">> smoke: kern one-shot (PV=50.0 / v=16,755)"
docker exec -i "${SERVICE}" python - <<'PY' || smoke_fail
import sys
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
e = CascadeCalcEngine()
v = {c.calc_id: round(c.value, 3) for c in e.evaluate(params={"d1_mm": 40, "rpm": 8000, "seal_type": "rwdr"}).computed}
pv = {c.calc_id: round(c.value, 3) for c in e.evaluate(params={"p_bar": 10, "v_m_s": 5.0, "seal_type": "hydraulik"}).computed}
ok = abs(v.get("umfangsgeschwindigkeit", 0) - 16.755) < 0.01 and abs(pv.get("pv_wert", 0) - 50.0) < 0.001
print("kern:", v, pv, "OK" if ok else "MISMATCH")
sys.exit(0 if ok else 1)
PY

echo ">> smoke: restart-survival"
docker restart "${SERVICE}" >/dev/null
for i in $(seq 1 30); do
  h="$(docker inspect "${SERVICE}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' 2>/dev/null || true)"
  [ "${h}" = "healthy" ] && break
  [ "${i}" -eq 30 ] && { echo "!! did not recover after restart (last=${h})" >&2; smoke_fail; }
  sleep 2
done

# ── 6. ledger (machine-readable commit→deploy index) + GOVERNANCE_LOG paste ───
LINE="$(/usr/bin/python3 -I - "$TS" "$TREE_HASH" "$RUN_LABEL" "$IMAGE_SHA" "$SOURCE_GIT_SHA" "$GATE_CONTROL_GIT_SHA" "$ROLLBACK_FROM" "$SERVED_L1" "$BACKEND_IMAGE_REF" "$RUNTIME_PROFILE_HASH" "$MIGRATION_BACKUP" "$RELEASE_STAGE" "$EVAL_STATUS" "$DATABASE_MIGRATION_SHA256" "${AUTHORITY_EPOCH:-}" "$APPROVED_EVIDENCE_MANIFEST_SHA256" "$PREPARED_IMAGE_ID" <<'PY'
import json, sys
ts, tree_hash, run_label, image_sha, source_git_sha, gate_control_git_sha, rollback_from, served_l1, backend_image, runtime_profile_hash, migration_backup, release_stage, eval_status, database_migration_sha256, authority_epoch, promotion_evidence_sha256, image_config_digest = sys.argv[1:18]
print(json.dumps({
    "ts": ts, "tree_hash": tree_hash, "run_label": run_label,
    "image_sha": image_sha, "git_sha": source_git_sha,
    "gate_control_git_sha": gate_control_git_sha,
    "dirty": False, "rollback_from": rollback_from,
    "l1": served_l1, "backend_image": backend_image or None,
    "runtime_profile_hash": runtime_profile_hash,
    "pre_migration_backup": migration_backup,
    "release_stage": release_stage,
    "eval_status": eval_status,
    "database_migration_sha256": database_migration_sha256,
    "authority_epoch": authority_epoch or None,
    "promotion_evidence_sha256": promotion_evidence_sha256,
    "image_config_digest": image_config_digest,
}))
PY
)"
printf '%s\n' "${LINE}" >> "${LEDGER}"
echo ">> ledger appended: ${LEDGER}"

if [[ "${RELEASE_STAGE}" == "final" ]]; then
  RELEASE_EVIDENCE="Validated by complete non-provisional eval-REPLAY \`${RUN_LABEL}\` (eval git \`${EVAL_GIT_SHA}\`, source \`${SOURCE_GIT_SHA}\`, gate-control \`${GATE_CONTROL_GIT_SHA}\`, dirty=false); all gated axes Schranken-quota(final)=1.000."
else
  RELEASE_EVIDENCE="Live candidate only. Paid eval-REPLAY intentionally deferred (eval_status=pending); this deployment is not final-release evidence."
fi

cat <<EOF

================ GOVERNANCE_LOG paste-block (owner-authored prose) ================
## ${TS} — V2 ${RELEASE_STAGE} deploy: \`backend-v2\` promotion via ops/release-backend-v2.sh (run ${RUN_LABEL})

**Release stage: ${RELEASE_STAGE}** — tree_hash \`${TREE_HASH}\` + L1 \`${SERVED_L1}\` + runtime profile \`${RUNTIME_PROFILE_HASH}\`.
${RELEASE_EVIDENCE}
- approved source commit = \`${SOURCE_GIT_SHA}\`; dedicated Gate-10 control commit = \`${GATE_CONTROL_GIT_SHA}\`
- new live \`sealai-backend-v2:latest\` = \`${IMAGE_SHA}\`
- promoted image ref = \`${BACKEND_IMAGE_REF:-local-build}\`
- rollback rung (read from the daemon) = \`${ROLLBACK_FROM}\`, tagged \`${ROLLBACK_TAG}\`
- smoke GREEN: health internal+public; kern one-shot (v=16,755 / PV=50.0); restart-survival.
- worker GREEN: process running and outbox daemon importable.
- ledger: ${LEDGER}
==================================================================================
EOF
echo ">> Done."
