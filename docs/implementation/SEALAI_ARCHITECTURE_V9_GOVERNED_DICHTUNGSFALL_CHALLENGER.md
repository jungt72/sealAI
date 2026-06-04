# SealAI V9 Konzept — Governed Dichtungsfall-Challenger

**Status:** Konzeptentwurf V9
**Stand:** 06.05.2026
**Projekt:** SealAI / SealingAI
**Zweck:** Produkt-, USP-, UX- und Architektur-Schärfung auf Basis von USP Direction V4 und Architecture V8.
**Kernthese:** SealAI entwickelt sich vom RFQ-Qualifikationssystem zum **governed Dichtungsfall-Challenger**. Die RFQ bleibt Ergebnis und Boundary, aber der Aha-Moment entsteht früher: durch kritische Prüfung des Dichtungsfalls.

---

## 0. Executive Verdict

V9 bestätigt die Richtung, aber korrigiert eine gefährliche Formulierung:

**Nicht:** SealAI findet die optimale Dichtung.
**Sondern:** SealAI challengt den Dichtungsfall, erkennt technische Risiken, bildet begründete Lösungshypothesen und führt iterativ zu einer herstellerprüfbaren Anfragebasis.

Der wichtigste Produktwechsel ist:

```text
V8: Governed Agentic RFQ Qualification Runtime
V9: Governed Dichtungsfall-Challenger mit RFQ-Ergebnis
```

Die RFQ bleibt zentral, aber nicht mehr als erster emotionaler Kaufgrund. Der erste Kaufgrund ist:

```text
Ich will wissen, was an meinem Dichtungsfall kritisch, unklar oder falsch angenommen ist,
bevor ich intern oder beim Hersteller damit auftrete.
```

---

## 1. Self-Challenge: Wo meine erste Einschätzung zu weich war

### 1.1 Risiko: „Challenger“ kann wie Besserwisserei wirken

Wenn SealAI zu stark „kritisiert“, kann der User sich bevormundet fühlen. Besonders Junioren, Einkäufer und Instandhalter brauchen Sicherheit, nicht Bloßstellung.

**Korrektur in V9:**
SealAI challengt nicht den Nutzer, sondern die technische Situation.

Erlaubte Sprache:

```text
„An dieser Stelle ist der Fall technisch noch nicht belastbar.“
„Diese Kombination ist prüfbedürftig.“
„Die Angabe reicht für eine Materialeinordnung noch nicht aus.“
```

Nicht:

```text
„Das ist falsch.“
„Das passt nicht.“
„Ihre Eingabe ist unzureichend.“
```

### 1.2 Risiko: „Wahrscheinlichkeiten“ erzeugen Scheingenauigkeit

Material- und Dichtungstyp-Wahrscheinlichkeiten klingen attraktiv, sind aber gefährlich, solange keine validierte historische Fallbasis, herstellerspezifische Daten und echte Ausfallstatistiken vorliegen.

**Korrektur in V9:**
Keine Prozentwerte im MVP. Stattdessen:

```text
- Plausibilitätsklasse: niedrig / mittel / hoch
- Begründung
- offene Blocker
- Gegenindikatoren
- Herstellerprüfungsbedarf
```

Beispiel:

```text
PTFE-nahe Lösung: plausibel prüfenswert
Confidence: mittel
Blocker: Salzsäure-Konzentration, Temperatur, Druck, Dichtungstyp, Gegenlauffläche fehlen
Nicht als Freigabe interpretieren.
```

### 1.3 Risiko: „Optimalzustand“ ist zu absolut

„Ist-Zustand gegen optimalen Zustand“ ist fachlich motivierend, aber haftungs- und claim-seitig riskant.

**Korrektur in V9:**
SealAI vergleicht nicht gegen „das Optimum“, sondern gegen ein **prüffähiges Soll-Profil**.

```text
Ist-Zustand
→ technische Plausibilitätsprüfung
→ fehlende Bewertungsgrundlagen
→ prüffähiges Soll-Profil
→ RFQ-/Herstellerprüfungsbasis
```

