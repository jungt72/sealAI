#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ops/release-backend-v2.sh — THE ONLY sanctioned V2 (`backend-v2`) deploy.
#
# Closes the bypass found in the deploy-gate audit: the V1 deploy-gate hook only
# watches ops/release-backend.sh and checks V1 sentinels, so a raw
# `docker compose … --profile v2 up --build backend-v2` shipped UNGATED. This
# wrapper supports two explicit release stages and bakes a start-time marker so
# a raw build refuses to run: `candidate` is restricted to explicitly declared
# non-production environments; `final` binds production to an adjudicated replay.
#
# Gate chain:
#   1. TREE_HASH = ops/tree-hash.sh backend/sealai_v2   (served-runtime content)
#   2. Build/pull the candidate and derive its secret-free runtime-profile hash.
#   3. final only: ops/v2_deploy_gate.py → an adjudicated run with that exact
#      tree, L1 and runtime profile; all gated axes are clean.
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

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

SERVICE="backend-v2"
WORKER_SERVICE="backend-v2-worker"
RUNS_DIR="backend/sealai_v2/eval/runs"
COMPOSE=(docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml --profile v2)
BACKEND_IMAGE_REF="${BACKEND_V2_IMAGE:-}"
LOCAL_BACKEND_IMAGE="sealai-backend-v2:local"
ROLLBACK_IMAGE_OVERRIDE="${SEALAI_V2_ROLLBACK_IMAGE:-}"

die() { echo "release-backend-v2: $*" >&2; exit 1; }
env_prod() { sed -n "s/^$1=//p" .env.prod | tail -n1; }

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

# Production is an artifact promotion. Never deploy bytes from an uncommitted
# worktree because the content hash would no longer describe the served code.
if [[ -n "$(git status --porcelain)" ]]; then
  die "worktree is dirty; commit and deploy the exact reviewed commit"
fi
GIT_SHA_FULL="$(git rev-parse HEAD)"
RUNTIME_DIR="${SEALAI_RUNTIME_DIR:-${REPO_ROOT}/.runtime}"
LEDGER="${RUNTIME_DIR}/deploy-ledger.jsonl"
mkdir -p "${RUNTIME_DIR}"

# ── 1. served-runtime content hash (single source of truth) ──────────────────
TREE_HASH="$(bash ops/tree-hash.sh)"
[ -n "${TREE_HASH}" ] || die "empty tree_hash from ops/tree-hash.sh"
echo ">> served tree_hash = ${TREE_HASH}"

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
docker run --rm --entrypoint python "${ROLLBACK_SOURCE}" \
  -m sealai_v2.config.build_identity verify >/dev/null \
  || die "rollback source failed immutable identity verification: ${ROLLBACK_SOURCE}"
ROLLBACK_HOLD_TAG="sealai-backend-v2:rollback-hold-${RUNNING_REVISION:0:8}-${ROLLBACK_STAMP}"
docker tag "${ROLLBACK_SOURCE}" "${ROLLBACK_HOLD_TAG}"
ROLLBACK_FROM="$(docker image inspect --format '{{.Id}}' "${ROLLBACK_HOLD_TAG}")"
echo ">> rollback artifact preserved before build: ${ROLLBACK_HOLD_TAG} -> ${ROLLBACK_FROM}"

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
if [[ -n "${BACKEND_IMAGE_REF}" ]]; then
  [[ "${BACKEND_IMAGE_REF}" == *@sha256:* ]] || die "BACKEND_V2_IMAGE must be pinned as tag@sha256:digest"
  echo ">> pulling immutable backend-v2 image ${BACKEND_IMAGE_REF}"
  docker pull "${BACKEND_IMAGE_REF}" >/dev/null
  IMAGE_TREE_HASH="$(docker image inspect --format '{{index .Config.Labels "io.sealai.served-tree-hash"}}' "${BACKEND_IMAGE_REF}" 2>/dev/null || true)"
  IMAGE_REVISION="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "${BACKEND_IMAGE_REF}" 2>/dev/null || true)"
  [[ "${IMAGE_TREE_HASH}" == "${TREE_HASH}" ]] || die "image tree hash ${IMAGE_TREE_HASH:-<missing>} does not match served tree ${TREE_HASH}"
  [[ "${IMAGE_REVISION}" == "${GIT_SHA_FULL}" ]] || die "image revision ${IMAGE_REVISION:-<missing>} does not match checkout ${GIT_SHA_FULL}"
  PREPARED_IMAGE="${BACKEND_IMAGE_REF}"
