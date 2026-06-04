# sealing | Intelligence — finales Produkt- und MVP-Konzept

**Stand:** 2026-05-27
**Fokus:** RWDR / Radialwellendichtringe als erster vertikaler MVP
**Produktstatus:** Ready for limited external RWDR demo — nur geführt, nicht öffentlich/self-service
**Dachmarke:** sealing | Intelligence
**Engine / Systemname:** sealingAI
**Erstes Produktartefakt:** Technical RWDR RFQ Brief

---

## SSoT-Hinweis für Codex

Dieses Dokument ist die **Produkt-SSoT** für den aktuellen RWDR-MVP.

Es ersetzt nicht den V10-Architekturrahmen. V10 bleibt die technische
Dacharchitektur für freie Kommunikation, Wissensdialog, semantisches Routing,
Governed Runtime, RAG, LangSmith und Deployment.

Dieses Dokument entscheidet aber den **aktuellen Produktfokus**:

```text
RWDR zuerst.
Geführte limitierte Demo.
Technical RWDR RFQ Brief als Produktartefakt.
Keine Material-, Produkt- oder Herstellerempfehlung.
Keine finale Freigabe.
```

Codex soll bei Produktentscheidungen zuerst dieses Dokument lesen, danach
`AGENTS.md`, `docs/architecture/SSOT_REGISTRY.md` und das V10-Konzept gegenprüfen.

Live-Status-Korrektur zum ursprünglichen Entwurf: Am 2026-05-27 wurde auf dem
VPS geprüft, dass `/api/v1/rfq/rwdr/analyze` live montiert und ohne Token
korrekt auth-gated ist (`401`), also nicht mehr `404`. Ein vollständiger
authentifizierter End-to-End-Smoke bleibt weiterhin separat zu prüfen.

---

## 1. Executive Summary

**sealing | Intelligence** ist eine spezialisierte KI- und Fachlogik-Plattform für Dichtungstechnik. Der erste MVP fokussiert bewusst auf **Radialwellendichtringe / RWDR / Rotary Shaft Seals**.

Das Produkt gibt **keine finale Dichtungslösung frei**, empfiehlt **kein Material**, kein Produkt und keinen Hersteller. Stattdessen verwandelt sealing | Intelligence unklare technische Dichtungsanfragen in strukturierte, belegte und herstellerfähige **Technical RWDR RFQ Briefs**.

Der zentrale Produktnutzen lautet:

> **sealing | Intelligence macht unklare RWDR-Anfragen herstellerbewertbar.**

Oder noch konkreter:

> **Aus „Wellendichtring 45x62x8 undicht“ wird eine strukturierte Herstelleranfrage mit bestätigten Daten, fehlenden kritischen Angaben, berechneten Signalen, Review-Themen und gezielten Rückfragen.**

---

## 2. Produktdoktrin

Die nicht verhandelbare Produktdoktrin lautet:

```text
AI extracts.
User confirms.
sealing | Intelligence structures.
Manufacturer / distributor / responsible engineer evaluates.
```

Auf Deutsch:

```text
KI extrahiert.
Der Nutzer bestätigt.
sealing | Intelligence strukturiert.
Hersteller, Händler oder verantwortliche Fachstelle bewertet final.
```

Das System darf nicht behaupten:

```text
- finale technische Eignung
- Materialfreigabe
- Produktempfehlung
- Herstellerempfehlung
- Zertifizierung
- Sicherheitsfreigabe
- Lebensdauerzusage
```

Das System darf liefern:

```text
- strukturierte technische Anfrage
- bestätigte und unbestätigte Angaben
- kritische fehlende Informationen
- technische Review-Themen
- berechnete Signale, z. B. Umfangsgeschwindigkeit
- Mess- und Prüfangaben
- gezielte Herstellerfragen
- exportierbarer Technical RWDR RFQ Brief
```

---

## 3. Positionierung

### Dachpositionierung

> **sealing | Intelligence — technische Intelligenz für bessere Dichtungsanfragen.**

### MVP-Positionierung

> **Der kostenlose Technical RWDR RFQ Brief Generator für Radialwellendichtringe.**

### Nutzerclaim

