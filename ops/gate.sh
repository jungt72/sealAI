#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "${1:-}" != "--bind-eval" ] || {
  echo "GATE-FAIL: --bind-eval is retired; production binding requires the fixed root-trusted evidence bundle and Gate-10 hashes"
  exit 2
}
[ -d backend/sealai_v2 ] || { echo "GATE-FAIL: nicht im Repo-Root"; exit 1; }
export PYTHONPATH="backend${PYTHONPATH:+:$PYTHONPATH}"
if   [ -x .venv/bin/python ] && .venv/bin/python -c '' 2>/dev/null; then PY=.venv/bin/python
elif command -v python3 >/dev/null; then PY=python3
else PY=python; fi
RUFF=".venv/bin/ruff"; [ -x "$RUFF" ] || RUFF="ruff"
step(){ printf '\n\033[1m[gate]\033[0m %s\n' "$*"; }
fail(){ echo "GATE-FAIL: $*"; exit 1; }

step "1/5  ruff format --check backend/  (Pin 0.6.9)"
"$RUFF" --version | grep -q '0\.6\.9' || fail "ruff != 0.6.9 (CI-Pin): $("$RUFF" --version)"
"$RUFF" format --check backend/ || fail "ruff format --check rot (backend)"

step "2/5  Import-Boundary-Keystone"
$PY -m pytest backend/tests/architecture/test_v2_import_boundary.py --noconftest -q || fail "Import-Boundary verletzt"

step "3/5  Architektur-Enforcer-Glob"
$PY -m pytest backend/tests/architecture --noconftest -q || fail "Architektur-Enforcer rot"

step "4/5  V2-Offline-Suite (sealai_v2)"
$PY -m pytest backend/sealai_v2 --noconftest -q || fail "V2-Offline-Suite rot"

step "5/5  Produktions-Eval-Gate-Contract (exact RC evidence; offline)"
TREE="$(/bin/bash -p ops/tree-hash.sh)"
SERVED_L1="$("$PY" -c 'from sealai_v2.config.settings import Settings; s = Settings(); print(f"{s.l1_provider or s.provider}/{s.l1_model}")')" \
  || fail "Served-L1-Bindung konnte nicht ermittelt werden"
RUNTIME_PROFILE_HASH="$("$PY" -m sealai_v2.config.runtime_profile --hash)" \
  || fail "Runtime-Profil-Bindung konnte nicht ermittelt werden"
[[ "${SERVED_L1}" == */* && -n "${SERVED_L1%%/*}" && -n "${SERVED_L1#*/}" ]] \
  || fail "Served-L1-Bindung ist ungültig"
[[ "${RUNTIME_PROFILE_HASH}" =~ ^[0-9a-f]{64}$ ]] \
  || fail "Runtime-Profil-Bindung ist ungültig"
"$PY" -m pytest backend/tests/test_v2_deploy_gate.py -q \
  || fail "Production-RC-Gate-Contract rot"
printf '  OK: production authorization is not inferred from local runs (%s / %s / %s); only release-backend-v2 supplies the fixed external evidence and all Gate-10 hashes.\n' \
  "$TREE" "$SERVED_L1" "$RUNTIME_PROFILE_HASH"
echo "  targeted/chained Evidence und Owner-Waiver autorisieren keine Promotion."

echo; echo "GATE: grün"; exit 0
