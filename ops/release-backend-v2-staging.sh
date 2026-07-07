#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ops/release-backend-v2-staging.sh — THE sanctioned `backend-v2-staging` deploy.
#
# Mirrors ops/release-backend-v2.sh's discipline (tree-hash gate marker, rollback
# rung from the running daemon, build+recreate ONLY the one service, smoke,
# ledger) for the staging stack under ops/staging/ — originally built for the
# V1->V2 cutover validation (docs/ops/RUNBOOK_V2_CUTOVER.md Phase 2, completed
# 2026-06-10) and reused here, by explicit owner direction, as the staging target
# for LangGraph-suitability-audit feature validation (route_optimization_enabled /
# route_prompt_families_enabled).
#
# Differences from the prod script, all load-bearing:
#   - Separate compose file (ops/staging/docker-compose.staging.yml, project
#     name "sealai-staging"), NOT docker-compose.deploy.yml. This script never
#     touches the prod compose files.
#   - `--env-file .env.prod` is passed to `docker compose` ONLY so Compose can
#     substitute `${OPENAI_API_KEY}` (staging's compose hardcodes everything
#     else directly, no other .env indirection) -- this script itself never
#     reads/prints the file's contents, matching every other backend-v2 script.
#   - backend-v2-staging publishes NO host port (this host's firewall drops
#     host->container traffic on freshly created bridges -- documented finding,
#     RUNBOOK_V2_CUTOVER.md Phase 3 Step 2). Health is checked INTERNALLY via
#     `docker exec ... curl 127.0.0.1:8001/health` only -- no public URL check.
#     A separate, OWNER-run `BASE_URL=https://sealingai.com:8443 ops/smoke-v2.sh`
#     remains available for the full (incl. nginx-staging + authed) picture --
#     out of scope for this script, which only asserts backend-v2-staging's own
#     correctness.
#   - Blast radius is exactly backend-v2-staging: nginx-staging is never
#     recreated, restarted, or reconfigured by this script.
#   - Ledger is a SEPARATE file (ops/deploy-ledger-staging.jsonl) -- kept apart
#     from prod's compliance ledger.
#
# Gate chain (same shape as prod):
#   1. TREE_HASH = ops/tree-hash.sh (served-runtime content of backend/sealai_v2)
#   2. No adjudicated-eval gate for staging (never existed for prod either in its
#      current owner-disabled state) -- explicit no-eval label, same as prod.
#   3. Rollback rung: tag the RUNNING backend-v2-staging image before rebuild.
#   4. Build with --build-arg GATE_TREE_HASH=$TREE_HASH (the image's start-time
#      TEETH, backend/docker-entrypoint-v2.sh, refuses to start without it) ->
#      recreate ONLY backend-v2-staging.
#   5. Smoke: internal health · kern one-shot (PV=50.0 / v=16,755) ·
#      restart-survival. RED anywhere -> HALT, NO ledger line, print rollback.
#   6. Ledger: append ops/deploy-ledger-staging.jsonl + print a ready
#      GOVERNANCE_LOG paste-block (prose stays owner-authored).
#
# This script is a DEPLOY: do not run it as part of a build/review.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

SERVICE="backend-v2-staging"
LEDGER="ops/deploy-ledger-staging.jsonl"
COMPOSE=(docker compose --env-file .env.prod -f ops/staging/docker-compose.staging.yml --profile v2)

die() { echo "release-backend-v2-staging: $*" >&2; exit 1; }

# ── 1. served-runtime content hash (single source of truth) ──────────────────
TREE_HASH="$(bash ops/tree-hash.sh)"
[ -n "${TREE_HASH}" ] || die "empty tree_hash from ops/tree-hash.sh"
echo ">> served tree_hash = ${TREE_HASH}"

# ── 1b. served L1 id — staging's compose sets NO SEALAI_V2_L1_* override, so the
# container runs on config/settings.py's Python defaults (provider=openai,
# l1_model=gpt-5.1). Reported for the ledger/paste-block only, not gated.
SERVED_L1="openai/gpt-5.1 (Settings defaults — staging compose sets no override)"
echo ">> served L1 = ${SERVED_L1}"

# ── 2. No adjudicated-eval gate for staging (mirrors prod's current
# owner-authorized no-eval state; staging has never had one). ─────────────────
RUN_LABEL="no-eval-staging-$(git rev-parse --short HEAD 2>/dev/null || echo manual)"
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo '')"
DIRTY="$(test -n "$(git status --porcelain 2>/dev/null)" && echo true || echo false)"
echo ">> ⚠️  STAGING deploy, no eval-REPLAY gate — tree ${TREE_HASH} (L1=${SERVED_L1}, git=${GIT_SHA}, dirty=${DIRTY})"

