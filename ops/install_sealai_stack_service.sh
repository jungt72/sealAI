#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SERVICE_SRC="$SCRIPT_DIR/sealai-stack.service"
SERVICE_DST="/etc/systemd/system/sealai-stack.service"

# shellcheck source=production-release-gate-check.sh
source "${SCRIPT_DIR}/production-release-gate-check.sh"
production_release_gate_check "${SCRIPT_DIR}/production_release_gate.py" deploy

if [[ "$(id -u)" -ne 0 ]]; then
  echo "install_sealai_stack_service must run as root" >&2
  exit 1
fi

if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "sealai-stack service definition missing at $SERVICE_SRC" >&2
  exit 1
fi

cp -- "$SERVICE_SRC" "$SERVICE_DST"
systemctl daemon-reload
systemctl enable --now sealai-stack.service
