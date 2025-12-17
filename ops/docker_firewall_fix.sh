#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
MODE="relaxed"
PORTS="3000,8000"
APPLY_UFW=1
RUN_TESTS=0
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_SMOKE="$OPS_DIR/stack_smoke.sh"

usage() {
  cat <<'EOF'
Usage: docker_firewall_fix.sh [OPTIONS]

  --dry-run             Show actions without changing rules.
  --mode MODE           relaxed|strict (default: relaxed)
  --ports "P1,P2,..."   Ports required in strict mode (default: 3000,8000).
  --apply-ufw           Apply matching UFW rules (default).
  --no-ufw              Skip ufw rule adjustments.
  --test                Run stack smoke diagnostics after configuring rules.
  -h,--help             Show this help text.
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

run_command() {
  local cmd=("$@")
  log "running: ${cmd[*]}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "dry run; counting command as successful"
    return 0
  fi
  "${cmd[@]}"
}

network_from_address() {
  local addr=$1
  if [[ -z "$addr" ]]; then
    return 1
  fi
  ADDR="$addr" python3 -c "import ipaddress, os, sys; addr=os.environ.get('ADDR'); sys.stdout.write(str(ipaddress.ip_network(addr, strict=False)))"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --mode)
        if [[ $# -lt 2 ]]; then
          log "fatal: --mode requires an argument"
          usage
          exit 1
        fi
        MODE="$2"
        shift
        ;;
      --ports)
        if [[ $# -lt 2 ]]; then
          log "fatal: --ports requires an argument"
          usage
          exit 1
        fi
        PORTS="$2"
        shift
        ;;
      --apply-ufw) APPLY_UFW=1 ;;
      --no-ufw) APPLY_UFW=0 ;;
      --test) RUN_TESTS=1 ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        log "fatal: unknown argument: $1"
        usage
        exit 1
        ;;
    esac
    shift
  done
}

ufw_status_lines() {
  local status
  if ! status=$(ufw status 2>&1); then
    log "warning: unable to read ufw status: $status"
    return 1
  fi
  if grep -q '^Status: active' <<< "$status"; then
    UFW_ACTIVE=1
  else
    UFW_ACTIVE=0
  fi

  UFW_RULE_LINES=()
  local divider_seen=0
  while IFS= read -r line; do
    if [[ "$line" =~ ^-+ ]]; then
      divider_seen=1
      continue
    fi
    if [[ $divider_seen -eq 0 ]]; then
      continue
    fi
    [[ -z "$line" ]] && continue
    UFW_RULE_LINES+=("$line")
  done <<< "$status"
}

ufw_rule_exists() {
  local cidr=$1
  shift
  for line in "${UFW_RULE_LINES[@]:-}"; do
    [[ "$line" != *"$cidr"* ]] && continue
    local ok=1
    for cond in "$@"; do
      [[ "$line" != *"$cond"* ]] && ok=0 && break
    done
    [[ $ok -eq 1 ]] && return 0
  done
  return 1
}

ensure_chain_exists() {
  if ! iptables -nL DOCKER-USER >/dev/null 2>&1; then
    log "fatal: DOCKER-USER chain is missing"
    exit 1
  fi
}

remove_port_specific_returns() {
  local port
  for port in "${PORTS_ARRAY[@]}"; do
    for direction in "--dport" "--sport"; do
      while true; do
        if ! iptables -C DOCKER-USER -p tcp -m tcp "$direction" "$port" -j RETURN >/dev/null 2>&1; then
          break
        fi
        log "removing DOCKER-USER rule with $direction $port"
        if [[ "$DRY_RUN" -eq 1 ]]; then
          log "dry run; skipping removal"
          break
        fi
        run_command iptables -D DOCKER-USER -p tcp -m tcp "$direction" "$port" -j RETURN
      done
    done
  done
}

ensure_return_rule_at_top() {
  local direction=$1
  local subnet=$2
  while true; do
    if ! iptables -C DOCKER-USER "$direction" "$subnet" -j RETURN >/dev/null 2>&1; then
      break
    fi
    # Remove existing so we can reinsert the rule at the top for idempotent ordering.
    log "removing existing DOCKER-USER ${direction} ${subnet} before reinserting"
    if [[ "$DRY_RUN" -eq 1 ]]; then
      log "dry run; skipping removal"
      break
    fi
    run_command iptables -D DOCKER-USER "$direction" "$subnet" -j RETURN
  done
  log "ensuring DOCKER-USER ${direction} ${subnet} -> RETURN at top"
  run_command iptables -I DOCKER-USER 1 "$direction" "$subnet" -j RETURN
}

ensure_output_accept_for_subnet() {
  local subnet=$1
  if [[ "$OUTPUT_POLICY" != "DROP" ]]; then
    log "OUTPUT policy is ${OUTPUT_POLICY}; skipping OUTPUT rule for ${subnet}"
    return 0
  fi
  if [[ "$UFW_AVAILABLE" -eq 0 ]]; then
    log "ufw unavailable; skipping OUTPUT rule for ${subnet}"
    return 0
  fi
  if [[ "$UFW_ACTIVE" -ne 1 ]]; then
    log "ufw inactive; skipping OUTPUT rule for ${subnet}"
    return 0
  fi
  if iptables -C OUTPUT -d "$subnet" -j ACCEPT >/dev/null 2>&1; then
    log "OUTPUT already accepts ${subnet}"
    return 0
  fi
  log "allowing OUTPUT to Docker bridge ${subnet} (policy DROP + ufw enabled)"
  run_command iptables -I OUTPUT 1 -d "$subnet" -j ACCEPT
}