> **Radialwellendichtring undicht? Erstelle in Minuten eine saubere Herstelleranfrage.**

### Kommerzieller Nutzensatz

> **Weniger Rückfragen. Schnellere Herstellerbewertung. Bessere technische Anfragequalität.**

---

## 4. Warum RWDR als erster MVP?

Radialwellendichtringe sind ein idealer erster vertikaler Fokus, weil sie häufig, technisch anspruchsvoll und in der Praxis oft unvollständig angefragt werden.

Typische echte Anfrage:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

Viele Nutzer kennen nur:

```text
- alte Maße
- Maschine / Einbaustelle
- grobes Medium
- Ausfallbild
- Dringlichkeit
```

Hersteller brauchen aber zusätzlich:

```text
- d1 / D / b
- Bauform / Dichtlippe / Staublippe / Feder / Außenmantel
- Medium innen und Umgebung außen
- Temperaturbereich
- Druckdifferenz
- Drehzahl / Umfangsgeschwindigkeit
- Drehrichtung / Reversierbetrieb
- Wellenzustand / Gegenlauffläche
- Rundlauf / Exzentrizität
- Gehäusebohrung / Einbauraum
- Montagebedingungen
- regulatorische Anforderungen
- gewünschte Standzeit / Leckageanforderung
```

Genau diese Lücke füllt sealing | Intelligence.

---

## 5. Nicht-Ziele

Der MVP ist ausdrücklich **kein**:

```text
- Dichtungsauswahltool mit finaler Empfehlung
- Materialfreigabe-System
- Produktkonfigurator mit Freigabe
- Hersteller-Routing
- Marketplace
- Lead-Gen-System
- Zertifizierungssystem
- Lebensdauerberechnung mit Garantie
- allgemeine Dichtungs-KI für alle Bauarten
```

Nicht im MVP:

```text
- Herstellerlisting
- Manufacturer Matching
- Materialkandidaten im Nutzeroutput
- Produktnummern
- Ranking von Herstellern
- automatische Anfrageversendung an Hersteller
- Self-Service Public Launch
```

---

## 6. Kern-Use-Case

### Eingabe

Ein Nutzer beschreibt einen RWDR-Fall per Freitext:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

### System verarbeitet

```text
1. Anfrage analysieren
2. technische Kandidatenfelder extrahieren
3. Source Spans anzeigen
4. haftungstragende Felder vom Nutzer bestätigen lassen
5. fehlende kritische Angaben erkennen
6. Umfangsgeschwindigkeit berechnen
7. Review-Themen ableiten
8. Messhinweise erzeugen
9. Herstellerfragen erzeugen
10. Technical RWDR RFQ Brief generieren
11. Markdown/PDF exportieren
12. Case-State revisionieren
```

### Ergebnis

Ein strukturierter **Technical RWDR RFQ Brief** mit:

```text
- Status
- bestätigte Angaben
- unbestätigte Angaben
- kritisch fehlende Angaben
- hilfreich fehlende Angaben
- berechnete Werte
- Engineering Review-Themen
- Mess- und Prüfangaben
- Herstellerfragen
- regulatorische / dokumentarische Anforderungen
- Quellenübersicht
- Disclaimer
```

---

## 7. Statusmodell

Es gibt genau drei kundenseitige Status:

```text
COMPLETE
Der Brief enthält genügend bestätigte Informationen für eine Herstellerbewertung.

NEEDS_CLARIFICATION
Kritische Informationen fehlen oder wurden noch nicht bestätigt.

OUT_OF_SCOPE
Der Fall liegt außerhalb des unterstützten RWDR-MVP-Scopes.
```

`COMPLETE` bedeutet ausdrücklich **nicht**, dass die Dichtung technisch freigegeben ist.

---

## 8. Evidence & Confirmation Gate

Haftungstragende Felder dürfen nur in den finalen Brief, wenn sie:

```text
1. direkt vom Nutzer eingegeben wurden
```

oder

```text
2. aus Text extrahiert wurden,
   eine exakte Quellenstelle haben,
   und vom Nutzer bestätigt oder editiert wurden.
```

Haftungstragende Felder sind unter anderem:

