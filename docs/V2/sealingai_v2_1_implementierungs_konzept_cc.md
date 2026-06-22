# sealingAI V2.1 — Implementierungs-Konzept für Claude Code

**Adressat:** Claude Code (CC, Opus) — autonome Umsetzung auf dem Hetzner VPS.
**Grundlage (das WAS):** `docs/V2/sealingai_v2_1_produkt_konzept.md`. Dieses Dokument ist das **WIE**.
**Verhältnis:** Evolution der bestehenden V2-Implementierung (`backend/sealai_v2/`). Kein Neubau.
**Arbeitsweise:** doktrin-gegatetes Relay — CC liest dies → **read-only Ist-Stand-Audit** → Build-Plan je Increment → **Owner-Review** → autonome Umsetzung unter den Self-Gates → **Owner-Review vor Prod**.

---

## 0. Mission & wie dieses Dokument zu lesen ist

**CC, deine Mission:** V2.1 *increment für increment* bauen — nicht alles auf einmal. Jedes Increment ist eine kohärente, testbare, deploybare Einheit mit Owner-Gates davor und danach.

**Wichtig — woher die Präzision kommt:** Dieses Dokument nennt Ziel-Module, -Seams und -Schemata. Es ist *bewusst kein* Datei-Diktat, weil es gegen eine Zusammenfassung des Codes geschrieben ist, nicht gegen den Live-Code. **Die Ultra-Präzision entsteht in Increment 0**, wenn du den *echten* Code read-only gegen dieses Konzept erdest und die exakten Gaps bestimmst. Alle Datei-/Modul-Verweise hier sind **Targets zum Bestätigen/Anpassen** gegen dein Audit — keine behaupteten Fakten.

**Reihenfolge im Kopf:** Leitplanken (§1) → Fundament-Audit (§2, Pflicht) → Ziel-Architektur (§3) → Increments (§4) → Schemata (§5) → Eval (§6) → Deploy (§7) → was *nicht* jetzt (§8) → Definition of Done (§9) → **Kickoff-Prompt (§10)**.

---

## 1. Nicht verhandelbare Leitplanken (Doktrin + Self-Gates)

Diese gelten in *jedem* Increment. Sie sind self-contained hier wiederholt, damit du sie nicht woanders suchen musst — die kanonische Quelle bleibt `.claude/rules/doctrine.md`, `.claude/rules/ops.md`, `AGENTS.md`.

### 1.1 Doktrin
- **Backend besitzt die Fakten und Zahlen; das LLM erzählt nur.** Keine Materialaussage, keine Zahl, keine Norm entsteht im LLM.
- **Wissen ist Daten** — owner-reviewt, mit Quelle, *niemals modell-generiert*. Neue Wissens-Stores folgen dem Muster der Fachkarten/Matrix (Schema + Loader + Daten).
- **Trust-Spine L1–L4 gilt uniform** für *jede* Operation: L1 erzählt, L2 erdet, L3 verifiziert (gegen Fallen-Katalog + Matrix), L4 ist die menschliche Hersteller-Freigabe. Eine Empfehlung, eine Diagnose, eine Äquivalenz, ein Gegencheck-Urteil sind *gleichrangig* geerdete/verifizierte Behauptungen.
- **Kalibrierung** (Produkt-Konzept §3): selbstbewusst-korrekt per Default; *so assertiv wie die Erdung*; der Hedge ist die seltene markierte Kante; auf sicherheitskritisch/unsicher → „Stopp, bestätigen"; **Normen geerdet, nie rezitiert** (§3.10/§9.3 des Produkt-Konzepts).
- **Neutralität ist heilig** — Hersteller-Auswahl/Alternativen nur nach Fähigkeit, nie pay-to-rank.

