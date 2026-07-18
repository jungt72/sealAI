# Remediation-PR-Bestand — Triage 2026-07-18

Bestandsaufnahme der offenen `remediation/p{0,1,2}-*`-Drafts und der übrigen offenen PRs.
Reine Sichtung/Priorisierung — keine der unten genannten PRs wurde gemerged, geschlossen
oder rebased. Inhaltliche Freigabe von Security-/Release-relevantem Code bleibt Owner-Sache.

## Kernbefund

Das ist **keine Liste von 16 unabhängigen PRs**, sondern:

- **1 zusammenhängender Stack aus 12 offenen Draft-PRs** (#293–#305), jede PR basiert auf dem
  Branch der vorherigen — kein Merge in dieser Kette ist möglich, ohne alle darunterliegenden
  vorher zu mergen.
- **1 freistehender Draft** (#311), direkt gegen `main`, deutlich frischer als der Stack.
- **2 routinemäßige Dependabot-PRs** (#222, #223, dazu #308 aus einer früheren Sichtung).
- **7 alte, vom Stack unabhängige Alt-PRs** (#6, #5, #89, #120, #127, #187, #205, #208).

## Der Stack (Basis → Spitze)

```
#291  remediation/p0-storage-safety           MERGED 2026-07-15 (Ursprung des aktiven
      ↓                                        GATE-10-Freezes, siehe production-release-state.json)
#293  remediation/p0-redis-stability           CONFLICTING gegen seine eigene Basis
      ↓                                        (Stack seit #291-Merge nicht mehr rebased)
#295  remediation/p1-release-integrity
      ↓
#294  remediation/p1-network-segmentation
      ↓
#296  remediation/p1-auth-cost-control
      ↓
#297  remediation/p1-data-authority
      ↓
#298  remediation/p2-dr-recovery
      ↓
#299  remediation/p2-monitoring-hardening
      ↓
#300  remediation/p2-supply-chain
      ↓
#301  remediation/agent-relay
      ├→ #302 remediation/p1-data-runtime-authority → #305 remediation/p1-api-lifecycle
      ├→ #303 remediation/p2-dr-external-receipts
      └→ #304 remediation/p1-reviewer-governance
```

**Kritischer Befund:** Die Basis der gesamten Kette (`remediation/p0-storage-safety`) ist bereits
als PR #291 in `main` gemerged — das ist der tatsächliche Ursprung des aktiven Production-Release-
Freezes (GATE-10). Der nächste Stack-Eintrag (#293) zeigt aber bereits `CONFLICTING` gegen genau
diesen Branch: Der gesamte Stack wurde seit dem #291-Merge (2026-07-15) nicht mehr gegen aktuellen
Stand rebased, während seither ~zusätzliche 12 Tage Main-Aktivität liefen (u. a. GATE-11, MAT-GOV/
MAT-EVID/MED-NORM-01-Serie). Damit ist unklar, ob der Inhalt oberhalb von #293 gegen den heutigen
`main` überhaupt noch konfliktfrei anwendbar wäre — das wurde hier bewusst nicht geprüft (zu
riskant/aufwändig für eine reine Priorisierung, siehe Empfehlung).

Größenordnung pro PR (Diff-Zeilen, `+`/`-`): #293 23k/1.5k · #294 1.9k/84 · #295 9.6k/579 ·
#296 5.1k/505 · #297 3.3k/433 · #298 4.0k/4 · #299 3.9k/581 · #300 16.0k/6.1k · #301 11.3k/145 ·
#302 1.3k/193 · #303 4.0k/260 · #304 5.0k/173 · #305 5.6k/485. Zusammen: weit über 90.000
Diff-Zeilen an sicherheitskritischem Code (Release-Gate-Bindung, Auth/Kosten-Kontrolle, Netzwerk-
Segmentierung, Daten-Autorität, DR, Monitoring, Supply-Chain, Agent-Relay, Reviewer-Governance).

## #311 — vom Stack losgelöst, vermutlich am dringendsten

`[codex] Stage-A recovery after fail-closed partial stop` — Base direkt `main`, erstellt
2026-07-16 (1 Tag nach dem Punkt, an dem der Stack stehen blieb), zuletzt aktualisiert
2026-07-16. Laut eigener PR-Beschreibung: schließt ausschließlich den "evidence-bound
Stage-A partial-recovery path" nach einem Fail-Closed-Partial-Stop ab — **autorisiert oder
führt KEINE Produktions-Recovery aus**, laut eigenem Wortlaut. Klein und fokussiert (finaler
Commit ändert laut Beschreibung genau 2 Dateien). Empfehlung: als Erstes vom Owner einzeln
angeschaut — thematisch und zeitlich am ehesten noch aktuell relevant.

## Dependabot (#222, #223, #308) — routinemäßig, geringes Risiko

Reine Dependency-Bumps (backend-python 53 Updates, marketing-frontend 26 Updates,
frontend-v2 11 Updates). Nach normalem CI-Grün mergebar, kein besonderer Prozess nötig.
Einzige Vorsicht: Major-Version-Sprünge einzeln im Diff gegenchecken, falls dabei.

## Alte, vom Stack unabhängige PRs — Kandidaten für Owner-Entscheidung "schließen oder nicht"

| PR | Alter | Ziel-Branch | Anmerkung |
|----|-------|-------------|-----------|
| #6 | seit Feb 2026 | main (release/v2.1.0-rc1) | 392 Dateien, 19k/11.5k — sehr groß, sehr alt |
| #5 | seit Feb 2026 | main | RAG-Admin-Dashboard, kein Update seit April |
| #89 | seit Juni 2026 | demo/rwdr-limited-external | Audit-Doku, Ziel-Branch ist ein Demo-Branch |
| #120 | seit Juni 2026 | demo/rwdr-limited-external | dito |
| #127 | seit Juni 2026 | demo/rwdr-limited-external | CONFLICTING |
| #187 | seit Juli 2026 | main | Staging-Deploy-Skript, seit Erstellung kein Update |
| #205 | seit Juli 2026 | main | Phase-3A-Aktivierungs-Log |
| #208 | seit Juli 2026 | main | Phase-3B-Aktivierungs-Log |

## Empfehlung (keine Handlung ohne Owner)

1. **#311 zuerst** — klein, frisch, direkt gegen `main`, thematisch mit dem GATE-10-Freeze
   verzahnt. Lohnt die erste Owner-Durchsicht.
2. **Stack #293–#305 nicht "durchtriagieren", sondern Grundsatzfrage klären**: Entweder (a)
   den Autor (Codex) bitten, den Stack gegen aktuellen `main` neu aufzusetzen/zu squashen,
   bevor überhaupt einzelne Inhalte bewertet werden, oder (b) bewusst akzeptieren, dass jede
   einzelne PR im Stack einzeln — von unten nach oben — gegen den *jeweils* aktuellen
   Zwischenstand reviewt und gemerged werden muss. Ein Massen-Review von >90.000 Zeilen
   sicherheitskritischem Code ist kein "Restarbeiten"-Posten, sondern eine eigene, große
   Owner-Entscheidung.
3. **Dependabot-PRs** können im normalen Alltag nebenbei gemerged werden, keine Eskalation nötig.
4. **Die 7 alten Alt-PRs** sind reif für eine einmalige Owner-Sichtung "behalten vs. schließen" —
   ähnlich wie die bereits durchgeführte Branch-Hygiene, nur PR-seitig statt Branch-seitig.