```text
- d1 / D / b
- Medium
- Konzentration
- Temperatur
- Druck
- Drehzahl
- Materialbezeichnung
- Normen / Standards
- Herstellerkennung
- Altteilnummer
- Gefahrstoffhinweise
- Food/FDA/Hygiene-Anforderungen
- Anwendungskategorie
- Dichtungstyp
```

Mögliche Nutzeraktionen:

```text
- Bestätigen
- Bearbeiten
- Nicht angegeben / unbekannt
- Verwerfen
```

Regeln:

```text
- Unbestätigte LLM-Felder erscheinen nicht als bestätigte Fakten.
- „Unbekannt“ ist ein expliziter Zustand, aber kein bestätigter Wert.
- Rejected Fields erscheinen nicht im Brief als bestätigte Fakten.
- Fehlende kritische Felder bleiben sichtbar.
```

---

## 9. Intelligence-Module

Der RWDR-MVP enthält explizite, testbare Module:

```text
1. RWDRCaseOrchestrator
2. UserIntentIntelligence
3. SealTypeIntelligence / Dichtungstyp Intelligence
4. ApplicationIntelligence / Anwendungs Intelligence
5. GeometryDimensionIntelligence
6. MediumIntelligence
7. MaterialIntelligence
8. OperatingConditionIntelligence
9. ShaftCounterfaceIntelligence
10. HousingInstallationIntelligence
11. LubricationIntelligence
12. EnvironmentContaminationIntelligence
13. LipContactMechanicsIntelligence
14. FailureModeIntelligence
15. RegulatoryComplianceIntelligence
16. StandardsNomenclatureIntelligence
17. EvidenceConfirmationIntelligence
18. ScopeGuardIntelligence
19. CalculationIntelligence
20. ContradictionIntelligence
21. PriorityRiskTriageIntelligence
22. QuestionIntelligence
23. RFQBriefIntelligence
24. KnowledgeSourceIntelligence
25. DataCaptureLearningIntelligence
26. EvaluationQualityIntelligence
27. MeasurementVerificationIntelligence
28. NormativeReferenceIntelligence
29. LeakageServiceLifeIntelligence
30. DocumentationRequirementIntelligence
31. ForbiddenLanguageIntelligence
```

Diese Module sind im MVP bewusst leichtgewichtig, aber sie bilden das künftige Backbone.

---

## 10. Dichtungstyp Intelligence

Zweck:

```text
- Erkennen, ob es überhaupt ein RWDR-Fall ist.
- RWDR-vs-Gleitringdichtung-vs-Hydraulikdichtung abgrenzen.
- Bauformthemen erkennen:
  Standard-RWDR, Staublippe, druckgeeignete Ausführung,
  PTFE-/Speziallippe, Kassette, V-Ring, Gamma-Seal,
  Wellenschutzhülse, Split-Seal.
```

Ausgabe ist keine Bauformempfehlung, sondern:

```text
zu prüfende Bauformthemen
```

Beispiel:

```text
Staubige Umgebung erkannt → Schutzlippe / Excluder durch Hersteller prüfen lassen.
```

Nicht:

```text
Nimm Typ AS.
```

---

## 11. Anwendungs Intelligence

Anwendung ist kein normales Textfeld, sondern ein Regelumschalter.

Beispiele:

```text
Getriebe:
- Öltyp
- Additive
- Drehzahl
- Temperatur
- Druckzustand
- Staub / Wasser / Schmutz außen
- Wellenzustand

Rührwerk / Mischer:
- Produktmedium
- Reinigung / CIP / SIP
- Produktkontakt
- Behälterdruck / Vakuum
- Axialspiel
- Wellenbewegung
- Lebensmittel-/Pharmaanforderung

Pumpe:
- Pumpentyp
- Prozessmedium
- Druck / Vakuum
- Trockenlauf
- Dichtungstyp-Klärung: RWDR vs. Gleitringdichtung
```

Kernregel:

> **Getriebe, Rührwerk und Pumpe dürfen nicht dieselbe RWDR-Fragelogik verwenden.**

---

## 12. Medium Intelligence

Medium Intelligence strukturiert:

```text
- Medium innen
- Medium außen
- Reinigungsmedium
- Prozessmedium
- Schmiermedium
- Umgebung
```