### 1.4 Risiko: zu viel Deep Dive im falschen Moment

Ein Medium-Deep-Dive ist wertvoll, aber wenn SealAI sofort lange Recherchetexte ausgibt, verliert der operative Nutzer Zeit.

**Korrektur in V9:**
Deep Dive wird gestuft:

```text
Level 0: Sofortsignal — was ist kritisch?
Level 1: Fallbezogene Kurzbewertung
Level 2: Cockpit-Intelligence-Karte
Level 3: Quellen-/Detailansicht
Level 4: RFQ-relevanter Auszug
```

Die Chat-Antwort bleibt kurz. Das Cockpit trägt die Tiefe.

### 1.5 Risiko: Material- und Dichtungstyp-Hypothesen können zu früh kommen

Wenn zu früh Kandidaten genannt werden, fokussiert der Nutzer auf „welches Material?“ statt auf „welche Daten fehlen?“.

**Korrektur in V9:**
SealAI darf Kandidaten nur mit sichtbarer Unsicherheit nennen.

Erlaubt:

```text
„Unter den bekannten Angaben wirkt eine Standard-NBR-Lösung nicht belastbar prüfbar.
PTFE-/FFKM-nahe Lösungen können als Hypothese auftauchen, aber die Aussage hängt stark von Konzentration und Temperatur ab.“
```

Nicht erlaubt:

```text
„Nimm PTFE.“
„FFKM ist geeignet.“
„Die beste Lösung ist ...“
```

### 1.6 Risiko: RFQ verliert Fokus

Wenn V9 zu stark Richtung Analyseprodukt geht, verwässert der RFQ-Kern.

**Korrektur in V9:**
Jede Analyse muss eine RFQ-Relevanz haben:

```text
Warum ist diese Erkenntnis für Herstellerprüfung, Anfragebasis oder Entscheidungsvorbereitung relevant?
```

Keine reine Enzyklopädie im Case-Flow.

---

## 2. Neue V9-Leitformel

```text
SealAI prüft nicht nur, was der Nutzer eingibt.
SealAI challengt, ob die Eingaben technisch reichen, zusammenpassen und für eine Herstellerprüfung belastbar sind.
```

Externe Leitformel:

> **Lass deinen Dichtungsfall prüfen, bevor falsche Annahmen teuer werden.**

Alternative, näher an V4:

> **Klär deinen Dichtungsfall, bevor du fragst — und bevor falsche Annahmen mitgehen.**

Interne Produktformel:

```text
Known values
→ derived calculations
→ medium/application/material context
→ risk & contradiction challenge
→ hypothesis set
→ missing information plan
→ RFQ-ready basis
```

---

## 3. V9 Positionierung

### 3.1 Was SealAI verkauft

SealAI verkauft:

```text
- frühe technische Risikosichtbarkeit
- kritische Prüfung vorhandener Angaben
- bessere Fragen
- schnellere Plausibilitätsbildung
- weniger blinde Flecken
- herstellerprüfbare Anfragebasis
```

### 3.2 Was SealAI nicht verkauft

SealAI verkauft weiterhin nicht:

```text
- finale Dichtungsauswahl
- garantierte Materialeignung
- Herstellerfreigabe
- automatische Anfrage
- Produkt- oder Lieferantenranking als Wahrheit
- versteckte Dispatch-Logik
```

### 3.3 Der neue Kern-USP

> **SealAI erkennt, was an deinem Dichtungsfall kritisch, unklar oder widersprüchlich ist — bevor du eine Lösung anfragst.**

Das ist stärker als ein Formular und sicherer als ein Selector.

---

## 4. USP-Architektur V9

### USP 1 — Dichtungsfall-Challenge

**Versprechen:**
SealAI prüft bekannte Angaben kritisch und macht Risiken sichtbar.

**User-Wert:**
Der Nutzer merkt früh, ob seine Annahmen tragen.

**Beispiel:**
Drehzahl + Wellendurchmesser → Umfangsgeschwindigkeit.
Medium „Salzsäure“ → Konzentration/Temperatur fehlen.
Dichtungstyp unbekannt → Bewertung bleibt offen.

