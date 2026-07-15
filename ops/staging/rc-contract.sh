#!/bin/bash -p
# Strict, shared input boundary for isolated release-candidate evaluation/staging.
#
# The host-local rc.env is inert data, never shell code. Only an explicit key
# allow-list is imported, while inherited serving/provider/Compose/Docker variables
# are rejected before parsing. Error messages name keys but never values.

rc_contract_fail() {
  local reason="${1:-invalid_contract}"
  local key="${2:-none}"
  printf '%s\n' \
    "{\"component\":\"sealai-rc-contract\",\"result\":\"blocked\",\"reason_code\":\"${reason}\",\"key\":\"${key}\"}" >&2
  return 78
}

rc_contract_reject_inherited_environment() {
  local prefix
  local name

  # rc.env is the only RC configuration source. Serving credentials/config and
  # caller-selected Docker/Compose targets must not influence this boundary.
  for prefix in \
    RC_ SEALAI_RC_ SEALAI_V2_ OPENAI_ MISTRAL_ LANGSMITH_ LANGCHAIN_ \
    POSTGRES_ QDRANT_ REDIS_ KEYCLOAK_ DATABASE_ DOCKER_ COMPOSE_; do
    while IFS= read -r name; do
      [[ -z "${name}" ]] && continue
      rc_contract_fail inherited_forbidden_variable "${name}"
      return 78
    done < <(compgen -v "${prefix}")
  done
}

rc_contract_file_mode() {
  local path="$1"
  local mode

  if mode="$(/usr/bin/stat -Lc '%a' -- "${path}" 2>/dev/null)" && \
     [[ "${mode}" =~ ^[0-7]{3,4}$ ]]; then
    printf '%s' "${mode}"
    return 0
  fi
  if mode="$(/usr/bin/stat -f '%Lp' -- "${path}" 2>/dev/null)" && \
     [[ "${mode}" =~ ^[0-7]{3,4}$ ]]; then
    printf '%s' "${mode}"
    return 0
  fi
  return 1
}

rc_contract_key_allowed() {
  case "$1" in
    SEALAI_RC_MODE | \
    RC_DATA_SEED_STATUS | \
    RC_POSTGRES_PASSWORD | \
    RC_POSTGRES_SNAPSHOT_SHA256 | \
    RC_QDRANT_SNAPSHOT_SHA256 | \
    RC_AUTHORITY_EPOCH | \
    RC_QDRANT_COLLECTION | \
    RC_QDRANT_MEMORY_COLLECTION | \
    RC_POSTGRES_IMAGE | \
    RC_QDRANT_IMAGE | \
    RC_STUB_PROVIDER_STATUS | \
    RC_LLM_STUB_IMAGE | \
    RC_WEB_STUB_STATUS | \
    RC_TLS_FIXTURE_STATUS | \
    RC_NGINX_IMAGE | \
    RC_AUTH_STUB_IMAGE | \
    RC_FRONTEND_STUB_IMAGE)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

rc_contract_require_key() {
  local key="$1"
  if ! declare -p "${key}" >/dev/null 2>&1 || [[ -z "${!key}" ]]; then
    rc_contract_fail missing_or_empty_key "${key}"
    return 78
  fi
}

rc_contract_validate_hash() {
  local key="$1"
  local value="${!key}"
  if [[ ! "${value}" =~ ^[0-9a-f]{64}$ ]] || \
     [[ "${value}" == 0000000000000000000000000000000000000000000000000000000000000000 ]]; then
    rc_contract_fail invalid_sha256 "${key}"
    return 78
  fi
}

rc_contract_validate_prefixed_hash() {
  local key="$1"
  local value="${!key}"
  if [[ ! "${value}" =~ ^sha256:[0-9a-f]{64}$ ]] || \
     [[ "${value}" == sha256:0000000000000000000000000000000000000000000000000000000000000000 ]]; then
    rc_contract_fail invalid_sha256 "${key}"
    return 78
  fi
}

rc_contract_validate_image() {
  local key="$1"
  local repository_pattern="$2"
  local value="${!key}"
  local digest="${value##*@sha256:}"

  if [[ ! "${value}" =~ ^${repository_pattern}(:[A-Za-z0-9._-]+)?@sha256:[0-9a-f]{64}$ ]] || \
     [[ "${digest}" == 0000000000000000000000000000000000000000000000000000000000000000 ]]; then
    rc_contract_fail invalid_immutable_image "${key}"
    return 78
  fi
}

