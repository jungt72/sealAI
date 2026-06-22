#!/usr/bin/env bash
# relay.sh — Gated-Relay-Orchestrator  (Builder-CC -> Gate -> Reviewer-CC)
# ---------------------------------------------------------------------------
# Doktrin:
#   * merge / deploy passieren NIE in diesem Skript -> owner-triggered only.
#   * deterministisches Gate ist die Wahrheit; der LLM-Reviewer ist Filter
#     OBENDRAUF, nie der Trust-Anchor.
#   * Builder und Reviewer sind getrennte `claude -p`-Aufrufe (frischer,
#     unabhängiger Kontext je Aufruf -> echte Reviewer-Unabhängigkeit).
#   * Exit-Codes:  0 = baufertig (dein Trigger fehlt noch)
#                  2 = Eskalation an Owner (Zahl/Limit/Selektion/Ambiguität)
#                  3 = Iterations-Cap ohne grünes Gate
# ---------------------------------------------------------------------------
set -euo pipefail

# ---- Konfiguration (per ENV überschreibbar) -------------------------------
REPO="${REPO:-$HOME/sealai}"                    # echte Repo-Wurzel
INCREMENT="${1:?Nutzung: relay.sh <pfad/zur/increment-aufgabe.md>}"
MAX_ITER="${MAX_ITER:-3}"
MAX_TURNS="${MAX_TURNS:-20}"
MAX_BUDGET="${MAX_BUDGET:-1.50}"
MODEL="${MODEL:-sonnet}"

BUILDER_CONTRACT="ops/contracts/BUILDER_CONTRACT.md"
REVIEW_CONTRACT="ops/contracts/REVIEW_CONTRACT.md"
ESCALATION_FILE="ops/ESCALATION.md"
GATE="ops/gate.sh"

# Builder: lesen/schreiben/bauen JA — aber kein push/merge/deploy/release/flip.
BUILDER_ALLOW="Read,Edit,Write,Grep,Glob,Bash"
BUILDER_DENY='Bash(git push:*),Bash(git merge:*),Bash(gh pr merge:*),Bash(*deploy*),Bash(*release-backend*),Bash(*v2-flip*),Bash(docker compose up*),Bash(rm -rf:*)'
# Reviewer: strikt read-only -> kann per Konstruktion nichts verändern.
REVIEW_ALLOW="Read,Grep,Glob"
REVIEW_DENY="Write,Edit,Bash"
# ---------------------------------------------------------------------------

cd "$REPO"
log(){ printf '\n\033[1m[relay]\033[0m %s\n' "$*"; }
die(){ printf '\n\033[1;31m[relay:STOP]\033[0m %s\n' "$*"; exit "${2:-1}"; }

[ -f "$INCREMENT" ]      || die "Increment-Datei fehlt: $INCREMENT"
[ -f "$GATE" ]           || die "Gate fehlt: $GATE"
command -v jq >/dev/null || die "jq nicht installiert (apt install jq)"
[ -z "$(git status --porcelain)" ] || die "Working-Tree nicht sauber — committe/stashe WIP vor dem Relay-Lauf."
rm -f "$ESCALATION_FILE"

BASELINE="$(git rev-parse HEAD)"
log "Baseline $BASELINE | Increment $INCREMENT | Cap $MAX_ITER"

cleanup_on_fail() {
  local rc=$?
  [ "$rc" -eq 0 ] && return 0          # Erfolg (PASS): Diff im Tree lassen
  [ -z "${BASELINE:-}" ] && return 0   # vor Baseline gestorben: nichts zu rollen
  echo "[relay] Rollback auf Baseline (Lauf nicht erfolgreich, rc=$rc); ESCALATION.md bleibt."
  git reset -q --hard "$BASELINE"
  git clean -fdq
}
trap cleanup_on_fail EXIT

findings=""   # nur Remediation im eingefrorenen Scope — NIE neuer Scope

for (( i=1; i<=MAX_ITER; i++ )); do
  # ---- 1) BUILDER ----------------------------------------------------------
  log "Runde $i/$MAX_ITER — BUILDER"
  if [ -z "$findings" ]; then
    build_prompt="Lies $BUILDER_CONTRACT und setze AUSSCHLIESSLICH das Increment in $INCREMENT um."
  else
    build_prompt="Lies $BUILDER_CONTRACT. Behebe AUSSCHLIESSLICH diese Befunde im eingefrorenen Scope (kein neuer Scope):
$findings"
  fi

  claude -p "$build_prompt" \
    --permission-mode dontAsk \
    --allowedTools "$BUILDER_ALLOW" \
    --disallowedTools "$BUILDER_DENY" \
    --max-turns "$MAX_TURNS" \
    --max-budget-usd "$MAX_BUDGET" \
    --model "$MODEL" \
    --output-format json > /tmp/relay_build.json \
    || die "Builder-Lauf fehlgeschlagen (siehe /tmp/relay_build.json)"

  # ---- 2) ESKALATION? -> fail-closed an Owner ------------------------------
  if [ -f "$ESCALATION_FILE" ]; then
    log "ESKALATION durch Builder:"; cat "$ESCALATION_FILE"
    die "Builder hat eskaliert — Owner-Entscheidung nötig (Zahl/Limit/Selektion/Ambiguität)." 2
  fi

  # ---- 3) DETERMINISTISCHES GATE — die Wahrheit ----------------------------
  log "Runde $i — GATE (deterministisch)"
  if ! bash "$GATE" > /tmp/relay_gate.txt 2>&1; then
    findings="GATE ROT:
$(cat /tmp/relay_gate.txt)"
    log "Gate rot -> Remediation."
    continue
  fi
  log "Gate grün."

  # ---- 4) REVIEWER (unabhängig, read-only) ---------------------------------
  log "Runde $i — REVIEWER"
  git add -A
  diff="$(git --no-pager diff --cached "$BASELINE")"
  git reset -q
  review_input="$(cat "$REVIEW_CONTRACT")

GATE-AUSGABE (grün):
$(cat /tmp/relay_gate.txt)

DIFF gegen Baseline $BASELINE:
$diff

Gib AUSSCHLIESSLICH das Verdict-JSON aus, nichts sonst (kein Markdown, keine Fences)."

  claude -p "$review_input" \
    --permission-mode dontAsk \
    --allowedTools "$REVIEW_ALLOW" \
    --disallowedTools "$REVIEW_DENY" \
    --max-turns 6 \
    --output-format json > /tmp/relay_review.json \
    || die "Reviewer-Lauf fehlgeschlagen."

  inner="$(jq -r '.result' /tmp/relay_review.json | sed 's/```json//g; s/```//g')"
  verdict="$(echo "$inner" | jq -r '.verdict' 2>/dev/null || echo PARSE_ERROR)"

  case "$verdict" in
    PASS)
      printf '\n\033[1;32m[relay:READY]\033[0m Increment baufertig — NICHT gemerged/deployed.\n'
      echo "Diff liegt uncommitted im Working Tree. Dein Schritt: prüfen -> Owner-Trigger (commit/merge/deploy)."
      exit 0 ;;
    BLOCK)
      findings="REVIEWER BLOCK:
$(echo "$inner" | jq -r '.findings' 2>/dev/null)"
      log "Reviewer BLOCK -> Remediation."
      continue ;;
    *)
      die "Reviewer-Verdict nicht parsebar ($verdict). Roh: $(cat /tmp/relay_review.json)" ;;
  esac
done

die "Iterations-Cap ($MAX_ITER) ohne grünes Gate + PASS. Letzte Befunde:
$findings" 3