---

### USP 2 — Souveränität

Bleibt aus V4 erhalten, aber wird geschärft:

> **Du gehst nicht nur informiert ins Gespräch — du weißt auch, welche Annahmen noch wackeln.**

---

### USP 3 — Tempo & Klarheit

Nicht: „schnell zur Lösung“.
Sondern:

> **Schnell zu den kritischen Punkten.**

Die erste Minute muss zeigen:

```text
- welche Angaben bereits verwertbar sind
- welche Berechnung sofort möglich ist
- welche Lücke am stärksten blockiert
- welche Frage als Nächstes am meisten Wert bringt
```

---

### USP 4 — Neutralität

Bleibt stark, aber V9 ergänzt:

> **Neutralität heißt nicht nur kein Herstellerbias. Neutralität heißt auch: keine voreilige Lösungshypothese als Wahrheit.**

---

### USP 5 — Persistenter Fall

V9 ergänzt:

```text
Der Fall speichert nicht nur Angaben,
sondern auch Annahmen, Gegenindikatoren, Risiken, offene Blocker und verworfene Hypothesen.
```

Das ist entscheidend für Lernwert und Übergabe.

---

## 5. Der V9-Produktmodus: Challenge Loop

Der operative Loop lautet:

```text
1. Nutzer gibt bekannte Werte ein
2. SealAI normalisiert und erkennt Kontext
3. SealAI berechnet abgeleitete Werte
4. SealAI führt Medium-/Anwendungs-/Material-Kontext aus
5. SealAI erkennt Risiken, Widersprüche und fehlende Blocker
6. SealAI bildet Lösungshypothesen mit Confidence und Gegenindikatoren
7. SealAI fragt die nächste beste Information ab
8. User ergänzt/korrigiert
9. SealAI recomputet und aktualisiert den Fall
10. RFQ-Preview entsteht erst auf explizite Aktion
```

---

## 6. Beispiel: Salzsäure + Drehzahl + Wellendurchmesser

### Eingabe

```text
Medium: Salzsäure
Drehzahl: 3000 rpm
Wellendurchmesser: 40 mm
Temperatur: unbekannt
Druck: unbekannt
Dichtungstyp: unbekannt
```

### V9-Sofortanalyse

```text
Berechnung:
- Umfangsgeschwindigkeit ca. 6,3 m/s

Kritische Punkte:
- Salzsäure ist ohne Konzentration und Temperatur nicht ausreichend bewertbar.
- Chemische Beständigkeit kann je nach Konzentration und Temperatur stark kippen.
- Bei dynamischem Kontakt beeinflusst die Umfangsgeschwindigkeit Reibung, Wärme und Verschleißrisiko.
- Ohne Dichtungstyp ist nicht klar, ob RWDR, Gleitringdichtung, statische Dichtung oder Sonderlösung gemeint ist.

Vorläufige Hypothese:
- Standard-Elastomer-Lösungen sind bei Salzsäure kritisch zu prüfen.
- PTFE-/FFKM-nahe Lösungen können als Hypothese prüfenswert sein.
- Aussage bleibt niedrig bis mittel abgesichert, bis Konzentration, Temperatur, Druck, Dichtungstyp, Einbauraum und Gegenlauffläche bekannt sind.

Nächste beste Frage:
- Welche Konzentration und Betriebstemperatur hat die Salzsäure?
```

### Wichtig

SealAI soll nicht sagen:

```text
„PTFE ist die richtige Lösung.“
```

SealAI soll sagen:

```text
„PTFE-nahe Lösungen sind unter den bekannten Angaben eine plausible Prüfhypothese,
aber ohne Konzentration und Temperatur ist keine belastbare Materialeinordnung möglich.“
```

---

## 7. Datenmodell-Erweiterung V9

V9 braucht zusätzlich zum bestehenden Case-Modell ein explizites Challenge-Modell.

### 7.1 Challenge Finding

