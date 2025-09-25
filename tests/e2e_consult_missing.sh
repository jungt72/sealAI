#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
curl -fsS "$BASE/health" >/dev/null

chat="missing_$(date +%s)"

R1=$(curl -fsS -X POST "$BASE/api/v1/ai/beratung" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"$chat\",\"input_text\":\"Bitte Empfehlung für RWDR.\"}" \
  | jq -r .response)

# Soll Rückfragen enthalten, aber KEINE Empfehlung
echo "$R1" | grep -qiE 'Welche|Bitte|Fehlen|Angaben|Drehzahl|Druck|Temperatur' || { echo "FAIL: keine Rückfrage erkannt"; exit 1; }
echo "$R1" | grep -q '^🔎 \*\*Meine Empfehlung' && { echo "FAIL: Empfehlung trotz fehlender Pflichtfelder"; exit 1; }

echo "OK ✅"