rc_contract_load() {
  if [[ $# -ne 2 ]]; then
    rc_contract_fail invalid_usage mode
    return 64
  fi

  local repo_root="$1"
  local contract_mode="$2"
  local raw
  local key
  local value
  local seen='|'
  local line_number=0
  local file_mode
  local file_size

  case "${contract_mode}" in
    eval | staging) ;;
    *)
      rc_contract_fail invalid_mode mode
      return 64
      ;;
  esac
  if [[ "${repo_root}" != /* ]]; then
    rc_contract_fail non_absolute_repo_root repo_root
    return 64
  fi

  rc_contract_reject_inherited_environment || return $?

  RC_ENV_FILE="${repo_root}/ops/staging/rc.env"
  export RC_ENV_FILE
  if [[ ! -f "${RC_ENV_FILE}" || -L "${RC_ENV_FILE}" || ! -O "${RC_ENV_FILE}" ]]; then
    rc_contract_fail unsafe_contract_file rc.env
    return 78
  fi
  file_mode="$(rc_contract_file_mode "${RC_ENV_FILE}" || true)"
  case "${file_mode}" in
    400 | 600) ;;
    *)
      rc_contract_fail unsafe_contract_mode rc.env
      return 78
      ;;
  esac
  file_size="$(/usr/bin/wc -c < "${RC_ENV_FILE}" | /usr/bin/tr -d '[:space:]')"
  if [[ ! "${file_size}" =~ ^[0-9]+$ ]] || (( file_size == 0 || file_size > 16384 )); then
    rc_contract_fail invalid_contract_size rc.env
    return 78
  fi

  while IFS= read -r raw || [[ -n "${raw}" ]]; do
    line_number=$((line_number + 1))
    if [[ "${raw}" == *$'\r'* ]]; then
      rc_contract_fail carriage_return "line_${line_number}"
      return 78
    fi
    [[ -z "${raw}" || "${raw}" == \#* ]] && continue
    if [[ ! "${raw}" =~ ^([A-Z][A-Z0-9_]*)=(.*)$ ]]; then
      rc_contract_fail invalid_literal_line "line_${line_number}"
      return 78
    fi
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    if ! rc_contract_key_allowed "${key}"; then
      rc_contract_fail forbidden_key "${key}"
      return 78
    fi
    if [[ "${seen}" == *"|${key}|"* ]]; then
      rc_contract_fail duplicate_key "${key}"
      return 78
    fi
    if [[ -z "${value}" ]]; then
      rc_contract_fail missing_or_empty_key "${key}"
      return 78
    fi
    seen="${seen}${key}|"
    printf -v "${key}" '%s' "${value}"
    export "${key}"
  done < "${RC_ENV_FILE}"

  for key in \
    SEALAI_RC_MODE \
    RC_DATA_SEED_STATUS \
    RC_POSTGRES_PASSWORD \
    RC_POSTGRES_SNAPSHOT_SHA256 \
    RC_QDRANT_SNAPSHOT_SHA256 \
    RC_AUTHORITY_EPOCH \
    RC_QDRANT_COLLECTION \
    RC_QDRANT_MEMORY_COLLECTION \
    RC_POSTGRES_IMAGE \
    RC_QDRANT_IMAGE \
    RC_STUB_PROVIDER_STATUS \
    RC_LLM_STUB_IMAGE; do
    rc_contract_require_key "${key}" || return $?
  done

  [[ "${SEALAI_RC_MODE}" == isolated-nonprod ]] || {
    rc_contract_fail invalid_rc_mode SEALAI_RC_MODE
    return 78
  }
  [[ "${RC_DATA_SEED_STATUS}" == READY ]] || {
    rc_contract_fail blocked_external RC_DATA_SEED_STATUS
    return 78
  }
  [[ "${RC_STUB_PROVIDER_STATUS}" == READY ]] || {
    rc_contract_fail blocked_external RC_STUB_PROVIDER_STATUS
    return 78
  }
  if [[ ! "${RC_POSTGRES_PASSWORD}" =~ ^[A-Za-z0-9._~-]{24,128}$ ]]; then
    rc_contract_fail invalid_rc_credential RC_POSTGRES_PASSWORD
    return 78
  fi
  rc_contract_validate_hash RC_POSTGRES_SNAPSHOT_SHA256 || return $?
  rc_contract_validate_hash RC_QDRANT_SNAPSHOT_SHA256 || return $?
  rc_contract_validate_prefixed_hash RC_AUTHORITY_EPOCH || return $?
  if [[ ! "${RC_QDRANT_COLLECTION}" =~ ^sealai_rc_[a-z0-9_]{1,48}$ ]]; then
    rc_contract_fail invalid_rc_collection RC_QDRANT_COLLECTION
    return 78
  fi
  if [[ ! "${RC_QDRANT_MEMORY_COLLECTION}" =~ ^sealai_rc_[a-z0-9_]{1,48}$ ]] || \
     [[ "${RC_QDRANT_MEMORY_COLLECTION}" == "${RC_QDRANT_COLLECTION}" ]]; then
    rc_contract_fail invalid_rc_collection RC_QDRANT_MEMORY_COLLECTION
    return 78
  fi
  rc_contract_validate_image RC_POSTGRES_IMAGE 'docker\.io/library/postgres' || return $?
  rc_contract_validate_image RC_QDRANT_IMAGE 'docker\.io/qdrant/qdrant' || return $?
  rc_contract_validate_image RC_LLM_STUB_IMAGE 'localhost/sealai-rc-[a-z0-9._/-]+' || return $?

  if [[ "${contract_mode}" == staging ]]; then
    for key in \
      RC_WEB_STUB_STATUS \
      RC_TLS_FIXTURE_STATUS \
      RC_NGINX_IMAGE \
      RC_AUTH_STUB_IMAGE \
      RC_FRONTEND_STUB_IMAGE; do
      rc_contract_require_key "${key}" || return $?
    done
    [[ "${RC_WEB_STUB_STATUS}" == READY ]] || {
      rc_contract_fail blocked_external RC_WEB_STUB_STATUS
      return 78
    }
    [[ "${RC_TLS_FIXTURE_STATUS}" == READY ]] || {
      rc_contract_fail blocked_external RC_TLS_FIXTURE_STATUS
      return 78
    }
    rc_contract_validate_image RC_NGINX_IMAGE 'docker\.io/library/nginx' || return $?
    rc_contract_validate_image RC_AUTH_STUB_IMAGE 'localhost/sealai-rc-[a-z0-9._/-]+' || return $?
    rc_contract_validate_image RC_FRONTEND_STUB_IMAGE 'localhost/sealai-rc-[a-z0-9._/-]+' || return $?
  fi
}

rc_contract_bind_approved_source() {
  if [[ $# -ne 3 ]]; then
    rc_contract_fail invalid_usage approved_source
    return 64
  fi
  local gate_control_sha="$1"
  local source_parent_sha="$2"
  local approved_source_sha="$3"
  local sha

  for sha in "${gate_control_sha}" "${source_parent_sha}" "${approved_source_sha}"; do
    if [[ ! "${sha}" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]]; then
      rc_contract_fail invalid_git_sha approved_source
      return 78
    fi
  done
  if [[ "${gate_control_sha}" == "${source_parent_sha}" ]]; then
    rc_contract_fail invalid_two_commit_boundary gate_control_sha
    return 78
  fi
  if [[ "${approved_source_sha}" != "${source_parent_sha}" ]] || \
     [[ "${approved_source_sha}" == "${gate_control_sha}" ]]; then
    rc_contract_fail approved_source_mismatch approved_source_sha
    return 78
  fi

  RC_APPROVED_SOURCE_SHA="${approved_source_sha}"
  export RC_APPROVED_SOURCE_SHA
}

rc_contract_assert_nonproduction_canonical_path() {
  if [[ $# -ne 1 || "$1" != /* ]]; then
    rc_contract_fail invalid_usage checkout_path
    return 64
  fi
  case "$1" in
    /home/thorsten/sealai | /home/thorsten/sealai/*)
      rc_contract_fail production_checkout_forbidden checkout_path
      return 78
      ;;
  esac
}

rc_contract_assert_nonproduction_checkout() {
  if [[ $# -ne 1 || "$1" != /* ]]; then
    rc_contract_fail invalid_usage checkout_path
    return 64
  fi
  local canonical_path
  if ! canonical_path="$(CDPATH= cd -- "$1" 2>/dev/null && pwd -P)"; then
    rc_contract_fail invalid_checkout_path checkout_path
    return 78
  fi
  rc_contract_assert_nonproduction_canonical_path "${canonical_path}"
}

rc_contract_assert_served_tree_binding() {
  if [[ $# -ne 2 || "$1" != /* || \
        ! "$2" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]]; then
    rc_contract_fail invalid_usage served_tree_binding
    return 64
  fi
  local repo_root="$1"
  local expected_source_sha="$2"
  local status
  local paths=(
    backend/sealai_v2
    ':(exclude)backend/sealai_v2/eval'
    ':(exclude)backend/sealai_v2/tests'
    backend/requirements-v2.txt
    backend/.dockerignore
    backend/Dockerfile.v2
    backend/docker-entrypoint-v2.sh
  )

  if ! /usr/bin/git -C "${repo_root}" cat-file -e \
      "${expected_source_sha}^{commit}" 2>/dev/null; then
    rc_contract_fail invalid_source_commit served_tree_binding
    return 78
  fi
  status="$(
    /usr/bin/git -C "${repo_root}" status --porcelain=v1 --untracked-files=all \
      -- "${paths[@]}"
  )"
  if [[ -n "${status}" ]]; then
    rc_contract_fail dirty_served_tree served_tree_binding
    return 78
  fi
  if ! /usr/bin/git -C "${repo_root}" diff --quiet \
      "${expected_source_sha}" -- "${paths[@]}"; then
    rc_contract_fail source_tree_mismatch served_tree_binding
    return 78
  fi
}

rc_contract_assert_snapshot_volumes() {
  if [[ $# -ne 1 || "$1" != /usr/bin/docker ]]; then
    rc_contract_fail invalid_docker_binary docker
    return 64
  fi

  local docker_bin="$1"
  local kind
  local hash
  local volume
  local attestation
  local attestation_key
  for kind in postgres qdrant; do
    if [[ "${kind}" == postgres ]]; then
      hash="${RC_POSTGRES_SNAPSHOT_SHA256}"
      attestation_key=RC_POSTGRES_SNAPSHOT_VOLUME
    else
      hash="${RC_QDRANT_SNAPSHOT_SHA256}"
      attestation_key=RC_QDRANT_SNAPSHOT_VOLUME
    fi
    volume="sealai-rc-${kind}-${hash}"
    if ! attestation="$(
      /usr/bin/env -i \
        HOME=/nonexistent \
        PATH=/usr/sbin:/usr/bin:/sbin:/bin \
        DOCKER_HOST=unix:///var/run/docker.sock \
        "${docker_bin}" volume inspect \
          --format '{{ index .Labels "io.sealai.rc.kind" }}|{{ index .Labels "io.sealai.rc.snapshot-sha256" }}|{{ index .Labels "io.sealai.rc.seed-status" }}' \
          "${volume}" 2>/dev/null
    )"; then
      rc_contract_fail blocked_external "${attestation_key}"
      return 78
    fi
    if [[ "${attestation}" != "${kind}|${hash}|READY" ]]; then
      rc_contract_fail invalid_snapshot_attestation "${attestation_key}"
      return 78
    fi
  done
}

rc_contract_assert_tls_fixtures() {
  if [[ $# -ne 1 ]]; then
    rc_contract_fail invalid_usage tls_fixtures
    return 64
  fi
  local repo_root="$1"
  local domain
  local file
  local file_mode
  local tls_root="${repo_root}/ops/staging/tls"

  if [[ ! -d "${tls_root}" || -L "${tls_root}" ]]; then
    rc_contract_fail blocked_external RC_TLS_FIXTURE_STATUS
    return 78
  fi
  for domain in \
    sealai.net sealingai.de sealingai.com auth.sealai.net erp.sealai.net \
    crm.sealai.net dms.sealai.net; do
    if [[ -L "${tls_root}/live" || -L "${tls_root}/live/${domain}" ]]; then
      rc_contract_fail unsafe_tls_fixture RC_TLS_FIXTURE_STATUS
      return 78
    fi
    for file in fullchain.pem privkey.pem; do
      if [[ ! -f "${tls_root}/live/${domain}/${file}" || \
            -L "${tls_root}/live/${domain}/${file}" || \
            ! -O "${tls_root}/live/${domain}/${file}" ]]; then
        rc_contract_fail blocked_external RC_TLS_FIXTURE_STATUS
        return 78
      fi
      if [[ "${file}" == privkey.pem ]]; then
        file_mode="$(rc_contract_file_mode "${tls_root}/live/${domain}/${file}" || true)"
        case "${file_mode}" in
          400 | 600) ;;
          *)
            rc_contract_fail unsafe_tls_fixture RC_TLS_FIXTURE_STATUS
            return 78
            ;;
        esac
      fi
    done
  done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  set -euo pipefail
  readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  export PATH
  readonly SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
  readonly REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
  [[ $# -eq 1 ]] || {
    printf '%s\n' 'usage: ops/staging/rc-contract.sh eval|staging' >&2
    exit 64
  }
  rc_contract_load "${REPO_ROOT}" "$1"
  if [[ "$1" == staging ]]; then
    rc_contract_assert_tls_fixtures "${REPO_ROOT}"
  fi
  printf '%s\n' \
    '{"component":"sealai-rc-contract","result":"valid","evidence_class":"RC_STUB_NON_ELIGIBLE"}'
fi
