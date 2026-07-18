<!-- Canonical Markdown projection of the ratified source DOCX. -->
<!-- Source SHA-256: 066dd803b7013fa8b7fdcac4703dee63c3fb183a55d7ef4e2cca76e963802580 -->

sealingAI

# Strategisches Leitbild, Produktkonzept und Zielarchitektur

*Single Source of Truth für Produkt, Architektur, KI, Daten, Website, Inhalte, Governance und Marktentwicklung*

| Verbindlicher Status Version 2.0 · Stand 10. Juli 2026 · RATIFIZIERTE SSoT Dieses Dokument ersetzt die strategischen Aussagen der Version 1.0 und konsolidiert Leitbild, Zielarchitektur, Challenge, Gegenprüfung und die Änderungsliste M1–M16. Bestehende strengere Safety-, Security-, Tenant-, Kernel-, Quellen- und Release-Invarianten im Repository bleiben wirksam, bis sie ausdrücklich und kontrolliert in diese SSoT überführt oder durch eine formale ADR ersetzt werden. |
| --- |

> Aus Dichtungsfragen werden prüfbare Dichtungsfälle.

Dichtungstechnik. Von der Frage zur prüfbaren Entscheidung.

<small>Internes Steuerungsdokument. Keine technische Freigabe, Rechtsberatung oder Normenwiedergabe.</small>

## 0. Dokumentstatus, Autorität und Gebrauch

### 0.1 Zweck

Diese SSoT definiert verbindlich, welches Produkt sealingAI baut, welche Probleme es löst, wie es sich positioniert, welche fachlichen und technischen Grenzen gelten und nach welchen Regeln Architektur, Datenmodell, KI, Website, Inhalte, Herstellerökosystem und Geschäftsmodell weiterentwickelt werden.

Jede neue Funktion, jeder Prompt, jedes Datenobjekt, jede Website-Seite, jede Herstellerfunktion und jede Architekturänderung muss gegen diese SSoT geprüft werden. Nicht passende Anforderungen werden abgelehnt, verschoben oder als formale Änderung dieser SSoT behandelt.

### 0.2 Authority Order

| Rang | Quelle | Bedeutung |
| --- | --- | --- |
| 1 | Gesetze, verbindliche regulatorische Anforderungen, Verträge und Lizenzbedingungen | Externe Pflicht; kann durch interne Dokumente nicht aufgehoben werden. |
| 2 | Diese sealingAI SSoT v2.0 | Verbindliche Produkt-, Governance- und Zielarchitektur. |
| 3 | Ratifizierte Invarianten, ADRs und Sicherheitsverträge | Konkretisieren die SSoT; strengere Schutzregeln bleiben wirksam. |
| 4 | Build-Specs, Datenverträge, API-/SSE-Schemas und Eval-Rubriken | Ausführbare Umsetzungsvorgaben. |
| 5 | Tests, CI/CD-Gates und Produktionsrunbooks | Beweisen und erzwingen die Umsetzung. |
| 6 | Implementierung | Muss den höheren Ebenen entsprechen. |
| 7 | Historische Konzepte, Audits, Screenshots und Diskussionen | Kontext, aber nicht normativ. |

| Konfliktregel Bei Widersprüchen gilt die höher priorisierte Quelle. Konflikte werden nicht stillschweigend durch Code oder Prompt gelöst, sondern in einem ADR beziehungsweise Owner-Decision-Record dokumentiert. Kein Agent darf eine Safety-, Tenant-, Kernel-, Quellen-, Neutralitäts- oder Freigabeinvariante eigenständig abschwächen. |
| --- |

### 0.3 Supersession

Diese Version ersetzt die strategische Version 1.0. Sie übernimmt deren fachliche 360°-Vision, präzisiert aber die heutige Positionierung, die Reifegrade, die Governance und die Aktivierungsgates. Die neue SSoT hebt keine bereits strengeren Schutzmechanismen im Repository automatisch auf.

### 0.4 Provenienzklassen für Aussagen

| Klasse | Bedeutung | Nutzung |
| --- | --- | --- |
| document_verified | Direkt in ratifizierter Dokumentation belegt | Normative Aussagen und Entscheidungen |
| repository_verified | Durch Code, Tests, Konfiguration oder Build belegt | Ist-Zustand der Implementierung |
| public_source_verified | Durch belastbare externe Quelle belegt | Markt, Recht, Normenstatus, Branchenfakten |
| owner_provided | Vom Owner bereitgestellt, aber nicht extern geprüft | Kapazität, persönliche Rahmenbedingungen, Geschäftsbeziehungen |
| pilot_observed | In Pilot oder Produktion gemessen | Produktwirkung und KPIs |
| assumption | Begründete Hypothese | Muss sichtbar bleiben und validiert werden |
| unknown | Nicht ausreichend belegt | Darf keine definitive Entscheidung tragen |

## 1. Executive Summary

sealingAI ist keine allgemeine Chatoberfläche und kein Preisvergleichsmarktplatz. sealingAI ist die herstellerneutrale Wissens-, Engineering- und Fallinfrastruktur für industrielle Dichtungstechnik. Die Plattform beantwortet einfache Fachfragen direkt und verwandelt anwendungsabhängige Fragen in strukturierte, quellenbasierte und prüfbare Dichtungsfälle.

| North Star sealingAI macht Dichtungstechnik anwendbar: von der Wissensfrage über Vergleich, Engineering und Schadensanalyse bis zur qualifizierten Hersteller- oder Expertenprüfung. Das System zeigt Datenlücken, Quellen, Geltungsbereiche, Unsicherheiten, Zielkonflikte und den fachlich richtigen nächsten Schritt. Die finale technische Freigabe bleibt beim zuständigen Fachverantwortlichen beziehungsweise Hersteller. |
| --- |

### 1.1 Positionierung

| Ebene | Verbindliche Formulierung |
| --- | --- |
| Kategorie | Sealing Intelligence – die digitale Wissens-, Engineering- und Fallinfrastruktur der industriellen Dichtungstechnik. |
| Plattform-USP | Aus Dichtungsfragen werden prüfbare Dichtungsfälle. |
| Mechanismus | Einfache Fragen erhalten direkte Antworten; anwendungsabhängige Fragen werden zu prüfbaren Fällen – mit sichtbaren Datenlücken, Quellen, Risiken und menschlicher Freigabe. |
| Anwendernutzen | Schneller zu einer belastbaren Entscheidungsgrundlage und zur fachlich richtigen nächsten Aktion. |
| Herstellernutzen | Qualifizierte Fälle statt unvollständiger Anfragen – für weniger Rückfragen und eine schnellere technische Bewertung. |
| Trust-Claim | Vollständigkeit vor Empfehlung. Quellen vor Behauptung. Freigabe vor Einsatz. |
| Operativer Dachclaim | Dichtungstechnik. Von der Frage zur prüfbaren Entscheidung. |
| Lifecycle-Vision | Von Wissen und Engineering über Freigabe und Einbau bis zur dokumentierten Felderfahrung – in einem verbundenen System. |

### 1.2 Strategische Entscheidungen

- 360° ist das Architektur- und Lebenszyklusziel, nicht die Behauptung vollständiger heutiger Abdeckung.
- Der kommerzielle Wedge ist die qualifizierte Fallbearbeitung; der Wissensmodus schafft Reichweite, Vertrauen und frühen Nutzerwert.
- sealingAI bleibt eine neutrale Plattform mit optionaler Herstellerübergabe, kein preisgetriebener Marktplatz.
- Der modulare Monolith bleibt das bevorzugte Architekturmodell; Microservices werden nur bei belegtem Bedarf extrahiert.
- Das LLM formuliert, erklärt und orchestriert. Berechnungen, Grenzwerte, Claims, Freigaben und Status werden durch geprüfte Daten und deterministische Systeme kontrolliert.
- Tiefe vor Breite: Jede neue Fachdomäne wird als vollständige vertikale Scheibe aufgebaut.
- Neue Produktmodi werden nur feature-flagged und nach Eval-Gate aktiviert.
## 2. Problemraum und Branchen-Pains

Die Branche besitzt viele Datenblätter, Normen, Produktfinder und Experten. Der Engpass liegt nicht primär im Fehlen einzelner Informationen, sondern in ihrer Fragmentierung, im fehlenden Anwendungskontext und in der schwachen Überführung einer realen Situation in einen prüfbaren technischen Fall.

### 2.1 Kernprobleme

