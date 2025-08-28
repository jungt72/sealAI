#!/usr/bin/env bash
set -euo pipefail

echo "Lösche alle Altlasten jetzt endgültig..."

# 1) TRASH-Ordner
for d in TRASH_*; do
  [ -d "$d" ] || continue
  du -sh -- "$d" || true
  rm -rf -- "$d"
done

# 2) Alte Audit-/Review-Artefakte
for d in AUDIT_* REVIEW_*; do
  [ -e "$d" ] || continue
  du -sh -- "$d" || true
  rm -rf -- "$d"
done

# 3) Cleanup-Skripte
for f in CLEAN_*.sh; do
  [ -f "$f" ] || continue
  ls -l -- "$f" || true
  rm -f -- "$f"
done

# 4) Offensichtliche Restdateien
for f in ERROR sse_output.txt sse_output.tx_; do
  [ -e "$f" ] || continue
  ls -l -- "$f" || true
  rm -f -- "$f"
done

echo "Bereinigung abgeschlossen."
