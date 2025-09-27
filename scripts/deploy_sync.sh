#!/usr/bin/env bash
# Deploy helper that syncs the repository to the requested branch and
# restarts the docker-compose stack. Intended to be triggered via CI/CD.

set -euo pipefail

BRANCH="${1:-refactor/intake-triage-unify}"
REPO_DIR="${REPO_DIR:-/root/sealai}"
COMPOSE_FILES=("docker-compose.yml")

# Optional extra compose overrides (can be space/comma separated env).
if [[ -n "${COMPOSE_EXTRA:-}" ]]; then
  IFS=',' read -r -a extra_files <<< "${COMPOSE_EXTRA}"
  COMPOSE_FILES+=("${extra_files[@]}")
else
  # Default deploy override if it exists
  if [[ -f "${REPO_DIR}/docker-compose.deploy.yml" ]]; then
    COMPOSE_FILES+=("docker-compose.deploy.yml")
  fi
fi

cd "${REPO_DIR}"

if [[ ! -d .git ]]; then
  echo "[deploy] ${REPO_DIR} is not a git repository" >&2
  exit 1
fi

# Ensure we always operate on the requested branch
git fetch --prune origin

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [[ "${CURRENT_BRANCH}" != "${BRANCH}" ]]; then
  git checkout "${BRANCH}"
fi

if ! git diff --quiet --ignore-submodules HEAD; then
  if [[ "${FORCE_DEPLOY:-0}" == "1" ]]; then
    echo "[deploy] Cleaning uncommitted changes (FORCE_DEPLOY=1)"
    git reset --hard
    git clean -fd
  else
    echo "[deploy] Working tree dirty. Set FORCE_DEPLOY=1 to override." >&2
    exit 1
  fi
fi

git pull --ff-only origin "${BRANCH}"

COMPOSE_ARGS=()
for f in "${COMPOSE_FILES[@]}"; do
  if [[ -f "${f}" ]]; then
    COMPOSE_ARGS+=("-f" "${f}")
  fi
done

if [[ ${#COMPOSE_ARGS[@]} -eq 0 ]]; then
  echo "[deploy] No docker-compose files found" >&2
  exit 1
fi

echo "[deploy] Using compose files: ${COMPOSE_ARGS[*]}"

docker compose "${COMPOSE_ARGS[@]}" pull || true
docker compose "${COMPOSE_ARGS[@]}" build
docker compose "${COMPOSE_ARGS[@]}" up -d

# Optional pruning to keep disk usage reasonable
if [[ "${PRUNE_AFTER_DEPLOY:-1}" == "1" ]]; then
  docker system prune -f
fi

echo "[deploy] Deployment completed on branch ${BRANCH}."
