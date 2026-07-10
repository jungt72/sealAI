#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ops/release-backend-v2.sh — THE ONLY sanctioned V2 (`backend-v2`) deploy.
#
# Closes the bypass found in the deploy-gate audit: the V1 deploy-gate hook only
# watches ops/release-backend.sh and checks V1 sentinels, so a raw
# `docker compose … --profile v2 up --build backend-v2` shipped UNGATED. This
# wrapper binds the deploy to an adjudicated eval-REPLAY of the EXACT served tree
# and bakes a start-time marker so a raw build refuses to run.
#
# Gate chain:
#   1. TREE_HASH = ops/tree-hash.sh backend/sealai_v2   (served-runtime content)
#   2. Build/pull the candidate and derive its secret-free runtime-profile hash.
#   3. ops/v2_deploy_gate.py → an adjudicated run with that exact tree, L1 and
#      runtime profile; all gated axes schranken_quota_final == 1.0.
#   4. Rollback rung, verified pre-migration backup and Alembic migration,
#      then recreate backend-v2 + its durable worker from the same image.
#   5. Smoke: health (internal+public) · worker · kern one-shot (PV=50.0 / v=16,755) ·
#      restart-survival. RED at any point → HALT, NO ledger line, print rollback.
#   6. Ledger: append ops/deploy-ledger.jsonl (machine-readable commit→deploy
#      index) + print a ready GOVERNANCE_LOG paste-block (prose stays owner-authored).
#
# This script is a DEPLOY: do not run it as part of a build/review. Only the gate
# logic (step 2, ops/v2_deploy_gate.py) is unit-tested offline.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

SERVICE="backend-v2"
WORKER_SERVICE="backend-v2-worker"
RUNS_DIR="backend/sealai_v2/eval/runs"
COMPOSE=(docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml --profile v2)
BACKEND_IMAGE_REF="${BACKEND_V2_IMAGE:-}"

die() { echo "release-backend-v2: $*" >&2; exit 1; }

# Production is an artifact promotion. Never deploy bytes from an uncommitted
# worktree because the eval tree hash would no longer describe the served code.
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

# ── 1b. served L1 id (P1.6): the SAME runtime config the container reads. tree_hash binds the CODE
# but not the model, so an .env-only L1 swap would otherwise ship on a stale eval. The container reads
# .env.prod (SEALAI_V2_ prefix); resolve provider/model with the settings.py defaults (provider→openai,
# model→gpt-5.1) — pure config, no models.list() (the gate stays network-free). Read directly from
# .env.prod (the file --env-file feeds the container) rather than the shell env. ──────────────────
env_prod() { sed -n "s/^$1=//p" .env.prod | tail -n1; }
SERVED_L1_PROVIDER="$(env_prod SEALAI_V2_L1_PROVIDER)"; SERVED_L1_PROVIDER="${SERVED_L1_PROVIDER:-openai}"
SERVED_L1_MODEL="$(env_prod SEALAI_V2_L1_MODEL)";       SERVED_L1_MODEL="${SERVED_L1_MODEL:-gpt-5.1}"
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
  PREPARED_IMAGE="$("${COMPOSE[@]}" images -q "${SERVICE}" | head -n1)"
  [[ -n "${PREPARED_IMAGE}" ]] || die "could not resolve locally built candidate image"
fi

echo ">> deriving secret-free runtime behavior profile from candidate image"
RUNTIME_PROFILE_HASH="$(docker run --rm --env-file .env.prod --entrypoint python "${PREPARED_IMAGE}" \
  -m sealai_v2.config.runtime_profile --hash)"
[[ "${RUNTIME_PROFILE_HASH}" =~ ^[0-9a-f]{64}$ ]] || die "invalid runtime profile hash: ${RUNTIME_PROFILE_HASH:-<empty>}"
echo ">> runtime profile = ${RUNTIME_PROFILE_HASH}"

# ── 3. GATE: exact tree + L1 + runtime profile require adjudication ──────────
if ! MATCH="$(python ops/v2_deploy_gate.py "${RUNS_DIR}" "${TREE_HASH}" "${SERVED_L1}" "${RUNTIME_PROFILE_HASH}")"; then
  echo "!! refusing deploy — no adjudicated eval-REPLAY for tree ${TREE_HASH}, L1 ${SERVED_L1}, runtime profile ${RUNTIME_PROFILE_HASH}" >&2
  echo "!! run and adjudicate an eval-REPLAY under this exact production profile, then retry." >&2
  exit 2
