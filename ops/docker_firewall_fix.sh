#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: docker_firewall_fix.sh [--dry-run]

  --dry-run   Display the iptables commands instead of running them.
  -h,--help   Show this help text.
EOF
}

log() {
  echo "[docker-firewall] $*"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "fatal: $1 is not installed"
    exit 1
  fi
}

ensure_chain_exists() {
  if ! iptables -nL DOCKER-USER >/dev/null 2>&1; then
    log "fatal: DOCKER-USER chain is missing"
    exit 1
  fi
}

insert_or_report() {
  local direction=$1
  local subnet=$2
  if iptables -C DOCKER-USER "$direction" "$subnet" -j RETURN >/dev/null 2>&1; then
    log "rule already present: DOCKER-USER ${direction} ${subnet}"
    return
  fi
  local cmd=(iptables -I DOCKER-USER 1 "$direction" "$subnet" -j RETURN)
  log "inserting rule: ${cmd[*]}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "dry run; skipping actual insertion"
    return
  fi
  "${cmd[@]}"
}

allow_output_to_subnet() {
  local subnet=$1
  if iptables -C OUTPUT -d "$subnet" -j ACCEPT >/dev/null 2>&1; then
    log "OUTPUT already accepts ${subnet}"
    return
  fi
  local cmd=(iptables -I OUTPUT 1 -d "$subnet" -j ACCEPT)
  log "allowing host OUTPUT to Docker bridge ${subnet}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "dry run; skipping actual insertion"
    return
  fi
  "${cmd[@]}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      -h|--help) usage; exit 0 ;;
      *)
        log "unknown argument: $1"
        usage
        exit 1
        ;;
    esac
    shift
  done
}

parse_args "$@"

if [[ "$(id -u)" -ne 0 ]]; then
  log "fatal: this script must be executed as root"
  exit 1
fi

require_command ip
require_command iptables
ensure_chain_exists

mapfile -t BRIDGES < <(ip -o link show | awk -F': ' '{print $2}' | grep '^br-' | cut -d'@' -f1)

if [[ "${#BRIDGES[@]}" -eq 0 ]]; then
  log "no Docker bridge interfaces detected"
  exit 0
fi

declare -A SEEN_SUBNET

for bridge in "${BRIDGES[@]}"; do
  log "processing bridge interface ${bridge}"
  while IFS= read -r subnet; do
    [[ -z "$subnet" ]] && continue
    if [[ -n "${SEEN_SUBNET[$subnet]:-}" ]]; then
      log "skipping duplicate subnet ${subnet}"
      continue
    fi
    SEEN_SUBNET["$subnet"]=1
    insert_or_report -s "$subnet"
    insert_or_report -d "$subnet"
    allow_output_to_subnet "$subnet"
  done < <(ip -4 addr show dev "$bridge" | awk '/inet /{print $2}')
done

log "completed Docker bridge subnet rules"
