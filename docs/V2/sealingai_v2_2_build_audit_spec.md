# sealingAI V2.2 — Build- & Audit-Spezifikation

**Status:** Finalisiert — L2 (Prelon-Abgrenzung) ratifiziert. Bau-Spec zur CC-Auditierung gegen den Ist-Stand.
**Verhältnis zu V2.1:** Gehärtetes, scope-geschnittenes Delta. Die *Vision* steht (V2.1 §1–§9) und wird **nicht** neu verhandelt. Dieses Dokument ersetzt V2.1 §10–§11 (Bau-Reihenfolge) durch einen harten Scope-Cut und ein Audit-Protokoll.
**Zweck:** CC auditiert das aktuelle Repo gegen die SOLL-Spezifikation hier, meldet den Ist-Stand, der Owner reviewt, dann baut CC Lücke für Lücke — an jedem Gate haltend (TRAP-02).

---

## 0. Was dieses Dokument ist — und was nicht

V2.2 ist **kein Konzept**, das fragt *was sealingAI sein soll*. Das ist beantwortet. V2.2 ist die Antwort auf *was als Nächstes gebaut wird, in welcher Reihenfolge, und — entscheidend — was bewusst NICHT*.

Der Disziplin-Anker, der dieses Dokument von V2.1 unterscheidet: Der Analyse-Loop (technische Challenge → Strategie-Deep-Dive → Bewertung → Gegen-Challenge) hat seinen Grenzertrag erreicht. Eine weitere Verfeinerungs-Runde liefert kein besseres Produkt, sondern nur eine raffiniertere Begründung, noch nicht zu bauen. **V2.2s einzige Aufgabe ist, das Designen zu stoppen und EINEN scope-geschnittenen Wedge gut zu bauen.** Sein Wert misst sich an dem, was es wegschneidet und sperrt.

Deshalb gilt für CC die strengste Lesart: Alles, was nicht ausdrücklich unter §3 „IN" steht, wird **nicht** gebaut — auch nicht „hilfsweise", auch nicht, wenn es in V2.1 als wünschenswert beschrieben war. Scope-Erweiterung ist hier ein Audit-Verstoß, kein Mehrwert.

---

## 1. Die Owner-Locks vor dem CC-Lauf

Drei Entscheidungen sind **Owner-final**. **L2 ist ratifiziert** (siehe unten). L1 und L3 müssen noch bestätigt sein, bevor CC einen Bau-Vorschlag macht. CC darf keine davon selbst adjudizieren (TRAP-02). Meine Empfehlung steht je dabei.

| # | Lock | Meine Empfehlung | Owner-Entscheid |
|---|---|---|---|
| **L1** | **Wedge-Reihenfolge** | Primär **Gegencheck (E)** — baut auf bestehendem INC-GEGENCHECK-CORE auf, Käufer ist der Konstrukteur (Risiko-Reduktions-Kauf, bei dem die Vorsicht der Honest-Engine ein *Feature* ist), und E ist günstig, weil es C im Bewertungs-Modus ist. Sekundär **Decode entschärft (G1/G2)** als akuter Cold-Start-Magnet. | ☐ bestätigt / ☐ umsortiert |
| **L2** | **Prelon-Abgrenzung** *(ratifiziert)* | **Owner-Entscheid getroffen: Prelon bringt nichts ein — dauerhaft.** Kein Prelon-Feldwissen (Reklamations-/Kunden-/Anwendungsdaten) fließt je in sealingAI. Damit entfällt jede IP-/Vertraulichkeits-Angriffsfläche, und die Neutralitäts-Spannung ist entschärft (sealingAI zieht nachweislich nichts aus dem Arbeitgeber). Folge: alle feldwissens-abhängigen Teile sind **verschoben** (§3), nicht blockiert — sie kommen über den **Flywheel (§9)** als clean-room Feldwissen, der damit der *einzige* Pfad dorthin ist. | ✓ **ratifiziert** |
| **L3** | **Eval-Schwellen** | Confident-Wrong-Rate und Equivalence-Overclaim-Rate: **Hard-Fail bei jedem Vorkommen** auf dem Lineal (Katastrophen-Quadranten). Coverage-Classification-Accuracy: hoher Floor (Vorschlag ≥ 0,95). Die Doktrin (§2) gilt produktiv **erst**, wenn diese gemessen erfüllt sind. | ☐ bestätigt / ☐ Schwellen: ___ |