| Pain | Typische Folge | Antwort durch sealingAI | Evidenzstatus |
| --- | --- | --- | --- |
| Unvollständige Betriebsdaten | Scheingenauigkeit, Rückfragen, Fehlbewertung | Adaptive Fallaufnahme, Coverage-Status, sichtbare Unknowns | Branchenlogisch und quellenbasiert; Pilotmessung erforderlich |
| Werkstofffamilie wird mit Compound verwechselt | Unzulässige Verallgemeinerung und falsche Freigabe | Trennung Familie – Typ – Compound – Produkt – Charge | Fachlich belegt |
| Schaden wird isoliert an der Dichtung gesucht | Teiletausch ohne Root Cause, Wiederholfehler | Systemische Failure Intelligence mit Hypothesen und Prüfplan | Fachlich belegt |
| Kontextverlust zwischen Engineering, Einkauf, Montage und Betrieb | Falsches Teil, fehlende Freigabe, keine Traceability | Versionierter Sealing Case Record und Asset Memory | Fachlich belegt |
| Herstelleranfragen sind unstrukturiert | Vorqualifizierungsaufwand und lange Schleifen | Manufacturer-Ready Brief und Capability Fit | Qualitative Hypothese; im Pilot zu messen |
| Angebote basieren auf unterschiedlichen Randbedingungen | Technische Antworten sind schwer vergleichbar | Gemeinsamer technischer Fall und strukturierte Antwortformate | Qualitative Hypothese; im Pilot zu messen |
| Regulatorik und Lieferketten ändern sich | Riskante Schnellsubstitution oder verspätete Reaktion | Versionierter Compliance- und Substitutionsworkflow | Öffentlich belegt |
| Erfahrungswissen ist personengebunden | Wissensverlust und langsame Einarbeitung | Validierte Fälle, Entscheidungsgründe und Outcomes | Industrieübergreifend belegt; dichtungsspezifisch zu validieren |
| Bauteilpreis dominiert | TCO und Ausfallrisiko bleiben unsichtbar | Fallbezogenes Kosten- und Risikomodell | Branchenindikator; organisationsspezifisch zu validieren |

### 2.2 Pain Evidence Ledger

Alle strategischen Pain-Claims werden in einem separaten Evidence Ledger geführt. Jeder Claim erhält Quelle, Provenienzklasse, Geltungsbereich, Aktualität, offene Hypothese und geplante Validierung. Pilot-KPIs dürfen erst nach Messung als Marketingclaim verwendet werden.

| Status | Bedeutung |
| --- | --- |
| Belegt | Direkte fachliche oder öffentliche Evidenz mit passendem Geltungsbereich. |
| Teilweise belegt | Richtung belegt, konkretes Ausmaß in Dichtungstechnik noch offen. |
| Owner-/Expertenhypothese | Plausibel und relevant, aber nicht objektiviert. |
| Pilotmessung erforderlich | Nur durch reale Prozessdaten belastbar. |
| Nicht ausreichend unterstützt | Darf nicht als externer Claim verwendet werden. |

## 3. Vision, Mission und strategische Identität

### 3.1 Vision

Industrielle Dichtungsentscheidungen werden nicht mehr durch verstreute Daten, implizite Annahmen und verlorenes Erfahrungswissen geprägt, sondern durch einen gemeinsamen, nachvollziehbaren und lernenden technischen Kontext.

### 3.2 Mission

sealingAI macht Dichtungswissen zugänglich, übersetzt reale Anwendungen in strukturierte Fälle, verbindet geprüfte Evidenz mit Engineering und führt Nutzer zur fachlich richtigen nächsten Aktion – ohne Scheinsicherheit und ohne die finale Verantwortung des Menschen zu verdrängen.

### 3.3 Purpose

Dichtungstechnik ist Erfahrungswissenschaft. sealingAI bewahrt diese Erfahrung nicht als unprüfbare Anekdote, sondern überführt sie in strukturierte, quellenbezogene und kontrolliert wiederverwendbare Erkenntnisse.

### 3.4 Strategische Identität

- herstellerneutral, aber herstellerintegrierend
- ingenieurorientiert, aber für unterschiedliche Rollen verständlich
- quellenbasiert, aber nicht auf Dokumentensuche reduziert
- entscheidungsunterstützend, aber keine Freigabeinstanz
- 360° im Zielmodell, Depth-first in der Umsetzung
- dialogfähig, aber nicht LLM-zentriert
- kommerziell skalierbar, ohne technischen Fit käuflich zu machen
## 4. 360°-Geltungsbereich und Reifegradmodell

### 4.1 Definition

360° bedeutet, dass der vollständige fachliche Lebenszyklus der industriellen Dichtungstechnik im Datenmodell, in den Domänen und in den Nutzerpfaden vorgesehen ist: Wissen, Werkstoffe, Medien, Engineering, Auswahl, Montage, Schaden, Normen, Hersteller, Beschaffung, Freigabe, Asset-Historie und Feldergebnis.

360° bedeutet ausdrücklich nicht, dass alle Themen heute bereits in gleicher Tiefe verfügbar sind. Jede Oberfläche und jeder externe Claim muss den tatsächlichen Reifegrad sichtbar machen.

### 4.2 Reifegradstufen

| Stufe | Definition | Externe Darstellung |
| --- | --- | --- |
| Geprüft verfügbar | Fachlich reviewed, getestet, produktiv freigegeben | Ohne Zusatz oder als geprüft gekennzeichnet |
| Beta | Funktional, kontrolliert verfügbar, begrenzte Coverage | Beta und Coverage sichtbar |
| Pilot | Nur für ausgewählte Nutzer/Fälle, manuelle Begleitung | Pilot |
| Im Aufbau | Konzept oder Implementierung vorhanden, nicht freigegeben | Im Aufbau |
| Geplant | In SSoT vorgesehen, noch nicht umgesetzt | Geplant |
| Außer Scope | Bewusst nicht Teil des aktuellen Produkts | Klare Abgrenzung |

### 4.3 Fachlicher Kernbereich

- statische Elastomer- und Polymerdichtungen
- O-Ringe, Form- und Profildichtungen
- Radialwellendichtringe und rotierende Lippendichtungen
- Hydraulik- und Pneumatikdichtungen
- Flachdichtungen und Flanschsysteme
- Gleitringdichtungen und Versorgungssysteme
- Packungen, Kompensatoren und Spezialdichtungen
- Werkstoffe, Compounds, Medien, Tribologie, Gegenkörper und Oberflächen
- Konstruktion, Berechnung, Montage, Betrieb, Schaden und Root Cause
- Normen, Regulatorik, Zulassungen, Nachweise und Traceability
- Herstellerkompetenzen, Produkte, Substitution und technische Beschaffung
### 4.4 Abgrenzung

Bauwerksabdichtung, Dach, Fensterfugen, allgemeine Kleb- und Dichtstoffe, Verpackungsdichtheit oder elektromagnetische Abschirmung sind keine automatische Kernabdeckung. Sie können später als separate Domänen ergänzt werden, dürfen aber nicht die Tiefe der industriellen Fluid-Sealing-Technik verwässern.

## 5. Zielgruppen und Jobs-to-be-Done

| Rolle | Primärer Job | Erwarteter Output |
| --- | --- | --- |
| Konstruktion/Engineering | Dichtungsprinzip, Werkstoff und Geometrie fachlich einordnen | Vergleich, Berechnung, Spezifikation, offene Prüfpunkte |
| Instandhaltung | Schaden schnell verstehen und nächste Prüfung festlegen | Hypothesen, Prüfplan, Ersatz-/Herstellerbriefing |
| Anwendungstechnik | Komplexe Fälle effizient vorqualifizieren | Vollständiger Fall, Quellen, Risiken, Entscheidungsdokument |
| Einkauf | Technisch vergleichbare Anfragen und Angebote erhalten | Gemeinsame technische Basis, Alternativen, Freigabestatus |
| Qualitätsmanagement | Nachweise, Abweichungen und Entscheidungen nachvollziehen | Audit Trail, Dokumente, 8D-/RCA-Bezug |
| Hersteller | Weniger Lead-Rauschen, mehr technische Substanz | Qualifizierte Fälle, offene Punkte, Capability Fit |
| Vertrieb/Händler | Kundenanfragen fachlich sauber aufnehmen | Strukturierte Intake- und Übergabedaten |
| Lernende/Fachfremde | Dichtungstechnik verständlich lernen | Erklärungen, Visualisierungen, Lernpfade |
| Betreiber/Management | Risiko, Aufwand und Wirkung verstehen | TCO-/Risikoperspektive, KPI und Governance |