Mediumklassen:

```text
- Mineralöl
- synthetisches Öl
- Getriebeöl / Additivöl
- Fett
- Wasser
- wässrige Lösung
- Heißwasser / Dampf
- alkalische Reinigung
- saure Reinigung
- aggressive Lösungsmittel
- Gas / Luft
- flüssiges Lebensmittel
- pastöses Lebensmittel
- fettiges Lebensmittel
- abrasive Suspension
- Staub / Pulver außen
- unbekanntes Medium
```

Beispiel Schokolade:

```text
food_pasty
→ Produktkontakt prüfen
→ Reinigung/CIP prüfen
→ Feststoff-/Zuckerpartikel möglich
→ Materialkompatibilität offen
→ keine Materialfreigabe
```

---

## 13. Material Intelligence

Material Intelligence bedeutet **nicht** Materialempfehlung.

Sie erkennt und strukturiert:

```text
- Materialnennungen
- Wunschmaterial
- vorhandenes Altteilmaterial
- Werkstofffamilien
- Medienrisiken
- Temperatur- und Alterungsrisiken
- Quellung / Schrumpfung
- Härteänderung
- Compression Set
- Kriechen / Kaltfluss bei PTFE
- Verschleiß / Reibwärme
- Feder-/Metallkorrosion
```

Beispiel:

```text
„NBR gewünscht“
→ Materialangabe erfasst
→ nicht als Empfehlung übernommen
→ Herstellerprüfung erforderlich
```

Kundenseitig verboten:

```text
NBR geeignet
FKM empfohlen
PTFE nehmen
```

Kundenseitig erlaubt:

```text
Genanntes Material wurde erfasst, aber nicht als Empfehlung übernommen.
Werkstoffprüfung durch Hersteller erforderlich.
```

---

## 14. Shaft & Counterface Intelligence

Bei RWDR ist die Gegenlauffläche entscheidend.

Parameter:

```text
- Wellenwerkstoff
- Wellenhärte
- Rauheit Ra / Rz / Rmr
- Richtungsstruktur / Lead
- Riefen
- Korrosion
- Einlaufspur
- Wellenschutzhülse
- dynamischer Rundlauf / DRO
- statische Exzentrizität / STBM
- Axialspiel
- Vibration
- Lagerabstand
- Lagerspiel
```

Output:

```text
Wellenlauffläche muss geprüft werden.
Rundlauf / Exzentrizität fehlen.
Wellenschutzhülse prüfen lassen.
```

Nicht:

```text
Welle ist geeignet.
```

---

## 15. Housing & Installation Intelligence

Parameter:

```text
- Gehäusebohrung D
- Bohrungstoleranz
- Bohrungsrauheit
- Gehäusematerial
- Einbauraumbreite
- Bohrungstiefe
- Schulter / Anschlag
- Sicherungsring
- Einführfase / Radius
- geteiltes Gehäuse
- Blindmontage
- keine Wellendemontage möglich
- Montage über Nut / Gewinde / scharfe Kante
```

Beispiel:

```text
Welle kann nicht demontiert werden
→ Split-Seal-Review erforderlich
```

---

## 16. Calculation Intelligence

Pflichtberechnung im MVP:

```text
v = π × d1_mm × rpm / 60000
```

Beispiel:

```text
d1 = 40 mm
n = 3000 rpm
v ≈ 6,28 m/s
```

Berechnungsausgaben sind nur:

```text
- computed values
- review flags
- Herstellerfragen
```

Keine Freigabe.

Erweiterbare Engineering-Preview-Berechnungen:

```text
- n_max aus zulässiger Umfangsgeschwindigkeit
- Lippenkontaktpressung
- Reibkraft
- Reibmoment
- Reibleistung
- Wärmestromdichte
- Kontakt-Temperaturanstieg
- thermische Maßänderung
- Presssitzdruck
- PV-Wert
- Verschleißnäherung
```

Diese bleiben ohne Herstellerdaten nur Scoping-/Review-Signale.

---

## 17. Normative Backbone

Normative Referenzen werden als Metadaten geführt, ohne Compliance-Claim:

```text
ISO 6194-1
Typen, Nennmaße, Toleranzen für elastomerische RWDR.

ISO 6194-3
Lagerung, Handhabung, Einbau.

ISO 6194-4
Performance-/Qualifikationsprüfungen.

ISO 6194-5
Sichtbare Fehlermerkmale.

ISO 16589
Thermoplastische / PTFE-basierte Radialwellendichtringe.

DIN 3760
Deutsche Markt-/Standardreferenz.
```

Das System behauptet nicht:

```text
ISO-konform
DIN-konform
geprüft nach
```

Es sagt höchstens:

```text
Normative Referenzfamilie für Herstellerbewertung.
```

---

## 18. Measurement & Verification Intelligence

Für fehlende technische Angaben erzeugt das System Messhinweise:

```text
d1:
Bügelmessschraube / Außenmikrometer

D:
3-Punkt-Innenmessgerät / Bore Gauge

b:
Messschieber / Zeichnung

Runout:
Messuhr

Koaxialität:
Messuhr / CMM

Rauheit:
Tastschnitt-Profilometer

Härte:
Rockwell C / Vickers

Material unbekannt:
FTIR-ATR / DSC/TGA

Ölalterung:
Viskosität, FTIR-Ölanalyse, TAN/TBN

Partikel:
Partikelzählung, Mikroskopie, Ferrographie

Leckage / Reibmoment / Temperatur:
Prüfstand / Herstellerprüfung
```

---

## 19. Scope Guard

Harte Out-of-Scope-Fälle:

```text
- Gleitringdichtung
- mechanical face seal
- Hydraulik-Stangen-/Kolbendichtung
- O-Ring-Nutberechnung
- statische Flachdichtung als Primärfall
- ATEX
- Wasserstoff / hydrogen
- Hochdruckgas
- toxische Medien
- Aerospace
- Nuclear
- medical-device-critical
- safety-critical approval request
- final design approval request
```

Out-of-scope überschreibt alles.

---

## 20. Technical RWDR RFQ Brief

Pflichtsektionen:

```text
1. Header
2. Status
3. Anfrageart
4. bestätigte Anwendungskategorie
5. Bestätigte Angaben
6. Nicht bestätigte Angaben
7. Kritisch fehlende Angaben
8. Hilfreich fehlende Angaben
9. Berechnete Werte
10. Engineering Review-Themen
11. Empfohlene Mess- und Prüfangaben für Herstellerbewertung
12. Herstellerfragen
13. Dokumentations-/Regulatorikanforderungen
14. Leckage- und Standzeiterwartungen
15. Quellenübersicht
16. Export-Metadaten
17. Disclaimer
```

Pflicht-Disclaimer:

```text
Dieser Technical RWDR RFQ Brief strukturiert die Anfrage. Er enthält keine finale technische Eignungsfreigabe, keine Materialfreigabe, keine Produktempfehlung und keine Herstellerfreigabe. Die finale technische Bewertung erfolgt durch Hersteller, Händler oder eine verantwortliche technische Stelle.
```

---

## 21. Case-State, Snapshots und Revisionen

Der RWDR Case-State ist backend-owned und DB-backed über:

```text
cases / CaseRecord.payload
```

Gespeichert werden:

```text
- raw inquiry
- EvidenceFields
- Confirmation Decisions
- Evaluation
- Brief
- Markdown Export
- PDF Export
```

Zusätzlich gibt es append-only Snapshots über:

```text
case_state_snapshots
```

Events:

```text
case_created_after_analyze
extraction_candidates_stored
confirmation_decision_applied
evidence_field_edited
field_marked_explicitly_unknown
field_rejected
evaluation_generated
technical_brief_generated
markdown_export_generated
pdf_export_generated
```

Revision-Diff zeigt:

```text
- geänderte Felder
- Bestätigungsstatusänderungen
- Missing-Field-Änderungen
- berechnete Werte
- Review Flags
- Herstellerfragen
- Export-Metadaten
```

---

## 22. technical_case_challenge Answer-Mode

Zusätzlich zum RFQ-Brief-Flow gibt es einen expliziten Answer-Mode:

```text
technical_case_challenge
```

Pfad:

