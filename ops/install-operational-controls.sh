#!/bin/bash -p
# Launch only the hash-bound GATE-08 operational-control bootstrap.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

usage() {
  printf 'Usage: %s [--source-repository ABSOLUTE_LOCAL_PATH --apply]\n' "$0"
}

if [[ "$#" -eq 0 ]]; then
  printf '%s\n' \
    'operational-control installer dry-run: no files changed' \
    'requires the fixed root-owned GATE-08 approval' \
    'would clone the approved commit into a root-private /run checkout' \
    'would re-hash the exact approved artifact set and target preconditions' \
    'would atomically install four fixed controls with private rollback evidence'
  exit 0
fi
if [[ "$#" -ne 3 || "$1" != --source-repository || "$3" != --apply ]]; then
  usage >&2
  exit 64
fi
if [[ "$2" != /* || "$2" == *$'\n'* || "$2" == *$'\r'* ]]; then
  printf 'operational-control installer: source repository must be absolute\n' >&2
  exit 64
fi
if [[ "${EUID}" -ne 0 ]]; then
  printf 'operational-control installer: --apply requires root\n' >&2
  exit 77
fi

readonly SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
readonly BOOTSTRAP="${SOURCE_DIR}/bootstrap_gate08_operational_controls.py"
[[ -f "${BOOTSTRAP}" && ! -L "${BOOTSTRAP}" ]] || {
  printf 'operational-control installer: bootstrap path is unsafe\n' >&2
  exit 78
}
exec /usr/bin/python3 -I "${BOOTSTRAP}" \
  --source-repository "$2" --apply