## 6. Nutzungsmodi und risikoadaptive Interaktion

| Modus | Beispiel | Systemverhalten | Output |
| --- | --- | --- | --- |
| Wissen | Wie funktioniert ein RWDR? | Direkte, tiefe Antwort; Quellen bei spezifischen Claims | Erklärung, Visualisierung, Verweise |
| Vergleich | FKM oder EPDM? | Kriterien und Geltungsbedingungen klären; Zielkonflikte zeigen | Vergleichsmatrix |
| Engineering | Welche Nut/Umfangsgeschwindigkeit? | Inputs validieren; deterministischen Kernel nutzen | Berechnung und Annahmen |
| Anwendungsfall | Welche Dichtung bei Medium X? | Adaptive Rückfragen, Coverage und Risikoklasse | Prüfbarer Fall |
| Schaden | Warum leckt der RWDR? | Systemische Ursachenhypothesen und Prüfplan | RCA-/Failure-Dossier |
| Substitution | Alternative für abgekündigten Compound | Leistung, Regulatorik und Requalifizierung abbilden | Substitutionsdossier |
| Hersteller-Fit | Wer kann den Fall prüfen? | Capability Match erst nach technischem Fall | Begründete Auswahl |
| Lifecycle | Was war eingebaut und wie lange lief es? | Asset-Historie und Outcomes zusammenführen | Dichtungslebenslauf |

### 6.1 Risikoklassen

| Klasse | Typ | Pflichten |
| --- | --- | --- |
| A | Allgemeines Wissen | Direkte Antwort; keine unnötige Fallaufnahme. |
| B | Technische Orientierung | Applicability und Grenzen sichtbar. |
| C | Anwendungsspezifische Aussage | Strukturierte Inputs, Coverage, Quellen und Unsicherheit. |
| D | Kritische Anwendung | Erhöhte Evidenz, Pflichtfragen, explizite Eskalation und Freigabegate. |
| E | Formale Konformität/Zertifizierung | Keine Bestätigung durch sealingAI; Übergabe an autorisierte Stelle. |

## 7. Verbindliche Produkt- und Vertrauensprinzipien

| ID | Prinzip | Verbindliche Auslegung |
| --- | --- | --- |
| P1 | Der Kernel entscheidet, das LLM formuliert. | Berechnungen, Formeln und numerische Ergebnisse stammen aus deterministischem Code. |
| P2 | Kein technischer Claim ohne Status. | Quelle, Reviewstatus, Version, Geltungsbereich und Unsicherheit sind Teil des Claims. |
| P3 | Unknown ist ein Fachzustand. | Fehlende Daten werden weder geschätzt noch sprachlich versteckt. |
| P4 | Familie orientiert, Compound bewertet, Bauteil wird extern freigegeben. | Werkstofffamilien dürfen nicht wie konkrete Produkte behandelt werden. |
| P5 | Was das System nicht weiß, sagt es zuerst. | Keine Scheingenauigkeit und kein rhetorisches Verbergen. |
| P6 | Matching folgt dem technischen Fall. | Kommerzielle Partnerdaten dürfen keine technische Bewertung erzeugen. |
| P7 | Felderfahrung ist Evidenz, kein Autopilot. | Outcomes werden kontextbezogen und mit Übertragbarkeitsgrenzen genutzt. |
| P8 | Das Produkt ist das Entscheidungsdokument. | Chat ist die Bedienoberfläche, nicht das Endergebnis. |
| P9 | Tiefe vor Breite. | Neue Domänen werden vollständig genug gebaut, bevor weitere angekündigt werden. |
| P10 | Grenzen stehen im Produkt. | Disclaimers ersetzen keine sichere Produktlogik. |
| P11 | Technischer Fit ist nicht käuflich. | Sponsoring und Abonnement verändern keine Eignungsbewertung. |
| P12 | Jede Scope-Erweiterung braucht ein Eval-Gate. | Feature Flag, Referenzset, Hard Gates und Owner-Aktivierung. |

## 8. Vollständige 360°-Themenarchitektur

### 8.1 Grundlagen und Physik

- statisch/dynamisch, berührend/berührungslos, radial/axial
- Leckage, Dichtspalt, Kontaktzone, Schmierfilm und Tribologie
- Reibung, Verschleiß, Wärme, Alterung, Relaxation, Kriechen
- Diffusion, Permeation, Quellung, Extraktion und explosive Dekompression
- Toleranzen, Oberflächen, Härte, Rundlauf, Exzentrizität und Drall
### 8.2 Dichtungsarten

- O-Ringe, X-Ringe, Form- und Profildichtungen
- RWDR, PTFE-Lippendichtungen, V-Ringe, Kassettendichtungen, Labyrinthe
- Stangen-, Kolben-, Puffer-, Abstreif- und Führungselemente
- Flachdichtungen, Graphit, PTFE, Spiral-, Kammprofil- und Metalldichtungen
- Gleitringdichtungen, Cartridge-Systeme, Dry-Gas-Seals und Versorgungssysteme
- Packungen, Kompensatoren, Membranen und Spezialdichtungen
### 8.3 Werkstoffe und Compounds

- NBR, HNBR, FKM, FFKM, EPDM, VMQ, FVMQ, ACM, AEM, CR, IIR, ECO, PU
- PTFE, modifiziertes und gefülltes PTFE, PEEK, PAI, PI, PPS, UHMWPE, POM, PA
- Graphit, Faserstoffe, Metalle, Keramiken, Kohlegraphit, SiC und WC
- Eigenschaften, Härten, Alterung, Zulassungen, Verarbeitung, Lieferzustand und Charge
### 8.4 Medien und Beständigkeit

- Wasser, Dampf, Öle, Fette, Hydraulikflüssigkeiten, Kraftstoffe und Kältemittel
- Säuren, Laugen, Lösemittel, Reinigungsmedien, Gase, Wasserstoff und CO₂
- Lebensmittel-, Pharma-, High-Purity- und Halbleitermedien
- Konzentration, Additive, Verunreinigung, Kontaktzeit, Wechselmedien und Reinigungszyklen
### 8.5 Engineering

- O-Ring-Nut, Verpressung, Dehnung, Nutfüllung und Extrusion
- RWDR-Umfangsgeschwindigkeit, Gegenlauffläche, Druck, Schmierung und Wärme
- Hydraulikspalt, Führung, Reibung, PV, Stick-Slip und Druckaufbau
- Flanschsystem, Schraubenkraft, Flächenpressung, Setzen und Emission
- Gleitringdichtflächen, Wärmehaushalt, Druckverhältnisse und Piping Plans
### 8.6 Montage, Betrieb und Zuverlässigkeit

- Lagerung, Haltbarkeit, Wareneingang, Reinigung und Montagehilfen
- Einbaukontrolle, Inbetriebnahme, Inspektion und Zustandsüberwachung
- Ersatzteilstrategie, Wartungsintervalle, MTBF, TCO und kritische Assets
### 8.7 Failure Intelligence

- chemischer, thermischer und mechanischer Angriff
- Extrusion, Abrasion, Spiralversagen, Trockenlauf und Montagefehler
- Wellen-, Lager-, Flansch-, Schrauben-, Versorgungs- und Systemursachen
- Hypothesen, Evidenz dafür/dagegen, Prüfplan und Root Cause
### 8.8 Normen, Regulierung und Nachweise

- ISO, DIN, EN, ASME, API, ASTM, SAE, VDI und Werksnormen
- REACH, PFAS, Lebensmittel, Trinkwasser, Pharma, Sauerstoff, ATEX und Druckgeräte
- Prüfberichte, Zertifikate, Herstellererklärungen, CoC/CoA, FMEA, PPAP und 8D
### 8.9 Hersteller, Produkte und Beschaffung

- Capability Profiles, Produkte, Compounds, Zertifikate und Fertigungsverfahren
- Cross-Reference, Substitution, Muster, RFQ, Antwortformate und Freigabestatus
- technischer Fit, Verfügbarkeit, Lieferzeit und wirtschaftliche Zielkonflikte
### 8.10 Academy und Lernen

- rollenbasierte Lernpfade, Grundlagen, Vertiefung und Fallbeispiele
- Animationen, Visualisierungen, Übungen, Prüfungen und Kompetenznachweise
- Unternehmenswissen, Expert Review und Lessons Learned
## 9. Zielprodukt und Modulverantwortung