else
  echo ">> building ${SERVICE} with GATE_TREE_HASH=${TREE_HASH}"
  "${COMPOSE[@]}" build --build-arg "GATE_TREE_HASH=${TREE_HASH}" --build-arg "SOURCE_GIT_SHA=${GIT_SHA_FULL}" "${SERVICE}"
  PREPARED_IMAGE="$(docker image inspect --format '{{.Id}}' "${LOCAL_BACKEND_IMAGE}" 2>/dev/null || true)"
  [[ -n "${PREPARED_IMAGE}" ]] || die "could not resolve locally built candidate image"
fi

echo ">> deriving secret-free runtime behavior profile from candidate image"
RUNTIME_PROFILE_HASH="$("${COMPOSE[@]}" run --rm --no-deps --entrypoint python "${SERVICE}" \
  -m sealai_v2.config.runtime_profile --hash)"
[[ "${RUNTIME_PROFILE_HASH}" =~ ^[0-9a-f]{64}$ ]] || die "invalid runtime profile hash: ${RUNTIME_PROFILE_HASH:-<empty>}"
echo ">> runtime profile = ${RUNTIME_PROFILE_HASH}"

# ── 3. RELEASE STAGE: candidate defers paid eval; final requires it ──────────
if [[ "${RELEASE_STAGE}" == "final" ]]; then
  if ! MATCH="$(python ops/v2_deploy_gate.py "${RUNS_DIR}" "${TREE_HASH}" "${SERVED_L1}" "${RUNTIME_PROFILE_HASH}")"; then
    echo "!! refusing FINAL deploy — no adjudicated eval-REPLAY for tree ${TREE_HASH}, L1 ${SERVED_L1}, runtime profile ${RUNTIME_PROFILE_HASH}" >&2
    echo "!! run and adjudicate the complete eval-REPLAY under this exact production profile, then retry." >&2
    exit 2
  fi
  RUN_LABEL="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(json.load(sys.stdin)["run_label"])')"
  EVAL_GIT_SHA="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(json.load(sys.stdin).get("git_sha") or "")')"
  EVAL_DIRTY="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(str(json.load(sys.stdin).get("dirty")).lower())')"
  EVAL_STATUS="passed"
  echo ">> final gate PASS — run '${RUN_LABEL}' (eval git ${EVAL_GIT_SHA}, dirty=${EVAL_DIRTY}, L1=${SERVED_L1}, profile=${RUNTIME_PROFILE_HASH})"
else
  RUN_LABEL="candidate-no-eval-${GIT_SHA_FULL:0:8}"
  EVAL_GIT_SHA=""
  EVAL_DIRTY=""
  EVAL_STATUS="pending"
  echo ">> candidate gate PASS — paid eval deferred; deterministic release controls remain active"
fi

# ── 4. rollback rung: promote the artifact preserved before candidate preparation ───────────────
ROLLBACK_TAG="sealai-backend-v2:rollback-pre-${RUN_LABEL}-$(date -u +%Y%m%d-%H%M%S)"
docker tag "${ROLLBACK_HOLD_TAG}" "${ROLLBACK_TAG}"
docker image rm "${ROLLBACK_HOLD_TAG}" >/dev/null 2>&1 || true
echo ">> rollback rung: ${ROLLBACK_TAG} -> ${ROLLBACK_FROM}"