### 1.2 Self-Gates (HALT bei Verletzung)
- **Eval-REPLAY:** deterministische und Agent-Final-Schranken bleiben **1.000**. Klassen, die nie fallen dürfen: `memory_fabrication`, `exfiltration`, `injection_override`, `edge_overreach`, `flags_on`, `flags_off`, plus die deterministische und die Agent-Final-Schranke. Vor *und* nach jeder Änderung gemessen.
- **Reversibilität vor Prod:** Rollback-Image-ID **aus dem Docker-Daemon gelesen** (nie aus der Erinnerung), getaggt (`sealai-backend-v2:rollback-<datum>`), *bevor* deployt wird.
- **Restart-Survival-Beweis** nach jedem Prod-Deploy.
- **Chirurgischer Deploy:** `docker compose up -d --no-deps <service>`. Staging und **Fremdprojekte (Prelon, ERPNext, …) bleiben unberührt**.
- **Provisorische Judge-Flags → Owner als Oracle** (TRAP-02-Disziplin): wörtlich protokollieren, mit `--adjudicate` neu rechnen, *nie selbst-ticken*.

### 1.3 Owner-Review-Pflicht — wo du HÄLTST
Du hältst an und holst Thorstens explizite Freigabe bei:
1. dem **read-only Fundament-Audit** (§2),
2. jedem **Increment-Build-Plan** (vor dem ersten Code),
3. **jeder Änderung an reviewter Wissens-/Katalog-/Seed-Daten** — inkl. *jedem von dir gedrafteten* Archetyp-/Versagensmodus-/Hersteller-/Norm-Inhalt (Doktrin-Gate: du *draftest*, der Owner *reviewt*, erst dann ist es geerdet),
4. **jedem Prod-Deploy.**

### 1.4 Neue/komplexe Fläche → read-only zuerst
Bevor du in einer neuen oder komplexen Code-Fläche *irgendetwas* schreibst, machst du ein read-only, spec-geerdetes Surfacing (jeder Befund mit Spec-`file:line` + Code-`file:line`). Das ist der etablierte Modus dieses Projekts.

---

## 2. Increment 0 (PFLICHT, read-only): Fundament-Audit

Bevor *eine Zeile* entsteht. Erde dieses Konzept gegen den echten Code + `build_spec`. Surface read-only den exakten Ist-Stand der Seams, auf denen V2.1 aufbaut:

- **Pipeline-Stufen** (`verstehen`→`grounden`→`rechnen`→`antworten`→`verifizieren`→`zitieren`→`erinnern`): wo, aktuelles Verhalten, soft-intent annotate-only bestätigen.
- **`case_context`**: wie heute gebaut/typisiert, welche Felder — der Keim des expliziten *Falls* (§3).
- **Soft-Intent-Read**: wo er lebt, was er annotiert (treibt die fließenden Modi).
- **Tiefe-nach-Fragetyp in L1**: wo und wie.
- **Maschinen-/Archetyp-Wissen heute**: steckt es implizit im L1-Jinja? Gibt es *irgendeinen* strukturierten Store? (Entscheidet den Umfang von Increment 1.)
- **Wissens-Store-Muster**: Fachkarten-Loader, Matrix-Loader — das Muster, dem ein neuer Daten-Store folgt (Schema, Laden, Validierung).
- **Eval-Harness**: wie Fälle/Schranken definiert sind, wie `REPLAY`/`--adjudicate` läuft, wo die 25 Fälle × 2 Spalten liegen.

**Output:** ein read-only Audit-Dokument in `.claude/plans/` (eigener Pfad, *nicht* dieses Konzept überschreiben), das Konzept → Ist-Stand mappt und die *präzisen* Gaps für Increment 1 listet — jeder Verdict mit `file:line`. → **STOP, Owner-Review.** Hierauf gründet alle weitere Präzision.

---

## 3. Ziel-Code-Architektur (Target — gegen das Inc-0-Audit bestätigen/anpassen)