| Modul | Verantwortung | Darf nicht |
| --- | --- | --- |
| Universal Sealing Assistant | Intent, Risikoklasse, Antworttiefe und Übergang in Workflows | Fachliche Wahrheit selbst erzeugen |
| SealingPedia | Grundlagen, Dichtungsarten, Mechanismen und Glossar | Anwendungsfreigaben suggerieren |
| Material Intelligence | Familien, Typen, Compounds, Eigenschaften und Trade-offs | Familie und Produkt gleichsetzen |
| Media Intelligence | Medium, Zusammensetzung, Bedingungen und Beständigkeit | Ampel ohne Geltungsbereich ausgeben |
| Compare | Kriterienbasierte Vergleiche und Zielkonflikte | Unbegründeten Sieger bestimmen |
| Engineering Studio | Deterministische Berechnungen, Plausibilitäten und Spezifikationen | LLM als Rechenkern nutzen |
| Failure Intelligence | Schadensaufnahme, Hypothesen und Prüfplan | Ferndiagnose als Gewissheit ausgeben |
| Compliance Navigator | Status, Version, Region und Nachweisart | Rechts- oder Zertifizierungsfreigabe erteilen |
| Manufacturer & Product Graph | Verifizierte Kompetenzen, Produkte und Ausschlüsse | Bezahlstatus in technischen Fit mischen |
| Sealing Case Workspace | Versionierter Fall, Aufgaben, Entscheidungen und Übergaben | Chattranskript als alleinige Fallakte verwenden |
| Asset & Lifecycle Memory | Einbau, Charge, Betrieb, Austausch und Outcome | Einzeloutcome blind verallgemeinern |
| Sealing Academy | Lernen, Übungen und Kompetenznachweise | Marketing als Fachreview ausgeben |
| Organization Knowledge | Tenant-eigenes Wissen, Rechte und Integrationen | Cross-Tenant-Daten vermischen |

## 10. Daten- und Wissensarchitektur

### 10.1 Claims als kleinste Wissenseinheit

Die kanonische Wissenseinheit ist der technische Claim, nicht das Dokument und nicht der generierte Absatz. Ein Claim beschreibt genau eine Aussage und trägt seine Beweis- und Geltungsinformationen mit.

| Feldgruppe | Pflichtinhalt |
| --- | --- |
| Identität | Claim-ID, Version, Status, Erstell- und Reviewdatum |
| Aussage | Normalisierte technische Aussage und Datentyp |
| Subjekt | Dichtung, Werkstofffamilie, Compound, Medium, Norm, Prozess oder Produkt |
| Applicability | Temperatur, Druck, Konzentration, Bewegung, Branche, Region, Dichtungstyp und weitere Bedingungen |
| Evidenz | Quelle, Seiten-/Abschnittsbezug, Quellentyp, Reviewstatus, Konflikte |
| Unsicherheit | Known, unknown, conditional, conflicting, not sufficiently supported |
| Übertragbarkeit | Welche Ebene gilt: Familie, Typ, Compound, Produkt, Charge oder konkreter Fall |
| Governance | Reviewer, Freigabestatus, Ablauf-/Reviewdatum, Änderungsgrund |

### 10.2 Kernobjekte

- SealType, SealPrinciple, Component und Geometry
- MaterialFamily, MaterialType, Compound, Product und Batch
- Medium, Mixture, Concentration und OperatingProfile
- Claim, Source, SourceVersion, ApplicabilityScope und Conflict
- Case, CaseSnapshot, Fact, Unknown, Assumption, Risk und Decision
- Calculation, Formula, Input, Result und ValidationStatus
- FailureObservation, Hypothesis, Test und RootCause
- Manufacturer, Capability, Evidence und Product
- Approval, Reviewer, Scope und Limitation
- Asset, Installation, Inspection, Replacement und Outcome
- Document, Artifact, Revision und AccessPolicy
### 10.3 Datenzonen

| Zone | Inhalt | Nutzung |
| --- | --- | --- |
| Draft | KI-extrahierte oder ungeprüfte Claims | Review-Queue; nicht autoritativ |
| Reviewed | Fachlich geprüfte Claims | Grounding, Vergleich, Verifier |
| Quarantined | Konfliktbehaftete oder unzureichend unterstützte Claims | Sichtbar für Review, nicht für definitive Aussagen |
| Tenant Private | Unternehmens- und Falldaten | Nur tenant- und rollenbezogen |
| Derived | Embeddings, Suchindex, Zusammenfassungen und Scores | Rebuildable, niemals SoR |
| Audit | Entscheidungen, Statuswechsel, Freigaben und Zugriffe | Append-only beziehungsweise unveränderbar |

## 11. Zielarchitektur der Plattform

### 11.1 Architekturstrategie

| Verbindliche Entscheidung sealingAI wird als modularer Monolith mit API-first-Verträgen aufgebaut. Fachliche Bounded Contexts werden im Code, Datenzugriff und Testsystem sauber getrennt. Ein Microservice wird erst extrahiert, wenn Skalierung, Sicherheitsgrenzen, Teamautonomie oder Betriebsanforderungen dies nachweisbar rechtfertigen. |
| --- |

### 11.2 Deployables

| Deployable | Aufgabe | Grenze |
| --- | --- | --- |
| Marketing Web | Öffentliche Website, Fachseiten, SEO, Einstieg | Keine vertrauliche Fallbearbeitung |
| Workspace Web | Chat, Cases, Engineering, Schäden, Dokumente und Freigaben | Keine fachliche Wahrheit im Client |
| API | Versionierte HTTP-/SSE-Grenze und Use-Case-Orchestration | Keine untypisierten Domänenabkürzungen |
| Worker | Dokumentenverarbeitung, Outbox, Embeddings, Exporte, Retention | Keine versteckten request-scoped Dauerjobs |

### 11.3 Zielstruktur im Monorepo

apps/ { marketing-web, workspace-web } services/ { api, worker } domain/ { identity, knowledge, taxonomy, materials, engineering, cases, failure, compliance, manufacturers, lifecycle, learning, documents, ai, retrieval, platform } packages/ { contracts, api-client, ui, evals } content/ { reviewed, drafts, quarantined } infrastructure/ · ops/ · docs/ · archive/

Die physische Verschiebung erfolgt erst nach abgesicherten Importgrenzen, Ports, Contract-Tests und Buildpfaden. Kosmetische Ordneränderungen ohne echte Ownership-Trennung sind kein Architekturfortschritt.

### 11.4 System of Record

| System | Rolle |
| --- | --- |
| Postgres | Kanonische Claims, Quellenmetadaten, Cases, Entscheidungen, Hersteller, Assets, Jobs und Audit. |
| Object Storage | Originaldokumente, Zeichnungen, Bilder, Exporte und große Artefakte. |
| Qdrant | Abgeleiteter, vollständig wiederaufbaubarer Retrieval-Index. |
| Redis | Cache, Locks, Rate Limits und kurzlebiger Arbeitszustand. |
| Identity Provider | Authentifizierung; Autorisierung bleibt zusätzlich serverseitig im Produkt. |

## 12. KI-, Kernel- und Entscheidungsarchitektur

### 12.1 Vertrauensmodell

| Schicht | Rolle | Autorität |
| --- | --- | --- |
| L1 Generator | Erklärt, strukturiert und formuliert | Keine autonome Fakt- oder Freigabeautorität |
| L2 Grounding | Liefert geprüfte Claims mit Provenienz | Autoritativ nur innerhalb Applicability und Reviewstatus |
| L3 Verifier/Guards | Prüft Claims, Sprache, Zahlen, Risiken und Konflikte | Darf blocken, aber keine neue Wahrheit erfinden |
| L4 Human/Manufacturer | Prüft und genehmigt konkrete Anwendung | Finale fachliche Verantwortung |

### 12.2 Referenzpipeline

1. Nutzerabsicht, Risikoklasse und Tenant bestimmen.
1. Relevanten Gesprächs- und Case-Kontext typisiert zusammensetzen.
1. Reviewed Claims und zulässige Tenant-Quellen mit Applicability abrufen.
1. Deterministische Berechnungen ausschließlich im Kernel ausführen.
1. Response Contract aus Fakten, Unknowns, Risiken und erlaubten Aussagen erzeugen.
1. LLM-Antwort beziehungsweise Artefaktentwurf erstellen.
1. Claim-, Zahlen-, Quellen-, Freigabe-, Injection- und Tenant-Guards ausführen.
1. Finale autoritative Antwort mit Quellen, Coverage und nächsten Schritten ausgeben.
1. Entscheidungsrelevanten Zustand versioniert persistieren; Draft-Streaming bleibt nicht autoritativ.
### 12.3 Streaming

