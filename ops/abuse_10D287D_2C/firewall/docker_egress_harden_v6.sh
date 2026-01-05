#!/usr/bin/env bash
set -euo pipefail

CHAIN="DOCKER-USER"

ensure_chain() {
  if ! ip6tables -nL "$CHAIN" >/dev/null 2>&1; then
    ip6tables -N "$CHAIN"
  fi
}

rule_exists() {
  local rule=("$@")
  ip6tables -C "$CHAIN" "${rule[@]}" >/dev/null 2>&1
}

insert_rule() {
  local rule=("$@")
  if ! rule_exists "${rule[@]}"; then
    ip6tables -I "$CHAIN" "${rule[@]}"
  fi
}

append_rule() {
  local rule=("$@")
  if ! rule_exists "${rule[@]}"; then
    ip6tables -A "$CHAIN" "${rule[@]}"
  fi
}

main() {
  ensure_chain

  insert_rule -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
  insert_rule -p udp --dport 53 -j RETURN
  insert_rule -p tcp --dport 53 -j RETURN
  insert_rule -p tcp --dport 80 -j RETURN
  insert_rule -p tcp --dport 443 -j RETURN
  insert_rule -p udp --dport 123 -j RETURN
  append_rule -j DROP
}

main "$@"

