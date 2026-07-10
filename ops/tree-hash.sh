#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ops/tree-hash.sh — canonical, side-effect-free CONTENT hash of the backend-v2
# IMAGE build-inputs. SINGLE SOURCE OF TRUTH: the eval manifest (sealai_v2/eval),
# the V2 deploy wrapper (ops/release-backend-v2.sh) and the kern-fix-01 backfill
# ALL call this script (no args) — byte-identical by construction.
#
# SCOPE — every input that determines the image content, per backend/Dockerfile.v2
# (FROM python:3.12-slim; COPY requirements-v2.txt; COPY sealai_v2; COPY
# docker-entrypoint-v2.sh):
#     backend/Dockerfile.v2            # the build recipe itself
#     backend/.dockerignore            # controls which context bytes COPY can observe
#     backend/requirements-v2.txt      # pinned runtime deps (COPYed)
#     backend/sealai_v2                # the app — minus eval/ + tests/ (see below)
#     backend/docker-entrypoint-v2.sh  # the COPYed entrypoint (the deploy teeth)
# EXCLUDED: backend/sealai_v2/eval and /tests, and git-ignored files
# (__pycache__). eval/runs/ is SELF-REFERENTIAL (the backfill writes this hash
# INTO eval/runs/<label>/results.json, and every eval run mutates it); eval/ +
# tests/ are dev infra never imported by the served app (api.main → pipeline →
# core → knowledge/prompts/llm/security/config/db). So an image-content change
# forces a fresh eval; an eval-harness / test / runs-artifact change does not.
#
# The per-build GATE_TREE_HASH is a Dockerfile --build-arg, NOT file content, so
# it never enters this hash (no circularity). Any positional arg is ignored — the
# input set is fixed.
#
# RECIPE (NO side effects on the real index/worktree): a throwaway GIT_INDEX_FILE,
# `git add` the inputs into it, `git write-tree` → the tree-object SHA. The real
# .git/index and the worktree are untouched (proven by the status-invariance test).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

TMP_INDEX="$(mktemp -u "${TMPDIR:-/tmp}/sealai-tree-index.XXXXXX")"
trap 'rm -f "${TMP_INDEX}"' EXIT

GIT_INDEX_FILE="${TMP_INDEX}" git add -A -- \
  backend/sealai_v2 \
  ":(exclude)backend/sealai_v2/eval" \
  ":(exclude)backend/sealai_v2/tests" \
  backend/requirements-v2.txt \
  backend/.dockerignore \
  backend/Dockerfile.v2 \
  backend/docker-entrypoint-v2.sh >/dev/null

GIT_INDEX_FILE="${TMP_INDEX}" git write-tree
