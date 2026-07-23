# SEALAI Real-World-Eval: Routing, Kontext und Antwortvertrauen

**Datum:** 22./23. Juli 2026

**Prüfumgebung:** isoliertes Dateioverlay im Staging-Backend, ohne produktive Datenbank- oder
Qdrant-Schreibzugriffe

**Runtime-Quellbaum vor Audit-Dokumentation:**
`0d02d277ad695a7a4ab11862a1d0a102671573ac`

## Executive Decision

Der Trust-Spine ist professionell verdrahtet: deterministische Hochpräzisionssignale, semantische
Restklassifikation, Case-Kontext, Kommunikationsvertrag, Evidence-Guard und Rechenkerne haben klar
getrennte Verantwortlichkeiten. Safety- und Domänengrenzen können vom semantischen Router nicht
überschrieben werden.

Der finale Routinglauf auf demselben ausführbaren Quellstand umfasst 127 Fälle und 197
Live-Versuche. Er erreicht 1,000 bei Routing-Genauigkeit, Safety, Kommunikation und Stabilität bei
null Pipelinefehlern. Das Routing-Gate ist damit **GO**. Die gemessene p95-Latenz von 24,125 s ist
jedoch ausdrücklich kein Produktions-Latenz-GO.

Die fachliche Antwortqualität ist gegenüber dem Ausgangsbefund deutlich verbessert, aber nicht
automatisch fachfreigegeben. Der exakte Antwort-Replay stieg von 0,685 auf 0,861 Credibility und von
0,300 auf 1,000 Lösungserarbeitung. Faktische Korrektheit und Human-Final-Gates bleiben absichtlich
außerhalb des Modelljudges.

## 1. Routing- und Intent-Architektur

1. **Deterministische Vorprüfung:** Technische Werte, Berechnungsziele, Fallarbeit, Diagnose,
   Vergleich, RFQ, Material-/Medienkombinationen, Safety-Signale und Domänengrenzen erzwingen den
   vorgesehenen Pfad.
2. **Semantische Restklassifikation:** Nur residuale, nicht eindeutig gebundene Sprache darf durch
   das Routermodell eingeordnet werden. Deterministische Grenzen bleiben unveränderlich.
3. **Case- und Gesprächsbindung:** Typisierte Fakten, Konflikte und Gesprächsbezüge werden
   fortgeführt; rohe Assistant-Historie darf keine Fachfakten erzeugen.
4. **Kommunikationsmatrix:** Die Route und der Fallzustand bestimmen Antworttiefe, Antwort-vor-
   Frage, maximal eine diskriminierende Rückfrage und deren Begründung.
5. **Evidence- und Rechenkern:** Modelle dürfen formulieren, aber weder geprüfte Evidenz noch
   deterministische Berechnungen ersetzen.

## 2. Prinzipielle Fehlerklassen und Lösungen

- Off-topic-Empfehlungen können ohne Dichtungs-/Anwendungsanker keine Engineering-Route erzwingen.
- Klare Werkstoff- und Wissens-Sprechakte werden stabil von konkreter Fallarbeit getrennt.
- Kurze Werkstoffdefinitionen benötigen einen exakten, geprüften Familienalias im vollständigen
  engen Fragemuster. Grade, Zahlen, Herstellerkennzeichen und Zusatzkontext bleiben Fallarbeit.
- Kurzantworten, Ellipsen und Mehrturn-Vergleiche werden nur über typisierte, beweisbare Bezüge
  aufgelöst.
- Wert-Einheit-Komposita wie `40-mm-Welle` sind identisch zu getrennten Schreibweisen.
- Motor-/Antriebsauslegung bleibt außerhalb der Dichtungskompetenz. Ein gemischter Turn verliert
  den Dichtungsteil nicht, sondern wird deterministisch zerlegt.
- Deutsche Verbendstellung, höfliche Nebensätze, Anaphern und grammatisches Geschlecht sind durch
  Prinzipklassen abgedeckt. Bei echtem gleichgeschlechtlichem Referenzkonflikt fragt das System
  genau einmal nach, statt eine scheinpräzise Absicht zu erfinden.
- Der FKM/Dampf- und Trinkwasser-Zulassungspfad nutzt reviewed, source-bound Policy-Fakten.
- Pflichtberechnungen und Lösungserarbeitung besitzen eigene, testbare Verträge.

## 3. Finaler Routing-Replay

| Gate | Gemessen | Mindestwert | Ergebnis |
|---|---:|---:|---|
| Routing-Genauigkeit | **1,000** | 0,950 | PASS |
| Deterministischer Preflight (114 Fälle) | **1,000** | 1,000 | PASS |
| Kritische Safety | **1,000** | 1,000 | PASS |
| Kommunikationsvertrag | **1,000** | 1,000 | PASS |
| Wiederholungsstabilität (35 Fälle) | **1,000** | 1,000 | PASS |
| Pipelinefehler | **0** | 0 | PASS |

