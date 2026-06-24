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
#   2. ops/v2_deploy_gate.py → an adjudicated run with that tree_hash, all gated
#      axes schranken_quota_final == 1.0; else exit 2 (refuse — no deploy).
#   3. Rollback rung: tag the RUNNING image (read from the daemon) before the flip.
#   4. Build with --build-arg GATE_TREE_HASH=$TREE_HASH → recreate only backend-v2.
#   5. Smoke: health (internal+public) · kern one-shot (PV=50.0 / v=16,755) ·
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
RUNS_DIR="backend/sealai_v2/eval/runs"
LEDGER="ops/deploy-ledger.jsonl"
COMPOSE=(docker compose --env-file .env.prod -f docker-compose.yml -f docker-compose.deploy.yml --profile v2)

die() { echo "release-backend-v2: $*" >&2; exit 1; }

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

# ── 2. GATE: refuse unless an adjudicated eval-REPLAY validates this exact tree AND L1 (P1.6) ─
if ! MATCH="$(python ops/v2_deploy_gate.py "${RUNS_DIR}" "${TREE_HASH}" "${SERVED_L1}")"; then
  echo "!! refusing deploy — no adjudicated eval-REPLAY for tree ${TREE_HASH} + L1 ${SERVED_L1}" >&2
  echo "!! run + adjudicate an eval-REPLAY for this exact served tree AND L1, then retry." >&2
  exit 2
fi
RUN_LABEL="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(json.load(sys.stdin)["run_label"])')"
GIT_SHA="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(json.load(sys.stdin).get("git_sha") or "")')"
DIRTY="$(printf '%s' "${MATCH}" | python -c 'import json,sys; print(str(json.load(sys.stdin).get("dirty")).lower())')"
echo ">> gate PASS — validated by run '${RUN_LABEL}' (git ${GIT_SHA}, dirty=${DIRTY}, L1=${SERVED_L1})"

# ── 3. rollback rung: tag the RUNNING image (from the daemon, never memory) ───
ROLLBACK_FROM="$(docker inspect "${SERVICE}" --format '{{.Image}}' 2>/dev/null || true)"
[ -n "${ROLLBACK_FROM}" ] || die "cannot read running ${SERVICE} image from the daemon"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROLLBACK_TAG="sealai-backend-v2:rollback-pre-${RUN_LABEL}-$(date -u +%Y%m%d-%H%M%S)"
docker tag "${ROLLBACK_FROM}" "${ROLLBACK_TAG}"
echo ">> rollback rung: ${ROLLBACK_TAG} -> ${ROLLBACK_FROM}"

# ── 4. build (marker baked in) + recreate ONLY backend-v2 ────────────────────
echo ">> building ${SERVICE} with GATE_TREE_HASH=${TREE_HASH}"
"${COMPOSE[@]}" build --build-arg "GATE_TREE_HASH=${TREE_HASH}" "${SERVICE}"
"${COMPOSE[@]}" up -d --no-deps --force-recreate "${SERVICE}"
IMAGE_SHA="$(docker inspect "${SERVICE}" --format '{{.Image}}')"
echo ">> live ${SERVICE} image = ${IMAGE_SHA}"

# ── 5. smoke — RED anywhere → HALT, no ledger, print the rollback path ────────
rollback_hint() {
  echo "!! SMOKE RED — NOT writing the ledger. Rollback path:" >&2
  echo "   docker tag ${ROLLBACK_TAG} sealai-backend-v2:latest && \\" >&2
  echo "   ${COMPOSE[*]} up -d --no-deps --force-recreate ${SERVICE}" >&2
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
LINE="$(python - "$TS" "$TREE_HASH" "$RUN_LABEL" "$IMAGE_SHA" "$GIT_SHA" "$DIRTY" "$ROLLBACK_FROM" "$SERVED_L1" <<'PY'
import json, sys
ts, tree_hash, run_label, image_sha, git_sha, dirty, rollback_from, served_l1 = sys.argv[1:9]
print(json.dumps({
    "ts": ts, "tree_hash": tree_hash, "run_label": run_label,
    "image_sha": image_sha, "git_sha": git_sha,
    "dirty": dirty == "true", "rollback_from": rollback_from,
    "l1": served_l1,
}))
PY
)"
printf '%s\n' "${LINE}" >> "${LEDGER}"
echo ">> ledger appended: ${LEDGER}"

cat <<EOF

================ GOVERNANCE_LOG paste-block (owner-authored prose) ================
## ${TS} — V2 PROD deploy: \`backend-v2\` rebuild — gated via ops/release-backend-v2.sh (run ${RUN_LABEL})

**Gated deploy** — tree_hash \`${TREE_HASH}\` + L1 \`${SERVED_L1}\` validated by adjudicated
eval-REPLAY \`${RUN_LABEL}\` (git \`${GIT_SHA}\`, dirty=${DIRTY}); all gated axes Schranken-quota(final)=1.000.
- new live \`sealai-backend-v2:latest\` = \`${IMAGE_SHA}\`
- rollback rung (read from the daemon) = \`${ROLLBACK_FROM}\`, tagged \`${ROLLBACK_TAG}\`
- smoke GREEN: health internal+public; kern one-shot (v=16,755 / PV=50.0); restart-survival.
- ledger: ${LEDGER}
==================================================================================
EOF
echo ">> Done."