ensure_ufw_relaxed_rules() {
  if [[ "$APPLY_UFW" -eq 0 ]]; then
    log "ufw adjustments disabled by flag; skipping relaxed mode"
    return
  fi
  if [[ "$UFW_AVAILABLE" -eq 0 ]]; then
    log "ufw is not available; cannot manage rules"
    return
  fi
  if [[ "$UFW_ACTIVE" -ne 1 ]]; then
    log "ufw is not active; skip relaxed ufw adjustments"
    return
  fi
  for cidr in "${SUBNETS[@]}"; do
    if ufw_rule_exists "$cidr" "ALLOW OUT"; then
      log "ufw already allows out to ${cidr}"
      continue
    fi
    log "enabling ufw allow out to ${cidr}"
    run_command ufw allow out to "$cidr"
  done
}

ensure_ufw_strict_rules() {
  if [[ "$APPLY_UFW" -eq 0 ]]; then
    log "ufw adjustments disabled by flag; skipping strict mode"
    return
  fi
  if [[ "$UFW_AVAILABLE" -eq 0 ]]; then
    log "ufw is not available; cannot manage rules"
    return
  fi
  if [[ "$UFW_ACTIVE" -ne 1 ]]; then
    log "ufw is not active; skip strict ufw adjustments"
    return
  fi
  local port
  for cidr in "${SUBNETS[@]}"; do
    for port in "${PORTS_ARRAY[@]}"; do
      local pattern="${port}/tcp"
      if ufw_rule_exists "$cidr" "ALLOW OUT" "$pattern"; then
        log "ufw already allows ${port}/tcp out to ${cidr}"
        continue
      fi
      log "enabling ufw allow out proto tcp to ${cidr} port ${port}"
      run_command ufw allow out proto tcp to "$cidr" port "$port"
    done
  done
}

parse_args "$@"

if [[ "$MODE" != "relaxed" && "$MODE" != "strict" ]]; then
  log "fatal: unsupported mode ${MODE}"
  usage
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  log "fatal: must be run as root"
  exit 1
fi

require_command ip
require_command iptables
require_command python3

PORTS_ARRAY=()
IFS=',' read -r -a raw_ports <<< "$PORTS"
for port in "${raw_ports[@]}"; do
  port=${port// /}
  [[ -z "$port" ]] && continue
  PORTS_ARRAY+=("$port")
done

UFW_AVAILABLE=0
UFW_ACTIVE=0
UFW_RULE_LINES=()
if command -v ufw >/dev/null 2>&1; then
  UFW_AVAILABLE=1
  ufw_status_lines || true
else
  log "ufw command unavailable; skipping ufw detection"
fi

ensure_chain_exists

mapfile -t BRIDGES < <(ip -o link show | awk -F': ' '{print $2}' | grep -E '^(br-[[:alnum:]]+|docker0)$' || true)

SUBNETS=()
declare -A SEEN_SUBNET
for bridge in "${BRIDGES[@]}"; do
  if ! ip link show "$bridge" >/dev/null 2>&1; then
    continue
  fi
  if ! ip link show "$bridge" | grep -q 'state UP'; then
    log "bridge ${bridge} is not up; skipping"
    continue
  fi
  log "scanning bridge interface ${bridge}"
  while IFS= read -r addr; do
    [[ -z "$addr" ]] && continue
    net=$(network_from_address "$addr")
    [[ -z "$net" ]] && continue
    if [[ -n "${SEEN_SUBNET[$net]:-}" ]]; then
      log "already processed ${net}"
      continue
    fi
    SEEN_SUBNET["$net"]=1
    SUBNETS+=("$net")
    log "detected Docker bridge subnet ${net}"
  done < <(ip -4 addr show dev "$bridge" | awk '/inet /{print $2}')
done

if [[ "${#SUBNETS[@]}" -eq 0 ]]; then
  log "no Docker bridge IPv4 subnets detected"
  exit 0
fi

remove_port_specific_returns

for subnet in "${SUBNETS[@]}"; do
  ensure_return_rule_at_top -s "$subnet"
  ensure_return_rule_at_top -d "$subnet"
done

OUTPUT_POLICY=$(iptables -L OUTPUT -n | awk 'NR==1 {print $4}' | tr -d ')')
for subnet in "${SUBNETS[@]}"; do
  ensure_output_accept_for_subnet "$subnet"
done

if [[ "$MODE" == "relaxed" ]]; then
  ensure_ufw_relaxed_rules
else
  ensure_ufw_strict_rules
fi

if [[ "$RUN_TESTS" -eq 1 ]]; then
  if [[ ! -x "$STACK_SMOKE" ]]; then
    log "fatal: stack smoke script $STACK_SMOKE missing or not executable"
    exit 1
  fi
  if ! "$STACK_SMOKE"; then
    smoke_code=$?
    case "$smoke_code" in
      11) log "services not running (compose/systemd issue)" ;;
      22) log "listeners missing (container crash or port mapping issue)" ;;
      33) log "curl blocked/timeouts (firewall/routing issue)" ;;
      *)  log "stack smoke failed (exit code $smoke_code)" ;;
    esac
    exit "$smoke_code"
  fi
fi

log "docker firewall fix complete"
