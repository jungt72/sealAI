#!/usr/bin/env bash
set -euo pipefail

# Prüfe, dass wir im Repo-Root sind (heuristisch)
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
  echo "Bitte im Repo-Root ausführen (backend/ und frontend/ müssen existieren)." >&2
  exit 1
fi

declare -a CANDIDATES=()

# --- Backend: gezielt relevante Bereiche hinzufügen ---
# Kern: LangGraph, Chat, RAG, API-Routen, Config, DB, Alembic
while IFS= read -r f; do CANDIDATES+=("$f"); done < <(find backend/app/services -type f -name "*.py" \( -path "*/langgraph/*" -o -path "*/chat/*" -o -path "*/rag/*" \) 2>/dev/null)
while IFS= read -r f; do CANDIDATES+=("$f"); done < <(find backend/app/api -type f -name "*.py" 2>/dev/null)
while IFS= read -r f; do CANDIDATES+=("$f"); done < <(find backend/app/config -type f -name "*.py" 2>/dev/null)

# Häufig wichtige Einzeldateien
CANDIDATES+=(
  "backend/app/database.py"
  "backend/alembic/env.py"
  "backend/alembic.ini"
)

# --- Frontend: API-Proxies, Dashboard/Chat, Auth/Keycloak ---
while IFS= read -r f; do CANDIDATES+=("$f"); done < <(find frontend/app/api -type f \( -name "*.ts" -o -name "*.tsx" \) \( -path "*/langgraph/*" -o -path "*/chat/*" -o -path "*/v1/*" -o -path "*/api/*" \) 2>/dev/null)
while IFS= read -r f; do CANDIDATES+=("$f"); done < <(find frontend/app/dashboard -type f -name "*.tsx" 2>/dev/null)
while IFS= read -r f; do CANDIDATES+=("$f"); done < <(find frontend/app/auth -type f \( -name "*.ts" -o -name "*.tsx" \) 2>/dev/null || true)
while IFS= read -r f; do CANDIDATES+=("$f"); done < <(find frontend/app -maxdepth 2 -type f -name "middleware.ts" 2>/dev/null || true)

# Optional: zentrale Konfigurations-/Env-Beispiele (nur Namen, keine Secrets)
for f in ".env.example" ".env.local.example" "frontend/.env.example" "backend/.env.example"; do
  [ -f "$f" ] && CANDIDATES+=("$f")
done

# Dedup + nur existierende Dateien
declare -A SEEN=()
declare -a FILES=()
for f in "${CANDIDATES[@]}"; do
  [ -f "$f" ] || continue
  if [[ -z "${SEEN[$f]+x}" ]]; then
    SEEN[$f]=1
    FILES+=("$f")
  fi
done

if [ ${#FILES[@]} -eq 0 ]; then
  echo "Keine relevanten Dateien gefunden. Passen wir die Suchpfade an." >&2
  exit 2
fi

# Sortierte Ausgabe mit klaren Markern und Zeilennummern
IFS=$'\n' FILES=($(printf "%s\n" "${FILES[@]}" | sort))
unset IFS

for f in "${FILES[@]}"; do
  echo
  echo "========== BEGIN FILE: $f =========="
  nl -ba "$f"
  echo "=========== END FILE: $f ==========="
done
