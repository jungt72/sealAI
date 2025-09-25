#!/usr/bin/env bash
set -euo pipefail
TRASH="TRASH_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$TRASH"
while IFS= read -r p; do
  [[ -z "$p" ]] && continue
  q="${p#./}"
  [[ -e "$q" ]] || continue
  size="$(du -sh -- "$q" 2>/dev/null | cut -f1 || stat -c%s "$q" 2>/dev/null || echo 0)"
  echo "-> $q ($size)"
  if git ls-files --error-unmatch "$q" >/dev/null 2>&1; then cmd="git mv -f"; else cmd="mv -f"; fi
  $cmd -- "$q" "$TRASH"/
done < "$L/POTENTIAL_STALE.txt"
echo "Moved to: $TRASH"
