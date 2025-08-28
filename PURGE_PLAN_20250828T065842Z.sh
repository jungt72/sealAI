#!/usr/bin/env bash
set -euo pipefail
# Vorsicht: Dieser Plan löscht erst, wenn du die "#" vor den rm-Zeilen entfernst.

echo "Zu löschende Ordner/Dateien (wenn bestätigt):"

# 1) TRASH-Ordner
for d in TRASH_*; do
  [ -d "$d" ] || continue
  du -sh -- "$d" || true
  echo "# rm -rf -- "
done

# 2) Alte Audit-/Review-Artefakte
for d in AUDIT_* REVIEW_*; do
  [ -e "$d" ] || continue
  du -sh -- "$d" || true
  echo "# rm -rf -- "
done

# 3) Cleanup-Skripte
for f in CLEAN_*.sh; do
  [ -f "$f" ] || continue
  ls -l -- "$f" || true
  echo "# rm -f -- "
done

# 4) Offensichtliche Restdateien
for f in ERROR sse_output.txt sse_output.tx_; do
  [ -e "$f" ] || continue
  ls -l -- "$f" || true
  echo "# rm -f -- "
done

echo
echo "Hinweis:"
echo "  - Entferne die führenden # vor rm, dann ausführen: bash -bash"