V2.1 auf konkrete Code-Struktur abgebildet. Sitzt auf der bestehenden dünnen Pipeline — sie ist für die fließenden Modi *bereits* gebaut (weicher Intent-Read + Tiefe-nach-Fragetyp).

- **Der explizite Fall (`Case`):** ein *typisiertes* Objekt — die Verallgemeinerung des `case_context`. Felder: `archetype`, `conditions` (Geschwindigkeit/Temperatur/Druck), `medium`, `geometry` (Welle Ø, Bauraum), `seal_spec` (optional: Werkstoff/Typ/Bauform). *Eine* Quelle, die alle Operationen lesen/schreiben.
- **Eingänge (Adapter, die den `Case` füllen):** `describe` (existiert), `decode`, `failed_part`, `existing_solution` (bauen später). Annotate-only, kein Hard-Routing.
- **Operationen (über dem `Case`, auf der Pipeline):** `recommend` (existiert), `diagnose`, `gegencheck`, `find_alternatives`, `explain`. Tiefe nach Fragetyp.
- **Wissens-Stores (alle als Daten, owner-reviewt, config-swappbarer Protocol-Seam):**
  - vorhanden: Fachkarten, Verträglichkeitsmatrix, Rechenkern;
  - neu: **Archetypen**, **Versagensmodi**, **Hersteller-Fähigkeiten**, **Bezeichnungs-Schemata + Quervergleich**.
  - Jeder neue Store = Schema + Loader nach dem bestehenden Muster.
- **Normen-Quer-Schicht (KEIN eigener Store):** fädelt durch Fachkarten/Matrix (Provenienz-Felder), die Geometrie-Schicht (Decode/Bauform-Norm-Hooks) und die Archetypen (`anwendbare_regime`-Feld). **Jetzt wird nur die STRUKTUR gebaut** (die Felder + Hooks); der **INHALT kommt aus dem Deep-Research-Normen-Katalog (separat, morgen)**. Cite-not-recite ist Pflicht (§1.1).
- **Trust-Spine uniform:** jeder Operations-Output ist eine Behauptung → L2-geerdet + L3-verifiziert + Provenienz + ehrlich-an-der-Kante. L3 muss perspektivisch **Norm-Behauptungen und Äquivalenz-Behauptungen** prüfen können (die schärfsten — Produkt-Konzept §9.2/§9.3).

---

## 4. Build-Increments (Sequenz, gegatet)

Vorschlag der Reihenfolge; **Thorsten setzt die Priorität**. Jedes Increment: Scope / realisiert (Produkt-Konzept §) / Ziel-Module / Daten-Schema (falls neuer Store) / Akzeptanz + Eval-Gate / Owner-Checkpoints / *nicht* im Scope.

### ▶ Increment 1 (ZUERST, morgen) — Der explizite `Case` + Archetyp-Dimension + archetyp-geführtes Verstehen

*Die foundationale neue Architektur, auf der der Empfehlungs-Flow und die meisten Modi aufbauen — und **unabhängig vom Normen-Katalog**, läuft daher morgen parallel zur Deep Research.*

- **Scope:**
  1. **`Case` explizit machen** — das typisierte Objekt aus `case_context` herausziehen/generalisieren (Felder s. §3 / Schema §5.1).
  2. **Archetyp-Store anlegen** — Schema + Loader nach dem Fachkarten-Muster; `anwendbare_regime` als *strukturelles* Feld (Inhalt bleibt leer/Platzhalter bis Normen-Katalog).
  3. **2–3 Starter-Archetyp-Profile** (aus Produkt-Konzept §8: Getriebe + Rührwerk zuerst, distinkt) — **CC draftet, Owner reviewt, erst dann geerdet** (Doktrin-Gate).
  4. **Verstehen verdrahten** — Archetyp erkennen → Profil laden → Interview-Fragen + blinde Flecken *aus dem Profil* treiben. Weich, annotate-only, *kein* Hard-Routing (konsistent mit dem bestehenden Soft-Intent).
