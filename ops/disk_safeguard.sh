#!/bin/bash -p
# Compatibility entry point for the retired disk_safeguard cron command.
# The canonical guard is observation-only and never removes Docker or host data.
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"

# The historical entry is a user cron and cannot read the root-private
# canonical config. Once the GATE-08 rollout installs systemd, this shim is only
# a harmless marker until that exact cron line is retired.
if [[ "$(id -u)" -ne 0 ]]; then
  printf '%s\n' '{"component":"sealai-disk-guard-legacy-cron","result":"retirement_pending","monitoring_authority":"systemd"}'
  exit 0
fi

exec "${SCRIPT_DIR}/docker-disk-guard.sh" check "$@"
