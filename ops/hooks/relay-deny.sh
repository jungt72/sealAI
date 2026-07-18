#!/bin/bash -p
cmd="$(cat | jq -r '.tool_input.command // empty')"
case "$cmd" in
  *"git merge"*|*"git push"*|*v2-flip*|*release-backend*|*"docker compose up"*)
    echo "relay-deny: blockiert -> '$cmd' (owner-triggered only)" >&2; exit 2 ;;
esac
exit 0
