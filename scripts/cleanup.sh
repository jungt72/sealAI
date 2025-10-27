#!/usr/bin/env bash
set -euo pipefail
DRY=1
[[ "${1:-}" == "--apply" || "${1:-}" == "--no-dry-run" ]] && DRY=0
GUARDS_REGEX='^(\.env|secrets/|keycloak/realm-exports|migrations/versions/|.*\.(lic|pdf|bin|png|jpg|zip)|.*(LICENSE|AGB|LEGAL).*)$'
STAMP="$(date +%Y-%m-%d_%H%M%S)"; TRASH=".trash/${STAMP}"; mkdir -p "$TRASH"
MODE_MSG=$([[ $DRY -eq 1 ]] && echo "(dry-run)" || echo "")
echo "==> Cleanup $MODE_MSG | TRASH=$TRASH"
while IFS= read -r line; do
  [[ "$line" =~ ^DELETE\  ]] || continue
  path="$(echo "$line" | cut -d' ' -f2- | cut -d'|' -f1 | xargs)"
  [[ -e "$path" ]] || { echo "skip (missing): $path"; continue; }
  if echo "$path" | egrep -q "$GUARDS_REGEX"; then echo "GUARD skip: $path"; continue; fi
  if [[ $DRY -eq 1 ]]; then echo "[dry-run] would move $path -> $TRASH/$path"
  else mkdir -p "$TRASH/$(dirname "$path")"; git rm -r --cached --ignore-unmatch "$path" >/dev/null 2>&1 || true; mv "$path" "$TRASH/$path"; echo "moved: $path -> $TRASH/$path"; fi
done < CLEANUP_REPORT.md
echo "Done. Use '--apply' to execute moves."
