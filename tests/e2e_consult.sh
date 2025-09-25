#!/usr/bin/env bash
set -euo pipefail

BASE=${BASE:-http://localhost:8000}
echo "Health:"; curl -fsS "$BASE/health" | jq .

chat="rev_fix_$(date +%s)"

# Turn 1
R1=$(curl -fsS -X POST "$BASE/api/v1/ai/beratung" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"$chat\",\"input_text\":\"Hydraulik-Stangendichtung Ersatz: Stange 40 mm, Bohrung 45 mm, Nutbreite 6 mm, Medium HLP46, Druck 200 bar, Temp 80 °C, Geschwindigkeit 0,8 m/s.\"}" \
  | jq -r .response)

# Turn 2
R2=$(curl -fsS -X POST "$BASE/api/v1/ai/beratung" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"$chat\",\"input_text\":\"Ja, Back-up-Ring ist zulässig. Bitte mit Stützring prüfen.\"}" \
  | jq -r .response)

# Turn 3
R3=$(curl -fsS -X POST "$BASE/api/v1/ai/beratung" \
  -H "Content-Type: application/json" \
  -d "{\"chat_id\":\"$chat\",\"input_text\":\"Bitte konkrete Empfehlung nennen.\"}" \
  | jq -r .response)

echo "— Prüfe R3 —"
hdr=$(echo "$R3" | grep -c -E '^🔎 \*\*Meine Empfehlung')
cta=$(echo "$R3" | grep -ci -E '^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}')
after=$(awk 'BEGIN{IGNORECASE=1} found{print} /^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}/{found=1; next}' <<< "$R3" | wc -l)
last_nonempty=$(printf "%s\n" "$R3" | awk 'NF{last=$0} END{print last}')

[[ "$hdr" -eq 1 ]] || { echo "FAIL: Header=$hdr != 1"; exit 1; }
[[ "$cta" -eq 1 ]] || { echo "FAIL: CTA=$cta != 1"; exit 1; }
[[ "$after" -eq 0 ]] || { echo "FAIL: $after Zeilen nach CTA"; exit 1; }
echo "$last_nonempty" | grep -qiE '^M(ö|o)chten Sie ein \*{0,2}Angebot\*{0,2}' \
  || { echo "FAIL: endet nicht an CTA"; exit 1; }

echo "OK ✅"
