#!/usr/bin/env bash
set -euo pipefail

# ops/system_snapshot.sh
# Creates an LLM-friendly snapshot of this monorepo + system + deps (WITHOUT leaking secrets).
# Also writes full dependency dumps as sidecar files (pip/npm) to avoid huge markdown.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-$ROOT/ops/_snapshots}"
TS="$(date -u +"%Y%m%dT%H%M%SZ")"
OUT_MD="$OUT_DIR/stack_snapshot_${TS}.md"
OUT_TXT="$OUT_DIR/stack_snapshot_${TS}.txt"

mkdir -p "$OUT_DIR"

has() { command -v "$1" >/dev/null 2>&1; }

h1() { printf '\n# %s\n\n' "$1" | tee -a "$OUT_MD" >/dev/null; }
h2() { printf '\n## %s\n\n' "$1" | tee -a "$OUT_MD" >/dev/null; }

code() {
  local lang="$1"; shift
  printf '```%s\n' "$lang" | tee -a "$OUT_MD" >/dev/null
  ( "$@" ) 2>&1 | tee -a "$OUT_MD" >/dev/null || true
  printf '\n```\n\n' | tee -a "$OUT_MD" >/dev/null
}

code_stdin() {
  local lang="$1"; shift
  printf '```%s\n' "$lang" | tee -a "$OUT_MD" >/dev/null
  cat 2>&1 | tee -a "$OUT_MD" >/dev/null || true
  printf '\n```\n\n' | tee -a "$OUT_MD" >/dev/null
}

safe_head() {
  local file="$1" n="${2:-260}"
  if [[ -f "$file" ]]; then
    echo "### $file" | tee -a "$OUT_MD" >/dev/null
    printf '```text\n' | tee -a "$OUT_MD" >/dev/null
    sed -n "1,${n}p" "$file" 2>/dev/null | tee -a "$OUT_MD" >/dev/null || true
    printf '\n```\n\n' | tee -a "$OUT_MD" >/dev/null
  fi
}

env_keys_only() {
  local file="$1"
  if [[ -f "$file" ]]; then
    echo "### $file (keys only, values redacted)" | tee -a "$OUT_MD" >/dev/null
    printf '```text\n' | tee -a "$OUT_MD" >/dev/null
    awk '
      BEGIN{FS="="}
      /^[[:space:]]*#/ {next}
      /^[[:space:]]*$/ {next}
      {
        key=$1
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
        if (key != "") print key"=<redacted>"
      }
    ' "$file" 2>/dev/null | tee -a "$OUT_MD" >/dev/null || true
    printf '\n```\n\n' | tee -a "$OUT_MD" >/dev/null
  fi
}

repo_tree() {
  if has tree; then
    tree -a -I '.git|.next|node_modules|dist|build|.venv|__pycache__|.pytest_cache|coverage|.turbo|.cache|ops/_snapshots|.mypy_cache|.ruff_cache' -L 4 "$ROOT"
  else
    # find: maxdepth must come before other tests
    find "$ROOT" -maxdepth 4 \
      \( -path "$ROOT/.git" -o -path "$ROOT/node_modules" -o -path "$ROOT/.next" -o -path "$ROOT/.venv" -o -path "$ROOT/ops/_snapshots" \) -prune -o \
      -type d -print
  fi
}

: > "$OUT_MD"
: > "$OUT_TXT"

h1 "Monorepo Stack Snapshot"
{
  echo "Timestamp (UTC): $TS"
  echo "Root: $ROOT"
  echo "Host: $(hostname -f 2>/dev/null || hostname)"
  echo "User: $(id -un) (uid=$(id -u))"
  echo "PWD: $(pwd)"
} | code_stdin "text"

