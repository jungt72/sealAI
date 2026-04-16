# SeaLAI — Finales Produktkonzept

**Version:** 1.2  
**Datum:** 2026-04-16  
**Status:** Derived product concept — subordinate to `konzept/sealai_ssot_architecture_plan.md`

> Dieses Dokument beschreibt Produktlogik, Positionierung, Nutzerwert, MVP-Fokus,
> UX-Zielbild, Marktansatz und Geschäftsmodell.
> Für Architektur, Routing, Datenmodell, Phase-Gates, Output-Classes, Risk Scores,
> Readiness, State Regression und Implementierungsreihenfolge gilt ausschließlich
> `konzept/sealai_ssot_architecture_plan.md` als bindende Quelle.

---

## 1. Die Idee in einem Satz

SeaLAI ist der schnellste Weg von einem unklaren Dichtungsproblem
zu einer belastbaren, herstellerfähigen Anfrage — und macht damit
einen bislang fragmentierten, intransparenten und expertendominierten Markt
für Konstrukteure, Instandhalter und technische Einkäufer deutlich zugänglicher.

---

## 2. Das Problem, das SeaLAI löst

### 2.1 Für den Nutzer

Der Dichtungstechnik-Markt ist aus Nutzersicht schwer zugänglich:

- Hersteller sprechen in eigenen Produktsprachen
- identische oder ähnliche Lösungen erscheinen unter unterschiedlichen Bezeichnungen
- die technische Vergleichbarkeit ist für Nicht-Spezialisten gering
- Rückfragen und Außendienstschleifen kosten Zeit
- der Nutzer weiß oft nicht, ob ein Vorschlag technisch passend oder nur verfügbar ist

Typischerweise läuft eine Anfrage heute so:

1. Unscharfe Suche nach Medium, Werkstoff oder Maschinentyp
2. Herstellerseiten, Verzeichnisse oder Kontakte
3. Kontaktaufnahme ohne saubere Fachsprache
4. Mehrere Rückfrageschleifen
5. Einzelangebote ohne transparente Vergleichbarkeit
6. Unsicherheit über technische Eignung, Preisniveau und Alternativen

Der Nutzer hat meist nicht primär ein Technikproblem.
Er hat ein Problem mit:

- Orientierung
- Übersetzung in Fachsprache
- Vergleichbarkeit
- Datenvollständigkeit
- Herstellerzugang

### 2.2 Für kleinere und mittlere Hersteller

Ein spezialisierter Dichtungshersteller hat oft:

- starkes technisches Know-how
- gute Nischenkompetenz
- aber geringe digitale Sichtbarkeit
- viel Aufwand durch unqualifizierte Anfragen
- wenig strukturierte Vorqualifikation eingehender Fälle

Er verliert Aufträge häufig nicht wegen schlechter Technik,
sondern weil:

- er nicht gefunden wird
- oder der Kunde die Anfrage nicht qualifiziert genug formulieren kann

---

## 3. Die Lösung

SeaLAI führt den Nutzer durch eine strukturierte technische Klärung,
ordnet die Dichtaufgabe fachlich ein,
macht fehlende Informationen transparent
und überführt den Fall in eine belastbare technische Vorauswahl
bzw. eine herstellerfähige Anfragebasis.

```text
Nutzer beschreibt Problem oder Ziel
        ↓
SeaLAI versteht, strukturiert und qualifiziert
        ↓
Technische Einordnung + offene Punkte + Checks
        ↓
Vorqualifizierte, herstellerneutrale Anfragebasis
        ↓
Matching mit geeigneten Herstellern
        ↓
Hersteller prüfen final und antworten
```

### 3.1 Was SeaLAI liefert

- strukturierte Bedarfsermittlung
- fachliche Einordnung der Dichtaufgabe
- pfadbezogene Datensammlung
- Risikotransparenz
- deterministische Checks und Vorbewertungen
- Hersteller-vorqualifizierte Anfragebasis
- PDF- und JSON-Artefakte
- transparente offene Punkte

### 3.2 Was SeaLAI nicht liefert

- keine finale technische Herstellerfreigabe
- keine Garantie über Eignung
- keine verdeckte Herstellerbevorzugung
- keine Normkonformitätsbehauptung ohne Nachweise

---

## 4. Positionierung

### 4.1 Was SeaLAI ist

SeaLAI ist der strukturierte, neutrale Einstiegspunkt für technische Dichtungsanfragen.

### 4.2 Was SeaLAI nicht ist