```text
RuntimeAction.answer_mode
→ GraphState.runtime_answer_mode
→ output_public["answer_mode"]
→ GovernedAnswerContext.answer_mode
→ Composer
```

Für technische Fallanalysen erzeugt das Backend einen deterministischen Plan:

```text
TechnicalCaseChallengePlan
RWDRChallengeSignals
```

Antwortstruktur:

```text
1. Kurzurteil
2. Kritische Punkte
3. Abgeleitete Signale
4. Vorsichtige Prüfhypothesen
5. Gegenindikatoren / Risiken
6. Fehlende Blocker
7. Nächste beste Rückfrage
8. Grenze der Aussage
```

Beispiel Salzwasser/RWDR:

```text
d1 = 40 mm
n = 3000 rpm
v ≈ 6,28 m/s
Salzwasser
2 bar
Boot
Gegenlauffläche 0,2
```

Erwartete Analyse:

```text
- Salzwasser: Korrosion / Federwerkstoff / Materialverträglichkeit prüfen
- 2 bar: Standard-RWDR-Druckkontext kritisch
- 6,28 m/s: Wärme, Rundlauf, Oberfläche relevant
- Gegenlauffläche 0,2: Parameter und Einheit klären
- nächste beste Rückfrage: Sind die 2 bar dauerhafte Druckdifferenz direkt über der Dichtung, und ist 0,2 als Ra in µm gemeint?
```

---

## 23. Auth und SSE-Stabilität

Bereits verbessert:

```text
- Pre-stream Backend-401 / token_expired:
  Force Refresh + einmaliger Retry.

- Mid-stream Reader-Failure:
  structured interrupted event.

- Teilantworten:
  bleiben streamingText und werden ohne final state_update nicht als finale Assistant Message geschrieben.

- Kein automatischer Blind-Retry nach begonnenem Stream.

- Dedupe:
  gleiche event_id wird im Hook dedupliziert.
```

Offen:

```text
Backend-SSE-Contract liefert noch nicht durchgehend stabile:
- turn_id
- event_id
- sequence
- is_final
- error_code
```

Nächster technischer Stabilisierungsschritt:

```text
Backend-SSE-Event-Contract typisieren.
```

---

## 24. Demo- und Release-Stand

Aktueller Branch:

```text
demo/rwdr-limited-external
```

Commits:

```text
f1f11626dc1d28423b76996e2ade410055e68c10
feat(rwdr): prepare limited external demo

42ee1cc8bf3dd2c25b3b50fea44d79e3c59b4508
docs(rwdr): record demo deploy verification
```

Gepusht:

```text
origin/demo/rwdr-limited-external
```

Live-Status laut letzter Prüfung:

```text
sealingai.com erreichbar
/api/health erreichbar
/api/agent/health erreichbar

/api/v1/rfq/rwdr/analyze live montiert und ohne Token korrekt auth-gated (401)
```

Damit gilt:

```text
Code committed/pushed: ja
RWDR-Demo branch: ja
Live deployed: ja, Route montiert und auth-gated
Live aktueller Commit: über Deploy-Worktree und Docker-Image prüfen
RWDR live smoke: Route-Mount-Smoke ja, vollständiger authentifizierter E2E-Smoke noch separat prüfen
```

---

## 25. Readiness-Status

### Full-App-Release

```text
NOT READY
```

Gründe:

```text
- nicht-RWDR V10/Graph/Runtime-Failures
- dirty Worktree
- Full-App-Broad-Suite nicht grün
- Deploy-Pfad für kombinierten Backend+Frontend-Branch noch nicht final verifiziert
```

### Geführte interne Demo

```text
READY
```

### Geführte limitierte externe RWDR-Fach-Demo

```text
READY_FOR_LIMITED_EXTERNAL_RWDR_DEMO
```

Nur unter Bedingungen:

```text
- geführt, nicht Self-Service
- 3–5 ausgewählte Fachreviewer
- kein öffentlicher Launch
- kein Herstellerlisting
- kein Routing
- klare Scope-Kommunikation
- PDF visuell prüfen
- RWDR-Demo-Branch sauber deployen
```

---

## 26. Golden Cases

