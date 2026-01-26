#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIR="$ROOT/ops/_snapshots"

SNAP="${1:-}"
if [[ -z "$SNAP" ]]; then
  SNAP="$(ls -1t "$DIR"/stack_snapshot_*.md | head -n 1)"
fi

# Extract TS from file name: stack_snapshot_<TS>.md
base="$(basename "$SNAP")"
TS="${base#stack_snapshot_}"
TS="${TS%.md}"

PIP_FREEZE="$DIR/pip_freeze_${TS}.txt"
PIP_LIST="$DIR/pip_list_${TS}.txt"
NPM_FRONT="$DIR/npm_ls_frontend_${TS}.txt"
NPM_STRAPI="$DIR/npm_ls_strapi_${TS}.txt"

OUT="$DIR/LLM_CONTEXT_BUNDLE_${TS}.md"

{
  echo "# LLM Context Bundle (SealAI Monorepo)"
  echo
  echo "- Generated (UTC): $TS"
  echo "- Repo root: $ROOT"
  echo
  echo "## 0) Instructions for the LLM"
  cat <<'TXT'
You are a senior full-stack architect and debugger for a self-hosted, multi-tenant AI platform (FastAPI + LangGraph v2 + Redis checkpointing + Qdrant + Postgres + Keycloak + Next.js).
Do this in order:

1) Read-only audit:
   - Build a precise repo map (entrypoints, modules, dataflow).
   - Identify mismatches/stale configs/missing wiring.
   - Focus on: multi-tenancy scoping, SSE contract, LWW parameter sync, auth (Keycloak), RAG/Qdrant single-collection tenant filter, Redis checkpoints, background jobs.

2) Output:
   - Architecture summary (bullet points).
   - Prioritized issues list (each with: severity, why it matters, evidence pointers: file path + what to inspect).
   - Minimal-diff patch plan: small patches only, each with verification steps/tests.

Constraints:
- Do NOT invent new subsystems or lots of new files.
- Prefer minimal diffs; reuse existing patterns in the repo.
- Treat Keycloak tenant/user scoping as source of truth.
- Qdrant must remain a single collection with strict tenant_id payload filtering.
TXT

  echo
  echo "## 1) Stack Snapshot (Markdown)"
  echo
  cat "$SNAP"

  echo
  echo "## 2) Python Dependencies"
  echo
  if [[ -f "$PIP_FREEZE" ]]; then
    echo "### pip freeze (complete)"
    echo '```text'
    cat "$PIP_FREEZE"
    echo '```'
    echo
  elif [[ -f "$PIP_LIST" ]]; then
    echo "### pip list (complete, fallback)"
    echo '```text'
    cat "$PIP_LIST"
    echo '```'
    echo
  else
    echo "_No pip deps file found for TS=$TS_"
    echo
  fi

  echo
  echo "## 3) Node Dependencies"
  echo
  if [[ -f "$NPM_FRONT" ]]; then
    echo "### npm ls --depth=0 (frontend)"
    echo '```text'
    cat "$NPM_FRONT"
    echo '```'
    echo
  else
    echo "_No frontend npm ls found for TS=$TS_"
    echo
  fi

  if [[ -f "$NPM_STRAPI" ]]; then
    echo "### npm ls --depth=0 (strapi)"
    echo '```text'
    cat "$NPM_STRAPI"
    echo '```'
    echo
  else
    echo "_No strapi npm ls found for TS=$TS_"
    echo
  fi

} > "$OUT"

echo "OK: wrote bundle:"
echo " - $OUT"