Ohne bestätigte L1 und L3 läuft der Audit als reiner Ist-Bericht (kein Bau-Vorschlag).

---

## 2. Ratifizierte Doktrin — als Invarianten

Der eine Satz, der V2.2 trägt:

> **sealingAI ist nicht pauschal selbstbewusst. Es ist beweisbar selbstbewusst innerhalb seines geprüften Envelopes — und beweisbar ehrlich außerhalb.**

Das ist stärker *und* sicherer als V2.1 §3 („selbstbewusst-korrekt per Default"), weil es die Assertivität an einen *gemessenen, deterministischen* Zustand bindet statt an eine Behauptung. Die folgenden Invarianten **erweitern** das bestehende Neun-Invarianten-Charter (I1–I9) und lassen TRAP-02 unangetastet. CC auditiert das Repo gegen jede einzelne.

- **I-COV-1 — Coverage-Status ist deterministisch.** Der `coverage_status` (`IN_ENVELOPE` / `PARTIAL_ENVELOPE` / `ANALOG_ONLY` / `OUT_OF_ENVELOPE`) entsteht ausschließlich aus Daten-/Regelabgleich im Kernel. Das LLM darf ihn **nicht setzen, nicht überschreiben, nicht „fühlen"**. (TRAP-02-Prinzip, auf Coverage angewandt.)
- **I-COV-2 — Assertivität ist eine Funktion des Status, kein Default.** Der erlaubte Antwortmodus ist hart an `coverage_status` gekoppelt (§5). Kein assertiver Material-Tipp bei `PARTIAL` / `ANALOG_ONLY` / `OUT`.
- **I-COV-3 — Chemische Verträglichkeit nie aus Grundprinzipien.** First-Principles-Schlüsse sind dem LLM nur für **geometrisch/strukturell Deterministisches** erlaubt (norm-gestützt). Chemische/Compound-Eignung außerhalb des Envelopes → höchstens nächster geerdeter Analog + explizites Delta + Hersteller-Bestätigung *zwingend*. Nie ein First-Principles-Material auf ungeprüfter Medienbeständigkeit.
- **I-COV-4 — Kein Material-Finaltipp außerhalb der Coverage.** Der Anwender bekommt **immer eine verwertbare Empfehlungsebene** — Material *oder* Kandidatenklasse *oder* Ausschluss *oder* Prüfpfad — aber **nicht immer ein finales Material**. (Ersetzt V2.1 §3.3 „der Anwender kriegt immer ein Material".)
- **I-EQ-1 — Äquivalenz ist hart gegated.** „Teil X = Teil Y" / „technisch gleichwertig" nur bei dokumentierter Hersteller-/Datenblatt-Evidence. Decode + Vergleichskorridor erlaubt; **Ersatzteilgleichheit ohne harte Evidence verboten** (§7).
- **I-CAL-1 — Die Doktrin ist gemessen, nicht behauptet.** Confident-Wrong-Rate und Coverage-Classification-Accuracy sind harte Eval-Schranken (§8). Die Assertivitäts-Doktrin gilt produktiv erst bei gemessener Erfüllung.

---

## 3. Der Scope-Cut

Zwei Zustände. CC behandelt sie als bindend. (Den dritten Zustand „GESPERRT" gibt es nicht mehr — mit der L2-Ratifizierung ist nichts mehr hinter einer offenen Rechtsfrage blockiert; was Feldwissen braucht, ist schlicht *verschoben*, bis der Flywheel es clean-room liefert.)

| Zustand | Bedeutung für CC |
|---|---|
| **IN** | Jetzt bauen (nach Owner-Review des Audits, Inkrement für Inkrement). |
| **VERSCHOBEN** | Bewusst zurückgestellt — per Kapazitäts-/Risiko-Disziplin oder bis der Flywheel (§9) das nötige clean-room Feldwissen produziert hat. Nicht bauen, nicht vorbereiten. |

### IN — V2.2-Bau-Umfang
- **Coverage-Gate** (deterministisch, Kernel-owned) — §4. *Die neue Kern-Komponente.*
- **Korrigierte Assertivitäts-Mechanik** — §5 (Status→Modus-Kopplung, Vier-Ebenen-Output, First-Principles-Einschnürung).
- **Gegencheck (E)** für den Konstrukteur — §6. *Primärer Wedge.*
- **Decode entschärft (G1/G2)** — §7. *Sekundärer Wedge, hart gegated gegen Äquivalenz-Overclaim.*
- **Geometrie-Norm-Schicht** (öffentlicher Teil von Dim. 7: DIN 3760/3761, ISO 3601, Einbauraum-Normen) — nur soweit für Decode/Bauform nötig.
- **Minimaler Archetyp-Satz** (öffentliches Ingenieurwissen, owner-kuratiert aus öffentlichen Quellen — *nicht* aus Prelon-Daten): Getriebe + Elektromotor + Hydraulikzylinder als Start. Treibt Verstehen/Challenge im E-Wedge.
- **Erweitertes Eval-Lineal** — fünf neue Schranken — §8.
- **Flywheel-Gerüst** (Logging + Klassifikation + Kurations-Queue) — §9. Kuration bleibt owner-manuell.

### VERSCHOBEN — per Disziplin oder bis Flywheel-Signal
Mit der L2-Ratifizierung kommt **alles Feldwissen ausschließlich aus dem Flywheel (§9, clean-room)** — nie aus Prelon. Was Feldwissen braucht, ist daher *verschoben, bis genug davon vorliegt* — nicht durch eine offene Rechtsfrage blockiert. Das ist der einzige inhaltliche Unterschied zur vorigen Fassung, und er ist eine Vereinfachung: kein Warten auf eine Klärung, die nicht kommt.

- **Versagensmodi (Dim. 5)** — verschoben, bis der Flywheel reale Versagensmuster/Fehlerketten aus echter Nutzung produziert hat. (Lehrbuch-/öffentliche Versagensmodi waren nie Prelon-abhängig, haben aber ohne Diagnose-Modus keinen Konsumenten in V2.2.)
- **Hersteller-Fähigkeiten (Dim. 6)** — verschoben; ohne Operation F kein Konsument in V2.2. Der wertende/interne Teil entsteht später aus eigener, über die Zeit gesammelter Evidence (Kategorie-Trennung unten beachten), nie aus Prelon-Daten.
- **Diagnose (D)** als vollständiger Modus — braucht Dim. 5 *und* ein bewiesenes Empfehl-/Coverage-Rückgrat. Doppelt verschoben.
- **Alternativen/Hersteller finden (F)** — braucht Dim. 6.
- **Jede Äquivalenz-Behauptung jenseits des G1/G2-Korridors** — braucht dokumentierte Hersteller-/Datenblatt-Evidence (I-EQ-1), die du dir selbst beschaffst, nie aus Prelon-internen Quellen.
- **Voller Sieben-Modi-/Sieben-Dimensionen-Ausbau** und die breitere Archetyp-Welle (Pumpe, Rührwerk, Pneumatik, Radlager, Flansch …) — nach Flywheel-Signal nachziehen, nicht vorab.
- **Bestehende V2-Deferrals** (Token-Streaming, Vektor-Retrieval/Qdrant, Redis-Working-Memory, Postgres-kanonisches Wissen) — bleiben deferred bis Skalierungs-Trigger.

**Dauerhaft ausgeschlossen (nicht verschoben):** Prelon-Feldwissen in jeder Form (Reklamations-/Kunden-/Anwendungsdaten). Owner-Entscheid, ratifiziert (L2). Dies kommt nie — im Unterschied zu den verschobenen Punkten, die der Flywheel über die Zeit clean-room nachliefert.

**Hersteller-Fähigkeiten — Kategorie-Trennung (für später, festhalten):** Wenn Dim. 6 je gebaut wird, strikt trennen — **belegbar** (Werkstoff/Bauform/Größenbereich verfügbar, Zertifikat vorhanden, Lieferfähigkeit am Datum X bestätigt) vs. **vorsichtig/intern** (Erfahrungsqualität, Reklamationshäufigkeit, Lieferzuverlässigkeit, Compound-Stabilität). Wertende Qualitätsurteile nur mit Beleg, Datum und sauberer Kategorie — sonst wird aus dem Moat eine Haftungsfläche.

---

## 4. Neue Kern-Komponente: das Coverage-Gate

Die wichtigste fehlende Komponente aus dem gesamten Loop. Ohne sie ist „so assertiv wie die Erdung" ein schöner Satz, keine Systemgarantie.

### 4.1 Sitz in der Pipeline
Das Coverage-Gate sitzt **nach** Verstehen/Grounding/Rechnen und **vor** der Antwort-Generierung (L1). Es ist ein deterministischer Kernel-Schritt — wie der Rechenkern, nur für die Frage „wie weit reicht meine geprüfte Erdung für *diesen* Fall?".

```
verstehen → grounden (L2) → rechnen → [COVERAGE-GATE] → antworten (L1, modus-beschränkt) → verifizieren (L3) → zitieren → erinnern
```

### 4.2 Vertrag (I/O)
- **Input:** der normalisierte Fall (Medium, Temperatur, Druck, Bewegung/Geschwindigkeit, Geometrie, Archetyp) + die geerdeten Evidence-Treffer (Matrix-Zellen, Fachkarten, Rechenkern-Resultate, Norm-Bezüge, Archetyp-Profil).
- **Output:** `coverage_status` ∈ {`IN_ENVELOPE`, `PARTIAL_ENVELOPE`, `ANALOG_ONLY`, `OUT_OF_ENVELOPE`} + die Liste der getroffenen/fehlenden Evidence-Achsen (welche Dimension geerdet ist, welche an der Grenze, welche fehlt).
- **Garantie (I-COV-1):** Der Status entsteht aus Daten-/Regelabgleich. Das LLM erhält Status + Evidence und narriert **innerhalb** des erlaubten Modus — es setzt den Status nie.

### 4.3 Status-Bestimmung (Regel-Skizze — CC verfeinert gegen den Ist-Stand)
- **`IN_ENVELOPE`** — alle Fall-Dimensionen gegen geerdete Evidence gedeckt: Matrix-Zelle für Medium×Werkstoff existiert (verträglich), Betriebspunkt innerhalb der validierten Rechenkern-Bereiche, Archetyp-Profil deckt die Konstellation. → assertive Empfehlung erlaubt.
- **`PARTIAL_ENVELOPE`** — Kern gedeckt, aber ≥ 1 Dimension an/nahe einer geerdeten Grenze, **oder** eine `bedingt`-Zelle greift. → bedingte Empfehlung; die konkrete Bedingung wird sichtbar gemacht. *Dies ist die fall-Ebenen-Verallgemeinerung des zell-Ebenen `bedingt` (`disqualified: False, basis: "matrix_conditional"`) — CC baut DARAUF auf, kollabiert es nicht.*
- **`ANALOG_ONLY`** — kein direkter geerdeter Treffer, aber ein naher Nachbar existiert (gleiche Werkstofffamilie, benachbartes Medium). → Analog-Hinweis + **explizites Delta** + Hersteller-Bestätigung zwingend. **Nie** als finaler Material-Tipp auf chemischer Verträglichkeit (I-COV-3).
- **`OUT_OF_ENVELOPE`** — kein geerdeter Treffer, kein sicherer Analog. → keine Materialfreigabe; Kandidatenklassen/Ausschlüsse + Prüfpfad + Hersteller-Prüfung zwingend. **Wird als wertvollstes Flywheel-Signal geloggt (§9).**

### 4.4 Owner-tunbar: die Assertivitäts-Rampe
*Was* „genug Erdung für `IN_ENVELOPE`" heißt, ist eine **Dichte-Frage je Werkstoff/Medium/Archetyp/Operation**, die der Owner tunt (adressiert „Assertivität rampen statt globaler Default"). Anfangs (dünne Matrix) ist die Schwelle streng — wenige Konstellationen qualifizieren als `IN`. Mit wachsender Kuration sinkt die Schwelle dort, wo die Dichte es trägt. Die Rampe ist **Daten/Konfiguration, nicht Code-Logik** — owner-reviewt wie alles Wissen.

---

## 5. Korrigierte Assertivitäts-Mechanik

### 5.1 Status → erlaubter Antwortmodus
Harte Kopplung (I-COV-2). Das LLM darf den Modus nicht überschreiten.

| `coverage_status` | Erlaubter Modus | Output-Ebene (I-COV-4) |
|---|---|---|
| `IN_ENVELOPE` | assertive Empfehlung | **Material** (prescriptive, mit Warum + Quelle) |
| `PARTIAL_ENVELOPE` | bedingte Empfehlung | **Material unter Bedingung** (Bedingung explizit, vor Freigabe prüfen) |
| `ANALOG_ONLY` | Analog-Hinweis | **Kandidatenklasse + Delta** (Hersteller-Bestätigung zwingend) |
| `OUT_OF_ENVELOPE` | keine Materialfreigabe | **Ausschlüsse + Prüfpfad** (Hersteller-Prüfung zwingend) |

In **jedem** Modus: Evidence-Status sichtbar angehängt; L4 (Hersteller-/Anwender-Freigabe) bleibt intakt; auf sicherheitskritisch/unsicher kippt es in „Stopp, bestätigen" (V2.1 §3.6 unverändert).

### 5.2 First-Principles-Kante — nach Reasoning-Typ eingeschnürt (I-COV-3)
Die V2.1-§3.3-Formulierung („begründete Empfehlung aus den Grundprinzipien") leckte die Kern-Doktrin. Korrektur:
- **Geometrisch/strukturell** (Maße, Bauraum, Verpressung, norm-definierte Geometrie) → das LLM darf näherungsweise schließen; das ist deterministisch und norm-gestützt.
- **Chemische Verträglichkeit / Compound-Eignung** → **nie** aus Grundprinzipien. Außerhalb des Envelopes höchstens `ANALOG_ONLY` mit explizitem Delta. „Immer ein Material" heißt nie „ein geratenes Material auf der gefährlichsten Dimension".

---

## 6. Erster Wedge: Gegencheck (E) für den Konstrukteur

### 6.1 Warum dieser Wedge zuerst
- **Käufer-Fit:** Der Konstrukteur kauft *Risiko-Reduktion* („spezifiziere ich gerade das Falsche?"). Für ihn ist die Vorsicht der Honest-Engine — „das ist unbewiesen, beim Hersteller bestätigen" — **kein Manko, sondern das Produkt**. (Im Gegensatz zu Einkauf/Händler, für die dieselbe Vorsicht eine Steuer ist und deren Substitutions-JTBD das sichere Produkt ohnehin nicht bedienen darf.)
- **Bau-Ökonomie:** E ist **C im Bewertungs-Modus** — günstig, sobald der Empfehl-Engine + das Coverage-Gate stehen.
- **Kontinuität:** baut auf bestehendem INC-GEGENCHECK-CORE auf (CC prüft den Ist-Stand dieses Increments im Audit).

### 6.2 Output-Vertrag
Eingabe: Fall + aktuelle Dichtung. Ausgabe — geerdet, verifiziert, mit Quelle, modus-beschränkt durch das Coverage-Gate:
- **passt** (`IN`) → „ja, passt — hier das Warum + Quelle."
- **passt nicht** (`IN`, geerdeter Konflikt) → „nein → *weil* … → Fix."
- **bedingt** (`PARTIAL`) → „passt unter Bedingung X — vor Freigabe prüfen."
- **außerhalb geprüfter Daten** (`OUT`) → „kann ich nicht geerdet bewerten → Prüfpfad + Hersteller-Bestätigung."

Trust-Spine uniform (L1–L4): ein Gegencheck-Urteil ist genauso eine geerdete, verifizierte Behauptung wie eine Empfehlung.

---

## 7. Sekundärer Wedge: Decode entschärft (G1/G2)

Starker akuter Cold-Start-Magnet (täglicher, nerviger, mit Google nicht lösbarer Schmerz) — **aber** mit der schärfsten Haftungs-Kante, also hart gegated.

| Stufe | Status | Regel |
|---|---|---|
| **G1 — Bezeichnung aufschlüsseln** | erlaubt | Code → strukturierte Spezifikation (Maße, Werkstoffklasse, Typ, Merkmale). |
| **G2 — Vergleichskorridor** | erlaubt | Nennmaß-/Bauform-/Werkstoffklassen-Vergleich als *Korridor* + RFQ-fähige Anfragebasis. |
| **G3 — „Teil X ersetzt Teil Y"** | **verboten** ohne Hersteller-/Datenblatt-Evidence (I-EQ-1) | — |
| **G4 — „technisch gleichwertig"** | **nur** bei harter, dokumentierter Äquivalenz (I-EQ-1) | — |

Output-Disziplin (hart verdrahtet, nicht nur Prinzip): „Das bedeutet diese Bezeichnung. Diese Nennmaße, Werkstoffklasse und Bauform sind erkennbar. Diese Punkte sind noch unbewiesen. Daraus erzeugen wir eine saubere Vergleichs-/Anfragebasis." **Nie** eine Ersatzteil-Gleichheit. Die konservative Äquivalenz-Formel ist eine **Bau-Schranke** (Equivalence-Overclaim-Rate, §8), kein Vorsatz.

Braucht: Geometrie-Norm-Schicht (öffentlicher Dim.-7-Teil) + Decode-Parser. Kein Prelon-Feldwissen → IN.

---

## 8. Erweitertes Eval-Lineal — fünf neue Schranken

Das bestehende Lineal (25 Fälle, 10 Klassen, 8 harte Schranken, Human-Oracle-Adjudikation) **misst Korrektheit**. Die Doktrin (§2) behauptet aber **Kalibrierung**. V2.2 fügt fünf Schranken hinzu, die die Doktrin tatsächlich tracken. Owner-adjudiziert (TRAP-02). Schwellen aus L3.

| Metrik | Misst | Schranke |
|---|---|---|
| **Confident-Wrong-Rate** | assertiv *und* falsch (Katastrophen-Quadrant) | Hard-Fail bei jedem Vorkommen |
| **False-Hedge-Rate** | gehedged auf geerdetem Terrain (Wert-Zerstörung andersrum) | Ceiling (owner) |
| **Unsupported-Claim-Rate** | Behauptung ohne Grounding-Provenienz | nahe null |
| **Coverage-Classification-Accuracy** | erkennt das Gate korrekt, *ob* es geerdet ist? (Meta-Metrik) | hoher Floor (≥ 0,95 Vorschlag) |
| **Equivalence-Overclaim-Rate** | Äquivalenz über die Evidence hinaus (Decode) | Hard-Fail bei jedem Vorkommen |

**Coverage-Classification-Accuracy ist die wichtigste:** Bevor man misst, ob eine assertive Antwort falsch war, muss man messen, ob das System überhaupt korrekt erkannt hat, dass es assertiv sein *durfte*. Sie validiert das Coverage-Gate selbst.

Jede neue Operation (E, G1/G2) kommt mit ihren eigenen Eval-Fällen + Schranken — eine Diagnose/Äquivalenz/ein Gegencheck wird genauso gemessen wie eine Empfehlung. **Die Doktrin (§2) gilt produktiv erst, wenn das erweiterte Lineal grün ist (I-CAL-1).**

---

## 9. Der Flywheel — als verdrahtete Pipeline

Der load-bearing Punkt — jetzt eindeutig: **Da Prelon ratifiziert ausgeschlossen ist (L2), ist dieser Flywheel der einzige Pfad zum Feldwissen-Moat.** Er generiert *deine eigene*, clean-room Feldwissens-Basis aus echter Nutzung — Prelon-unabhängig. Damit ist er nicht „nice-to-have", sondern die tragende Säule deiner Wissensstrategie: Ohne ihn entsteht über die Zeit *kein* Feldwissen, und genau das Feldwissen ist der Teil des Moats, den ein Konkurrent nicht von außen kopieren kann.

Konkrete Mechanik (kein Startup-Wort, eine Schleife):

```
Nutzerfall kommt rein
→ Coverage-Gate klassifiziert (PARTIAL / ANALOG / OUT = Lücken-Signal)
→ Lücke wird mit normalisiertem Fall geloggt
→ Häufigkeit wird gezählt (gleiche Lücke = stärkeres Signal)
→ Owner-Kurations-Queue (nach Häufigkeit sortiert)
→ Owner reviewt → neue Matrix-Zelle / Fachkarte / Archetyp-Regel (nie modell-generiert)
→ Eval-Fall wird automatisch ergänzt
→ erst danach steigt der Coverage-Status für diese Konstellation
```

**Bau-Teilung:** CC baut **jetzt** das Gerüst — Logging der Coverage-Lücken mit normalisiertem Fall, Häufigkeits-Zählung, die Kurations-Queue, das Auto-Anhängen des Eval-Falls. Die **Kuration selbst bleibt owner-manuell** (I-COV-1-Geist: Wissen nie modell-generiert).

**Strategischer Effekt:** Dies dreht den Kapazitäts-Engpass ins Asset. Der Owner kuratiert nicht den Chemie-Raum (für eine Person unmöglich), sondern die **gemessene Nachfrage-Verteilung** — die Lücken, die echte Nutzer real treffen. Bau-Priorität folgt damit „Kurations-Kosten pro abgedecktem Realfall", nicht „Wert × Adoption".

---

## 10. Audit-Protokoll für CC

CC führt **zuerst** einen reinen Ist-vs-SOLL-Audit gegen das Repo durch und **hält dann** (Owner-Review), bevor irgendetwas gebaut wird. Das spiegelt den etablierten V2.1-IST-Audit (PR #139).

**Schritt 1 — Ist-Stand etablieren.** Für jede IN-Komponente (§3) gegen das Repo bestimmen: **vorhanden / teilweise / fehlt**. Insbesondere:
- Existiert ein deterministischer Coverage-Schritt in der Pipeline, oder wird Coverage heute implizit im LLM/L2 entschieden? (Wenn implizit → das ist die Haupt-Lücke.)
- Ist `bedingt` / `matrix_conditional` (zell-Ebene) so vorhanden, dass `PARTIAL_ENVELOPE` (fall-Ebene) darauf aufbauen kann?
- Stand von INC-GEGENCHECK-CORE — wie weit trägt es den E-Wedge?
- Welche der drei Start-Archetypen / Geometrie-Normen sind geerdet vorhanden?
- Welche der fünf Eval-Schranken (§8) existieren bereits im Lineal?

**Schritt 2 — Konflikte melden.** Wo widerspricht der Ist-Stand den Invarianten (§2)? Besonders: irgendeine Stelle, an der das LLM heute Coverage/Assertivität *fühlt* statt aus Daten ableitet (I-COV-1-Verstoß), oder Äquivalenz lässig behaupten könnte (I-EQ-1-Verstoß).

**Schritt 3 — Minimalen Änderungs-Satz vorschlagen.** Als Inkremente, jedes mit (a) Doktrin-Gate-Bezug, (b) seinen Eval-Schranken, (c) Halt-Punkt. Vorgeschlagene Inkrement-Reihenfolge:
1. **INC-COVERAGE-GATE** — die deterministische Komponente (§4) + Status→Modus-Kopplung (§5). *Das Fundament; alles andere reitet darauf.*
2. **INC-EVAL-CALIBRATION** — die fünf Schranken (§8) + Coverage-Classification-Fälle. *Vor produktiver Doktrin-Freigabe (I-CAL-1).*
3. **INC-GEGENCHECK-E** — den E-Wedge auf Coverage-Gate + INC-GEGENCHECK-CORE fertigstellen (§6).
4. **INC-DECODE-G12** — Decode entschärft, hart gegated (§7).
5. **INC-FLYWHEEL-SCAFFOLD** — Logging/Queue/Eval-Append (§9).

**Schritt 4 — Halten.** CC adjudiziert keine Owner-finalen Gates (TRAP-02). Jeder produktiv-mutierende Schritt ist owner-freigegeben. `ops/gate.sh` + GOVERNANCE_LOG + eval-REPLAY bleiben durchsetzend.

**Verbote für CC während Audit und Bau:**
- **Nichts unter VERSCHOBEN bauen oder vorbereiten, und nichts dauerhaft Ausgeschlossenes (Prelon-Feldwissen) berühren** — auch nicht „hilfsweise", auch nicht, wenn V2.1 es als wünschenswert beschrieb. Scope-Erweiterung ist ein Audit-Verstoß.
- Keine Wissens-Dimension modell-generieren — Kuration ist owner-manuell.
- Keine `bedingt`-/Coverage-Marker kollabieren — distinkt halten.
- Datei-Edits via Python-Literal-Match-Patches oder Heredocs, nicht nano/inline-sed (Paste-Mangling-Risiko auf dem VPS).

---

## 11. Was bewusst wartet (Sperrliste)

Explizit, damit CC es nicht „hilfsbereit" baut:

- **Diagnose (D)** als Modus — verschoben (braucht verschobene Dim. 5 + bewiesenes Rückgrat).
- **Alternativen/Hersteller (F)** — verschoben (braucht verschobene Dim. 6).
- **Prelon-Feldwissen** in jeder Form — **dauerhaft ausgeschlossen** (Owner-Entscheid L2, ratifiziert). Kommt nie; im Unterschied zu den verschobenen Punkten liefert es auch der Flywheel nicht nach.
- **Hersteller-Fähigkeiten** — verschoben (kein Konsument ohne Operation F; der wertende/interne Teil entsteht später aus eigener, datierter Evidence, nie aus Prelon).
- **Breitere Archetyp-Welle** (über die drei Start-Profile hinaus) — nach Flywheel-Signal nachziehen.
- **V2-Skalierungs-Deferrals** (Streaming, Qdrant, Redis, Postgres-kanonisches Wissen) — bis Trigger.
- **Ops-Schicht** (Anwalt-Claim-Grenze, Keycloak-Secret-Rotation, Per-Turn-Provenienz, CSP/Token-Beweis, LangSmith-Privacy) — eigener Pfad, außerhalb V2.2. *Hinweis: Die Assertivitäts-Doktrin IST eine Haftungs-Position (Product Liability Directive 2024/2853, EU AI Act). Doktrin und Haftungs-Framing gemeinsam designen, auch wenn die juristische Arbeit später kommt — §2 ist nicht rechtlich neutral.*

---

*Ende V2.2 Build- & Audit-Spec. Implementierung folgt dem etablierten doktrin-gegateten Relay: Thorsten = Owner-Oracle (alle Merge/Deploy-Gates), Claude = Senior Reviewer/Gatekeeper, CC = autonomer Builder, an jedem Gate haltend. Gemessen gegen das erweiterte Eval-Lineal und das GOVERNANCE_LOG.*