Live-Token-Streaming ist zulässig, wenn der Kanal eindeutig als Vorschau gekennzeichnet ist. Für technische Fälle bleibt ausschließlich das finale, vollständig geprüfte Resultat autoritativ. Smalltalk oder reine Navigation kann direkt gestreamt werden, sofern keine fachlichen Claims entstehen.

### 12.4 Eval-Gate für allgemeinen Wissensmodus – M15

| Bereich | Verbindliche Anforderung |
| --- | --- |
| Referenzset | Grundlagen, Dichtungsarten, Werkstoffe, Vergleiche, Medien, Montage, Schäden, Normen, Grenzfälle, falsche Prämissen, Smalltalk und Injection. |
| Metriken | Fachrichtigkeit, Provenienz, Applicability, Overclaim, erfundene Präzision, Freigabesprache, Tiefe, Zitationsabdeckung und Eskalation. |
| Hard Gates | Keine erfundenen Normen/Grenzwerte, keine Material- oder Bauteilfreigabe, keine verschleierte Unsicherheit, keine ungeprüfte Herstellerbevorzugung. |
| Aktivierung | Feature Flag standardmäßig OFF; nur nach adjudiziertem Replay und Owner-Freigabe. |

## 13. Sealing Case und Entscheidungsdokument

### 13.1 Case-Phasen

| Phase | Zustand | Möglicher Ausgang |
| --- | --- | --- |
| Intake | Frage, Problem oder Dokument | Wissen oder Fall |
| Context | Anwendung, Medium, Betriebsprofil, Geometrie, Historie | Known/Unknown/Conflict |
| Assessment | Claims, Berechnungen, Risiken und Optionen | Orientierung |
| Decision Preparation | Trade-offs, Prüfbedarf und nächste Aktion | Hersteller-/Expertenbriefing |
| Review | Fachliche Rückfragen und Freigabegrenzen | Approved/Rejected/Conditional |
| Implementation | Produkt, Charge, Einbau und Dokumentation | Installed |
| Outcome | Standzeit, Schaden, Austausch oder laufender Betrieb | Field Evidence |

### 13.2 Manufacturer-Ready Brief

- Anwendung und Asset
- Dichtungstyp und vorhandene Ausführung
- Geometrie und Schnittstellen
- Medium, Konzentration, Additive und Verunreinigungen
- Druck-, Temperatur- und Bewegungsprofile einschließlich Spitzen
- Gegenkörper, Oberflächen, Schmierung und Umgebung
- Schadensbild und Historie
- bekannte, unbekannte und widersprüchliche Daten
- berechnete Werte mit Formel und Eingabeprovenienz
- Werkstoff- und Bauartoptionen mit Zielkonflikten
- Risiken, Ausschlüsse und konkrete Herstellerfragen
- Freigabestatus, Version und Verantwortliche
### 13.3 Minimal-Viable-Outcome – M14

| Stufe | Signal | Wert |
| --- | --- | --- |
| 1 Passiv | Fall erneut geöffnet, Ersatzteil nachbestellt, Wartung/Austausch erkannt | Frühe, unvollständige Indikatoren |
| 2 Ein-Klick | Läuft noch / ersetzt / undicht / ungeklärt | Niedrige Rückmeldehürde |
| 3 Strukturiert | Laufzeit, Ausfallart, Abweichung, Korrektur | Vergleichbare Outcomes |
| 4 Integration | CMMS, ERP, Sensorik oder Wartungsdaten | Skalierbare Rückführung |
| 5 Validiert | Fachlich geprüfte, anonymisierte und übertragbare Erkenntnis | Moat und Qualitätsverbesserung |

## 14. Herstellerökosystem, Neutralität und Capability Profile

### 14.1 Capability Profile v0 – H2-Pflicht

| Dimension | Mindestinhalt |
| --- | --- |
| Identität | Unternehmen, Region, Ansprechpartner, Status |
| Dichtungskompetenz | Dichtungsarten, Bauformen und Anwendungsgrenzen |
| Werkstoffkompetenz | Familien, Compounds, Spezialwerkstoffe |
| Fertigung | Verfahren, Größen, Toleranzen und Sonderteile |
| Branchen | Nachgewiesene Zielindustrien |
| Nachweise | Zertifikate, Prüfstände, Zulassungen, Dokumente |
| Service | Entwicklung, Schadensanalyse, Reparatur, Vor-Ort-Unterstützung |
| Ausschlüsse | Nicht angebotene oder nicht freigegebene Bereiche |
| Verifikation | Quelle, Reviewer, Status und Aktualität |

### 14.2 Neutralität by Design

- Technischer Fit basiert nur auf Fallanforderungen und verifizierten Fähigkeiten.
- Bezahlstatus, Sponsoring und Abonnement verändern keinen technischen Fit.
- Jede Zuordnung zeigt erfüllte, offene und nicht erfüllte Anforderungen.
- Hersteller können Nachweise einreichen, aber ihre eigene Verifikation nicht abschließen.
- Kommerzielle Sichtbarkeit wird getrennt und gekennzeichnet.
- Hersteller behalten direkten Fachkontakt und können annehmen, ablehnen oder Rückfragen stellen.
- Keine erzwungene Preisvergleichslogik und keine Offenlegung proprietärer Auslegungsregeln.
### 14.3 Conflict-of-Interest-Policy – M5

| Regel | Verbindliche Umsetzung |
| --- | --- |
| Offenlegung | Berufliche, wirtschaftliche und gesellschaftliche Herstellerbeziehungen werden dokumentiert. |
| Recusal | Betroffene Personen prüfen oder verifizieren verbundene Hersteller nicht selbst. |
| Datenzugriff | Falldaten sind tenant- und rollenbezogen; keine Sonderrechte für verbundene Unternehmen. |
| Fit | Verbundene Hersteller werden nach identischen Regeln bewertet und sichtbar gekennzeichnet, soweit rechtlich zulässig. |
| Audit | Ranking, Verifikation und Ausnahmen sind unveränderlich protokolliert. |
| Einspruch | Hersteller können Capability-Daten und Zuordnungen korrigieren lassen. |
| Unabhängigkeit | Kritische Verifikation wird durch externe oder voneinander unabhängige Reviewer abgesichert. |

## 15. Recht, Haftung, Datenschutz und Lizenzen

Diese SSoT trifft keine abschließende rechtliche Bewertung. Vor öffentlicher Aktivierung sicherheitskritischer Modi, Hersteller-Matching, organisationsübergreifender Datenverarbeitung und regulatorischer Aussagen ist eine spezialisierte Rechtsprüfung erforderlich.

### 15.1 Legal-Mindestpaket – M4

- AI-Act-Rollen-, Scope- und Risikoklassifizierung
- Haftungsmatrix je Produktmodus und Nutzerrolle
- Vertrags-, AGB- und Disclaimer-Kaskade
- Datenschutz, Auftragsverarbeitung, Löschung und Betroffenenrechte
- Geschäftsgeheimnisse, vertrauliche Zeichnungen und Herstellerwissen
- Normen-, Datenblatt-, Grafik-, CAD- und Content-Lizenzen
- Incident-, Beschwerde-, Korrektur- und Rückrufprozess
- Versicherungsprüfung: Cyber, Vermögensschaden, Betrieb und Produkt
- internationale Verfügbarkeit und regionale Rechtsunterschiede
### 15.2 Haftungsarchitektur

| Produktmodus | Rolle von sealingAI | Verbindliche Grenze |
| --- | --- | --- |
| Wissen | Informations- und Lernunterstützung | Keine Anwendungsfreigabe |
| Vergleich | Kriterienbasierte Orientierung | Kein Ersatz für Compound-/Produktprüfung |
| Engineering | Deterministische Berechnung aus Nutzereingaben | Eingaben, Formeln und Geltungsbereich sichtbar |
| Fall | Strukturierung und Vorbewertung | Keine finale technische Verantwortung |
| Hersteller-Fit | Kompetenzbasierte Vermittlung | Keine Garantie für Eignung oder Verfügbarkeit |
| Compliance | Orientierung und Nachweisnavigation | Keine Rechtsberatung oder Zertifizierung |
| Outcome | Dokumentation und Lernen | Keine automatische Übertragung auf andere Fälle |

