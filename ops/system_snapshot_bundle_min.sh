#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$ROOT/ops/_snapshots"

SNAP="${1:-}"
if [[ -z "$SNAP" ]]; then
  SNAP="$(ls -1t "$DIR"/stack_snapshot_*.md | head -n 1)"
fi

base="$(basename "$SNAP")"
TS="${base#stack_snapshot_}"
TS="${TS%.md}"

PIP_FREEZE="$DIR/pip_freeze_${TS}.txt"
NPM_FRONT="$DIR/npm_ls_frontend_${TS}.txt"
NPM_STRAPI="$DIR/npm_ls_strapi_${TS}.txt"

OUT="$DIR/LLM_CONTEXT_MIN_${TS}.md"

extract_section() {
  local start="$1"
  local end="$2"
  awk -v start="$start" -v end="$end" '
    $0 ~ start {p=1}
    p==1 {print}
    p==1 && $0 ~ end {exit}
  ' "$SNAP" || true
}

cap() {
  local n="$1"
  awk -v n="$n" 'NR<=n{print} NR==n+1{print "...<truncated>..."}' || true
}

tmp="${OUT}.tmp.$$"

{
  echo "# LLM Context (MIN) (SealAI Monorepo)"
  echo
  echo "- Generated (UTC): $TS"
  echo "- Repo root: $ROOT"
  echo
  echo "## Instructions for the LLM"
  echo "You are a senior full-stack architect for a self-hosted multi-tenant AI platform (FastAPI + LangGraph v2 + Redis + Qdrant + Postgres + Keycloak + Next.js)."
  echo "Do:"
  echo "1) Read-only audit: repo map + dataflow; identify mismatches/stale configs/missing wiring."
  echo "2) Output: architecture summary; prioritized issues (with file evidence: path + what to inspect); minimal-diff patch plan + tests."
  echo "Constraints: minimal diffs, reuse patterns, Keycloak scoping is SoT, Qdrant single-collection tenant filter stays."
  echo "If you need full deps: ask for sidecars (pip_freeze / npm_ls)."
  echo
  echo "## Snapshot (selected, capped)"
  echo
  echo "### Git / Repo Identity (cap 220)"
  extract_section '^## 2) Git / Repo Identity' '^## 3) Repo Structure' | cap 220
  echo
  echo "### Repo Structure (cap 260)"
  extract_section '^## 3) Repo Structure' '^## 4) Key Files' | cap 260
  echo
  echo "### Key Files (cap 420)"
  extract_section '^## 4) Key Files' '^## 5) Env Files' | cap 420
  echo
  echo "### Docker / Compose (cap 420)"
  extract_section '^## 6) Docker / Compose' '^## 7) Open Ports' | cap 420
  echo
  echo "### Fast Architecture Hints (cap 260)"
  extract_section '^## 10) Fast' '^## 11)' | cap 260
  echo
  echo "## Dependencies (preview only)"
  if [[ -f "$PIP_FREEZE" ]]; then
    echo "### pip freeze (first 180 lines; full file exists)"
    echo '```text'
    sed -n '1,180p' "$PIP_FREEZE"
    echo '...<truncated>...'
    echo '```'
    echo
  fi
  if [[ -f "$NPM_FRONT" ]]; then
    echo "### npm ls --depth=0 (frontend) (first 80 lines)"
    echo '```text'
    sed -n '1,80p' "$NPM_FRONT"
    echo '...<truncated>...'
    echo '```'
    echo
  fi
  if [[ -f "$NPM_STRAPI" ]]; then
    echo "### npm ls --depth=0 (strapi) (first 80 lines)"
    echo '```text'
    sed -n '1,80p' "$NPM_STRAPI"
    echo '...<truncated>...'
    echo '```'
    echo
  fi
  echo
  echo "## Sidecar files (full deps)"
  echo "- pip freeze: $PIP_FREEZE"
  echo "- npm ls frontend: $NPM_FRONT"
  echo "- npm ls strapi: $NPM_STRAPI"
} > "$tmp"

mv "$tmp" "$OUT"

echo "OK: wrote min bundle:"
echo " - $OUT"
