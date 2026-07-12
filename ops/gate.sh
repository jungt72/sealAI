#!/usr/bin/env bash
set -euo pipefail
BIND_EVAL=0
[ "${1:-}" = "--bind-eval" ] && BIND_EVAL=1
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

step "5/5  Eval<->Tree-Bindung"
TREE="$(bash ops/tree-hash.sh)"
if $PY ops/v2_deploy_gate.py backend/sealai_v2/eval/runs "$TREE" >/tmp/gate_bind.txt 2>&1; then
  echo "  OK: adjudizierter REPLAY für $TREE vorhanden."
elif [ "$BIND_EVAL" = 1 ]; then cat /tmp/gate_bind.txt; fail "Kein adjudizierter REPLAY ($TREE) [--bind-eval]"
else printf '  \033[1;33mWARN\033[0m: kein adjudizierter REPLAY für %s. Final-Deploy blockt; Nonprod-Candidate oder expliziter Owner-Waiver bleiben möglich.\n' "$TREE"; fi

echo; echo "GATE: grün"; exit 0