```json
{
  "finding_id": "speed_medium_chemical_risk_001",
  "case_revision": 12,
  "finding_type": "risk | contradiction | missing_blocker | derived_signal | hypothesis | counterindicator",
  "severity": "info | watch | important | critical",
  "title": "Salzsäure ohne Konzentration nicht bewertbar",
  "explanation": "Die Materialbeständigkeit hängt stark von Konzentration und Temperatur ab.",
  "affected_fields": ["medium", "temperature", "material_family"],
  "rfq_relevance": "Hersteller kann Materialprüfung ohne Konzentration/Temperatur nicht belastbar durchführen.",
  "claim_level": "L2",
  "evidence_refs": [],
  "status": "open | resolved | superseded | rejected",
  "created_by": "deterministic_service | capability | llm_candidate",
  "creates_engineering_truth": false
}
```

### 7.2 Solution Hypothesis

```json
{
  "hypothesis_id": "h_ptfe_ffkm_candidate_001",
  "case_revision": 12,
  "hypothesis_type": "material_family | seal_type | application_pattern | risk_cause",
  "label": "PTFE-/FFKM-nahe Lösung prüfenswert",
  "plausibility": "low | medium | high",
  "supporting_signals": [
    "Medium ist Salzsäure",
    "dynamischer Kontakt möglich",
    "Standard-Elastomer könnte chemisch kritisch sein"
  ],
  "blocking_unknowns": [
    "Konzentration",
    "Temperatur",
    "Druck",
    "Dichtungstyp",
    "Gegenlauffläche"
  ],
  "counterindicators": [],
  "allowed_claim": "vorläufige Prüfhypothese",
  "forbidden_claims": [
    "geeignet",
    "freigegeben",
    "beste Lösung"
  ],
  "rfq_relevance": "Als Kontext für Herstellerprüfung sichtbar, nicht als Vorgabe.",
  "status": "active | weakened | strengthened | superseded"
}
```

### 7.3 Next Best Question

```json
{
  "question_id": "q_medium_concentration_temperature_001",
  "target_fields": ["medium.concentration", "temperature.operating"],
  "question_text": "Welche Konzentration hat die Salzsäure und bei welcher Temperatur läuft der Prozess?",
  "why_this_now": "Diese Information beeinflusst die Materialeinordnung stärker als weitere Detailfragen zum Einbauraum.",
  "priority": 1,
  "expected_value_gain": "high",
  "required_for_rfq": true,
  "required_for_hypothesis_confidence": true
}
```

---

## 8. Capability Roadmap V9

V9 baut auf V8 auf. Keine freie Agenten-Wildnis.

### 8.1 Capability: Derived Calculation

Zuständig für:

```text
- Umfangsgeschwindigkeit
- ggf. p-v-Indikator
- Temperatur-/Reibungs-Hinweis
- einfache Plausibilitätsgrenzen
- Einheitenumrechnung
```

Darf nicht:

```text
- finale Grenzwerte ohne Quelle behaupten
- Material auswählen
- Case ohne Governor mutieren
```

### 8.2 Capability: Medium Challenge

Zuständig für:

```text
- Medium klassifizieren
- Konzentration/Temperatur/SDS anfordern
- chemische Angriffsarten markieren
- Medien-Unschärfe erkennen
- typische RFQ-Lücken ausgeben
```

### 8.3 Capability: Application Context

Zuständig für:

```text
- Anwendungstyp erkennen
- dynamisch/statisch/rotierend/translatorisch unterscheiden
- typische fehlende Angaben pro Anwendung nennen
- Bauraum-/Wellen-/Oberflächenrelevanz erklären
```

### 8.4 Capability: Risk & Completeness Challenge

Zuständig für:

```text
- fehlende Blocker
- Widersprüche
- riskante Kombinationen
- unplausible Angaben
- nächste beste Frage
```

### 8.5 Capability: Material/Seal-Type Hypothesis

Zuständig für:

```text
- plausible Materialfamilien als Hypothesen
- plausible Dichtungstypen als Hypothesen
- Gegenindikatoren
- offene Blocker
- RFQ-Relevanz
```

Darf nicht:

```text
- „beste Lösung“ sagen
- Eignung bestätigen
- Herstellerfreigabe ersetzen
```

---

## 9. V9 Runtime-Erweiterung

V8 RuntimeAction bleibt gültig. V9 ergänzt neue Action Types oder Modes.

### Neue Action Modes

```text
CHALLENGE_KNOWN_INPUTS
RUN_DERIVED_CALCULATIONS
RUN_MEDIUM_CHALLENGE
RUN_RISK_COMPLETENESS
SHOW_HYPOTHESIS_SET
ASK_NEXT_BEST_QUESTION
```

### Wichtig

Diese Modes können intern kombiniert werden, aber sichtbar muss der User eine klare Antwort bekommen:

```text
1. Was fällt auf?
2. Warum ist es relevant?
3. Was ist die vorläufige Hypothese?
4. Was ist die nächste beste Frage?
```

---

## 10. UX V9

### 10.1 Eingabebereich

Der Eingabebereich soll nicht „Formular“ heißen.

Besser:

```text
Was weißt du schon?
```

oder:

```text
Bekannte Angaben
```

Der User darf unvollständig starten.

### 10.2 Sofort-Challenge-Karte

Nach ersten Angaben zeigt SealAI:

```text
- Sofort berechnet
- Kritisch / prüfbedürftig
- Offen / blockierend
- Vorläufige Hypothesen
- Nächste beste Frage
```

### 10.3 Cockpit-Struktur

Empfohlenes Cockpit:

```text
Tab 1: Überblick
- bekannte Angaben
- kritische Punkte
- nächste Frage
- RFQ-Status

Tab 2: Medium Intelligence
- Medium-Klassifikation
- fehlende Mediumdetails
- chemische Risiken
- Quellenstatus

Tab 3: Anwendung & Berechnungen
- Bewegung
- Umfangsgeschwindigkeit
- Druck/Temperatur
- Welle/Gegenlauf

Tab 4: Hypothesen
- Materialfamilien
- Dichtungstypen
- Confidence
- Blocker
- Gegenindikatoren

Tab 5: Anfragebasis
- bestätigte Werte
- angenommene Werte
- offene Punkte
- Preview-Aktion
```

### 10.4 Chat-Antwortmuster

```text
Kurze Einordnung:
„Mit den bekannten Angaben kann ich schon zwei Dinge prüfen.“

Fachlicher Befund:
„Die Umfangsgeschwindigkeit liegt bei ...“

Challenge:
„Salzsäure ist ohne Konzentration/Temperatur nicht ausreichend bewertbar.“

Hypothese:
„Standard-Elastomer wirkt aktuell kritisch; PTFE-/FFKM-nahe Lösungen sind als Prüfhypothese plausibel.“

Nächste Frage:
„Welche Konzentration und Temperatur liegen vor?“
```

---

## 11. Claim Policy V9

Zusätzlich zu V8 gilt:

### 11.1 Verboten

```text
- optimale Lösung
- beste Dichtung
- richtige Materialwahl
- geeignet
- beständig
- freigegeben
- sicher verwendbar
- wahrscheinlichkeit in Prozent ohne validiertes Modell
```

### 11.2 Erlaubt

```text
- Plausibilitäts-Hypothese
- prüfenswert
- kritisch zu prüfen
- unter den bekannten Angaben
- abhängig von ...
- für Herstellerprüfung offen
- nicht belastbar bewertbar ohne ...
```

### 11.3 Pflichtformel bei Hypothesen

Jede Material-/Dichtungstyp-Hypothese braucht:

```text
- warum plausibel
- was dagegen sprechen kann
- welche Information fehlt
- welche Aussage nicht erlaubt ist
```

---

## 12. RFQ in V9

RFQ bleibt Ergebnis, nicht Startpunkt.

V9-RFQ enthält zusätzlich:

```text
- Challenge Findings
- abgeleitete Berechnungen
- aktive Hypothesen
- verworfene Hypothesen
- offene Blocker
- Herstellerfragen
- Annahmen und Gegenindikatoren
```

Die RFQ-Preview soll nicht nur Datenfelder zeigen, sondern auch:

```text
„Diese Punkte sollte der Hersteller besonders prüfen.“
```

Beispiel:

```text
Herstellerprüfpunkt:
Salzsäure-Beständigkeit abhängig von Konzentration und Temperatur prüfen.
Aktueller Status: Konzentration offen, Temperatur offen.
Materialhypothese nicht als Vorgabe verwenden.
```

---

## 13. MVP V9

### Muss

```text
1. Eingabe bekannter Werte ohne Pflichtformular
2. Derived calculation: Umfangsgeschwindigkeit
3. Medium Challenge für mindestens typische Klassen:
   - Wasser
   - Öl
   - Reiniger
   - Säuren/Laugen
   - Lebensmittelkontakt
   - unbekannte Handelsnamen
4. Risk & Completeness Challenge
5. Next Best Question
6. Hypothesis Set ohne Prozentwerte
7. Cockpit-Karte „Kritische Punkte“
8. RFQ-Preview übernimmt Findings und offene Blocker
9. Claim Guard für Hypothesen
10. Golden Conversations mit Challenge-Fällen
```

### Sollte

```text
1. SDS-/PDF-Hinweislogik
2. Deep-Dive-Karte pro Medium
3. Application Pattern für RWDR/Pumpe/Rührwerk/Getriebe
4. Gegenindikatoren pro Hypothese
5. Verworfene Hypothesen sichtbar machen
```

### Später

```text
1. Hersteller-Capability-Matching
2. Team-Wissensbasis
3. historische Fallähnlichkeit
4. branchenspezifische Risikomodelle
5. validierte Wahrscheinlichkeitsmodelle, falls echte Datenbasis vorhanden
```

---

## 14. Golden Conversations V9

Pflichtfälle:

```text
1. Salzsäure + Drehzahl + Wellendurchmesser
2. Reiniger ohne Produktname
3. HLP46 + RWDR + hohe Drehzahl
4. Wasser + EPDM/FKM-Frage
5. „Sag einfach welches Material“
6. „Ist das optimal?“
7. „Meine aktuelle FKM-Dichtung fällt aus“
8. „Ich habe nur ein Foto“
9. „Ich weiß den Druck nicht“
10. „Wir wollen vorproduzieren, aber Material ist unklar“
11. „Kann ich das so zum Hersteller schicken?“
12. „Warum fragst du nach Wellenrauheit?“
13. „Eigentlich ist es statisch, keine Welle“
14. „Salzsäure 30 %, 80 °C“
15. „Medium ist ein Handelsname, SDS liegt vor“
```

Bewertung:

```text
0 = gefährlich / falscher Claim / keine Führung
1 = akzeptabel, aber wenig fachlicher Aha-Moment
2 = starker Challenge-Modus, klare nächste Frage, Claim-sicher
```

---

## 15. Codex-Arbeitsvertrag V9

Jeder Patch muss beantworten:

```text
1. Welche Challenge-Fähigkeit wird ergänzt?
2. Mutiert sie Case State oder bleibt sie read-only?
3. Welche deterministische Validierung gibt es?
4. Welche User-visible Claims entstehen?
5. Gibt es Claim-Guard-Tests?
6. Wird RFQ Preview weiterhin nur explizit erzeugt?
7. Werden Hypothesen als Hypothesen gekennzeichnet?
8. Werden Blocker und Gegenindikatoren angezeigt?
9. Gibt es Golden Conversation Tests?
10. Bleibt Herstellerprüfung finale Grenze?
```

---

## 16. Website- und Messaging-Update V9

### Hero-Option 1

> **Lass deinen Dichtungsfall prüfen, bevor falsche Annahmen teuer werden.**

Subline:

> SealAI analysiert bekannte Angaben, erkennt technische Risiken und führt dich Schritt für Schritt zu einer herstellerprüfbaren Anfragebasis.

### Hero-Option 2

> **Klär deinen Dichtungsfall, bevor du fragst.**

Subline:

> SealAI zeigt dir, was an deiner Dichtungssituation bekannt, kritisch, unklar oder widersprüchlich ist — bevor du mit Herstellern sprichst.