Es gibt 12 Golden Cases:

```text
1. Simple gearbox replacement
2. Complete gearbox case
3. Missing D and b
4. Chocolate mixer / food paste
5. Pump ambiguity
6. Mechanical face seal out-of-scope
7. ATEX out-of-scope
8. Hydrogen out-of-scope
9. Shaft groove review
10. No shaft disassembly / split review
11. Material mention safety
12. Pressure boundary case
```

Diese laufen durch:

```text
analyze
confirm
evaluate
brief
markdown export
pdf export
snapshots
revision diff
```

---

## 27. Demo-Skript

Demo-Input:

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

Demo-Ablauf:

```text
1. Anfrage einfügen
2. Source-spanned Fields zeigen
3. d1/D/b/speed/application bestätigen
4. Druck/Temperatur/Wellenzustand als unbekannt markieren
5. Brief generieren
6. Umfangsgeschwindigkeit zeigen
7. PDF exportieren
8. Snapshot-Historie zeigen
9. Revision-Diff zeigen
```

Talk Track:

```text
sealing | Intelligence gibt keine Dichtung frei.
Es macht die Anfrage für Hersteller bewertbar.
```

---

## 28. Feedback-Checkliste für Fachreviewer

Kernfragen:

```text
1. Würdest du mit diesem Technical RWDR RFQ Brief schneller arbeiten als mit einer normalen Kundenmail?
2. Welche Pflichtangaben fehlen noch?
3. Welche Fragen sind unnötig?
4. Welche Fragen sind besonders wertvoll?
5. Würdest du dieses Format in Inside Sales oder Application Engineering nutzen?
6. Wirkt etwas wie eine Material- oder Produktempfehlung?
7. Ist der Disclaimer klar?
8. Ist der PDF-Brief professionell genug?
9. Was fehlt für Quote-Readiness?
10. Würdest du dieses Format als Eingangsstandard akzeptieren?
```

---

## 29. Business- und GTM-Modell

Kurzfristig:

```text
Kostenloser RWDR-Brief-Generator
Manual Export / Copy / PDF
Geführte Fachvalidierung
Keine Herstellervermittlung
```

Mittelfristig:

```text
B2B-SaaS für Hersteller, Händler, technische Distributoren, Inside Sales und Application Engineering.
```

Später optional:

```text
Herstellerlisting / RFQ-Netzwerk
```

Aber nur nach Nachweis von:

```text
- echtem Nutzerbedarf
- brauchbarer Briefqualität
- wiederkehrendem RFQ-Volumen
- klarem Trust-Modell
```

Keine frühe Marketplace-Implementierung.

---

## 30. Nächste empfohlene Schritte

### Kurzfristig technisch

```text
1. Backend-SSE-Event-Contract typisieren:
   turn_id, event_id, sequence, is_final, error_code.

2. RWDR-Demo-Branch aktualisieren und sauber deployen.

3. Live-RWDR-Smoke-Test:
   POST /api/v1/rfq/rwdr/analyze
   muss case_id und EvidenceFields liefern.

4. Live technical_case_challenge testen:
   Salzwasser, 50 °C, 2 bar, 3000 rpm, d1=40 mm.
```

### Kurzfristig produktseitig

```text
1. Demo-PDF visuell prüfen.
2. 3–5 geführte Fachsessions durchführen.
3. Feedback dokumentieren.
4. Keine neuen Features bauen, bevor Feedback ausgewertet ist.
```

### Mögliche nächste Produktpatches nach Fachfeedback

```text
- RWDR Question Quality Patch
- PDF Professionalization Patch
- RWDR Field Taxonomy Patch
- Material Review Preparation Patch
```

Nicht als nächstes:

```text
- Herstellerlisting
- Routing
- Marketplace
- Materialempfehlung
- Produktvorschlag
```

---

## 31. Finaler Leitsatz

> **sealing | Intelligence entscheidet nicht die Dichtung. sealing | Intelligence macht die Anfrage entscheidbar.**

Oder für RWDR:

> **Aus unklaren Radialwellendichtring-Fällen werden bestätigte, strukturierte und exportierbare Technical RWDR RFQ Briefs für die Herstellerbewertung.**
