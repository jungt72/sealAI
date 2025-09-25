#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
curl -fsS "$BASE/health" >/dev/null

chat="rwdr_fix_$(date +%s)"

R1=$(curl -fsS -X POST "$BASE/api/v1/ai/beratung" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"$chat\",\"input_text\":\"RWDR Ersatz: Welle 25 mm, Gehäuse 47 mm, Breite 7 mm, Medium Luft mit Überdruck 3 bar, Temp 60 °C, Drehzahl 1500 U/min.\"}" \
  | jq -r .response)

# Erwartung: Rückfrage zur Druckstufe
echo "$R1" | grep -qi 'Druckstufen' || { echo "FAIL: Keine Druckstufen-Rückfrage"; exit 1; }

R2=$(curl -fsS -X POST "$BASE/api/v1/ai/beratung" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"$chat\",\"input_text\":\"Druckstufenlösung ist zulässig.\"}" \
  | jq -r .response)

# Empfehlung soll nur 1x erscheinen & an CTA enden
hdr=$(echo "$R2" | grep -c -E '^🔎 \*\*Meine Empfehlung')
cta=$(echo "$R2" | grep -ci -E '^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}')
after=$(awk 'BEGIN{IGNORECASE=1} found{print} /^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}/{found=1; next}' <<< "$R2" | wc -l)
[[ "$hdr" -eq 1 && "$cta" -eq 1 && "$after" -eq 0 ]] || { echo "FAIL: Formatfehler in R2"; exit 1; }

echo "OK ✅"
