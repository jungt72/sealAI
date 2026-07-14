#!/bin/bash -p
# Build the dashboard twice from one clean commit and materialize an inert,
# content-addressed release. This command intentionally cannot activate it.
set -Eeuo pipefail
set -o noclobber
umask 022

fail() {
  printf 'dashboard release preparation denied: %s\n' "$1" >&2
  exit 78
}

[[ $# -eq 0 ]] || fail "arguments_not_supported"

DISCOVERED_NODE="$(command -v node || true)"
[[ -n "${DISCOVERED_NODE}" ]] || fail "node_not_found"
TOOLCHAIN_DIR="$(cd -- "$(dirname -- "${DISCOVERED_NODE}")" && pwd -P)"
readonly TOOLCHAIN_DIR
readonly PATH="${TOOLCHAIN_DIR}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
export PATH

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly FRONTEND_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly REPOSITORY_ROOT="$(cd -- "${FRONTEND_DIR}/.." && pwd -P)"
readonly CANDIDATE_DIR="${FRONTEND_DIR}/.build/dashboard-candidate"
readonly RELEASE_ROOT="${FRONTEND_DIR}/dashboard-releases"
readonly LOCKFILE="${FRONTEND_DIR}/package-lock.json"
readonly NODE_VERSION_FILE="${FRONTEND_DIR}/.node-version"
readonly NPM_VERSION_FILE="${FRONTEND_DIR}/.npm-version"
readonly RELEASE_TOOL="${SCRIPT_DIR}/dashboard_release.py"
readonly INSPECTION_ONE="${FRONTEND_DIR}/.build/.dashboard-inspection-one.$$.json"
readonly INSPECTION_TWO="${FRONTEND_DIR}/.build/.dashboard-inspection-two.$$.json"

case "${REPOSITORY_ROOT}" in
  /home/thorsten/sealai|/home/thorsten/sealai/*)
    fail "production_build_forbidden"
    ;;
esac

[[ -x "${TOOLCHAIN_DIR}/node" ]] || fail "node_not_executable"
[[ -x "${TOOLCHAIN_DIR}/npm" ]] || fail "npm_not_executable"
[[ -x /usr/bin/git ]] || fail "git_not_executable"
[[ -f "${LOCKFILE}" ]] || fail "lockfile_missing"
[[ -f "${NODE_VERSION_FILE}" ]] || fail "node_version_pin_missing"
[[ -f "${NPM_VERSION_FILE}" ]] || fail "npm_version_pin_missing"
[[ -f "${RELEASE_TOOL}" ]] || fail "release_tool_missing"

PYTHON_BIN="$(command -v python3 || true)"
[[ -n "${PYTHON_BIN}" && -x "${PYTHON_BIN}" ]] || fail "python3_not_found"
readonly PYTHON_BIN

EXPECTED_NODE_VERSION="$(tr -d '[:space:]' < "${NODE_VERSION_FILE}")"
EXPECTED_NPM_VERSION="$(tr -d '[:space:]' < "${NPM_VERSION_FILE}")"
NODE_VERSION="$(${TOOLCHAIN_DIR}/node --version)"
NPM_VERSION="$(${TOOLCHAIN_DIR}/npm --version)"
readonly EXPECTED_NODE_VERSION EXPECTED_NPM_VERSION NODE_VERSION NPM_VERSION
[[ "${EXPECTED_NODE_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "invalid_node_version_pin"
[[ "${EXPECTED_NPM_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "invalid_npm_version_pin"
[[ "${NODE_VERSION}" == "v${EXPECTED_NODE_VERSION}" ]] || fail "node_version_mismatch"
[[ "${NPM_VERSION}" == "${EXPECTED_NPM_VERSION}" ]] || fail "npm_version_mismatch"

cleanup() {
  rm -f -- "${INSPECTION_ONE}" "${INSPECTION_TWO}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

assert_clean_frontend() {
  local status
  status="$(/usr/bin/git -C "${REPOSITORY_ROOT}" status --porcelain=v1 --untracked-files=all -- frontend-v2)"
  [[ -z "${status}" ]] || fail "frontend_worktree_not_clean"
}

assert_no_vite_env_files() {
  local env_file
  for env_file in "${FRONTEND_DIR}/.env" "${FRONTEND_DIR}"/.env.*; do
    if [[ -e "${env_file}" || -L "${env_file}" ]]; then
      fail "vite_env_file_forbidden"
    fi
  done
}

sha256_file() {
  "${PYTHON_BIN}" -I -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$1"
}

run_build() {
  /usr/bin/env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    CI=1 \
    LANG=C \
    LC_ALL=C \
    NPM_CONFIG_USERCONFIG=/dev/null \
    SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH}" \
    TZ=UTC \
    "${TOOLCHAIN_DIR}/npm" --prefix "${FRONTEND_DIR}" run build
}

inspect_candidate() {
  "${PYTHON_BIN}" -I "${RELEASE_TOOL}" inspect \
    --candidate "${CANDIDATE_DIR}" \
    --source-git-sha "${SOURCE_GIT_SHA}" \
    --source-date-epoch "${SOURCE_DATE_EPOCH}" \
    --npm-lock-sha256 "${NPM_LOCK_SHA256}" \
    --node-version "${NODE_VERSION}" \
    --npm-version "${NPM_VERSION}"
}

assert_no_vite_env_files
assert_clean_frontend
SOURCE_GIT_SHA="$(/usr/bin/git -C "${REPOSITORY_ROOT}" rev-parse --verify 'HEAD^{commit}')"
SOURCE_DATE_EPOCH="$(/usr/bin/git -C "${REPOSITORY_ROOT}" show -s --format=%ct "${SOURCE_GIT_SHA}")"
NPM_LOCK_SHA256="$(sha256_file "${LOCKFILE}")"
readonly SOURCE_GIT_SHA SOURCE_DATE_EPOCH NPM_LOCK_SHA256
[[ "${SOURCE_GIT_SHA}" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]] || fail "invalid_source_commit"
[[ "${SOURCE_DATE_EPOCH}" =~ ^[0-9]+$ ]] || fail "invalid_source_epoch"
[[ "${NPM_LOCK_SHA256}" =~ ^[0-9a-f]{64}$ ]] || fail "invalid_lockfile_digest"

/usr/bin/env -i \
  PATH="${PATH}" \
  HOME="${HOME}" \
  CI=1 \
  LANG=C \
  LC_ALL=C \
  NPM_CONFIG_USERCONFIG=/dev/null \
  TZ=UTC \
  "${TOOLCHAIN_DIR}/npm" --prefix "${FRONTEND_DIR}" ci --ignore-scripts --no-audit --no-fund
mkdir -p -- "${FRONTEND_DIR}/.build"

run_build
assert_clean_frontend
inspect_candidate > "${INSPECTION_ONE}"

run_build
assert_clean_frontend
inspect_candidate > "${INSPECTION_TWO}"

/usr/bin/cmp -s -- "${INSPECTION_ONE}" "${INSPECTION_TWO}" || fail "non_reproducible_build"
[[ "$(sha256_file "${LOCKFILE}")" == "${NPM_LOCK_SHA256}" ]] || fail "lockfile_changed_during_build"

printf '{"build_count":2,"live_activation_performed":false,"operation":"dashboard-reproducibility","result":"ok"}\n'
"${PYTHON_BIN}" -I "${RELEASE_TOOL}" prepare \
  --candidate "${CANDIDATE_DIR}" \
  --release-root "${RELEASE_ROOT}" \
  --source-git-sha "${SOURCE_GIT_SHA}" \
  --source-date-epoch "${SOURCE_DATE_EPOCH}" \
  --npm-lock-sha256 "${NPM_LOCK_SHA256}" \
  --node-version "${NODE_VERSION}" \
  --npm-version "${NPM_VERSION}"
