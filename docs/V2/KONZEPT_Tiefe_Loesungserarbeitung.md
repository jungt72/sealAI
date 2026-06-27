# KONZEPT — Iteration 2: Tiefe & Lösungs-Erarbeitung (+ Form-Schärfung)

**Status:** Entwurf zur Challenge (GPT-5.5) · **Berührt:** L1-Doktrin `prompts/system_l1.jinja` = Trust-Spine → eval-gated (TARGETED, kein voller Eval mehr — Owner-Vorgabe) · **Aufbauend auf** Iteration 1 (`KONZEPT_Beratungs_UX_Fallarbeit.md`, LIVE 2026-06-27).

---

## 1. Befund (Owner-Live-Test nach Iteration 1)

Iteration 1 (Prioritätsleiter + Klären-vor-Empfehlen) ist live + sicher; das **Gespräch** führt + klärt jetzt deutlich besser. ABER zwei Dinge offen:

- **(A) Tiefe-Lücke — der wichtige Befund:** Die KI **erarbeitet die Lösung nicht** — sie sammelt Anforderungen und **schiebt sie dem Hersteller aufs Auge**. Owner wörtlich: *„es ist zu wenig, dies dem Hersteller aufs Auge zu drücken — hier sollte die Stärke von sealingAI liegen."* **Wurzel:** die Doktrin macht aus *„begründete Orientierung aus Grundprinzipien"* die *„seltene, markierte Kante"* und verbietet *„ein konkretes Material / eine Material-Richtung … auch nicht aus Allgemeinwissen"* ohne Matrix-Treffer → aus **Angst vor Halluzination** unterdrückt sie die **Ingenieurarbeit selbst**, die das Produkt ausmacht.
- **(B) Form noch dokumentartig** (offen aus Iter. 1): Fallarbeit-Eröffnungen bleiben strukturierte Wände (GPT-5.5s Risiko #6 war prescient — die weiche Form-Regel allein reicht nicht).

## 2. Zielbild (owner-bestätigt „sehr nahe dran")

Der im Chat durchgearbeitete **Schoko-Rührwerk-Fall**: die KI erarbeitet **Typ** (doppeltwirkende hygienische GLRD-Cartridge + Sperrmedium), **Werkstoff-Richtung** (FKM→FFKM; EPDM/NBR raus), **Bauform-Logik** (Totraumfreiheit, Auslenkungs-Abfang), die **Ausschluss-Logik** (warum Lippe/Packung/Einzel-GLRD scheitern) + das **Warum** — und **landet auf einem Kandidaten**. Hersteller = nur finale Freigabe + konkretes Compound/Modell. Die Tiefe kommt als **Auszahlung NACH der Klärung** (Progressive Disclosure richtig herum).

## 3. Der Reframe (Kern): **erarbeiten ≠ erfinden**

Die Doktrin muss zwei Dinge TRENNEN, die sie heute beide unterdrückt:

| Ebene | Behandlung | heute |
|---|---|---|
| **Geerdet** (Fakt/Matrix/Kern) | direkt sagen | ✓ ok |
| **Aus Prinzip** (Typ/Familie/Bauform/Ausschluss-Logik/Warum) | **tief erarbeiten = KERN-STÄRKE** | ✗ als „seltene Kante" unterdrückt |
| **Kandidat zu verifizieren** (konkretes Compound/Modell/Zahl) | als **Kandidat** markieren + Verifikation benennen, **nichts erfinden** | ✗ in „bleib generisch" kollabiert |

## 4. Drei Prinzipien

- **P1 — Lösung erarbeiten + landen:** nach der Klärung erarbeitet die KI einen **Kandidaten-Typ + Werkstoff-Richtung + Bauform-Logik** mit Trade-offs + **Ausschluss-Logik**; kein Abladen ans „frag den Hersteller".
- **P2 — Drei-Ebenen-Ehrlichkeit:** jede Aussage als *geerdet / aus-Prinzip / Kandidat-zu-verifizieren* erkennbar. **Tiefe JA, erfundene Spezifika NEIN.**
- **P3 — Form = Progressive Disclosure:** knappe, gesprächige Eröffnung/Klärung; die **Tiefe (wie das Zielbild) ist die Auszahlung NACH der Klärung** — dort strukturiert + ausführlich erwünscht.

## 5. Konkrete Doktrin-Edits (`system_l1.jinja`)

**A — den „Kein Volunteering"-Block ersetzen** (heute Z. ~50–61):
> **Lösung erarbeiten — aus Prinzipien UND geerdeten Fakten.** Nach der Klärung ist es deine **Kern-Aufgabe**, die Lösung zu erarbeiten: den **Kandidaten-Dichtungstyp**, die **Werkstoff-Richtung (Familie)**, die **Bauform-Logik** — mit der **Ausschluss-Logik** (warum die einfacheren Optionen scheitern) und dem **Warum**. Das darfst und **sollst** du **aus Ingenieurprinzipien** tun, auch ohne Matrix-Treffer — **das ist die Stärke, nicht die seltene Kante**.

**B — Drei-Ebenen-Kennzeichnung** (neu):
> Mach jede Aussage erkennbar: (1) **geerdet** (Fakt/Matrix/Kern) → direkt; (2) **aus Prinzip** → tief erarbeiten, klar als ingenieurmäßige Herleitung; (3) **Kandidat** → als solchen markieren + nennen, was Datenblatt/Fachkarte/Hersteller bestätigen muss.

**C — die harte Grenze (Halluzinations-Firewall, neu + scharf):**
> **Erarbeiten ≠ erfinden.** Tiefe heißt **Typ / Familie / Richtung + Logik** — **NIE** eine erfundene Spezifik: keine konkrete Compound-Nummer, kein Firmenname, keine erfundene Grenz-/Lebensdauer-Zahl. Eine Material-**Familie** als Kandidat („food-grade FKM, bei scharfer CIP eher FFKM") ist erlaubt; eine erfundene Konkret-Type/-Zahl nicht. **Hersteller = finale Freigabe + konkretes Compound/Modell, NICHT die Ingenieurarbeit.**

**D — Form-Schärfung** (offen aus Iter. 1):
> Fallarbeit-**Erst-Turn**: keine `###`-Überschriften, keine nummerierten Abschnitte, Richtwert **~120 Wörter**, gesprächig — die **Tiefe** (Struktur erlaubt) kommt **erst nach** der Klärung.

## 6. Was UNVERÄNDERT bleibt (kritisch — Tiefe ERHÖHT das Halluzinations-Risiko)

- **Keine erfundenen Spezifika:** Compound-Nummern, Firmennamen, präzise Grenz-/Lebensdauer-Zahlen — verboten. Kandidat = Typ/Familie/Richtung, **nie** eine erfundene Konkretzahl.
- **§3.9 Neutralität**, **Gegencheck-nie-passt**, **Rechen-Restraint** (v/PV/Verpressung nur Kern), **Safety-Prioritätsleiter** (Iter. 1), **fail-closed**.
- „Orientierung ≠ Freigabe" bleibt — die Freigabe ist die **FINALE**, nicht die Ingenieurarbeit.

## 7. Eval (TARGETED — Owner-Vorgabe „kein voller Eval mehr")

- Neue/erweiterte Dimension **`loesungserarbeitung`** (oder Erweiterung `beratungs_ux`): Fälle mit **bereits geklärter** Situation →
  - `must_catch`: **landet** auf Kandidaten-Typ + Werkstoff-Richtung + Ausschluss-Logik + Warum.
  - `must_avoid`: nur Anforderungen sammeln + alles ans „frag den Hersteller" abladen (das ALTE Verhalten); **eine erfundene Compound-Nummer/Firma/Grenzzahl** (Halluzination — das **schärfste** must_avoid, ggf. Hard-Gate `confident_wrong`/`invented_precision`).
- **Targeted run:** nur die betroffene(n) Dimension(en) + die deterministischen Schranken (memory/exfil/parametric laufen ohnehin) + ein **kleiner Anker-Subset** (calibration/gegencheck — die ein Tiefe-Reframe am ehesten verschiebt). **Kein** 30-Fall-Lauf. Owner-adjudiziert (Charter A0).

## 8. Fachkarten-Skizze (macht die mittlere Spalte GEERDET statt nur Prinzip)

Zuerst nötig (Lebensmittel/Hygiene-Domäne, am Schoko-Fall sichtbar geworden):
1. **Hygiene-Dichtungstypen Rührwerk** (Lippe < Einzel-GLRD < Doppel-GLRD-Cartridge + Sperrmedium; wann was) + EHEDG/3-A.
2. **CIP-Werkstoffbeständigkeit** (Elastomerfamilien × Lauge/Säure/Oxidationsmittel × Temperatur).
3. **FDA/1935 food-grade Compound-Familien** (FKM/FFKM/EPDM-food × Fett/Temp/Chemie-Envelope).
4. **Rührwerk/Wellenauslenkung** (auslenkungs-tolerante Bauformen, Stützlager).

## 9. Risiken / für GPT-5.5 zum Challengen

1. **Der zentrale (gleiche Form wie Iter. 1's „Kürze→Safety-Bypass", jetzt „Tiefe→Halluzination"):** Verleitet *„erarbeite tief + lande auf Kandidat"* das Modell, **Spezifika zu erfinden** oder **Prinzip als geerdeten Fakt** auszugeben? Wie hält man die Tiefe **strukturell** OHNE die Halluzination?
2. Kippt das **Kandidaten-Mandat** die §3.9-Neutralität (drängt es Richtungen/Produkte auf)?
3. Ist die **Drei-Ebenen-Kennzeichnung** im Fließtext praktikabel — oder wird sie zur Floskel-Wand?
4. **Form-Schärfung** (~120 W, keine Überschriften im Erst-Turn) vs. die gewollte **Tiefe nach Klärung** — sauber getrennt, oder Widerspruch?
5. Reicht der **targeted Eval** (ohne die 25 Anker-Fälle) als Regressionsschutz für einen Doktrin-Eingriff **dieser Größe** — oder braucht GERADE diese Iteration den vollen Anker einmalig?