- **Realisiert:** §4 (der `Case`), §8 (Archetypen), §6 Schritt 1 (archetyp-geführtes Verstehen).
- **Ziel-Module (gegen Inc-0 bestätigen):** der `case_context`-Bau (→ typisierter `Case`); der `verstehen`-Stufen-Code; ein neues `knowledge/archetypes/`-Daten-Verzeichnis + Loader analog Fachkarten.
- **Akzeptanz + Eval:** Archetyp-Erkennung auf dem Starter-Satz; das Interview spiegelt das geladene Profil; blinde Flecken werden hochgeholt; **neue Eval-Fälle** dafür; **alle bestehenden Schranken halten 1.000** (keine Regression); Home-Topic-Empfehlungen erhalten.
- **Owner-Checkpoints:** (1) Inc-0-Audit · (2) Inc-1-Build-Plan · (3) **die gedrafteten Starter-Profile (Inhalt)** · (4) Prod-Deploy.
- **Nicht im Scope:** die anderen Modi/Operationen; der Normen-Katalog-Inhalt; die Kalibrierungs-Prompt-Änderungen (Increment 2).

### ▷ Increment 2 — Die Kalibrierung im Empfehlen-Flow
- **Scope:** selbstbewusst-korrekt-per-Default + „so assertiv wie geerdet" in L1; Challenge-Funde → transparente Bedingungen; der Hedge als markierte seltene Kante; sicherheitskritisch/unsicher → „Stopp, bestätigen". Berührt das L1-Jinja, ggf. die L3-Hedge-Logik. **Doktrin-gegated** (ändert, *wie* das System behauptet) → Owner-Review am Plan-Stand.
- **Eval:** neue Fälle für confident-correct-auf-geerdet, ehrlich-an-der-Kante, *keine* Über-Hedge-Regression; bestehende Schranken halten.
- *Increment 1 + 2 zusammen = „Kern festigen" (Produkt-Konzept §11, Schritt 1). Bei Wunsch zu einem Build mergebar — Owner entscheidet.*

### ▷ Increment 3 — Ein akuter Wedge: **G (Decode+Quervergleich)** ODER **D (Diagnose)**
- **Owner wählt, welcher zuerst.** Jeder bringt seine Wissens-Dimension als owner-reviewte Daten + die Operation + den Eingangs-Adapter.
- **G:** die scharfe Äquivalenz-Disziplin (geerdet, ehrlich-über-die-Grenze, L4) + die Geometrie-Norm-Hooks (DIN 3760/ISO 3601 — Inhalt via Normen-Katalog).
- **D:** Versagensmodi (Dim. 5) schärfen *zusätzlich* den Challenge im Empfehlen — synergetisch mit Inc 1/2.
- **Eval:** jeder Operations-Output wird gemessen wie eine Empfehlung (neue Schranken).

### ▷ Increment 4 — Gegencheck (E)
- Empfehlungs-Engine im *Bewertungs*-Modus; günstig, sobald Inc 1/2 stehen.

### ▷ Increment 5 — Alternativen/Hersteller (F)
- Braucht Dim. 6 (Hersteller-Fähigkeiten) geerdet. Neutral, kein pay-to-rank.

### ▷ Laufend — Wissens-Tiefe
- weitere Archetypen, Matrix-Zellen, Versagensmodi, Rechengrenzen. Owner-reviewt. *Die Dauer-Arbeit, die den geerdet-korrekten Bereich vergrößert (Produkt-Konzept §3.8).*

---

## 5. Daten-Schemata für die neuen Stores

Struktur baut CC; **Inhalt ist owner-reviewte Daten** (Doktrin-Gate).

