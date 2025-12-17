#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SRC="$SCRIPT_DIR/sealai-stack.service"
SERVICE_DST="/etc/systemd/system/sealai-stack.service"

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
