#!/bin/bash -p
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
# RECIPE (NO side effects on the real index/worktree/object store): a throwaway
# GIT_INDEX_FILE plus private object directory, `git add` the inputs into it,
# `git write-tree` → the tree-object SHA. The real .git index/objects and the
# worktree are untouched (including in a root-owned read-only staged checkout).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
readonly GIT_CONFIG_NOSYSTEM=1
readonly GIT_CONFIG_GLOBAL=/dev/null
readonly GIT_TERMINAL_PROMPT=0
readonly GIT_OPTIONAL_LOCKS=0
readonly GIT_CONFIG_COUNT=0
readonly GIT_ATTR_NOSYSTEM=1
export GIT_CONFIG_NOSYSTEM GIT_CONFIG_GLOBAL GIT_TERMINAL_PROMPT GIT_OPTIONAL_LOCKS
export GIT_CONFIG_COUNT GIT_ATTR_NOSYSTEM
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
unset GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES
unset GIT_CONFIG_PARAMETERS GIT_EXEC_PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd "${REPO_ROOT}"
GIT=(/usr/bin/git -c core.hooksPath=/dev/null -c "safe.directory=${REPO_ROOT}" -C "${REPO_ROOT}")
REPO_GIT_OBJECTS_RAW="$("${GIT[@]}" rev-parse --git-path objects)"
REPO_GIT_OBJECTS="$(CDPATH= cd -- "${REPO_GIT_OBJECTS_RAW}" && pwd -P)"
readonly REPO_GIT_OBJECTS_RAW REPO_GIT_OBJECTS

TMP_WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sealai-tree-hash.XXXXXX")"
chmod 0700 "${TMP_WORK_DIR}"
trap 'rm -rf -- "${TMP_WORK_DIR}"' EXIT
TMP_INDEX="${TMP_WORK_DIR}/index"
if [[ -n "${SEALAI_TREE_HASH_OBJECT_DIR:-}" ]]; then
  TREE_OBJECT_DIR="${SEALAI_TREE_HASH_OBJECT_DIR}"
  /usr/bin/python3 -I - "${TREE_OBJECT_DIR}" <<'PY'
import os
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
try:
    metadata = path.lstat()
except OSError:
    raise SystemExit(78)
if (
    not path.is_absolute()
    or stat.S_ISLNK(metadata.st_mode)
    or not stat.S_ISDIR(metadata.st_mode)
    or metadata.st_uid != os.geteuid()
    or stat.S_IMODE(metadata.st_mode) != 0o700
):
    raise SystemExit(78)
PY
else
  TREE_OBJECT_DIR="${TMP_WORK_DIR}/objects"
  mkdir -m 0700 "${TREE_OBJECT_DIR}"
fi
readonly TMP_WORK_DIR TMP_INDEX TREE_OBJECT_DIR
readonly GIT_ALTERNATE_OBJECT_DIRECTORIES="${REPO_GIT_OBJECTS}"
readonly GIT_OBJECT_DIRECTORY="${TREE_OBJECT_DIR}"
readonly GIT_INDEX_FILE="${TMP_INDEX}"
export GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_OBJECT_DIRECTORY GIT_INDEX_FILE

"${GIT[@]}" add -A -- \
  backend/sealai_v2 \
  ":(exclude)backend/sealai_v2/eval" \
  ":(exclude)backend/sealai_v2/tests" \
  backend/requirements-v2.txt \
  backend/.dockerignore \
  backend/Dockerfile.v2 \
  backend/docker-entrypoint-v2.sh >/dev/null

"${GIT[@]}" write-tree
