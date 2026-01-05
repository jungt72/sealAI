#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() {
  echo "[install-docker-firewall] $*"
}

if [[ "$(id -u)" -ne 0 ]]; then
  log "fatal: installer must run as root"
  exit 1
fi

log "installing docker firewall fixer to /usr/local/bin"
install -m 0755 "${SCRIPT_DIR}/docker_firewall_fix.sh" /usr/local/bin/docker_firewall_fix.sh

log "installing systemd unit to /etc/systemd/system"
install -m 0644 "${SCRIPT_DIR}/docker-firewall.service" /etc/systemd/system/docker-firewall.service

log "reloading systemd configuration"
systemctl daemon-reload

log "enabling and starting docker-firewall.service"
systemctl enable --now docker-firewall.service