- kein Ersatz für Herstellerberatung
- kein Produktkatalog
- kein bloßer Suchindex
- kein generischer Chatbot
- kein Black-Box-Empfehlungssystem

### 4.3 Das Versprechen an den Nutzer

Du musst kein Dichtungsexperte sein.
Du musst nicht wissen, wie die Lösung heißt.
Du beschreibst dein Problem oder deinen Bedarf — SeaLAI hilft dir,
daraus eine fachlich saubere und herstellerfähige Anfrage zu machen.

### 4.4 Das Versprechen an den Hersteller

Weniger Schrottanfragen.
Mehr technisch vorqualifizierte Fälle.
Mehr Klarheit über Medium, Geometrie, Risiko und offene Prüfpunkte.
Weniger Vorqualifizierungsaufwand im Vertrieb.

---

## 5. Das technische Grundversprechen

SeaLAI gibt keine finale Produktempfehlung aus,
sondern erstellt eine technische Vorauswahl und belastbare Anfragebasis.

Das bedeutet:

**SeaLAI darf:**

- technische Daten strukturieren
- Rückfragen priorisieren
- Berechnungen durchführen
- Risiken markieren
- Materialien / Typen / Dichtfamilien vorqualifizieren
- Hersteller-Kandidaten transparent vorqualifizieren

**SeaLAI darf nicht:**

- finale Freigabe behaupten
- Haftung des Herstellers übernehmen
- unbestätigte Stoffdaten als Wahrheit behandeln
- ohne ausreichende Daten Sicherheit suggerieren

### 5.1 Sprachregeln

SeaLAI spricht bewusst in Formulierungen wie:

- Vorauswahl
- `fit_score`
- wahrscheinliche Richtung
- offene Punkte
- Herstellerprüfung erforderlich

SeaLAI vermeidet:

- „garantiert passend“
- „final freigegeben“
- „wird sicher funktionieren“
- „normkonform bestätigt“, wenn Nachweise fehlen

---

## 6. Geschäftsmodell

### 6.1 Wer zahlt wen

| USER | SeaLAI | HERSTELLER |
|---|---|---|
| Kostenlos | Technische Intelligence + UX + Neutralität | Zahlt für Listing + qualifizierte Leads |

### 6.2 Monetarisierung Herstellerseite

| Modell | Beschreibung | Phase |
|---|---|---|
| Pilot-Listing | feste monatliche Fee für 1 Subsegment | MVP |
| Standard-Listing | Listing + Inquiry-Weiterleitung | V1 |
| Performance | pay-per-accepted-inquiry / pay-per-quote | V2 |
| Featured | erhöhte Sichtbarkeit in passenden Fällen, transparent markiert | V2 |

### 6.3 Zwingender Grundsatz

Technischer Fit ist niemals käuflich.
Sichtbarkeit kann käuflich sein — aber nur transparent und nachgelagert.

---

## 7. Der ideale erste Hersteller

Der ideale erste Hersteller ist nicht der größte Marktteilnehmer,
sondern ein mittelständischer Spezialist mit:

- klarer technischer Stärke
- schwächerem digitalen Vertrieb
- hohem Vorqualifizierungsaufwand im Außendienst
- Bereitschaft, neue Kanäle zu testen
- echtem Nutzen aus sauber qualifizierten Anfragen

---

## 8. MVP-Strategie

### 8.1 Der entscheidende KPI

Der Kern-KPI ist:

Anteil der SeaLAI-Inquiries, die innerhalb definierter SLA
zu einer echten Hersteller-Quote führen.

Nicht:

- Klicks
- Registrierungen
- reine PDF-Erzeugung
- bloße Chat-Nutzung

### 8.2 Scope des MVP

Nicht: gesamte Dichtungstechnik in voller Tiefe
Ja: klar abgegrenzter technischer Tiefenpfad

### 8.3 Empfohlener MVP-Fokus

Gleitringdichtungen für Kreiselpumpen in chemischen / prozesstechnischen Anwendungen (`ms_pump`)

### 8.4 Warum genau dieser Scope

- klare fachliche Problemklasse
- hoher Pre-Sales-Aufwand
- großer Nutzen durch Vorqualifikation
- hoher Bedarf an sauberer Datenstruktur
- gute Basis für spätere norm- und pfadlogische Erweiterungen

### 8.5 Strategische Erweiterbarkeit

SeaLAI wird architektonisch so gebaut, dass später sauber integrierbar sind:

- Radialwellendichtringe
- statische Dichtungen
- Labyrinth-/Bearing-Isolator-Konzepte
- Hydraulik-/Pneumatikdichtungen
- hygienische / Emissions- / ATEX- / Offshore-Spezialfälle

Aber:

Im MVP wird nur `ms_pump` fachlich tief beherrscht.
Alle anderen Pfade werden strukturell vorbereitet, aber nicht auf identischer Tiefe umgesetzt.

---

## 9. Die reale Nutzerwelt: Request Types

SeaLAI muss die reale Eingangssituation des Nutzers abbilden.
Nicht jede Anfrage ist eine Neuauslegung.

Die maßgeblichen Request Types sind:

- `new_design`
- `retrofit`
- `rca_failure_analysis`
- `validation_check`
- `spare_part_identification`
- `quick_engineering_check`

### 9.1 Warum das wichtig ist

Der typische Nutzer kommt oft nicht mit:

„Bitte legen Sie mir eine neue Dichtung aus.“

Sondern mit:

- „Die Dichtung hält nur 3 Monate.“
- „Wir haben nur den Einbauraum und das Altteil.“
- „Ist unsere bestehende Lösung unter neuen Bedingungen noch zulässig?“
- „Was ist das überhaupt für ein Dichttyp?“

Gerade RCA und Retrofit sind daher entscheidend für hohen User-Nutzen.

---

## 10. UX-Zielbild

### 10.1 Grundprinzip

Der Nutzer soll SeaLAI wie einen sehr guten technischen Gesprächspartner erleben:

- strukturiert
- ruhig
- transparent
- fachlich führend
- nicht überfordernd
- nicht formularartig

### 10.2 Chat + Cockpit

Das zentrale UX-Muster ist:

- Chat für geführte Klärung, Erklärung und Rückfragen
- Cockpit für Zustand, Daten, Risiken, Blocker, Berechnungen und Reifegrad

### 10.3 Was das Cockpit leisten muss

Das Cockpit soll sichtbar machen:

- was sicher bekannt ist
- was aus Chat / Dokument / Registry stammt
- was fehlt
- welche Risiken aktiv sind
- welche Checks schon berechnet wurden
- welche Schritte als nächstes relevant sind
- ob eine belastbare Aussage oder Anfrage bereits möglich ist

### 10.4 UX-Prinzipien

- Eine gute Frage nach der anderen
- Keine Scheinsicherheit
- Stale-State sichtbar
- Pfad und Reifegrad sichtbar
- Offene Punkte transparent
- Hersteller-Matching nachvollziehbar
- Fachsprache übersetzen, nicht voraussetzen

---

## 11. Die Produktlogik auf hoher Ebene

### 11.1 SeaLAI denkt nicht zuerst in Produkten

SeaLAI denkt zuerst in:

- Dichtaufgabe
- Request Type
- Dichtfamilie / Pfad
- Datenlage
- Risiko
- Fit
- Nachweisbedarf

### 11.2 SeaLAI arbeitet nicht formularzentriert

Es arbeitet:

- gesprächsgeführt
- zustandsbasiert
- regelgestützt
- provenance-sensibel
- pfadabhängig

### 11.3 SeaLAI ist kein Ratensystem

Wenn Daten fehlen, sagt SeaLAI:

- was fehlt
- warum es fehlt
- was deshalb noch nicht zulässig ist

---

## 12. Request Types und Pfade in der Produktsicht

### 12.1 Top-Level-Eingangsarten

- Neuauslegung (`new_design`)
- Retrofit (`retrofit`)
- RCA / Schadensanalyse (`rca_failure_analysis`)
- Validierung (`validation_check`)
- Ersatzteil / Identifikation (`spare_part_identification`)
- Quick Check (`quick_engineering_check`)

### 12.2 Technische Hauptpfade

- `ms_pump`
- `rwdr`
- `static`
- `labyrinth`
- `hyd_pneu`
- `unclear_rotary`

### 12.3 Produktregel

SeaLAI soll zuerst die Dichtaufgabe sauber einordnen,
erst danach die technische Familie bestimmen,
und erst dann eine Vorselektion oder Anfragebasis erzeugen.

---

## 13. Medium-Intelligence als Produktmerkmal

Ein großer Unterschied zu einfachen Formular- oder Suchsystemen ist,
dass SeaLAI den bloßen Mediennamen nicht mit einer vollständigen Stoffwahrheit verwechselt.

SeaLAI unterscheidet auf Produktebene:

- Rohangabe des Nutzers
- assistiven Medium-Kontext
- validierte Stoff-/Registry-Daten
- bestätigte technische Eigenschaften
- offene Stoffdatenlücken

Das bringt dem Nutzer:

- intelligentere Rückfragen
- frühere Risikoerkennung
- bessere Werkstoffdiskussion
- weniger Scheinsicherheit

---

## 14. Transparenz und Vertrauen

Vertrauen entsteht in SeaLAI nicht durch „KI-Magie“, sondern durch:

- sichtbare Datenherkunft
- sichtbare offene Punkte
- sichtbare Reifegrenzen
- saubere Trennung zwischen Vorauswahl und Herstellerfreigabe
- transparente Sponsored-/Listing-Logik

---

## 15. Hersteller-Matching

### 15.1 Ziel

SeaLAI soll nicht den lautesten Hersteller priorisieren,
sondern den technisch passenden.

### 15.2 Matching-Kriterien

- Dichtfamilie / Capability
- Werkstoff- und Medienkompetenz
- Druck-/Temperatur-/PV-Fenster
- Norm-/Branchenfähigkeiten
- Support-System-Fähigkeiten
- Geometrie-/Größenbereich
- offene Prüfpunkte
- Lieferfähigkeit / Commercial Context

### 15.3 Transparenz

Der Nutzer muss sehen:

- warum ein Hersteller vorgeschlagen wird
- welche Punkte noch zu prüfen sind
- ob Sichtbarkeit bezahlt ist

---

## 16. Artefakte und Deliverables

SeaLAI soll dem Nutzer und den Herstellern strukturierte Ergebnisse liefern:

- technische Zusammenfassung
- offene Punkte
- Risiken
- Vorselektion
- PDF
- JSON
- inquiry-/RFQ-nahe Pakete

Diese Artefakte dienen dazu,
den Fall anschlussfähig an reale Herstellerprozesse zu machen.

---

## 17. Sicherheits- und Qualitätsprinzipien

### 17.1 Keine stille Freigabe

SeaLAI darf nie so wirken, als hätte es die finale Herstellerfreigabe ersetzt.

### 17.2 Keine unmarkierten Annahmen

Wenn Annahmen nötig sind, müssen sie sichtbar sein.

### 17.3 Keine versteckten Sponsoring-Effekte

Technischer Fit bleibt von Bezahlung getrennt.

### 17.4 Keine Scheinklarheit aus Web-/LLM-Hinweisen

Hinweiswissen ist nicht automatisch bestätigte Engineering-Wahrheit.

---

## 18. Go-to-Market

### Phase 1 — Beweis
- enger Subsegmentfokus
- Pilot-Hersteller
- echte Nutzeranfragen
- Quote Rate messen
- Prozesse manuell eng begleiten

### Phase 2 — Monetarisierung
- Listing-Fee
- mehr Hersteller
- klarer Nachweis von Mehrwert
- strukturierter Vertrieb auf Herstellerseite

### Phase 3 — Ausbau
- weitere Pfade vertiefen
- norm- und branchenspezifische Module ausbauen
- Hersteller-Self-Service
- tieferes Commercial-/Supply-Layer
- stärkere Plattformeffekte

---

## 19. Was bewusst unverändert bleibt

- User-first-Positionierung
- Herstellerfreigabe als letzte Instanz
- neutrales Marktplatzprinzip
- PDF-/JSON-Artefakte als zentrale Deliverables
- enger MVP-Fokus statt Scope-Chaos
- Vertrauen durch Transparenz statt Behauptung

---

## 20. Schlussfazit

SeaLAI ist kein generischer KI-Chatbot für Dichtungen.
SeaLAI ist kein Industrieverzeichnis mit etwas Chat darüber.
SeaLAI ist auch kein verstecktes Hersteller-Tool.

SeaLAI ist ein neutrales, technisches Vorqualifikationssystem,
das reale Dichtungsprobleme und Dichtungsbedarfe so aufbereitet,
dass Nutzer Klarheit gewinnen und Hersteller mit deutlich besserer Datenqualität arbeiten können.

Der eigentliche Moat ist nicht nur Technologie.
Der eigentliche Moat ist:

- die Qualität der Bedarfsermittlung
- die Übersetzung in herstellerfähige Fachsprache
- die saubere Trennung zwischen Vorauswahl und Herstellerfreigabe
- die Transparenz gegenüber beiden Marktseiten
- das Vertrauen, das daraus entsteht