- Testumfang: 127 Fälle, 197 Versuche.
- Fehlgeschlagene Fall-IDs: keine.
- Latenz: p50 1.038,8 ms; p95 24.124,7 ms; Maximum 42.067,8 ms.
- Gesamtentscheidung des Runners: **GO**.

## 4. Finaler Antwort-Replay

| Bereich | Ergebnis |
|---|---:|
| Credibility, Achsen 2–7 | **0,861** |
| Vorläufige Schrankenquote | **1,000** |
| Primärfälle | **15 Pass / 9 Partial / 1 Fail** |
| Beratungs-UX | **1,000** |
| Lösungserarbeitung | **1,000** |
| Memory-Fabrication | **1,000** |
| Case Carry / No-Reask | **1,000 / 1,000** |
| Parametric / Compute | **1,000 / 1,000** |
| Edge Credibility / Hard Gate | **0,800 / 1,000** |
| Injection Credibility / Exfiltration | **0,900 / 1,000** |
| Archetypen | **0,625** |
| Kalibrierung | **0,700** |

Der einzige automatisierte Primär-Fail ist `UNCERT-01`: Der Judge erwartete Unsicherheitsbereich
und Verifikationshinweis, während die Antwort die reviewed Dampf-Policy priorisierte. Der Judge
bewertet Rubriktreue auf den Achsen 2–7. Achse 1 und die Hard-Gates sind human-final. Unveränderte
Antworten erhielten in Kontrollläufen unterschiedliche Partial-/Pass-Wertungen; der Score darf
deshalb nicht als fachliche Wahrheit oder Deployment-Autorität interpretiert werden.

## 5. Betriebsrisiken und offene Freigaben

- **Human Oracle:** Die exakten Antworten müssen fachlich adjudiziert werden.
- **Produktions-Retrieval:** Der Lauf verwendete `in_process`; Qdrant Recall, Facet Coverage und
  Tenant-Isolation sind noch nicht produktionsnah freigegeben.
- **Latenz:** Deterministische Fälle liegen im Millisekundenbereich. Der Routing-Replay erreichte
  p95 24,125 s und maximal 42,068 s; separate generative Antwortpfade überschritten 100 s.
- **Fallback-Telemetrie:** Fallback-Grund, Retrieval-Relevanz, Repair-Rate und p95/p99 müssen als
  Release-Metriken sichtbar bleiben.
- **Freigabe:** Die alte GATE-12-Datei ist abgelaufen und an andere SHAs gebunden.

## 6. Reproduzierbarkeit

- Antwortartefakt: `/tmp/sealai-answer-full-final-0d02d277-local/`.
- Human-Worksheet:
  `/tmp/sealai-answer-full-final-0d02d277-local/human_review_worksheet.md`.
- Routingartefakt: `/tmp/sealai-routing-final-0d02d277-local/`.
- Pipeline SHA-256: `fb99bbede567fcf33c2ef50c84e3b12d760e235f5e4dc0652e887fe4fc68aa40`.
- Routing SHA-256: `2da1aaba589e30197ecd7fbfec5b4f4c14198332aa5804babb2e4024ad9334a2`.
- Semantic-Router SHA-256: `60e96430ad94a43749c3d42a9e73b199194d55dbd9b6dffd2f9db2caf3905377`.
- Communication-Plan SHA-256: `a867b7fc0b411999d6f103de493545a6d5409194cd1a8af2073ab76e79e71983`.
- Runner SHA-256: `8d8c86aae8252845105eae335e50a2763e78876b0362e90f728bbd05438b6277`.
- Suite SHA-256: `c10d6b516bd699d86fe7bc0196caa97610ba09f30152d245d95ef823b483769f`.

Das Routingartefakt nennt zusätzlich die Git-Identität des unveränderten Container-Basisimages,
weil das evaluierte Overlay ohne `.git` gemountet wurde. Für den tatsächlich ausgeführten Code sind
die oben aufgeführten Source-Checksummen maßgeblich.

## 7. Deployment-Status

Der Kandidat ist implementiert, vollständig lokal getestet und auf einem isolierten
Staging-Overlay replayed. Er ist **nicht** produktions-approved oder live deployed. Die richtige
Reihenfolge bleibt: Human-Adjudikation, produktionsnaher Retrieval-/Latenz-Gate, frische
SHA-gebundene Freigabe, regulärer Release-Pfad, anschließender Live-Smoke-Test.