# ── 3. rollback rung: tag the RUNNING image (from the daemon, never memory) ───
ROLLBACK_FROM="$(docker inspect "${SERVICE}" --format '{{.Image}}' 2>/dev/null || true)"
[ -n "${ROLLBACK_FROM}" ] || die "cannot read running ${SERVICE} image from the daemon"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ROLLBACK_TAG="sealai-backend-v2-staging:rollback-pre-${RUN_LABEL}-$(date -u +%Y%m%d-%H%M%S)"
docker tag "${ROLLBACK_FROM}" "${ROLLBACK_TAG}"
echo ">> rollback rung: ${ROLLBACK_TAG} -> ${ROLLBACK_FROM}"

# ── 4. build (marker baked in) + recreate ONLY backend-v2-staging ─────────────
echo ">> building ${SERVICE} with GATE_TREE_HASH=${TREE_HASH}"
"${COMPOSE[@]}" build --build-arg "GATE_TREE_HASH=${TREE_HASH}" "${SERVICE}"
"${COMPOSE[@]}" up -d --no-deps --force-recreate "${SERVICE}"
IMAGE_SHA="$(docker inspect "${SERVICE}" --format '{{.Image}}')"
echo ">> live ${SERVICE} image = ${IMAGE_SHA}"

# ── 5. smoke — RED anywhere → HALT, no ledger, print the rollback path ────────
rollback_hint() {
  echo "!! SMOKE RED — NOT writing the ledger. Rollback path:" >&2
  echo "   docker tag ${ROLLBACK_TAG} sealai-backend-v2-staging:latest && \\" >&2
  echo "   ${COMPOSE[*]} up -d --no-deps --force-recreate ${SERVICE}" >&2
}
smoke_fail() { rollback_hint; exit 1; }

echo ">> smoke: health (internal only — no host port publish on this host, see header)"
for i in $(seq 1 30); do
  h="$(docker inspect "${SERVICE}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' 2>/dev/null || true)"
  [ "${h}" = "healthy" ] && break
  [ "${i}" -eq 30 ] && { echo "!! health never reached healthy (last=${h})" >&2; smoke_fail; }
  sleep 2
done
docker exec "${SERVICE}" curl -fsS http://127.0.0.1:8001/health >/dev/null || { echo "!! internal /health failed" >&2; smoke_fail; }

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

# ── 6. ledger (machine-readable commit→deploy index, staging-only file) ───────
LINE="$(python3 - "$TS" "$TREE_HASH" "$RUN_LABEL" "$IMAGE_SHA" "$GIT_SHA" "$DIRTY" "$ROLLBACK_FROM" "$SERVED_L1" <<'PY'
import json, sys
ts, tree_hash, run_label, image_sha, git_sha, dirty, rollback_from, served_l1 = sys.argv[1:9]
print(json.dumps({
    "ts": ts, "tree_hash": tree_hash, "run_label": run_label,
    "image_sha": image_sha, "git_sha": git_sha,
    "dirty": dirty == "true", "rollback_from": rollback_from,
    "l1": served_l1, "environment": "staging",
}))
PY
)"
printf '%s\n' "${LINE}" >> "${LEDGER}"
echo ">> ledger appended: ${LEDGER}"

cat <<EOF

================ GOVERNANCE_LOG paste-block (owner-authored prose) ================
## ${TS} — STAGING deploy: \`backend-v2-staging\` rebuild — gated via ops/release-backend-v2-staging.sh (run ${RUN_LABEL})

**Staging deploy** — tree_hash \`${TREE_HASH}\` (git \`${GIT_SHA}\`, dirty=${DIRTY}), L1 \`${SERVED_L1}\`.
No adjudicated eval-REPLAY (staging has never had one; mirrors prod's current owner-disabled state).
- new live \`sealai-backend-v2-staging:latest\` = \`${IMAGE_SHA}\`
- rollback rung (read from the daemon) = \`${ROLLBACK_FROM}\`, tagged \`${ROLLBACK_TAG}\`
- smoke GREEN: internal health; kern one-shot (v=16,755 / PV=50.0); restart-survival.
  (Public URL / authed check NOT run by this script — see
  \`BASE_URL=https://sealingai.com:8443 ops/smoke-v2.sh\`, owner-run, needs a real bearer token
  for the authed leg.)
- ledger: ${LEDGER}
- nginx-staging was NOT touched by this deploy (blast radius = backend-v2-staging only).
==================================================================================
EOF
echo ">> Done."