### 5.1 `Case` (typisiert)
```
Case:
  archetype: str | null            # Schlüssel in den Archetyp-Store
  conditions:
    speed: {value, unit} | null    # → Kern: Umfangsgeschwindigkeit
    temperature: {value, unit} | null
    pressure: {value, unit} | null
  medium: {name, concentration?, temperature?} | null
  geometry: {shaft_dia?, housing?, ...} | null
  seal_spec: {material?, type?, form?, designation?} | null   # bei decode/gegencheck/diagnose gefüllt
  provenance: [...]                 # je Feld: Quelle/Herkunft (User-Angabe vs. abgeleitet)
```

### 5.2 Archetyp-Profil (Increment 1 — voll)
Aus Produkt-Konzept §8 / Anhang B:
```yaml
archetyp: <key>                     # z.B. getriebe, ruehrwerk
typische_konstellation: {wellenlage, geschwindigkeit, druck_vakuum, schmierung, medium_charakter}
dichtungsrelevante_besonderheiten: [...]
typische_versagensmodi: [<ref Dim.5>]        # Verweis; Dim.5 baut später
typische_eignungen: {werkstoffe: [...], bauformen: [...]}
anwendbare_regime: []               # STRUKTUR jetzt; INHALT via Normen-Katalog (morgen)
interview_fragen: [...]
blinde_flecken: [...]
quelle: <owner-review-ref>          # Pflicht — geerdet
```

### 5.3 später (skizziert, Detail bei ihrem Increment)
- **Versagensmodus:** `{symptom, ursache, fix, betrifft_archetypen[], quelle}`
- **Hersteller-Fähigkeit:** `{hersteller, werkstoffe[], bauformen[], groessen, zertifikate[], quelle}` — neutral.
- **Bezeichnungs-Schema:** `{hersteller, parser_regeln, norm_bezug, quelle}` + Quervergleich-Logik (mit Äquivalenz-Grenze).

---

## 6. Eval-Anforderungen

- **Jede** neue Operation / Wissens-Erweiterung kommt mit neuen Eval-Fällen + Schranken.
- Die **8 harten Schranken** (§1.2) halten **1.000** durch *jedes* Increment.
- Neue Klassen pro Increment, z. B.: `archetype_fit` (Inc 1), `confident_correct_vs_hedge` (Inc 2), `equivalence_honesty` (Inc 3/G), `diagnosis_correctness` (Inc 3/D).
- Provisorische Judge-Flags → Owner-Oracle (TRAP-02): wörtlich, `--adjudicate`, nie selbst-ticken.
- RED-before-GREEN: neuer Test scheitert *vor* dem Fix, besteht *danach* (beide Richtungen).

---

## 7. Deploy-Disziplin (pro Increment, wenn Prod)

`backend-v2` ist de-facto **live in Prod**. Daher pro Deploy:
1. Rollback-Image-ID **aus dem Daemon** lesen → taggen (`sealai-backend-v2:rollback-<datum>`).
2. Neues Image bauen.
3. **Chirurgisch:** `docker compose up -d --no-deps backend-v2`. Staging + Fremdprojekte unberührt.
4. **Health + Restart-Survival** beweisen; im-Container-Fix-Beweis, wo sinnvoll.
5. **Eval-REPLAY live** (Label je Increment) → Schranken 1.000; provisorische Flags adjudizieren.
6. **`GOVERNANCE_LOG`-Eintrag.**
7. Der **öffentliche `/api/v2`-nginx-Flip** (`ops/v2-flip.sh`) bleibt **kommentiert/owner-gegated** — diese Deploys aktualisieren nur das Backend-Image.

---

## 8. Was bewusst NICHT jetzt

- **Normen-Katalog-INHALT** → morgen via Deep Research (jetzt nur die Felder/Hooks der Quer-Schicht, §3).
- **Deferred-by-design** (Produkt-Konzept §12): Token-Streaming, RFQ-Artefakt, Qdrant/Redis/Postgres-kanonisch-Swaps (Skalierungs-Trigger).
- **Pilot-Ops-Schicht** (Anwalt-Claim-Grenze, Keycloak-Secret-Rotation, Per-Turn-Provenienz, CSP/Token-Beweis, LangSmith-Privacy) — *eigener* Track, außerhalb dieses Konzepts.

