#!/usr/bin/env bash
set -euo pipefail

CHAIN="DOCKER-USER"

ensure_chain() {
  if ! iptables -nL "$CHAIN" >/dev/null 2>&1; then
    iptables -N "$CHAIN"
  fi
}

rule_exists() {
  local rule=("$@")
  iptables -C "$CHAIN" "${rule[@]}" >/dev/null 2>&1
}

insert_rule() {
  local rule=("$@")
  if ! rule_exists "${rule[@]}"; then
    iptables -I "$CHAIN" "${rule[@]}"
  fi
}

append_rule() {
  local rule=("$@")
  if ! rule_exists "${rule[@]}"; then
    iptables -A "$CHAIN" "${rule[@]}"
  fi
}

main() {
  ensure_chain

  # 1) allow established/related and return to Docker
  insert_rule -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN

  # 2) allow DNS
  insert_rule -p udp --dport 53 -j RETURN
  insert_rule -p tcp --dport 53 -j RETURN

  # 3) allow HTTP/HTTPS
  insert_rule -p tcp --dport 80 -j RETURN
  insert_rule -p tcp --dport 443 -j RETURN

  # 4) optional NTP
  insert_rule -p udp --dport 123 -j RETURN

  # 5) explicit block for known abuse target (documented)
  insert_rule -p udp -d 103.227.209.22 -j DROP

  # 6) default-deny for all other container egress
  append_rule -j DROP
}

main "$@"