fi
RUN_LABEL="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(json.load(sys.stdin)["run_label"])')"
EVAL_GIT_SHA="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(json.load(sys.stdin).get("git_sha") or "")')"
EVAL_DIRTY="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(str(json.load(sys.stdin).get("dirty")).lower())')"
echo ">> gate PASS — run '${RUN_LABEL}' (eval git ${EVAL_GIT_SHA}, dirty=${EVAL_DIRTY}, L1=${SERVED_L1}, profile=${RUNTIME_PROFILE_HASH})"

# ── 4. rollback rung: tag the RUNNING image (from the daemon, never memory) ───
ROLLBACK_FROM="$(docker inspect "${SERVICE}" --format '{{.Image}}' 2>/dev/null || true)"
[ -n "${ROLLBACK_FROM}" ] || die "cannot read running ${SERVICE} image from the daemon"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROLLBACK_TAG="sealai-backend-v2:rollback-pre-${RUN_LABEL}-$(date -u +%Y%m%d-%H%M%S)"
docker tag "${ROLLBACK_FROM}" "${ROLLBACK_TAG}"
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

"${COMPOSE[@]}" up -d --no-build --no-deps --force-recreate "${SERVICE}" "${WORKER_SERVICE}"
IMAGE_SHA="$(docker inspect "${SERVICE}" --format '{{.Image}}')"
echo ">> live ${SERVICE} image = ${IMAGE_SHA}"

# ── 5. smoke — RED anywhere → HALT, no ledger, print the rollback path ────────
rollback_hint() {
  echo "!! SMOKE RED — NOT writing the ledger. Rollback path:" >&2
  echo "   pre-migration database backup: ${MIGRATION_BACKUP:-<not-created>}" >&2
  echo "   docker tag ${ROLLBACK_TAG} sealai-backend-v2:latest && \\" >&2
  echo "   ${COMPOSE[*]} up -d --no-build --no-deps --force-recreate ${SERVICE} ${WORKER_SERVICE}" >&2
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
LINE="$(python - "$TS" "$TREE_HASH" "$RUN_LABEL" "$IMAGE_SHA" "$GIT_SHA_FULL" "$ROLLBACK_FROM" "$SERVED_L1" "$BACKEND_IMAGE_REF" "$RUNTIME_PROFILE_HASH" "$MIGRATION_BACKUP" <<'PY'
import json, sys
ts, tree_hash, run_label, image_sha, git_sha, rollback_from, served_l1, backend_image, runtime_profile_hash, migration_backup = sys.argv[1:11]
print(json.dumps({
    "ts": ts, "tree_hash": tree_hash, "run_label": run_label,
    "image_sha": image_sha, "git_sha": git_sha,
    "dirty": False, "rollback_from": rollback_from,
    "l1": served_l1, "backend_image": backend_image or None,
    "runtime_profile_hash": runtime_profile_hash,
    "pre_migration_backup": migration_backup,
}))
PY
)"
printf '%s\n' "${LINE}" >> "${LEDGER}"
echo ">> ledger appended: ${LEDGER}"

cat <<EOF

================ GOVERNANCE_LOG paste-block (owner-authored prose) ================
## ${TS} — V2 PROD deploy: \`backend-v2\` promotion — gated via ops/release-backend-v2.sh (run ${RUN_LABEL})

**Gated deploy** — tree_hash \`${TREE_HASH}\` + L1 \`${SERVED_L1}\` + runtime profile
\`${RUNTIME_PROFILE_HASH}\` validated by adjudicated
eval-REPLAY \`${RUN_LABEL}\` (eval git \`${EVAL_GIT_SHA}\`, checkout \`${GIT_SHA_FULL}\`, dirty=false); all gated axes Schranken-quota(final)=1.000.
- new live \`sealai-backend-v2:latest\` = \`${IMAGE_SHA}\`
- promoted image ref = \`${BACKEND_IMAGE_REF:-local-build}\`
- rollback rung (read from the daemon) = \`${ROLLBACK_FROM}\`, tagged \`${ROLLBACK_TAG}\`
- smoke GREEN: health internal+public; kern one-shot (v=16,755 / PV=50.0); restart-survival.
- worker GREEN: process running and outbox daemon importable.
- ledger: ${LEDGER}
==================================================================================
EOF
echo ">> Done."