---

## 9. Definition of Done — Increment 1

- [ ] Inc-0-Audit owner-freigegeben; Inc-1-Plan owner-freigegeben.
- [ ] `Case` ist ein typisiertes Objekt; bestehende Flows nutzen es ohne Regression.
- [ ] Archetyp-Store (Schema + Loader nach Fachkarten-Muster) steht; `anwendbare_regime` strukturell vorhanden (leer).
- [ ] Starter-Profile (Getriebe, Rührwerk) **owner-reviewt** und geerdet.
- [ ] `verstehen` erkennt Archetyp → lädt Profil → treibt Interview + blinde Flecken (weich, annotate-only).
- [ ] Neue Eval-Klasse `archetype_fit` grün; **alle 8 Schranken 1.000**; Home-Topic erhalten.
- [ ] Deploy unter §7 (falls Prod) — Rollback getaggt, chirurgisch, Restart-Survival, `GOVERNANCE_LOG`.

---

## 10. Kickoff-Prompt für CC (zum Einkippen, morgen)

> **Rolle:** Du bist Claude Code für sealingAI auf dem VPS. Repo `~/sealai`, Backend `backend/sealai_v2/`. Wir bauen **V2.1 Increment 1**.
>
> **Lies zuerst:** `docs/V2/sealingai_v2_1_produkt_konzept.md` (das WAS) und `docs/V2/sealingai_v2_1_implementierungs_konzept_cc.md` (das WIE), sowie `.claude/rules/doctrine.md`, `.claude/rules/ops.md`, `AGENTS.md`.
>
> **Nicht verhandelbar:** Backend besitzt Fakten/Zahlen, LLM erzählt; Wissen ist owner-reviewte Daten, *nie* von dir erfunden (du draftest, der Owner reviewt); Trust-Spine L1–L4; Self-Gates: Eval-Schranken 1.000, Rollback-Image aus dem Daemon vor Prod, Restart-Survival, chirurgischer `--no-deps`-Deploy, Fremdprojekte unberührt, provisorische Judge-Flags → Owner-Oracle (TRAP-02). Du **HÄLTST** für Owner-Freigabe bei: Audit, Build-Plan, gedrafteten Daten-Inhalten, Prod-Deploy.
>
> **Schritt 1 — read-only Fundament-Audit (§2 des WIE).** Surface gegen den echten Code: `case_context`, die `verstehen`-Stufe + Soft-Intent, Tiefe-nach-Fragetyp, wo Archetyp-Wissen heute steckt, das Fachkarten/Matrix-Store-Muster, der Eval-Harness. Schreib das Ergebnis nach `.claude/plans/` (eigener Pfad, dieses Konzept *nicht* überschreiben), jeder Befund mit `file:line`, plus die präzisen Gaps für Increment 1. **Dann STOP** und leg es mir vor.
>
> **Schritt 2 (nach Freigabe) — Increment-1-Build-Plan** (Scope §4 ▶). **STOP**, Review.
>
> **Schritt 3 (nach Freigabe) — bauen** unter den Self-Gates: typisierter `Case`, Archetyp-Store (Schema + Loader), **gedraftete** Starter-Profile Getriebe + Rührwerk *für mein Review*, `verstehen`-Verdrahtung, Eval-Klasse `archetype_fit` (RED-before-GREEN), alle Schranken 1.000. Deploy nur owner-gegated nach §7.
>
> Beginne mit Schritt 1.

---

*Ende. Umsetzung folgt dem etablierten Relay (CC autonom, Claude = Reviewer/Gatekeeper, alle produktiv-mutierenden Schritte owner-freigegeben), gemessen gegen `build_spec` und Eval-Lineal. Datei-/Modul-Verweise sind Targets — Increment 0 erdet sie gegen den Live-Code.*