## 16. Website-, Informations- und Experience-Architektur

### 16.1 Öffentliche Hauptnavigation

| Bereich | Inhalt |
| --- | --- |
| Wissen | SealingPedia, Werkstoffe, Medien, Dichtungsarten und Academy |
| Vergleichen & Auslegen | Vergleiche, Rechner, Selektoren und Engineering |
| Fälle lösen | Anwendung, Schaden, Substitution und Herstellerbriefing |
| Hersteller & Produkte | Kompetenzen, Produkte, Nachweise und Übergabe |
| Für Unternehmen | Workspace, Integrationen, Governance und Enterprise |
| Vertrauen & sealingAI | Methodik, Quellen, Neutralität, Sicherheit und Unternehmen |

### 16.2 Startseite

| Sektion | Zweck | Verbindlicher Inhalt |
| --- | --- | --- |
| Hero | Produkt in Sekunden verstehen | Claim, ein Eingabefeld, ein primärer CTA, drei Beispielanfragen, Trust Line |
| Zwei Nutzungstiefen | Wissen und Fall unterscheiden | Direkte Antwort vs. strukturierter Workflow |
| Mechanismus | USP beweisen | Frage → Kontext → Evidenz → Entscheidung → Fachprüfung |
| Beispielhafter Ablauf | Konkretheit | Sichtbar als Demo/fiktives Beispiel gekennzeichnet |
| Nutzen für Rollen | Relevanz | Kompakte Tabs oder Matrix statt Kachelwiederholung |
| Hersteller | Zweite Plattformseite | Qualifizierte Fälle und direkter Fachkontakt |
| Trust | Verantwortung sichtbar | Quellen, Grenzen, Neutralität und Freigabe |
| Wissenseinstieg | SEO und Exploration | Priorisierte, geprüfte Fachthemen |

### 16.3 Hero-Solltext

| Headline Dichtungstechnik. Von der Frage zur prüfbaren Entscheidung. |
| --- |

Subheadline: sealingAI beantwortet Fachfragen direkt und führt anwendungsabhängige Dichtungsfragen in einen strukturierten, quellenbasierten Fall – mit sichtbaren Datenlücken, Risiken und klarer fachlicher Freigabe.

Primärer CTA: Frage oder Fall starten.

Sekundärer Textlink: Wissen entdecken.

Trust Line: Vollständigkeit vor Empfehlung. Quellen vor Behauptung. Freigabe vor Einsatz.

### 16.4 Demo- und Proof-Regel

Vor dem ersten realen Pilotbeleg werden Beispiele ausschließlich als „beispielhafter Ablauf“, „Demonstrationsfall“ oder „fiktives Anwendungsbeispiel“ bezeichnet. Quantitative Wirkungsclaims und reale Fallstudien erfordern dokumentierte Pilotdaten und Freigabe.

### 16.5 Markenführung

Die verbindliche Schreibweise lautet sealingAI. Logo, Footer, Metadaten, strukturierte Daten, App, Rechtstexte, E-Mails und Herstellerportal werden automatisiert und manuell auf Konsistenz geprüft.

## 17. Fachseiten- und Content-Templates

### 17.1 Dichtungstyp-Seite

1. Kurzdefinition und Einsatz
1. Wirkprinzip und visualisierter Aufbau
1. Bauformen und Varianten
1. Werkstoffe und Komponenten
1. Betriebs- und Gegenkörperanforderungen
1. Auslegung und relevante Rechner
1. Montage, Lagerung und Inbetriebnahme
1. Schadensbilder und Diagnose
1. Normen, Prüfungen und Nachweise
1. Alternativen und Substitution
1. Herstellerkompetenzen und Produkte
1. Übergang in Frage, Vergleich oder Fall
### 17.2 Werkstoff-/Compound-Seite

1. Einordnung und chemischer Aufbau
1. Abgrenzung Familie, Typ, Compound und Produkt
1. mechanische, thermische und chemische Eigenschaften
1. Beständigkeit unter definierten Bedingungen
1. Alterung, Permeation, Quellung und Dekompression
1. statische und dynamische Eignung
1. Zulassungen und regulatorische Aspekte
1. Verarbeitung, Härten, Lieferformen und Lagerung
1. typische Anwendungen und Failure Modes
1. Trade-offs und Alternativen
1. konkrete Claims mit Quellen, Applicability und Reviewstatus
### 17.3 Vergleichsseite

Vergleiche zeigen keine pauschalen Gewinner. Jeder Vergleich enthält Kriterien, Bedingungen, Quelle, Spezifität, Unsicherheit, Zielkonflikt und notwendigen Prüfbedarf.

### 17.4 Schadensseite

Jede Schadensseite trennt Beobachtung, mögliche Ursache, Indizien dafür, Indizien dagegen, Prüfmaßnahme, Sofortmaßnahme und Eskalation. Ein Bildklassifikator darf nur Hypothesen priorisieren und niemals allein eine Root Cause bestätigen.

## 18. Messsystem und North-Star-Metriken

### 18.1 Reifegradabhängige Metrikkaskade – M16

| Horizont | North-Star-Metrik | Definition |
| --- | --- | --- |
| H1 Wissen | Monthly Useful Sealing Sessions | Sitzung mit positiver Bewertung, geöffneten Quellen, abgeschlossenem Vergleich, erzeugtem Artefakt oder gestartetem Workflow. |
| H2 Case Core | Monthly Qualified Sealing Cases | Strukturierter Fall mit Nutzerjob, Known/Unknown, Risiko und verwertbarem Ergebnis oder nächstem Schritt. |
| H3 Review | Technically Reviewed Cases | Fälle mit dokumentierter Hersteller-/Expertenprüfung. |
| H4 Netzwerk | Manufacturer-Ready Cases | Qualifizierte Übergaben, angenommen oder fachlich beantwortet. |
| H5 Lifecycle | Cases with Recorded Field Outcome | Fälle mit mindestens einem validen Feldergebnis. |

### 18.2 Qualitätsmetriken

- Hard-Gate-Verletzungen = 0
- erfundene Zahlen/Normen = 0
- Claim-Zitationsabdeckung
- Applicability- und Unknown-Abdeckung
- Overclaim-Rate
- Re-Ask-Rate bereits bekannter Fakten
- Rückfrageschleifen bis Herstellerbewertung
- Zeit bis Manufacturer-Ready Brief
- Annahme-/Ablehnungsgründe im Hersteller-Fit
- Outcome-Rückmeldequote und Validierungsqualität
## 19. Umsetzungsstrategie und Horizonte

| Horizont | Ziel | Pflichtumfang | Nicht jetzt |
| --- | --- | --- | --- |
| H0 Governance | SSoT, Audit und Schutzgrenzen | M1–M6, M15, Architektur-Baseline | Neue breite Features |
| H1 Knowledge Core | Nützlicher Wissensmodus | Geprüfte Grundlagen, RWDR/O-Ring, Werkstoffe, Eval-Gate | Vollständiger Marktplatz |
| H2 Case Core | Manufacturer-Ready Cases | Case State, Coverage, Briefing, Capability Profile v0, Pilot | Skalierter Produktgraph |
| H3 Engineering & Failure | Deterministische Tools und RCA | Rechner, Vergleiche, Failure Workflows, Reviews | Unkontrollierte Automatisierung |
| H4 Manufacturer Network | Verifiziertes Kompetenznetzwerk | Capabilities, Produkte, RFQ, Antwortformate, Governance | Preisgetriebener Marktplatz |
| H5 Lifecycle | Outcome-Loop und Organisationswissen | Asset Memory, CMMS/ERP, Outcomes, Analytics | Automatische Verallgemeinerung |

### 19.1 Vertikale Scheiben

Die Fachentwicklung erfolgt in dieser Priorität: O-Ringe/statische Elastomere, RWDR, Hydraulik/Pneumatik, Flachdichtungen/Flanschsysteme, Gleitringdichtungen, Packungen/Kompensatoren/Spezialdichtungen.

Eine Scheibe ist erst ausreichend, wenn Wissen, Werkstoffe, Medien, Engineering, Montage, Schäden, Normen, Falllogik, Herstellerfähigkeit und relevante Evaluationen gemeinsam funktionieren.

## 20. Operating Model, Ressourcen und WIP – M11