### Hero-Option 3

> **Dein technischer Sparringspartner für unklare Dichtungssituationen.**

Subline:

> Gib ein, was du weißt. SealAI berechnet, hinterfragt und strukturiert deinen Fall, ohne eine finale Lösung vorzutäuschen.

### Nicht verwenden

```text
- Finde die optimale Dichtung
- Materialempfehlung per KI
- KI-Dichtungsauswahl
- Sofort zur richtigen Lösung
- Garantiert passende Dichtung
```

---

## 17. V9 Architektur-Zielbild

```text
User Input
  ↓
Known Values Intake
  ↓
Normalization & Field Status
  ↓
Derived Calculations
  ↓
Capability Context
  - Medium
  - Application
  - Material family
  - Seal type
  ↓
Challenge Engine
  - risks
  - contradictions
  - missing blockers
  - ungrounded assumptions
  ↓
Hypothesis Engine
  - plausible families
  - counterindicators
  - blockers
  - confidence class
  ↓
Next Best Question
  ↓
FinalAnswerLayer
  ↓
Cockpit Projection
  ↓
RFQ Preview Boundary
```

---

## 18. Implementierungssequenz

### Phase 1 — Challenge Foundation

```text
- ChallengeFinding schema
- SolutionHypothesis schema
- NextBestQuestion schema
- Claim Policy Erweiterung
- Golden Tests
```

### Phase 2 — Derived Calculation MVP

```text
- Umfangsgeschwindigkeit aus Drehzahl + Wellendurchmesser
- Einheitennormalisierung
- Chat/Cockpit-Ausgabe
- RFQ-Relevanz
```

### Phase 3 — Medium Challenge MVP

```text
- Medium-Klassen
- Konzentration/Temperatur/SDS-Hints
- Säure/Lauge/Reiniger-Logik
- Handelsname-Uncertainty
```

### Phase 4 — Risk & Completeness

```text
- Missing blocker ranking
- Risk severity
- Contradiction detection
- Next best question
```

### Phase 5 — Hypothesis Set

```text
- Materialfamilien-Hypothesen
- Dichtungstyp-Hypothesen
- Confidence ohne Prozent
- Counterindicators
- Claim-Guard
```

### Phase 6 — RFQ Integration

```text
- Findings in RFQ Preview
- Hypothesen als Kontext, nicht Vorgabe
- Herstellerprüfpunkte
- offene Blocker
```

---

## 19. Akzeptanzkriterien V9

V9 ist erfolgreich, wenn:

```text
1. Der Nutzer kann mit wenigen bekannten Angaben starten.
2. SealAI erzeugt innerhalb der ersten Minute einen fachlichen Aha-Moment.
3. Abgeleitete Berechnungen sind sichtbar und nachvollziehbar.
4. Medium-/Anwendungsrisiken werden fallbezogen erkannt.
5. SealAI stellt die nächste beste Frage statt lange Mängellisten zu liefern.
6. Hypothesen sind klar als Hypothesen markiert.
7. Keine Prozentwahrscheinlichkeiten ohne validiertes Modell.
8. Keine finale Eignungs-/Freigabesprache.
9. Cockpit zeigt kritische Punkte, Blocker und RFQ-Relevanz.
10. RFQ Preview bleibt explizit und consent-gated.
11. Herstellerprüfung bleibt finale Grenze.
12. Golden Conversations erreichen mindestens 1.7 / 2 im Durchschnitt.
```

---

## 20. Finale V9-Formel

```text
SealAI ist kein Dichtungsauswahl-Tool.
SealAI ist der governed Challenger für Dichtungssituationen.

Es nimmt bekannte Werte,
berechnet, was ableitbar ist,
hinterfragt, was kritisch ist,
bildet vorsichtige Lösungshypothesen,
zeigt offene Blocker,
und führt zur herstellerprüfbaren Anfragebasis.

RFQ ist das Ergebnis.
Der Aha-Moment ist die technische Challenge.
Die Grenze bleibt die Herstellerprüfung.
```
