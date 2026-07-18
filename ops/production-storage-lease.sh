#!/bin/bash -p
# Source this file, then acquire one lease across the whole storage mutation.

_acquire_storage_lease() {
  local lock_file="$1"
  local guard="$2"
  local config="$3"
  local expected="$4"
  local privilege_mode="$5"
  local expected_identity
  local inherited_identity
  local observed

  if [[ ! -x "${guard}" ]]; then
    printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"canonical_guard_unavailable"}' >&2
    return 78
  fi
  if [[ "${privilege_mode}" != sudo && ( ! -f "${config}" || -L "${config}" ) ]]; then
    printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"canonical_guard_config_unavailable"}' >&2
    return 78
  fi
  if [[ -L "${lock_file}" ]]; then
    printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"mutation_lock_symlink"}' >&2
    return 78
  fi
  observed="$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- "${lock_file}" 2>/dev/null || true)"
  if [[ "${observed}" != "${expected}" ]]; then
    printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"mutation_lock_unsafe"}' >&2
    return 78
  fi

  expected_identity="$(/usr/bin/stat -Lc '%d:%i' -- "${lock_file}" 2>/dev/null || true)"
  if [[ -e /proc/self/fd/9 ]]; then
    inherited_identity="$(/usr/bin/stat -Lc '%d:%i' -- /proc/self/fd/9 2>/dev/null || true)"
    if [[ -z "${expected_identity}" || "${inherited_identity}" != "${expected_identity}" ]]; then
      printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"inherited_lock_invalid"}' >&2
      return 78
    fi
    # flock is associated with the inherited open-file description. This is
    # reentrant for the V2 release -> pre-migration-backup call chain; if an
    # unlocked matching descriptor was inherited, it acquires it here.
    if ! /usr/bin/flock -n 9; then
      printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"inherited_lock_not_owned"}' >&2
      return 75
    fi
    if [[ "${privilege_mode}" == sudo ]]; then
      /usr/bin/sudo -n -- "${guard}" --config "${config}" preflight
    else
      "${guard}" --config "${config}" preflight
    fi
    return
  fi

  exec 9<>"${lock_file}" || {
    printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"mutation_lock_unavailable"}' >&2
    return 75
  }
  observed="$(/usr/bin/stat -Lc '%F:%a:%U:%G' -- /proc/self/fd/9 2>/dev/null || true)"
  inherited_identity="$(/usr/bin/stat -Lc '%d:%i' -- /proc/self/fd/9 2>/dev/null || true)"
  if [[ "${observed}" != "${expected}" || "${inherited_identity}" != "${expected_identity}" ]]; then
    printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"mutation_lock_changed"}' >&2
    exec 9>&-
    return 78
  fi
  if ! /usr/bin/flock -n 9; then
    printf '%s\n' '{"component":"sealai-production-storage-lease","result":"blocked","reason_code":"mutation_lock_busy"}' >&2
    exec 9>&-
    return 75
  fi

  # The descriptor stays open in the calling shell and all of its children.
  # It is released automatically only when the complete entrypoint exits.
  if [[ "${privilege_mode}" == sudo ]]; then
    /usr/bin/sudo -n -- "${guard}" --config "${config}" preflight
  else
    "${guard}" --config "${config}" preflight
  fi
}

acquire_production_storage_lease() {
  _acquire_storage_lease \
    /run/lock/sealai-storage-mutation.lock \
    /usr/local/libexec/sealai/docker-disk-guard.sh \
    /etc/sealai/disk-guard.json \
    'regular file:660:root:thorsten' \
    sudo
}