Die Vision wird gegen reale Kapazität geschnitten. Owner-provided Angaben werden als solche dokumentiert und regelmäßig aktualisiert. Ohne Kapazitätsfreigabe darf kein zusätzlicher Hauptworkstream begonnen werden.

| Regel | Verbindliche Auslegung |
| --- | --- |
| WIP-Limit | Maximal ein primärer Produkt-/Architekturworkstream und ein begleitender Content-Track. |
| Scope | Jeder Horizont erhält klare Must/Should/Not-now-Listen. |
| Fachreview | Kritische Claims und neue Domänen benötigen benannte Reviewkapazität. |
| Build vs Buy | Commodity-Funktionen bevorzugt integrieren; Moat-Komponenten selbst kontrollieren. |
| Definition of Done | Code, Tests, Eval, Dokumentation, Betrieb, Rollback und Reifegradkennzeichnung. |
| Stop/Go | Keine Weiterentwicklung bei ungeklärtem Hard Gate, fehlendem Review oder negativer Pilotwirkung. |
| Budget | Content-, Modell-, Infrastruktur-, Rechts- und Reviewkosten je Horizont sichtbar machen. |

## 21. Go-to-Market, Content und Geschäftsmodell

### 21.1 Markteintritt

Der Markteintritt erfolgt nicht mit dem Versprechen, die gesamte Dichtungstechnik bereits vollständig abzudecken. Der erste belastbare Wedge ist die fachlich hochwertige Wissens- und Fallqualifizierung in wenigen priorisierten Dichtungsdomänen.

### 21.2 Herstelleradoption – M12

- sealingAI ersetzt nicht die Anwendungstechnik, sondern reduziert Vorqualifizierung
- direkter Herstellerkontakt bleibt erhalten
- keine Pflicht zur Offenlegung proprietärer Auslegungslogik
- keine technische Bevorzugung zahlender Partner
- kontrollierte Datenfreigaben je Fall
- Annahme, Ablehnung und Rückfragen durch Hersteller
- verifizierte Kompetenzen statt öffentlicher Qualitätsranglisten
### 21.3 Geschäftsmodell

- Nutzer-/Teamabonnements für Workspace, Organisation und Integrationen
- Herstellerabonnements für Fallmanagement, Profile, Collaboration und Analytics
- Enterprise-Wissensräume und API
- Expert Review und Implementierungsleistungen
- keine Monetarisierung durch käuflichen technischen Rangplatz
### 21.4 GTM- und Content-Plan – M13

Ein separates ausführbares GTM-Dokument definiert ICP, Pilotakquise, direkte Ansprache, Verbände, Fachcontent, Suchstrategie, Events, Sprache, Preisexperimente, Budget, Runway und Kill-/Pivot-Kriterien. SEO ist ein Kanal, nicht der alleinige Markteintritt.

## 22. Governance, Reviews und Änderungen

### 22.1 Owner-Decision-Register – M6

Alle strategischen Forks werden als formale Entscheidungen dokumentiert. Die folgenden Entscheidungen sind mit dieser SSoT ratifiziert:

| ODR-01 · Entscheidung | Plattformmodell |
| --- | --- |
| Beschluss | Neutrale Wissens-, Engineering- und Fallplattform mit optionaler Herstellerübergabe; kein preisgetriebener Marktplatz. |
| Begründung | Vertrauen, technische Qualität und Herstellerbeziehung haben Vorrang vor Transaktionsoptimierung. |
| Konsequenz | Technischer Fit bleibt unabhängig von Monetarisierung. |

| ODR-02 · Entscheidung | Wissensmodus |
| --- | --- |
| Beschluss | Allgemeine Dichtungsfragen gehören zum Produkt, werden aber nur über M15 evaluiert und aktiviert. |
| Begründung | Früher Nutzerwert und 360°-Vision ohne unkontrollierte Scope-Erweiterung. |
| Konsequenz | Feature Flag, Referenzset und Hard Gates sind Pflicht. |

| ODR-03 · Entscheidung | 360° |
| --- | --- |
| Beschluss | 360° ist Zielarchitektur und Lifecycle-Vision, nicht heutiger Vollständigkeitsclaim. |
| Begründung | Verhindert Overclaim und ermöglicht Depth-first-Ausbau. |
| Konsequenz | Reifegradkennzeichnung auf allen Oberflächen. |

| ODR-04 · Entscheidung | Operativer Claim |
| --- | --- |
| Beschluss | Dichtungstechnik. Von der Frage zur prüfbaren Entscheidung. |
| Begründung | Heute belastbar, merkfähig und deckungsgleich mit dem Kern-USP. |
| Konsequenz | Lifecycle-Claim bleibt Vision bis Outcome-Beleg. |

| ODR-05 · Entscheidung | Trust-Claim |
| --- | --- |
| Beschluss | Vollständigkeit vor Empfehlung. Quellen vor Behauptung. Freigabe vor Einsatz. |
| Begründung | Starkes, etabliertes Vertrauensversprechen. |
| Konsequenz | Alternative Claims benötigen neue Owner-Entscheidung. |

| ODR-06 · Entscheidung | Architektur |
| --- | --- |
| Beschluss | Modularer Monolith, API-first, vier Deployables. |
| Begründung | Beherrschbare Komplexität bei klaren Domänengrenzen. |
| Konsequenz | Extraktion nur nach ADR und belegtem Bedarf. |

| ODR-07 · Entscheidung | Hersteller-Fit |
| --- | --- |
| Beschluss | Capability-basierter Fit, nie käuflich. |
| Begründung | Neutralität ist Eintrittsbedingung. |
| Konsequenz | Ranking und Verifikation auditierbar. |

| ODR-08 · Entscheidung | Outcome |
| --- | --- |
| Beschluss | Stufenmodell von passivem Signal bis validierter Felderfahrung. |
| Begründung | Moat entsteht schrittweise und ohne unrealistische Rückmeldepflicht. |
| Konsequenz | Outcome-Claims nur nach belegtem Reifegrad. |

### 22.2 Änderungsprozess

1. Änderungsantrag mit Problem, Evidenz und betroffenen Invarianten.
1. Klassifikation: redaktionell, Produkt, Architektur, Safety, Legal oder Business.
1. Auswirkungsanalyse auf Daten, KI, Tests, Website, Governance und Betrieb.
1. Bei strategischer Änderung Owner-Decision oder ADR.
1. Implementierung feature-flagged und mit Tests/Eval.
1. Dokumentation, Reifegrad und SSoT aktualisieren.
1. Aktivierung erst nach Gate und Rollback-Nachweis.
### 22.3 Verbotene Abkürzungen

- kein Feature allein aufgrund eines überzeugenden Demos live schalten
- keine ungeprüften Deep-Research-Ergebnisse als Reviewed Claims übernehmen
- keine technische Zahl direkt aus LLM-Text persistieren
- keine Herstellerkompetenz ohne Nachweis als verifiziert markieren
- keine Cross-Tenant-Analytik ohne Rechts-, Datenschutz- und Governance-Freigabe
- keine Freigabesprache durch Disclaimer nachträglich relativieren
## 23. Architektur- und Produkt-Audit gegen die SSoT

Das aktuelle Monorepo wird gegen diese SSoT in einem evidenzbasierten Deep-Dive geprüft. Der Audit trennt deklarierte, implementierte, getestete, gebaute, deployte und beobachtete Zustände.

### 23.1 Auditdimensionen

- Authority Order und Dokumentdrift
- Repo-, Modul- und Importgrenzen
- Runtime und Deployables
- Datenhoheit und Tenant-Isolation
- Claim-, Quellen- und Applicability-Modell
- Kernel-, LLM-, Verifier- und Response-Contract-Grenzen
- API-, SSE- und Client-Verträge
- Worker, Jobs, Idempotenz und Outbox
- Marketing- und Workspace-Coverage
- Eval-, Test-, Release- und Rollbackintegrität
- Reifegradkennzeichnung und externe Claims
- Legal-, Neutralitäts- und Interessenkonflikt-Governance
### 23.2 Hard Gates

