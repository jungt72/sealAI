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

run_iptables_command() {
  local cmd=("$@")
  log "running: ${cmd[*]}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "dry run; skipping iptables execution"
    return
  fi
  "${cmd[@]}"
}

ensure_docker_user_rule() {
  local direction=$1
  local subnet=$2
  if iptables -C DOCKER-USER "$direction" "$subnet" -j RETURN >/dev/null 2>&1; then
    log "DOCKER-USER ${direction} ${subnet} already allows Docker bridge traffic"
    return
  fi
  log "adding DOCKER-USER ${direction} ${subnet} -> RETURN"
  run_iptables_command iptables -I DOCKER-USER 1 "$direction" "$subnet" -j RETURN
}

ensure_output_rule() {
  local subnet=$1
  if iptables -C OUTPUT -d "$subnet" -j ACCEPT >/dev/null 2>&1; then
    log "OUTPUT already accepts ${subnet}"
    return
  fi
  log "allowing host OUTPUT to Docker bridge ${subnet}"
  run_iptables_command iptables -I OUTPUT 1 -d "$subnet" -j ACCEPT
}

cleanup_redundant_rules() {
  local redundant_patterns=(
    "-p tcp -m tcp --dport 3000 -j RETURN"
    "-p tcp -m tcp --dport 8000 -j RETURN"
    "-i lo -p tcp -m tcp --dport 3000 -j RETURN"
    "-i lo -p tcp -m tcp --dport 8000 -j RETURN"
  )
  for pattern in "${redundant_patterns[@]}"; do
    read -r -a args <<< "$pattern"
    while true; do
      if ! iptables -C DOCKER-USER "${args[@]}" >/dev/null 2>&1; then
        break
      fi
      log "removing redundant DOCKER-USER rule: ${pattern}"
      if [[ "$DRY_RUN" -eq 1 ]]; then
        log "dry run; skipping redundant-rule cleanup"
        break
      fi
      run_iptables_command iptables -D DOCKER-USER "${args[@]}"
    done
  done
}

network_from_address() {
  local addr=$1
  if [[ -z "$addr" ]]; then
    return 1
  fi
  local network
  network=$(ADDR="$addr" python3 <<'PY'
import ipaddress, os, sys
addr = os.environ.get("ADDR", "")
if not addr:
    sys.exit(1)
print(ipaddress.ip_network(addr, strict=False))
PY
)
  echo "$network"
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
require_command python3
ensure_chain_exists

mapfile -t BRIDGES < <(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(br-|docker0)' | cut -d'@' -f1)

if [[ "${#BRIDGES[@]}" -eq 0 ]]; then
  log "no Docker bridge interfaces detected"
  exit 0
fi

declare -A SEEN_SUBNET
declare -a SUBNETS

for bridge in "${BRIDGES[@]}"; do
  log "scanning bridge interface ${bridge}"
  while IFS= read -r address; do
    [[ -z "$address" ]] && continue
    network=$(network_from_address "$address")
    [[ -z "$network" ]] && continue
    if [[ -n "${SEEN_SUBNET[$network]:-}" ]]; then
      log "already processed ${network}"
      continue
    fi
    SEEN_SUBNET["$network"]=1
    SUBNETS+=("$network")
    log "detected Docker bridge subnet ${network}"
  done < <(ip -4 addr show dev "$bridge" | awk '/inet /{print $2}')
done

if [[ "${#SUBNETS[@]}" -eq 0 ]]; then
  log "no Docker IPv4 subnets found on bridges"
  exit 0
fi

cleanup_redundant_rules

for subnet in "${SUBNETS[@]}"; do
  ensure_docker_user_rule -s "$subnet"
  ensure_docker_user_rule -d "$subnet"
  ensure_output_rule "$subnet"
done

log "completed Docker bridge subnet rules"

# Validation commands:
# sudo /usr/local/bin/docker_firewall_fix.sh --dry-run
# sudo /usr/local/bin/docker_firewall_fix.sh