h2 "1) System"
code "bash" bash -lc 'uname -a'
code "bash" bash -lc 'lsb_release -a 2>/dev/null || cat /etc/os-release 2>/dev/null || true'
code "bash" bash -lc 'date; date -u'
code "bash" bash -lc 'whoami; id'
code "bash" bash -lc 'df -hT'
code "bash" bash -lc 'free -h || true'
code "bash" bash -lc 'uptime || true'
code "bash" bash -lc 'ulimit -a || true'

h2 "2) Git / Repo Identity"
if has git; then
  code "bash" bash -lc "cd \"$ROOT\" && git rev-parse --show-toplevel && git remote -v && git status -sb"
  code "bash" bash -lc "cd \"$ROOT\" && git log -n 25 --oneline --decorate"
  code "bash" bash -lc "cd \"$ROOT\" && git diff --stat || true"
else
  echo "_git not found_" | tee -a "$OUT_MD" >/dev/null
fi

h2 "3) Repo Structure (depth-limited)"
printf '```bash\n' | tee -a "$OUT_MD" >/dev/null
repo_tree 2>&1 | tee -a "$OUT_MD" >/dev/null || true
printf '\n```\n\n' | tee -a "$OUT_MD" >/dev/null

h2 "4) Key Files (first ~260 lines)"
safe_head "$ROOT/README.md" 260
safe_head "$ROOT/docker-compose.yml" 260
safe_head "$ROOT/docker-compose.override.yml" 260
safe_head "$ROOT/docker-compose.prod.yml" 260
safe_head "$ROOT/docker-compose.biz.yml" 260
safe_head "$ROOT/nginx/default.conf" 260
safe_head "$ROOT/backend/Dockerfile" 260
safe_head "$ROOT/backend/pyproject.toml" 260
safe_head "$ROOT/backend/requirements.txt" 260
safe_head "$ROOT/backend/pytest.ini" 260
safe_head "$ROOT/frontend/package.json" 260
safe_head "$ROOT/frontend/next.config.js" 260
safe_head "$ROOT/frontend/tsconfig.json" 260
safe_head "$ROOT/strapi-backend/package.json" 260

h2 "5) Env Files (keys only, values redacted)"
while IFS= read -r f; do
  env_keys_only "$f"
done < <(find "$ROOT" -maxdepth 3 -type f \( -name ".env" -o -name ".env.*" \) 2>/dev/null | sort)

h2 "6) Docker / Compose"
if has docker; then
  code "bash" bash -lc 'docker --version'
  code "bash" bash -lc 'docker compose version 2>/dev/null || docker-compose --version 2>/dev/null || true'
  code "bash" bash -lc 'docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" || true'
  code "bash" bash -lc 'docker network ls || true'
  code "bash" bash -lc 'docker volume ls || true'

  if [[ -f "$ROOT/docker-compose.yml" ]]; then
    if docker compose -f "$ROOT/docker-compose.yml" config >/dev/null 2>&1; then
      code "yaml" bash -lc "docker compose -f \"$ROOT/docker-compose.yml\" config"
    else
      code "bash" bash -lc "docker compose -f \"$ROOT/docker-compose.yml\" config 2>&1 || true"
    fi
  fi
else
  echo "_docker not found_" | tee -a "$OUT_MD" >/dev/null
fi

h2 "7) Open Ports / Processes (best effort)"
code "bash" bash -lc 'ss -lntup 2>/dev/null || netstat -lntup 2>/dev/null || true'
code "bash" bash -lc 'ps aux --sort=-%mem | head -n 40 || true'