| Gate | Nicht kompensierbare Bedingung |
| --- | --- |
| G1 Tenant | Kein Cross-Tenant-Leak in Postgres, Retrieval, Memory, Jobs oder Artefakten. |
| G2 Evidence | Kein autoritativer technischer Claim ohne Quelle, Status und Applicability. |
| G3 Kernel | Keine berechnete Zahl aus unkontrollierter LLM-Ausgabe. |
| G4 Approval | Keine finale technische Freigabe durch sealingAI. |
| G5 Neutrality | Kein käuflicher technischer Fit. |
| G6 Audit | Entscheidungen und Freigaben sind versioniert und nachvollziehbar. |
| G7 Release | Kein ungeprüfter oder nicht reproduzierbarer Produktionsrelease. |
| G8 Scope | Kein neuer Produktmodus ohne Eval- und Reifegradgate. |

## 24. Verbindliche Änderungsliste M1–M16

| ID | Änderung | Priorität | Status | Abnahme |
| --- | --- | --- | --- | --- |
| M1 | Authority Order und Supersession | P0 | In dieser SSoT ratifiziert | Dokumentkonflikte eindeutig lösbar |
| M2 | Mapping auf Invarianten, Verdicts und Coverage | P0 | Im Repo-Audit zu materialisieren | Maschinenlesbare Mapping-Tabelle |
| M3 | Reifegrad- und Claim-Governance | P0 | In dieser SSoT definiert | UI/Website markieren Status |
| M4 | Legal-Mindestkonzept | P0 | Externe Fachprüfung offen | Freigegebene Legal-Matrix |
| M5 | Neutralitäts- und Conflict-of-Interest-Policy | P0 | Inhalt definiert; Betriebsaudit offen | Rollen, Recusal, Logs und Review |
| M6 | Owner-Decision-Register | P0 | Grundentscheidungen ratifiziert | ODRs versioniert |
| M7 | Zweiseitiger USP | P1 | In dieser SSoT definiert | Website und Sales konsistent |
| M8 | Capability Profile v0 in H2 | P1 | Schema umzusetzen | Pilotfähiges Herstellerprofil |
| M9 | Homepage vereinfachen und Demos kennzeichnen | P1 | Sollbild definiert | Prototyp + Usability-Test |
| M10 | Pain Evidence Ledger | P1 | Methodik definiert | Quellenregister und Validierungsstatus |
| M11 | Operating Model und Ressourcen | P2 | Owner-Inputs einzupflegen | Kapazität, Budget, WIP und Stop/Go |
| M12 | Wettbewerb und Herstelleradoption | P2 | Strategiegrundsätze definiert | Pilot- und Adoption-Plan |
| M13 | GTM- und Content-Ökonomie | P2 | Separates ausführbares Dokument offen | ICP, Kanäle, Budget und KPIs |
| M14 | Minimal-Viable-Outcome | P2 | Stufenmodell ratifiziert | Erste passive/einfache Signale live |
| M15 | Eval-Gate Wissensmodus | P0 | Pflichten ratifiziert | Adjudiziertes Referenzset grün |
| M16 | Interims-North-Star-Metrik | P1 | Metrikkaskade ratifiziert | Instrumentierung und Dashboard |

## 25. Definition of Done für die neue SSoT

- Die SSoT ist im Repository versioniert und in der Authority Order referenziert.
- AGENTS.md und relevante Build-Specs verweisen auf diese SSoT und enthalten keine widersprüchlichen strategischen Aussagen.
- Alle bestehenden Invarianten und Verdict-/Coverage-Zustände sind auf die SSoT gemappt.
- Der Codex-Deep-Dive-Audit bewertet den Ist-Zustand gegen diese SSoT.
- Website, Produkt und Herstellerportal verwenden dieselbe Positionierung und Reifegradlogik.
- Der allgemeine Wissensmodus bleibt bis M15 hinter einem Gate.
- Legal-, Conflict- und Neutralitätsregeln sind vor externen Piloten freigegeben.
- Capability Profile v0 existiert vor Herstellerübergaben.
- Metriken und Demo-Kennzeichnung verhindern Overclaim.
- Jede Abweichung besitzt Owner-Decision, ADR oder dokumentierte Remediation.
## Anhang A. Referenz-Journeys

| Journey | Auslöser | Sollverhalten |
| --- | --- | --- |
| A1 Wissensfrage | „Wie funktioniert ein RWDR?“ | Direkte Erklärung, Aufbau, Wirkprinzip, Grenzen, Quellen bei spezifischen Claims und Übergang zu vertiefenden Inhalten. |
| A2 Werkstoffvergleich | „FKM oder EPDM?“ | Kriterien klären, Vergleich nach Medium/Temperatur/Dynamik, Compoundspezifität und Prüfbedarf darstellen. |
| A3 Anwendung | „Welche Dichtung für Hydrauliköl bei 120 °C?“ | Fehlende Parameter erfassen, Coverage anzeigen, Optionen und Risiken strukturieren, keine Freigabe. |
| A4 Schaden | „Der Ring leckt nach drei Wochen.“ | Beobachtungen, Historie und Systemparameter aufnehmen; Hypothesen und Prüfplan erstellen. |
| A5 Substitution | „Ersatz für abgekündigten FKM-Compound.“ | Leistungsprofil, Zulassungen, Liefergrund, Alternativen und Requalifizierung abbilden. |
| A6 Hersteller | „Wer kann das prüfen?“ | Nur nach ausreichend strukturiertem Fall Capability Fit berechnen und begründen. |
| A7 Lifecycle | „Was war an Pumpe P-101 verbaut?“ | Asset, Installation, Freigabe, Charge, Wartung und Outcome zusammenführen. |

## Anhang B. Beispielhafte Herstellerantwort

| Kennzeichnung Demonstrationsfall – kein realer Kundenfall. |
| --- |

Die Herstellerantwort referenziert dieselbe Fallversion, bestätigt oder korrigiert Known/Unknown, nennt vorgeschlagene Produkte/Compounds, gibt Voraussetzungen, Ausschlüsse und Prüfbedarf an und dokumentiert den Freigabestatus. Sie darf technische Rückfragen stellen und den Fall ohne negative Rankingfolge ablehnen.

## Anhang C. Quellen- und Evidence-Grundsätze

- Primärquellen und offizielle Dokumentation haben Vorrang.
- Normtexte werden nur im lizenzrechtlich zulässigen Umfang gespeichert und wiedergegeben.
- Herstellerdaten gelten für die konkret angegebene Qualität und den genannten Geltungsbereich.
- Sekundärliteratur dient zur Einordnung, nicht zur Überschreibung konkreter Primärdaten.
- Deep Research erzeugt Drafts, keine Reviewed Truth.
- Konflikte bleiben sichtbar und werden nicht durch Mehrheitsabstimmung des Modells geglättet.
- Quellenstatus, Version und Reviewdatum sind nutzerseitig nachvollziehbar.
## Anhang D. Prüffragen für jede neue Funktion

1. Welchen Nutzerjob löst die Funktion?
1. Welcher Pain und welche Evidenz rechtfertigen sie?
1. Welche SSoT-Domäne ist Owner?
1. Welche kanonischen Datenobjekte werden benötigt?
1. Welche Claims oder Berechnungen entstehen?
1. Welche Risikoklasse und Hard Gates gelten?
1. Welche Tenant-, Datenschutz- und Lizenzfragen entstehen?
1. Welche Reifegradkennzeichnung ist ehrlich?
1. Welches Eval-Set und welche Akzeptanzmetriken gelten?
1. Wie wird die Funktion deaktiviert und zurückgerollt?
1. Welche Website- und Content-Auswirkungen entstehen?
1. Trägt sie zum aktuellen Horizont bei oder ist sie Not-now?
## 26. Verbindlicher Schlussbeschluss

| SSoT-Beschluss Diese Version 2.0 ist die neue strategische Single Source of Truth für sealingAI. Sie definiert das verbindliche Zielbild, die Positionierung, die Produkt- und Vertrauensprinzipien, das 360°-Domänenmodell, die Zielarchitektur, die Website- und Herstellerlogik sowie die Governance- und Aktivierungsgates. Der nächste Schritt ist kein weiterer freier Konzeptzyklus, sondern der evidenzbasierte Audit des aktuellen Monorepos und die priorisierte Umsetzung der offenen M1–M16-Abnahmen. |
| --- |

Verbindliche Kurzform: sealingAI beantwortet einfache Dichtungsfragen direkt und macht anwendungsabhängige Fragen zu prüfbaren Fällen. Es zeigt Datenlücken, Quellen, Geltungsbereiche, Risiken und die richtige nächste Aktion. Technische Entscheidungen bleiben nachvollziehbar; die finale Freigabe bleibt beim Fachverantwortlichen.