echo ">> creating verified pre-migration backup"
MIGRATION_BACKUP="$(ENV_FILE="${REPO_ROOT}/.env.prod" bash ops/backup_v2_database.sh)"
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
  -m sealai_v2.knowledge.outbox_worker drain-all --batch-size 100

"${COMPOSE[@]}" up -d --no-build --no-deps --force-recreate "${SERVICE}" "${WORKER_SERVICE}"
IMAGE_SHA="$(docker inspect "${SERVICE}" --format '{{.Image}}')"
echo ">> live ${SERVICE} image = ${IMAGE_SHA}"

# ── 5. smoke — RED anywhere → HALT, no ledger, print the rollback path ────────
rollback_hint() {
  echo "!! SMOKE RED — NOT writing the ledger. Rollback path:" >&2
  echo "   pre-migration database backup: ${MIGRATION_BACKUP:-<not-created>}" >&2
  echo "   BACKEND_V2_IMAGE=${ROLLBACK_TAG} ${COMPOSE[*]} up -d --no-build --no-deps --force-recreate ${SERVICE} ${WORKER_SERVICE}" >&2
}
smoke_fail() { rollback_hint; exit 1; }

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
LINE="$(python - "$TS" "$TREE_HASH" "$RUN_LABEL" "$IMAGE_SHA" "$GIT_SHA_FULL" "$ROLLBACK_FROM" "$SERVED_L1" "$BACKEND_IMAGE_REF" "$RUNTIME_PROFILE_HASH" "$MIGRATION_BACKUP" "$RELEASE_STAGE" "$EVAL_STATUS" <<'PY'
import json, sys
ts, tree_hash, run_label, image_sha, git_sha, rollback_from, served_l1, backend_image, runtime_profile_hash, migration_backup, release_stage, eval_status = sys.argv[1:13]
print(json.dumps({
    "ts": ts, "tree_hash": tree_hash, "run_label": run_label,
    "image_sha": image_sha, "git_sha": git_sha,
    "dirty": False, "rollback_from": rollback_from,
    "l1": served_l1, "backend_image": backend_image or None,
    "runtime_profile_hash": runtime_profile_hash,
    "pre_migration_backup": migration_backup,
    "release_stage": release_stage,
    "eval_status": eval_status,
}))
PY
)"
printf '%s\n' "${LINE}" >> "${LEDGER}"
echo ">> ledger appended: ${LEDGER}"

if [[ "${RELEASE_STAGE}" == "final" ]]; then
  RELEASE_EVIDENCE="Validated by adjudicated eval-REPLAY \`${RUN_LABEL}\` (eval git \`${EVAL_GIT_SHA}\`, checkout \`${GIT_SHA_FULL}\`, dirty=false); all gated axes Schranken-quota(final)=1.000."
else
  RELEASE_EVIDENCE="Live candidate only. Paid eval-REPLAY intentionally deferred (eval_status=pending); this deployment is not final-release evidence."
fi

cat <<EOF

================ GOVERNANCE_LOG paste-block (owner-authored prose) ================
## ${TS} — V2 ${RELEASE_STAGE} deploy: \`backend-v2\` promotion via ops/release-backend-v2.sh (run ${RUN_LABEL})

**Release stage: ${RELEASE_STAGE}** — tree_hash \`${TREE_HASH}\` + L1 \`${SERVED_L1}\` + runtime profile \`${RUNTIME_PROFILE_HASH}\`.
${RELEASE_EVIDENCE}
- new live \`sealai-backend-v2:latest\` = \`${IMAGE_SHA}\`
- promoted image ref = \`${BACKEND_IMAGE_REF:-local-build}\`
- rollback rung (read from the daemon) = \`${ROLLBACK_FROM}\`, tagged \`${ROLLBACK_TAG}\`
- smoke GREEN: health internal+public; kern one-shot (v=16,755 / PV=50.0); restart-survival.
- worker GREEN: process running and outbox daemon importable.
- ledger: ${LEDGER}
==================================================================================
EOF
echo ">> Done."