h2 "8) Python Environment (Backend)"
if has python3; then
  code "bash" bash -lc 'python3 --version && python3 -c "import sys; print(sys.executable); print(sys.prefix)"'

  PY_BIN="python3"
  if [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
    PY_BIN="$ROOT/backend/.venv/bin/python"
  fi

  # Full dumps as sidecar files (complete, not truncated)
  PIP_LIST_TXT="$OUT_DIR/pip_list_${TS}.txt"
  PIP_FREEZE_TXT="$OUT_DIR/pip_freeze_${TS}.txt"
  "$PY_BIN" -m pip --version > "$OUT_DIR/pip_version_${TS}.txt" 2>&1 || true
  "$PY_BIN" -m pip list --format=columns > "$PIP_LIST_TXT" 2>&1 || true
  "$PY_BIN" -m pip freeze > "$PIP_FREEZE_TXT" 2>&1 || true

  {
    echo "Python used for pip: $PY_BIN"
    echo "Full pip list: $PIP_LIST_TXT"
    echo "Full pip freeze: $PIP_FREEZE_TXT"
    echo
    echo "Preview (first 120 lines) of pip freeze:"
  } | code_stdin "text"
  sed -n '1,120p' "$PIP_FREEZE_TXT" | code_stdin "text"
else
  echo "_python3 not found_" | tee -a "$OUT_MD" >/dev/null
fi

h2 "9) Node / Frontend Environment"
if has node; then
  code "bash" bash -lc 'node --version'
fi
if has npm; then
  code "bash" bash -lc 'npm --version'

  if [[ -f "$ROOT/frontend/package.json" ]]; then
    NPM_FRONT_TXT="$OUT_DIR/npm_ls_frontend_${TS}.txt"
    (cd "$ROOT/frontend" && npm ls --depth=0) > "$NPM_FRONT_TXT" 2>&1 || true
    {
      echo "Full npm ls (frontend): $NPM_FRONT_TXT"
      echo "Preview (first 120 lines):"
    } | code_stdin "text"
    sed -n '1,120p' "$NPM_FRONT_TXT" | code_stdin "text"
  fi

  if [[ -f "$ROOT/strapi-backend/package.json" ]]; then
    NPM_STRAPI_TXT="$OUT_DIR/npm_ls_strapi_${TS}.txt"
    (cd "$ROOT/strapi-backend" && npm ls --depth=0) > "$NPM_STRAPI_TXT" 2>&1 || true
    {
      echo "Full npm ls (strapi): $NPM_STRAPI_TXT"
      echo "Preview (first 120 lines):"
    } | code_stdin "text"
    sed -n '1,120p' "$NPM_STRAPI_TXT" | code_stdin "text"
  fi
fi
if has pnpm; then code "bash" bash -lc 'pnpm --version'; fi
if has yarn; then code "bash" bash -lc 'yarn --version'; fi

h2 "10) Fast “Architecture Hints” (limited grep)"
code "bash" bash -lc "cd \"$ROOT\" && (rg -n \"FastAPI\\(|uvicorn|LangGraph|langgraph|Qdrant|qdrant|Redis|redis|Keycloak|OIDC|SSE|EventSource|httpx-sse\" backend frontend 2>/dev/null || true)"

h2 "11) Database / Migrations (best effort)"
if [[ -d "$ROOT/backend" ]]; then
  code "bash" bash -lc "cd \"$ROOT\" && ls -la backend/app 2>/dev/null || true"
  code "bash" bash -lc "cd \"$ROOT\" && ls -la backend/alembic 2>/dev/null || true"
  code "bash" bash -lc "cd \"$ROOT\" && ls -la backend/alembic/versions 2>/dev/null || true"
fi

h2 "12) What to paste into an LLM"
{
  echo "Paste stack snapshot markdown: $OUT_MD"
  echo "Also attach full dependency dumps if needed:"
  echo "- pip list:   $OUT_DIR/pip_list_${TS}.txt"
  echo "- pip freeze: $OUT_DIR/pip_freeze_${TS}.txt"
  echo "- npm ls (frontend/strapi): see $OUT_DIR/npm_ls_*_${TS}.txt"
  echo
  echo "Ask the LLM to: read-only audit -> prioritized issues -> minimal-diff patch plan + tests."
} | code_stdin "text"

cp "$OUT_MD" "$OUT_TXT" 2>/dev/null || true

echo "OK: wrote snapshot:"
echo " - $OUT_MD"
echo " - $OUT_TXT"
