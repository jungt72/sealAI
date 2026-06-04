
**Stand:** 2026-05-29  
**Produkt:** sealing | Intelligence / sealingAI  
**Vertikaler Fokus V1:** Radialwellendichtringe / RWDR, Wellendichtungs-Leckage- und Ersatzteilfälle  
**Ziel:** Vollständige, produktionsnahe und Codex-taugliche Architektur-Blaupause für ein professionelles, latenzarmes, mobile-first, cockpit-first, knowledge-aware, sheet-aware und RFQ-fähiges Engineering-Intelligence-System für Dichtungstechnik.  
**Primäres Implementierungsziel:** Codex App / Codex CLI soll dieses Dokument als verbindliche Zielarchitektur auditieren und anschließend patchweise im bestehenden sealingAI-Monorepo umsetzen können.  
**Zentrale Produktregel:** Der Chat führt. Das Cockpit dokumentiert. Das Sheet strukturiert. Knowledge erklärt. Das Pocket Cockpit verdichtet. Der RFQ-Brief übergibt. Das State Gate entscheidet.  
**Wichtigste Umsetzungsvorgabe:** Dieses Blueprint ist keine Big-Bang-Bauanweisung. Codex muss audit-first, evidenzbasiert und in kleinen Patches arbeiten. Bestehende Strukturen sind zu bevorzugen. Keine parallele Architektur erfinden.

---

## 0. Executive Summary

sealing | Intelligence ist kein klassischer Chatbot, kein Produktkonfigurator, kein Katalog, kein Marktplatz, kein automatisches Dichtungsauslegungssystem und keine finale technische Freigabestelle.

sealing | Intelligence ist ein **case-aware Engineering Intelligence Workspace** für Dichtungstechnik.

Das System soll reale Nutzersituationen verstehen, technische Angaben strukturieren, Wissensfragen fachlich beantworten, Schadensbilder vorqualifizieren, Fotos/Skizzen als unsichere Hinweise verwerten, Sheet-/Cockpit-Eingaben auswerten, kritische Lücken sichtbar machen, Hersteller-Rückfragen simulieren und daraus eine herstellerbewertbare RFQ-Anfrage erzeugen.

V1.6 ergänzt V1.5 um den entscheidenden Realitätscheck:

```text
Der P0-Nutzer steht nicht entspannt am Desktop.
Er steht an der Maschine, hat Zeitdruck, macht schlechte Fotos, tippt wenig und braucht schnell einen brauchbaren nächsten Schritt.
```

Deshalb gilt ab V1.6 zusätzlich:

```text
Desktop Cockpit dokumentiert ausführlich.
Mobile Pocket Cockpit verdichtet radikal.
Action Chips ersetzen unnötige Texteingaben.
Kein leerer Spinner.
Jeder längere Schritt zeigt sofort verwertbaren Fortschritt.
Schlechte Fotos führen nicht zu Scheitern, sondern zu Mess-/Foto-Führung.
RFQ wird als herstellerfreundlicher One-Pager erzeugt, nicht als langer KI-Report.
```

Die wichtigste Systemformel lautet:

```text
LLM versteht.
RAG belegt.
Impact-Agenten analysieren.
Jinja2 versioniert und kontrolliert Antworten.
State Gate validiert.
Cockpit dokumentiert.
Pocket Cockpit verdichtet.
Chat führt.
Sheet strukturiert.
RFQ-Brief übergibt.
Human Escalation erkennt Grenzfälle.
Hersteller bewertet final.
Herstellerfeedback verbessert RFQ-Qualität.
```

Die wichtigste UX-Formel lautet:

```text
Case-Turns sind cockpit-first.
Mobile Case-Turns sind pocket-cockpit-first.
Wissensfragen sind chat-first.
Sheet-Eingaben sind state-first.
RFQ-Turns sind brief-first.
Smalltalk ist fast-responder-first.
Uploads sind candidate-first.
Partnerprofile sind trust-first.
```

Die wichtigste Safety-Formel lautet:

```text
sealingAI entscheidet nicht die Dichtung.
sealingAI macht die Dichtungssituation verständlich, strukturiert und herstellerbewertbar.
```

Die wichtigste Implementierungsformel lautet:

```text
Master Blueprint ≠ Big-Bang-Implementation.
Master Blueprint → Read-only Gap Audit → kleiner Patch → Tests → nächster Patch.
```

---

## 1. Authority, Scope und P0-Hardening

Dieses Dokument ist die V1.6-Härtung der V1.5-Blaupause. Es behält die V1.5-Produktarchitektur und Production-Hardening-Contracts bei, ergänzt aber die notwendige Mobile-/Real-World-UX-Schicht für den wichtigsten MVP-Nutzer.

### 1.1 V1.6 ergänzt verbindlich

```text
1. Mobile-first Oily-Hands UX Contract
2. Pocket Cockpit für Smartphone- und Maschinenumgebung
3. Action Chips für schnelle Antworten ohne Tippen
4. No-empty-spinner-Regel für alle längeren Tiers
5. Degraded-useful-output-Regel bei schwacher Vision/OCR/Upload-Qualität
6. Visual Assist als Mess-/Foto-Führung statt Produktidentifikation
7. RFQ One-Pager Contract für herstellerfreundliche Übergabe
8. Critical Open Points Prioritization: kritisch / hilfreich / optional
9. Progressive Disclosure für Cockpit-Details
10. Mobile P0 Journey als Golden Flow
11. Agent Conflict Guardrails gegen unnötige Endlosschleifen und Über-Eskalation
12. State Gate Degradation: Feld-Konflikt statt Case-Blockade
13. Jinja2 Fluency Guard: Templates kontrollieren Struktur, nicht monotone Formulierungen
14. Codex Mobile-UX Patchplan vor visueller Vollintegration
```

### 1.2 Binding Product Rule

```text
Der Chat führt.
Das Cockpit dokumentiert.
Das Pocket Cockpit verdichtet.
Das Sheet strukturiert.
Knowledge erklärt.
Der RFQ-Brief übergibt.
Das State Gate entscheidet.
Jinja2 kontrolliert Output.
RAG belegt, aber schreibt keine Case-Wahrheit.
```

### 1.3 Produktgrenzen

sealingAI darf:

```text
- technische Vorqualifizierung leisten
- Dichtungssituationen strukturieren
- Parameter extrahieren
- Plausibilitäts- und Impact-Analysen liefern
- kritische offene Punkte sichtbar machen
- Nutzer fachlich anleiten
- Wissensfragen dichtungstechnisch erklären
- Review Flags erzeugen
- berechnete Werte als Review-Information anzeigen
- RFQ-Briefe mit offenen Punkten erzeugen
- Hersteller-Rückfragen simulieren
- Anfrageempfänger-/Herstellerprofile vorschlagen, aber nicht technisch final ranken
- auf Mobile mit minimaler Interaktion zu einem brauchbaren nächsten Schritt führen
```

sealingAI darf nicht:

```text
- finale technische Freigabe geben
- finale Materialfreigabe geben
- finale Produktempfehlung als sichere Lösung ausgeben
- garantierte Eignung behaupten
- Compliance-Freigabe behaupten
- ATEX/FDA/WRAS/KTW/DVGW/Food/Pharma freigeben
- sicherheitskritische Auslegung final bewerten
- Herstellerentscheidung ersetzen
- zahlende Partner als technisch beste Lösung ausgeben
- aus unscharfen Fotos Maße, Material oder Artikel final behaupten
```

### 1.4 Produkt-North-Star

```text
Aus unvollständigen, realen Dichtungsinformationen wird eine verständliche, strukturierte, überprüfbare und herstellerbewertbare Dichtungssituation.
```

### 1.5 Mobile-North-Star

```text
Aus „sifft“ + schlechtem Foto wird in weniger als vier Minuten ein brauchbarer nächster Schritt oder ein erster RFQ-Entwurf mit klaren offenen Punkten.
```

---

## 2. Kern-USP der sealing Intelligence

Der Nutzer soll nicht nur eine Anfrage generieren. Er soll seine Dichtungssituation besser verstehen und gleichzeitig schneller zu einer brauchbaren Herstelleranfrage kommen.

### 2.1 V1.6 Produktformel

```text
sealingAI macht aus unklaren Angaben eine verstandene Dichtungssituation,
zeigt die technische Struktur sichtbar im Cockpit,
verdichtet sie mobil im Pocket Cockpit,
führt den Nutzer im Chat wie ein erfahrener Dichtungstechniker,
ermöglicht strukturierte Sheet-Eingaben,
beantwortet Wissensfragen mit Dichtungskontext,
macht Unsicherheit und offene Punkte sichtbar,
und erzeugt daraus eine herstellerbewertbare RFQ-Anfrage.
```

### 2.2 Geschärfter User-USP

```text
Von „die Dichtung sifft“ zu „herstellerbewertbarer RFQ mit offenen Punkten, Review-Hinweisen und verständlicher Erklärung“ — ohne dass der Nutzer Dichtungsexperte sein muss.
```

Produktseiten-Satz:

```text
Beschreibe dein Dichtungsproblem in deinen Worten. sealingAI macht daraus eine verständliche technische Lageeinschätzung und eine Herstelleranfrage mit klaren offenen Punkten.
```

### 2.3 Warum das wertvoll ist

```text
- Nutzer starten oft mit Leckage, Fotos, Altteilen, Skizzen oder Halbwissen.
- Hersteller erhalten häufig schlechte Anfragen ohne Betriebsdaten.
- Reiner Maßersatz ignoriert oft Ausfallursachen.
- Allgemeine KI-Antworten sind zu wenig dichtungsspezifisch.
- Klassische Formulare sind zu starr und erklären nicht, warum etwas gefragt wird.
- Mobile Nutzer an der Maschine brauchen schnelle Action, keine Desktop-Komplexität.
- sealingAI verbindet freie Sprache, strukturierte Eingabe, technische Erklärung, sichtbare State-Dokumentation und RFQ-Übergabe.
```

---

## 2A. V1.6 USP-Schärfung: Killer-Flow vor Vollarchitektur

V1.6 setzt eine harte Produktpriorität: Die Architektur darf breit bleiben, aber der MVP darf nicht breit gebaut werden. Der erste unwiderstehliche User-Nutzen entsteht nicht durch „alle Agenten“, sondern durch einen sehr konkreten Schmerzfall, der schneller, verständlicher und besser gelöst wird als ChatGPT + Google + Herstellerformular.

### 2A.1 P0-Wedge: 4pm-Friday-Broken-Seal Scenario

Der wichtigste V1-Flow ist:

```text
Instandhalter / Techniker hat eine undichte Wellendichtung.
Er hat ein Altteil, Foto, Maße oder nur eine Leckagebeschreibung.
Er weiß nicht alle Parameter.
Er braucht schnell eine brauchbare Herstelleranfrage.
Er nutzt im Zweifel ein Smartphone an der Maschine.
```

P0-V1 heißt nicht:

```text
sealingAI kann alle Dichtungstechnik-Szenarien perfekt.
```

P0-V1 heißt:

```text
sealingAI ist extrem gut bei RWDR-/Wellendichtungs-Leckage- und Ersatzteilfällen.
```

### 2A.2 Interne Intelligenz vs. sichtbares Nutzerergebnis

Nutzer kaufen keine Agenten. Nutzer kaufen ein besseres Ergebnis.

| Ebene | Interne Architektur | Sichtbares User Outcome |
|---|---|---|
| Verstehen | Router, LLM, State Gate | „Das System erkennt meine Situation.“ |
| Prüfen | Impact-Agenten, Devil’s Advocate | „Es weist auf die wirklich kritische Stelle hin.“ |
| Ergänzen | Next Best Question, Sheet, Measurement Guidance, Action Chips | „Ich weiß, was ich als Nächstes prüfen/messen soll.“ |
| Anfrage erzeugen | RFQQualityAgent, RFQ Dispatch Policy, Jinja2 Brief | „Ich habe eine brauchbare Herstelleranfrage.“ |
| Hersteller fragen | Partner Trust Policy, Export, Herstellerfragen | „Ich kann die Anfrage sauber weitergeben.“ |

### 2A.3 V1.6-Prioritätsregel

```text
P0 = RWDR-/Wellendichtungs-Leckage- und Ersatzteil-Killer-Flow, mobile-tauglich.
P1 = case-aware Knowledge, Warum-Fragen, Material-/Medium-/Vergleichsfragen im aktiven Fall.
P2 = Visual Assist als Kandidaten- und Messhilfe, nicht finale Identifikation.
P3 = Sheet-Chat als Produktivitätsmodus für strukturierte Desktop-Nutzer.
P4 = Partnerprofile / Herstellerlisting als transparenter Zusatz, nicht Kernnutzen.
```

### 2A.4 4-Minuten-Nutzen-Kriterium

Nach spätestens vier Minuten muss der Nutzer mindestens eines dieser Ergebnisse haben:

```text
- erkannte Dichtungssituation
- sichtbare Parameter-/Case-Karte im Cockpit oder Pocket Cockpit
- ein kritischer Review-Hinweis
- eine konkrete nächste Prüf-/Messfrage
- eine erste RFQ-Fähigkeit oder klarer Mindestinput
- ein verständlicher Grund, warum ein Mensch/Hersteller direkt prüfen sollte
```

Wenn nach vier Minuten nur ein Formulargefühl entsteht, ist V1 gescheitert.

### 2A.5 North-Star-Metriken

Produktmetriken sind wichtiger als Agentenanzahl.

```text
Time to first structured case
Time to first useful next question
Time to first mobile action chip
Time to RFQ draft
First-pass RFQ completeness
Number of expected manufacturer follow-up questions
Number of open critical fields at RFQ generation
User confirms/corrects extracted fields rate
User returns for second case
RFQ accepted by manufacturer without major clarification
Mobile abandonment before first useful question
```

### 2A.6 One-Killer-Demo als Akzeptanzanker

Die wichtigste Demo bleibt:

```text
User:
RWDR 45x62x8, Getriebe, Öl, 1500 rpm, staubig, undicht.

sealingAI muss:
- Parameter übernehmen
- Umfangsgeschwindigkeit berechnen
- Leckage-/Wellenlauffläche als kritischen Punkt erkennen
- kurz erklären, warum
- nur eine nächste Frage stellen
- Cockpit sauber aktualisieren
- später RFQ mit offenen Punkten erzeugen
```

Die wichtigste Mobile-Demo ist:

```text
User:
Foto + „sifft“

sealingAI muss:
- sofort als Leckage-/Wellendichtungsfall triagieren
- nicht leer warten
- Foto als unsicheren Kandidaten behandeln
- eine einfache Scope-Frage stellen
- Action Chips anbieten
- bei schlechtem Foto konkrete Mess-/Foto-Führung geben
```

---

## 3. UX-Grundregeln

### 3.1 Der Chat führt

Der Chat ist nicht der technische Zettel. Der Chat soll:

```text
- kurz führen
- die wichtigste technische Priorität nennen
- eine konkrete nächste Frage stellen
- Wissensfragen erklären
- bei Konflikten sauber nachfragen
- bei RFQ-Erzeugung bestätigen und Grenzen nennen
- bei Freigabewünschen klar abgrenzen
- auf Mobile mit Action Chips und kurzen Schritten arbeiten
```

Der Chat soll nicht:

```text
- den vollständigen Case wiederholen
- alle Parameter aufzählen, die im Cockpit sichtbar sind
- nach jedem Turn einen Haftungsblock anhängen
- künstliche Meta-Phrasen verwenden
- wie ein Formular klingen
- finale Empfehlungen formulieren
- lange Desktop-Erklärungen auf Mobile erzwingen
```

### 3.2 Das Desktop-Cockpit dokumentiert

Das Cockpit ist der sichtbare technische Zettel. Es zeigt:

```text
- bekannte Felder
- Herkunft/Status
- offene Punkte
- aktive Frage
- Review Flags
- berechnete Werte
- Case Understanding
- RFQ-Status
- Knowledge Notes
- Konflikte
- Revisionen / Änderungshistorie
```

### 3.3 Das Pocket Cockpit verdichtet

Das Pocket Cockpit ist die mobile Kurzform des Cockpits. Es zeigt nicht alles, sondern nur:

```text
1. Erkannt
2. Kritisch
3. Nächster Schritt
4. RFQ-Status
```

Mobile Standard-Layout:

```text
Chat/Kamera oben
Pocket Cockpit Karte darunter
Action Chips unter der aktiven Frage
Details nur per Aufklappen
```

Pflichtregel:

```text
Auf Mobile darf keine vollständige Desktop-Cockpit-Komplexität sichtbar sein, bevor der Nutzer einen ersten nützlichen Schritt erhalten hat.
```

### 3.4 Das Sheet strukturiert

Das Sheet oder strukturierte Parameter-Cockpit ist die direkte Eingabefläche für technische Felder. Es erlaubt:

```text
- Feldbearbeitung
- Bulk-Eingabe
- Tabellen-/Formulareingabe
- Validierung
- Einheiten-Normalisierung
- Konfliktauflösung
- direkte RFQ-Vorbereitung
```

Der Chat kommentiert Sheet-Änderungen nur, wenn sie fachlich relevant sind.

### 3.5 Knowledge erklärt

Wissensfragen sind chat-first. Das heißt:

```text
- Der Chat darf ausführlicher erklären.
- RAG darf genutzt werden.
- Der aktive Case wird berücksichtigt, falls die Frage case-bezogen ist.
- Der Case wird nicht verändert, außer der Nutzer liefert neue technische Fakten.
```

### 3.6 Der RFQ-Brief übergibt

Der RFQ-Brief ist das Herstellerdokument. Er ist kein KI-Report, sondern ein klarer One-Pager beziehungsweise klar strukturierter Brief.

Er enthält:

```text
- Anfrageziel
- bestätigte Angaben
- offene Punkte priorisiert nach kritisch / hilfreich / optional
- berechnete Werte
- Review Flags
- Herstellerfragen
- Herkunft/Status
- Fotos/Anhänge
- klare Grenze: keine finale Freigabe durch sealingAI
```

### 3.7 Das State Gate entscheidet

Weder Chat noch LLM noch Agent entscheiden über Wahrheit. Das State Gate:

```text
- validiert Schema
- normalisiert Einheiten
- setzt Herkunft/Status
- erkennt Konflikte
- trennt Fakt, Annahme, Kandidat, Hypothese, RAG-Note und Berechnung
- entscheidet, was in Case State, Cockpit und RFQ darf
- blockiert nicht den gesamten Case, wenn nur ein Feld widersprüchlich ist
```

### 3.8 Degraded Useful Output

Wenn ein Modul unsicher ist, darf es nicht einfach scheitern. Es muss einen nützlichen Ersatz liefern.

Beispiele:

```text
Vision unsicher → Mess-/Foto-Anleitung
OCR unsicher → Beschriftung direkt fotografieren lassen
RAG unzureichend → Aussagegrenze + Herstellerprüfung
Konflikt im Feld → Konfliktfrage, Rest-Case bleibt nutzbar
RFQ zu dünn → Mindestinput nennen, nicht langen Brief erzeugen
```

---

## 4. Mobile-First Oily-Hands UX Contract

### 4.1 Zielgruppe

P0 Mobile User:

```text
- Instandhalter / Techniker / Einkäufer an Maschine oder Werkbank
- Zeitdruck
- Smartphone
- schlechte Beleuchtung
- ölige Hände
- unvollständige Informationen
- wenig Geduld für Formulare
```

### 4.2 Mobile-Prinzipien

```text
1. Erst triagieren, dann detaillieren.
2. Erst eine Handlung, dann ein Formular.
3. Action Chips vor Freitext, wenn Antworttypen bekannt sind.
4. Pocket Cockpit statt Desktop-Cockpit.
5. Foto hilft bei Führung, nicht bei finaler Identifikation.
6. Keine leeren Wartezeiten.
7. Offene Punkte sind erlaubt.
8. Nutzer darf jederzeit „mehr weiß ich nicht“ sagen.
```

### 4.3 Pocket Cockpit Contract

```json
{
  "pocket_cockpit": {
    "recognized": [
      {"label": "Fall", "value": "Leckage an Welle?", "status": "candidate"},
      {"label": "Dichtung", "value": "RWDR möglich", "status": "candidate"}
    ],
    "critical": [
      {"label": "Wellenlauffläche prüfen", "severity": "high"}
    ],
    "next_step": {
      "question": "Dreht sich die Welle im Betrieb?",
      "action_chips": ["Ja", "Nein", "Weiß ich nicht", "Foto senden"]
    },
    "rfq_status": "DRAFT"
  }
}
```

### 4.4 Mobile Layout

```text
Top:
- Kamera / Upload Button
- Chat Input

Main:
- letzte Assistant Guidance
- Action Chips
- Pocket Cockpit Card

Expandable:
- Parameter
- Offene Punkte
- Review Flags
- Berechnungen
- RFQ Preview
```

### 4.5 Action Chips

Action Chips werden immer angeboten, wenn die erwartete Antwort begrenzt ist.

Beispiele:

```text
Dreht sich die Welle?
[Ja] [Nein] [Weiß ich nicht] [Foto senden]

Lauffläche?
[glatt] [Rille sichtbar] [Rost] [weiß ich nicht] [Foto]

Maße bekannt?
[45x62x8] [Beschriftung unlesbar] [Ich messe jetzt] [weiß ich nicht]

Temperatur?
[<60 °C] [60–100 °C] [>100 °C] [weiß ich nicht]
```

### 4.6 No-empty-spinner-Regel

Bei Tier 3/4 darf der Nutzer nicht auf einen leeren Spinner schauen.

Pflichtverhalten:

```text
0–300 ms: Sofortreaktion anzeigen
<1 s: erster erkannter Kontext oder Triageschritt
Während längerer Analyse: Status und/oder erste Frage streamen
Nach Analyse: Cockpit/Pocket Cockpit final aktualisieren
```

Beispiel:

```text
Ich prüfe das als möglichen Leckage-/Wellendichtungsfall.
```

Pocket Cockpit:

```text
Fall erkannt: Leckage an Welle?
Status: Eingrenzung läuft
Nächster Schritt folgt
```

### 4.7 Progressive Disclosure

Mobile zeigt Details erst, wenn:

```text
- Nutzer explizit öffnet
- RFQ erzeugt wird
- Konflikt gelöst werden muss
- kritisches Review Flag erklärt wird
```

Standard:

```text
Kurzkarte sichtbar.
Details eingeklappt.
```

### 4.8 Mobile Golden Flow: Foto + „sifft“

User:

```text
[Foto hochgeladen]
sifft
```

Expected immediate response:

```text
Ich prüfe das als Leckagefall an einer möglichen Wellendichtung.

Dreht sich die Welle im Betrieb?
```

Action Chips:

```text
[Ja] [Nein] [Weiß ich nicht] [Foto vom Einbauort]
```

Expected Pocket Cockpit:

```text
Erkannt: Leckage / Dichtstelle unklar
Kritisch: Dichtungstyp und Wellenbewegung klären
Nächster Schritt: Dreht sich die Welle?
RFQ: noch DRAFT
```

### 4.9 Mobile Golden Flow: schlechtes Foto

User:

```text
[unscharfes Foto Altteil]
```

Expected response:

```text
Die Beschriftung kann ich auf dem Foto nicht sicher lesen.

Für die Anfrage hilft jetzt am meisten: Miss Innendurchmesser, Außendurchmesser und Breite — oder fotografiere die Stirnseite mit Beschriftung direkt von oben.
```

Action Chips:

```text
[So messe ich d1/D/b] [Neues Foto machen] [Ich weiß die Maße nicht]
```

Wichtig:

```text
Keine Frustrationsantwort „nicht erkannt“.
Immer nächster nutzbarer Schritt.
```

---

## 5. Vollständige Szenario-Matrix

Diese Matrix ist für Routing, Tests und Codex-Implementierung verbindlich.

| Szenario | Beispiel | Mode | Tier | Chat | Cockpit | Pocket Cockpit | State Mutation | RAG |
|---|---|---:|---:|---|---|---|---|---|
| Smalltalk | „Hallo“ | `smalltalk` | 0/1 | kurz freundlich | nein | nein | nein | nein |
| UI-Hilfe | „Wie funktioniert das?“ | `ui_help` | 1/2 | kurz erklärend | optional | optional | nein | nein |
| Mobile Foto + kurz | Foto + „sifft“ | `mobile_leakage_triage` | 1/2 | sofort + Frage | ja | ja | candidate | nein |
| Schlechtes Foto | unscharfer RWDR | `visual_low_confidence_guidance` | 2/4 | Mess-/Fotohilfe | candidate | ja | visual_candidate | nein |
| Pending Slot | „jo ca 3000“ | `pending_slot_answer` | 0 | sehr kurz | ja | optional | ja | nein |
| Unscharfe Slot-Antwort | „so um die drei tausend“ | `pending_slot_answer_micro` | 1 | kurz | ja | optional | ja/pending | nein |
| Strukturfeld geändert | Sheet-Feld Drehzahl = 3000 | `sheet_field_edit` | 0 | nur falls relevant | ja | nein | ja | nein |
| Mehrere Sheet-Felder geändert | Maße, Medium, rpm | `sheet_bulk_input` | 0/1 | kurzer Hinweis | ja | optional | ja | nein |
| Sheet-Konflikt | Temperatur 90 und 190 °C | `sheet_conflict_resolution` | 1/2 | klären | ja | optional | pending/conflict | nein |
| Neuer Case frei im Chat | RWDR 45x62x8… | `case_building` | 3 | kurz führend | ja | ja | ja | optional |
| Leckagefall | „Dichtung sifft“ | `leakage_diagnosis` | 2/3 | nächste Prüfhandlung | ja | ja | ja/pending | optional |
| Unbekannte Dichtung | „Öl an Welle“ | `unknown_seal_scoping` | 2/3 | Scope-Frage | ja | ja | Kandidat | nein |
| Foto Altteil | Bildupload | `visual_evidence` | 4 | Grenzen + Foto/Messfragen | ja | ja | visual_candidate | optional |
| Skizze | Handskizze mit d/D/b | `sketch_to_case` | 4 | Bestätigungsfrage | ja | optional | sketch_candidate | nein |
| Messanleitung | „Wo messe ich d1?“ | `measurement_guidance` | 2 | erklärend | optional | ja | nein | optional |
| Wissensfrage allgemein | „Was ist FFKM?“ | `knowledge_general` | 2 | ausführlicher | nein/Note | nein | nein | ja |
| Wissensfrage case-bezogen | „FKM in meinem Fall?“ | `knowledge_case_aware` | 2 | erklärend | ReviewFlag | optional | nein | ja/optional |
| Wissensfrage mit neuen Fakten | „Wir verwenden FKM, 100 °C“ | `knowledge_case_mutating` | 2/3 | kurz + Frage | ja | optional | ja | optional |
| Vergleich allgemein | „NBR oder FKM?“ | `technical_comparison_general` | 2 | erklärend | nein | nein | nein | ja |
| Vergleich case-bezogen | „NBR oder FKM für meinen Fall?“ | `technical_comparison_case_aware` | 2/3 | erklärend + Frage | ReviewFlag | optional | nein/optional | ja |
| Warum-Frage | „Warum fragst du nach der Welle?“ | `why_question_active_case` | 2 | Begründung | keine/leicht | optional | nein | optional |
| Norm/Wissen | „Was bedeutet WRAS?“ | `norm_documentation_knowledge` | 2 | erklärend + Grenze | optional Flag | nein | nein | ja |
| Dokument/PDF | Datenblatt hochgeladen | `document_analysis` | 4 | Zusammenfassung | ja | optional | candidate/extracted | ja/Doc |
| Herstellerfragen | „Was wird Hersteller fragen?“ | `manufacturer_question_simulation` | 2/3 | Liste | ja | optional | nein | optional |
| Herstellerprofile | „Wen kann ich anfragen?“ | `partner_profile_suggestion` | 2/3 | transparent | ja | nein | nein | optional |
| RFQ erzeugen | „Mach Anfrage“ | `rfq_brief_generation` | 4 | brief-first | ja | ja | snapshot | optional |
| RFQ ohne Mindestkern | „Mach Anfrage, Dichtung undicht“ | `rfq_draft_insufficient` | 1/2 | erklären | ja | ja | nein | nein |
| Finale Freigabe verlangt | „Was passt garantiert?“ | `blocked_boundary` | 1 | klare Grenze | nein | nein | nein | nein |
| Human Escalation | Widersprüche, hohe Unsicherheit, kritische Kombination | `complex_review_required` | 1/2 | klare Eskalation | ReviewFlag | ja | nein/pending | optional |
| Out of Scope/Safety | Aerospace, ATEX final | `out_of_scope` | 1 | Grenze + Alternative | Flag | optional | nein | optional |

---

## 6. Runtime-Tiers und Latency Budgets

Nicht jeder Turn darf durch den vollständigen Graph laufen. Die Tiers sind Produkt-, Kosten- und UX-Verträge.

| Tier | Zweck | LLM | RAG | Ziel-Latenz Backend | UX-Regel | Trace-Pflicht |
|---:|---|---|---|---:|---|---|
| 0 | klare Slot-/Sheet-/Smalltalk-Pfade | nein | nein | `<300 ms` | sofort | ja |
| 1 | Micro-Normalisierung kurzer Sprache | kleines LLM | nein | `<1.5 s` | kurze Antwort | ja |
| 2 | gezielte Wissens-/Warum-/Vergleichsfragen | ja | optional | `<3 s` | bei Mobile kurze Fortschrittsanzeige | ja |
| 3 | Agent Bundle für konkrete Cases | ja | optional | `<5–8 s` | kein leerer Spinner, erstes Signal <1 s | ja |
| 4 | Full Graph, Upload, RFQ, PDF | ja | optional/ja | länger erlaubt | Streaming/Status/Pocket Progress | ja |

### 6.1 Trace-Felder

Jeder Turn muss mindestens enthalten:

```json
{
  "turn_id": "...",
  "route": "case_building",
  "tier": 3,
  "latency_ms": 1420,
  "first_progress_ms": 280,
  "llm_used": true,
  "rag_used": false,
  "graph_used": false,
  "agents_run": ["failure_mode_impact"],
  "state_mutation": "proposed_delta_applied_by_state_gate",
  "template_id": "short_reply.v1",
  "tenant_id_present": true,
  "mobile_surface": true,
  "empty_spinner_violated": false
}
```

### 6.2 Performance-Regeln

```text
- Tier 0 darf keinen RAG-Aufruf und keinen Full Graph auslösen.
- Tier 1 darf nur Micro-LLM mit kleinem JSON-Schema nutzen.
- Tier 2 darf RAG nutzen, aber nur scoped retrieval.
- Tier 3 nutzt nur dirty modules, nicht alle Agenten.
- Tier 4 muss bei längeren Upload-/RFQ-Operationen Status streamen.
- Mobile Tier 3/4 muss vor vollständigem Ergebnis einen ersten nützlichen Zwischenstand liefern.
```

---

## 7. Mode Contracts

### 7.1 `smalltalk`

Smalltalk ist ein Fast-Responder-Mode. Er darf keinen Case eröffnen, keine Daten persistieren und keinen Full Graph starten.

Beispiele:

```text
Hallo
Kannst du mir helfen?
Was kannst du?
Danke
```

Beispielantwort:

```text
Hallo! Ja, ich kann dir bei Dichtungsfällen helfen — Ersatzteil, Leckage, Materialfrage, Foto, Skizze oder Herstelleranfrage.

Worum geht es bei dir?
```

Trace:

```json
{
  "route": "smalltalk",
  "tier": 0,
  "llm_used": false,
  "rag_used": false,
  "state_mutation": "none",
  "cockpit_patch": "none"
}
```

### 7.2 `ui_help`

Für Fragen zur Bedienung:

```text
Wie funktioniert das?
Was bedeuten die Chips?
Wo sehe ich offene Punkte?
Was ist der RFQ-Status?
```

Antwort darf kurz erklären, aber keinen Case ändern.

### 7.3 `mobile_leakage_triage`

Für Mobile-Einstiege wie:

```text
Foto + sifft
sifft an Welle
Öl läuft raus
```

Regel:

```text
- sofort triagieren
- keine Desktop-Zusammenfassung
- Pocket Cockpit erzeugen
- Action Chips anbieten
- nächste Frage muss scope-reduzierend sein
```

Beispiel:

```text
Ich prüfe das als möglichen Leckagefall an einer Wellendichtung.

Dreht sich die Welle im Betrieb?
```

Action Chips:

```text
[Ja] [Nein] [Weiß ich nicht] [Foto vom Einbauort]
```

### 7.4 `visual_low_confidence_guidance`

Wenn Vision/OCR unsicher ist.

Regel:

```text
Unsicherheit nicht als Scheitern formulieren.
Immer konkrete nächste Mess-/Foto-Handlung liefern.
```

Beispiel:

```text
Die Beschriftung kann ich auf dem Foto nicht sicher lesen.

Für die Anfrage hilft jetzt am meisten: Miss Innendurchmesser, Außendurchmesser und Breite — oder fotografiere die Stirnseite mit Beschriftung direkt von oben.
```

### 7.5 `pending_slot_answer`

Wenn eine aktive Frage existiert, wird die nächste Nutzereingabe zuerst als mögliche Antwort darauf geprüft.

Beispiel:

```text
Assistant: Welche Drehzahl liegt ungefähr an?
User: jo ca 3000
```

Ergebnis:

```text
speed_rpm = 3000
approximate = true
origin = user_direct_answer
confirmation_status = confirmed
```

Chat:

```text
Okay, ca. 3000 U/min ist übernommen.

Welche Temperatur liegt ungefähr an der Dichtstelle an?
```

### 7.6 `pending_slot_answer_micro`

Für kurze, unsaubere, aber wahrscheinlich antwortbezogene Eingaben:

```text
glaub 2 bar, bin mir aber nicht sicher
beim loslaufen eher trocken hart danach warm zäh
```

Regeln:

```text
- Micro-LLM bekommt nur pending_question, field schema, last assistant question und user answer.
- Output ist JSON-only.
- Keine freie Antwort.
- Keine RAG-Nutzung.
- Keine Materialempfehlung.
- State Gate entscheidet, ob confirmed oder pending_confirmation.
```

### 7.7 `case_building`

Für freie technische Eingaben mit mehreren Fakten.

Regel:

```text
Chat wiederholt nicht den gesamten Case.
Cockpit zeigt alle erkannten Daten.
Chat nennt nur den wichtigsten technischen Hebel und stellt eine klare nächste Frage.
```

### 7.8 `leakage_diagnosis`

Leckage ist ein zentraler Einstieg.

Typische Inputs:

```text
Die Dichtung sifft.
Nach kurzer Zeit wieder undicht.
Beim Anlauf quietscht es.
Die Welle hat eine Rille.
Nur warm tritt Öl aus.
Nach Reinigung leckt es.
```

Systemverhalten:

```text
FailureModeImpactAgent
ShaftCounterfaceImpactAgent
MeasurementGuidanceAgent optional
VisualEvidenceAgent optional
Next Best Question
```

Ziel:

```text
keine finale Diagnose,
sondern Schadensbild strukturieren,
mögliche Ursachenpfade sichtbar machen,
Fotos/Messungen anfordern,
Review-Fragen erzeugen.
```

### 7.9 `unknown_seal_scoping`

Für Nutzer ohne Dichtungswissen.

Input:

```text
Da tritt Öl an einer Welle aus.
```

Antwort:

```text
Das klingt nach einem möglichen Wellendichtungsfall. Zuerst müssen wir klären, ob es wirklich eine rotierende Welle ist.

Dreht sich die Welle im Betrieb?
```

### 7.10 `visual_evidence`

Für Fotos, Screenshots, Verpackungen, Typenschilder, Altteilbilder.

Erlaubt:

```text
- sichtbare Hinweise beschreiben
- Beschriftungskandidaten lesen
- Dichtungstyp-Kandidaten erkennen
- Schäden sichtbar beschreiben
- Foto-/Messcheckliste erzeugen
```

Nicht erlaubt:

```text
- Material aus Foto final bestimmen
- exakte Maße ohne Maßstab behaupten
- Hersteller/Artikel final identifizieren ohne klare Markierung
- finale Schadensursache behaupten
- finale Produktempfehlung geben
```

State:

```text
visual_candidate
requires_confirmation = true
```

### 7.11 `sketch_to_case`

Für Handskizzen oder technische Skizzen.

Extrahierbare Kandidaten:

```text
d1
D
b
Mediumseite
Umgebungsseite
Drehrichtung
Einbauraum
```

Alle Werte bleiben bestätigungspflichtig.

### 7.12 `measurement_guidance`

Für Mess- und Foto-Anleitung.

Beispiele:

```text
Was ist d1?
Wo messe ich D?
Wie messe ich b?
Wie fotografiere ich die Wellenlauffläche?
Wie erkenne ich eine Staublippe?
```

Antwort darf erklärend sein, aber muss praktisch bleiben.

### 7.13 `rfq_brief_generation`

RFQ darf jederzeit ausgelöst werden, wenn Minimum-Informationen vorhanden sind. Fehlende Punkte blockieren nicht automatisch, sondern werden sichtbar markiert.

### 7.14 `rfq_draft_insufficient`

Wenn der Nutzer „Mach Anfrage“ sagt, aber nicht einmal ein minimaler RFQ-Kern vorhanden ist.

Beispiel:

```text
Dichtung undicht. Mach Anfrage.
```

Antwort:

```text
Dafür ist der Brief noch zu dünn.

Mindestens brauche ich einen Anhaltspunkt zur Dichtung oder Einbausituation: Foto, Maße, Maschine/Anwendung oder wo genau das Medium austritt. Sonst kann ein Hersteller kaum sinnvoll vorbewerten.

Kannst du ein Foto der Dichtstelle oder des Altteils hochladen?
```

State:

```text
readiness = DRAFT
can_generate_brief = false
```

### 7.15 `complex_review_required`

Human Escalation ist keine Niederlage, sondern professionelle Grenze.

Trigger:

```text
- sicherheitskritische Kombination
- mehrere widersprüchliche liability-bearing fields
- Norm-/Compliance-Freigabe verlangt
- unklare Bildlage + hoher Risiko-Impact
- Druck/Geschwindigkeit/Medium kritisch zusammen
- User will trotz Warnsignalen finale Auslegung
```

Nicht triggern bei:

```text
- normale fehlende Temperatur
- fehlende Drehzahl
- Material unbekannt
- Wellenzustand unbekannt
- schlechtes Foto ohne Hochrisikokontext
```

Antwort:

```text
Der Fall ist für eine rein digitale Vorqualifizierung zu unsicher.

Ich kann die bekannten Daten trotzdem in einen Review-Brief bringen, aber die Bewertung sollte direkt durch Hersteller oder Fachstelle erfolgen.
```

### 7.16 `blocked_boundary`

Wenn der Nutzer finale Freigabe, Garantie oder Compliance-Freigabe verlangt.

Antwort:

```text
Das kann ich nicht seriös als Garantie freigeben.

Ich kann den Fall aber so vorbereiten, dass ein Hersteller ihn sauber bewerten kann: bekannte Daten, offene Punkte, Review-Hinweise und konkrete Rückfragen.
```

---

## 8. Knowledge Question Contract

Wissensfragen sind **chat-first**, nicht cockpit-first.

Der Chat darf bei expliziten Wissensfragen ausführlicher antworten, weil der Nutzer in diesem Moment fachliche Aufklärung erwartet. Trotzdem muss die Antwort dichtungstechnisch relevant, fallbezogen und grenzbewusst bleiben.

### 8.1 Knowledge-Modi

```text
knowledge_general
knowledge_case_aware
knowledge_case_mutating
technical_comparison_general
technical_comparison_case_aware
norm_documentation_knowledge
why_question_active_case
measurement_guidance
```

### 8.2 State-Mutation-Regel

```text
Wissensfragen verändern den Case standardmäßig nicht.
State-Mutation ist nur erlaubt, wenn der Nutzer neue technische Fakten liefert oder eine Angabe ausdrücklich bestätigt.
```

### 8.3 RAG-Regel

RAG wird genutzt bei:

```text
- Materialwissen
- Medienwissen
- Normen/Dokumentation
- technischen Vergleichen
- Datenblatt-/PDF-Fragen
- tiefer fachlicher Erklärung
```

RAG wird nicht genutzt bei:

```text
- reiner Slot-Antwort
- einfachem Case-Update
- einfacher Berechnung
- Smalltalk
- UI-Fast-Hilfe
```

### 8.4 `knowledge_general`

Beispiel:

```text
Was ist FFKM?
```

Erwartung:

```text
- route knowledge_general
- State Mutation none
- CockpitPatch none oder KnowledgeNote
- Chat erklärt Fachbegriff dichtungstechnisch
- keine finale Empfehlung
```

Beispielantwort:

```text
FFKM ist ein perfluorierter Elastomerwerkstoff für sehr anspruchsvolle Medien- und Temperaturbereiche.

Für Dichtungen ist FFKM vor allem dann interessant, wenn normale Elastomere chemisch oder thermisch an Grenzen kommen. Praktisch wichtig sind aber auch Kosten, Verfügbarkeit, Compound-Unterschiede und die konkrete Medien-/Temperaturkombination.

Kurz gesagt: FFKM ist kein „besseres FKM für alles“, sondern ein Spezialwerkstoff für harte Randbedingungen.
```

### 8.5 `knowledge_case_aware`

Beispiel:

```text
Was bedeutet FKM in meinem Fall?
```

Erwartung:

```text
- aktiver Case wird berücksichtigt
- keine automatische Materialübernahme
- optional ReviewFlag
- keine Freigabe
```

Beispiel:

```text
In deinem Getriebeöl-Fall wäre FKM vor allem wegen Öl, Temperaturreserve und Alterungsbeständigkeit ein sinnvoller Prüfpunkt.

Entscheidend ist aber nicht nur „Öl = FKM“, sondern die genaue Ölart, Additive, Temperatur an der Dichtlippe, Drehzahl, Wellenzustand und Außenumgebung.

Ich würde FKM im Herstellerbrief als zu prüfende Werkstoffrichtung aufnehmen, nicht als freigegebene Auswahl.
```

### 8.6 `knowledge_case_mutating`

Beispiel:

```text
Wir verwenden FKM. Öltemperatur liegt bei 100 °C.
```

Erwartung:

```text
- neue Fakten erkannt
- Proposed Case Delta
- State Gate
- CockpitPatch
- nächste Frage zur Temperaturqualität
```

Antwort:

```text
Okay, FKM und ca. 100 °C nehme ich als Angabe auf.

Bei 100 °C wird wichtig, ob das Dauerbetrieb, Spitzenwert oder direkt an der Dichtstelle gemessen ist.

Ist das die Öltemperatur im Betrieb oder die Temperatur an der Dichtstelle?
```

### 8.7 `technical_comparison_general`

Beispiel:

```text
Was ist besser, NBR oder FKM?
```

Antwortprinzip:

```text
- nicht „besser“, sondern Bewertungsachsen erklären
- Medium, Temperatur, Alterung, Reibung, Kosten, Compound, Verfügbarkeit
- keine Case-Mutation
```

### 8.8 `technical_comparison_case_aware`

Beispiel:

```text
NBR oder FKM für meinen Getriebefall?
```

Antwortprinzip:

```text
- aktiven Case nutzen
- fehlende Entscheidungsparameter nennen
- ReviewFlag erzeugen
- keine finale Auswahl
```

### 8.9 `norm_documentation_knowledge`

Beispiel:

```text
Was bedeutet WRAS bei einem RWDR?
```

Antwortprinzip:

```text
- RAG nutzen
- wasserberührte Komponenten trennen
- konkreten Compound/Nachweis betonen
- keine Compliance-Freigabe
- nach Anwendungskontext fragen
```

### 8.10 `why_question_active_case`

Beispiel:

```text
Warum fragst du nach der Welle? Ich will doch nur den Ring ersetzen.
```

Antwort:

```text
Weil der neue Ring auf genau dieser Stelle läuft.

Wenn die Welle dort eingelaufen, rostig oder riefig ist, dichtet auch ein neuer RWDR oft nicht lange sauber. Deshalb ist die Lauffläche bei einem Leckagefall wichtiger als sie auf den ersten Blick wirkt.

Ist die Stelle glatt, oder siehst du eine Spur/Rille?
```

State bleibt unverändert.

---

## 9. Sheet-Chat Contract

Sheet-Chat ist ein eigener Interaktionsmodus für strukturierte Eingaben im Cockpit, technische Felder, Tabellen oder Formulare.

### 9.1 Grundsatz

```text
Sheet ist strukturierte Eingabe.
Cockpit ist technischer Zustand.
Chat ist fachliche Führung zur nächsten sinnvollen Klärung.
```

### 9.2 Warum Sheet-Chat ein eigener Modus ist

Freier Chat und Sheet-Eingabe haben unterschiedliche UX:

```text
Freier Chat:
Der Nutzer beschreibt.
System extrahiert.
Cockpit dokumentiert.
Chat führt weiter.

Sheet:
Der Nutzer trägt strukturiert ein.
System validiert.
Cockpit aktualisiert.
Chat kommentiert nur fachlich relevante Konsequenzen.
```

### 9.3 Sheet-Modi

```text
sheet_chat
sheet_field_edit
sheet_bulk_input
sheet_validation_question
sheet_explanation
sheet_conflict_resolution
sheet_to_rfq
sheet_import
sheet_clear_or_reset
```

### 9.4 Routing bei Feldänderung

```text
field_change_event
→ identify field
→ validate schema
→ normalize unit
→ detect confidence/origin
→ State Gate
→ Dirty Module Scheduler
→ Evaluation Engine
→ CockpitPatch
→ optional ChatReply
```

### 9.5 Wann Chat antworten soll

Der Chat antwortet bei Sheet-Änderungen nur, wenn:

```text
- die Änderung technisch kritisch ist
- eine relevante Berechnung entsteht
- ein Konflikt erkannt wird
- eine nächste Frage sinnvoll ist
- RFQ-Status sich relevant ändert
- ein Feld unsicher/ungültig ist
- die Änderung einen Review Flag erzeugt
```

### 9.6 Wann Chat schweigen darf

Kein Chat-Kommentar ist nötig, wenn:

```text
- ein unkritisches Feld sauber übernommen wurde
- keine Folgefrage entsteht
- keine Berechnung/kein Review Flag entsteht
- die Änderung nur UI-/Notizcharakter hat
```

Das Cockpit aktualisiert sich trotzdem.

### 9.7 Sheet Event Schema

```json
{
  "event_type": "sheet_field_edit",
  "case_id": "...",
  "field": "temperature_operating_c",
  "value": 90,
  "unit": "°C",
  "source": "cockpit_sheet",
  "client_event_id": "uuid-for-idempotency",
  "case_revision_seen": 7
}
```

### 9.8 Beispiel: einzelnes Feld

Sheet Event:

```json
{
  "event_type": "sheet_field_edit",
  "field": "temperature_operating_c",
  "value": 90,
  "unit": "°C"
}
```

Chat:

```text
90 °C ist übernommen.

Für die Werkstoffprüfung wäre noch wichtig, ob das Dauerbetrieb oder ein kurzzeitiger Spitzenwert ist.
```

Cockpit:

```text
Temperatur: 90 °C
Status: übernommen
Open Point: Dauerbetrieb oder Spitze?
```

### 9.9 Beispiel: Bulk Input

Sheet Event:

```json
{
  "event_type": "sheet_bulk_input",
  "fields": {
    "speed_rpm": 3000,
    "temperature_operating_c": 90,
    "medium_internal": "Öl"
  }
}
```

Chat:

```text
Die Betriebsdaten sind übernommen.

Bei 45 mm Welle und 3000 U/min liegt die Umfangsgeschwindigkeit bei rund 7,1 m/s. Für den Leckagefall fehlt jetzt vor allem die Lauffläche.

Ist die Welle an der Dichtlippenstelle glatt, oder sieht man eine Rille?
```

### 9.10 Beispiel: Konflikt

Vorhandener State:

```text
Temperatur: 90 °C
```

Sheet-Änderung:

```text
Temperatur: 190 °C
```

Chat:

```text
Die Temperatur widerspricht der bisherigen Angabe von 90 °C.

Soll ich 190 °C als neuen Wert übernehmen, oder ist das ein Spitzenwert zusätzlich zu 90 °C Betrieb?
```

State:

```text
field temperature = conflicting
pending_question = temperature_conflict_resolution
```

### 9.11 Sheet-to-RFQ

Wenn der Nutzer im Sheet viele Felder gepflegt hat und dann RFQ erzeugt:

```text
Sheet State
→ RFQQualityAgent
→ Readiness Status
→ Open Points
→ Brief Snapshot
→ User Acknowledgement
```

Chat:

```text
Ja, der Brief kann aus den eingetragenen Daten erzeugt werden.

Ich markiere Druckdifferenz und Zustand der Wellenlauffläche noch als offen. Der Hersteller sieht damit klar, wo Rückfragen nötig sein können.
```

---

## 10. Jinja2 Template Contract

Jinja2 ist kein optionaler Prompt-Text. Jinja2 ist ein **versionierter Antwort- und Reasoning-Vertrag**.

### 10.1 Warum Jinja2 verbindlich ist

Jinja2 wird eingesetzt, um:

```text
- konsistente Antworten zu erzeugen
- Prompt-Drift zu reduzieren
- Antwortlänge und Stil je Mode zu kontrollieren
- Safety-Grenzen wiederverwendbar zu machen
- Output-Formate testbar zu machen
- Latenz zu senken, weil Kontext und Template klar getrennt sind
- Codex eine konkrete Implementierungsoberfläche zu geben
```

### 10.2 Jinja2 Fluency Guard

Jinja2 darf das System nicht wie ein starres Formular klingen lassen.

Regel:

```text
Jinja2 kontrolliert Struktur, Grenzen und Output-Verträge.
Jinja2 erzwingt nicht monotone Wort-für-Wort-Formulierungen.
```

Erlaubt:

```text
- mehrere opening variants je Template
- natürliche Kurzvarianten
- mode-spezifische Tonalität
- regionale deutsche Industrie-Sprache ohne Floskeln
```

Nicht erlaubt:

```text
- vollständige Case-Spiegelung im Chat
- mehr als eine Hauptfrage im normalen Case-Turn
- normale Haftungsgrenze in jedem Turn
- finale Freigabe-/Empfehlungssprache
```

### 10.3 Vorgeschlagene Pfade

Codex muss zuerst prüfen, ob bestehende Prompt-/Template-Pfade existieren. Falls nein, diese Struktur bevorzugen:

```text
backend/app/agent/templates/
  chat/
    senior_engineer_short.j2
    smalltalk_fast.j2
    ui_help.j2
    mobile_triage.j2
    visual_low_confidence_guidance.j2
    sheet_comment.j2
    conflict_resolution.j2
    blocked_boundary.j2
  knowledge/
    knowledge_explainer.j2
    case_aware_knowledge.j2
    technical_comparison.j2
    norm_documentation_knowledge.j2
    measurement_guide.j2
  agents/
    impact_agent_json.j2
    micro_slot_extraction_json.j2
    visual_evidence_json.j2
    sketch_to_case_json.j2
  rfq/
    rfq_one_pager.j2
    rfq_brief.j2
    manufacturer_question_simulation.j2
    evidence_summary_block.j2
    safety_disclaimer_block.j2
  cockpit/
    pocket_cockpit_card.j2
    case_understanding_summary.j2
    knowledge_note.j2
    review_flag_card.j2
```

### 10.4 Template Registry

Jedes Template braucht Metadaten:

```json
{
  "template_id": "chat.senior_engineer_short.v1",
  "path": "backend/app/agent/templates/chat/senior_engineer_short.j2",
  "output_type": "markdown",
  "allowed_modes": ["case_building", "leakage_diagnosis", "pending_slot_answer"],
  "max_questions": 1,
  "disclaimer_policy": "suppress_normal_turn",
  "forbidden_phrases": [
    "Ich verstehe den Fall aktuell als",
    "Als Nächstes wäre die wichtigste Frage",
    "Grenze:"
  ]
}
```

### 10.5 Pflicht-Template-Familie

```text
micro_slot_extraction_json.j2
knowledge_explainer.j2
case_aware_knowledge.j2
technical_comparison.j2
norm_documentation_knowledge.j2
impact_agent_json.j2
technical_case_challenge.j2
case_understanding_summary.j2
pocket_cockpit_card.j2
mobile_triage.j2
visual_low_confidence_guidance.j2
senior_engineer_short.j2
short_slot_reply.j2
sheet_comment.j2
conflict_resolution.j2
smalltalk_fast.j2
rfq_one_pager.j2
rfq_brief.j2
manufacturer_question_simulation.j2
safety_disclaimer_block.j2
evidence_summary_block.j2
visual_evidence_json.j2
sketch_to_case_json.j2
```

### 10.6 Beispiel: `senior_engineer_short.j2`

```jinja2
{% if opening -%}
{{ opening }}
{% endif %}

{% if technical_hint -%}
{{ technical_hint }}
{% endif %}

{{ primary_question }}
```

Regeln:

```text
- kein vollständiges Case-Spiegeln
- maximal eine primäre Frage
- keine normale Haftungsgrenze
- keine finale Empfehlung
```

### 10.7 Beispiel: `mobile_triage.j2`

```jinja2
{{ immediate_context }}

{{ primary_question }}

{% if action_chips %}
ACTIONS: {{ action_chips | tojson }}
{% endif %}
```

Beispiel:

```text
Ich prüfe das als möglichen Leckagefall an einer Wellendichtung.

Dreht sich die Welle im Betrieb?
```

Action Chips:

```json
["Ja", "Nein", "Weiß ich nicht", "Foto vom Einbauort"]
```

### 10.8 Beispiel: `visual_low_confidence_guidance.j2`

```jinja2
{{ uncertainty_statement }}

{{ useful_next_step }}

{% if action_chips %}
ACTIONS: {{ action_chips | tojson }}
{% endif %}
```

### 10.9 Template Tests

Für jedes Template:

```text
- Snapshot-Test für Standardfälle
- Forbidden Phrase Test
- Max-One-Question Test
- Disclaimer Policy Test
- JSON Schema Validation bei JSON-only Templates
- Mobile Action Chip Contract Test
- No-empty-spinner Progress Contract Test bei Tier 3/4
```

---

## 11. Multi-Output Contract

> **Amendment 2026-06-04 (P0-3, gap-audit C7 — Owner decision Option 2).** The
> in-turn delivery contract is **`pocket_cockpit_patch`**
> (recognized / critical / next_step / **rfq_status** — single-sourced from
> `evaluate_rfq_readiness`) + **`rfq_readiness_projection`** (readiness) +
> **`cockpit_patch`** (desktop documentation) + the **REST RFQ one-pager** on
> demand. The previously-listed `case_understanding_patch` and `rfq_brief_patch`
> were **stubs with no writer and no consumer** and are **removed** from the
> envelope (here and in §28.2). The original "§6.4" reference resolves to this
> §11 envelope definition (and the §28.2 schema) — §6.4 does not exist as a
> heading. Reason: align the documented envelope with the implemented, tested
> delivery path; stop carrying inert fields.

Jeder fachliche Turn erzeugt intern einen Output-Envelope:

```json
{
  "assistant_turn": {
    "chat_reply": {},
    "cockpit_patch": {},
    "pocket_cockpit_patch": {},
    "pending_question": {},
    "action_chips": [],
    "trace": {}
  }
}
```

### 11.1 ChatReply

```json
{
  "style": "senior_engineer_short",
  "markdown": "Okay, damit kann man arbeiten.\n\nBei einem undichten Altteil würde ich zuerst die Lauffläche prüfen. Siehst du dort eine Rille, Korrosion oder eine blank eingelaufene Spur?",
  "primary_question": {
    "field": "shaft_surface_condition",
    "text": "Siehst du auf der Welle im Bereich der Dichtlippe eine Rille, Korrosion oder eine blank eingelaufene Spur?"
  },
  "disclaimer_mode": "suppress_normal_turn",
  "template_id": "chat.senior_engineer_short.v1"
}
```

### 11.2 CockpitPatch

```json
{
  "known_fields": [],
  "computed_values": [],
  "review_flags": [],
  "open_points": [],
  "active_question": {},
  "rfq_status": {},
  "knowledge_notes": [],
  "conflicts": [],
  "visual_candidates": [],
  "sketch_candidates": []
}
```

### 11.3 PocketCockpitPatch

```json
{
  "recognized": [],
  "critical": [],
  "next_step": {},
  "rfq_status": "DRAFT",
  "details_available": true,
  "collapsed_by_default": true
}
```

### 11.4 ActionChips

```json
[
  {"label": "Ja", "value": "yes", "field": "shaft_rotates"},
  {"label": "Nein", "value": "no", "field": "shaft_rotates"},
  {"label": "Weiß ich nicht", "value": "unknown", "field": "shaft_rotates"},
  {"label": "Foto senden", "action": "upload_photo"}
]
```

### 11.5 CaseUnderstandingPatch

Nur bei expliziter Zusammenfassung, Case Understanding Tab oder RFQ-Vorbereitung.

```json
{
  "technical_short_image": "",
  "known_reliable_points": [],
  "critical_points": [],
  "easy_to_miss_points": [],
  "missing_points": [],
  "rfq_relevance": ""
}
```

### 11.6 RFQBriefPatch

Nur bei RFQ-Anforderung.

```json
{
  "format": "one_pager",
  "readiness": "RFQ_WITH_OPEN_POINTS",
  "confirmed_facts": [],
  "open_points_critical": [],
  "open_points_helpful": [],
  "open_points_optional": [],
  "computed_values": [],
  "review_flags": [],
  "manufacturer_questions": [],
  "attachments": [],
  "required_acknowledgements": []
}
```

### 11.7 Trace

```json
{
  "route": "case_building_agent_bundle",
  "tier": 3,
  "latency_ms": 1480,
  "first_progress_ms": 250,
  "llm_used": true,
  "rag_used": false,
  "graph_used": false,
  "agents_run": [],
  "state_mutation": "proposed_delta_applied_by_state_gate",
  "chat_style_policy": "senior_engineer_short",
  "disclaimer_mode": "suppress_normal_turn",
  "template_id": "chat.senior_engineer_short.v1",
  "mobile_surface": false,
  "empty_spinner_violated": false
}
```

---

## 12. Core Domain State Model

### 12.1 Field Status

```text
confirmed
pending_confirmation
explicitly_unknown
rejected
conflicting
not_applicable
visual_candidate
sketch_candidate
rag_supported_note
calculated
agent_inferred_review_flag
```

### 12.2 Origin Types

```text
user_direct_input
user_direct_answer
action_chip_answer
sheet_field_edit
sheet_bulk_input
structured_form_input
llm_extracted
micro_llm_extracted
rag_supported
visual_candidate
sketch_candidate
calculated
agent_inferred_review_flag
manufacturer_response
```

### 12.3 Liability-bearing Fields

Besonders kontrolliert:

```text
Maße
Druck
Temperatur
Drehzahl
Medium
Material
Normen
Compliance
Dichtungstyp
Hersteller-/Artikelnummern
Sicherheitsanforderungen
```

### 12.4 Field Envelope

```json
{
  "field": "speed_rpm",
  "label": "Drehzahl",
  "value": 3000,
  "unit": "rpm",
  "status": "confirmed",
  "origin": "user_direct_answer",
  "approximate": true,
  "confidence": "high",
  "requires_confirmation": false,
  "revision": 4
}
```

### 12.5 Conflict Envelope

```json
{
  "field": "temperature_operating_c",
  "existing_value": 90,
  "new_value": 190,
  "status": "conflicting",
  "resolution_question": "Soll 190 °C den bisherigen Wert ersetzen oder ist das ein Spitzenwert?",
  "case_blocking": false,
  "rfq_open_point": true
}
```

### 12.6 State Gate Degradation Rule

Das State Gate darf nicht unnötig den ganzen Case blockieren.

```text
Normale Feldkonflikte → nur Feldstatus conflicting.
Restlicher Case bleibt verwendbar.
RFQ bleibt ggf. mit offenem Punkt möglich.
Human Escalation nur bei hoher Risiko-/Safety-/Compliance-Relevanz.
```

---

## 13. Persistence Contract V1

Codex braucht eine klare Speicherentscheidung, damit keine verstreuten Payload-Lösungen entstehen.

### 13.1 V1-Entscheidung

```text
V1 Source of Truth:
CaseRecord.payload + case_state_snapshots + case_events/turn_events.
```

Falls bestehende Modelle anders heißen, Codex muss die vorhandenen Äquivalente nutzen und keine parallele Struktur erfinden.

### 13.2 V1-Persistenzregeln

```text
- Authoritative current case state liegt in CaseRecord.payload oder existierendem Case-State-Äquivalent.
- Jede relevante Änderung erzeugt ein Event.
- Nach State-Gate-Annahme wird eine Snapshot-Revision erzeugt oder aktualisiert.
- AssistantTurnEnvelope wird als Turn Output gespeichert oder rekonstruierbar gemacht.
- AgentOutputs werden in V1 primär als trace/turn_artifacts gespeichert, nicht als eigene relationale Wahrheit.
- VisualEvidenceCandidates werden nur als Kandidaten mit Attachment-Referenz und requires_confirmation gespeichert.
- RAG-gestützte Notes werden als KnowledgeNote/ReviewNote gespeichert, nicht als confirmed Case Fact.
- PocketCockpitPatch ist Projektion, nicht separate Wahrheit.
```

### 13.3 V1.5/V1.6 Option

```text
Später können relationale Tabellen ergänzt werden:
EvidenceField
Attachment
AgentFinding
ReviewFlag
RFQBriefSnapshot
CaseRevision
ManufacturerFeedback
```

Diese Tabellen sind in V1 optional und dürfen nicht Voraussetzung für die ersten Patches sein.

### 13.4 Idempotency

Jedes mutierende Event braucht:

```text
client_event_id oder server_turn_id
case_revision_seen
tenant_id
user_id
event_type
```

Regel:

```text
Doppelte client_event_id darf keine doppelte State-Mutation erzeugen.
Wenn case_revision_seen veraltet ist, muss Konflikt-/Merge-Logik greifen.
```

### 13.5 Event-Typen

```text
user_chat_message
assistant_turn_created
action_chip_selected
sheet_field_edit
sheet_bulk_input
visual_upload_received
visual_candidate_confirmed
sketch_candidate_confirmed
field_conflict_detected
field_conflict_resolved
rfq_brief_generated
rfq_acknowledged
manufacturer_profile_suggested
manufacturer_feedback_received
```

### 13.6 Snapshot-Regel

```text
Jede akzeptierte technische State-Mutation erhöht case_revision.
RFQ-Briefe referenzieren eine konkrete case_revision.
RFQ-Brief-Inhalt darf sich nachträglich nicht stillschweigend ändern.
```

---

## 14. RAG Retrieval Contract

RAG liefert Kontext und Quellen, aber keine automatische Case-Wahrheit.

### 14.1 Single-Collection-Regel

```text
V1 nutzt eine einzige Qdrant-Collection für sealingAI Knowledge.
Tenant-Isolation erfolgt strikt über tenant_id Payload-Filter.
Keine per-tenant Collections.
Keine tenant_id im Freitext ableiten.
```

### 14.2 Payload-Pflichtfelder

```json
{
  "tenant_id": "tenant-uuid",
  "entity_type": "material | seal_type | medium | application | failure_mode | standard | datasheet | manufacturer_profile",
  "entity_name": "FKM",
  "claim_level": "L1 | L2 | L3",
  "source_id": "doc-or-url-id",
  "source_title": "...",
  "source_version": "...",
  "source_date": "...",
  "language": "de | en",
  "application_relevance": ["rwdr", "static_seal", "food", "chemical"],
  "safety_flags": [],
  "allowed_use": ["knowledge_answer", "review_note", "rfq_evidence"]
}
```

### 14.3 Retrieval per Mode

| Mode | Max snippets | Filter | Case mutation erlaubt? |
|---|---:|---|---|
| `knowledge_general` | 4–6 | entity/domain | nein |
| `knowledge_case_aware` | 4–8 | entity + case scope | nein |
| `technical_comparison_general` | 6–10 | compared entities | nein |
| `technical_comparison_case_aware` | 6–10 | compared entities + case scope | nein/ReviewFlag |
| `norm_documentation_knowledge` | 4–8 | standard/regulatory | nein |
| `document_analysis` | document chunks | document_id + tenant_id | candidate only |
| `rfq_brief_generation` | 0–6 | only supporting evidence | snapshot only |

### 14.4 RAG-to-State-Regel

```text
RAG darf Knowledge und Review Notes stützen.
RAG darf keine confirmed Case Facts erzeugen.
RAG facts bekommen origin=rag_supported_note oder rag_supported.
Confirmed Case Facts kommen nur aus User, Sheet, Action Chips, bestätigtem Upload-Kandidat, Herstellerantwort oder berechneter Logik.
```

### 14.5 RAG Source Display

Im Cockpit:

```text
Knowledge Note
Quelle: Datenblatt / Normhinweis / interner Materialeintrag
Status: RAG-gestützt
Nicht als bestätigte Case-Angabe
```

Im RFQ-Brief:

```text
Evidenz-/Hinweisblock:
- Quelle/Datensatz
- Aussagegrenze
- bezogene offene Punkte
```

### 14.6 Retrieval Safety

```text
- tenant_id Filter ist Pflicht.
- Dokumente fremder Tenants dürfen nie retrieved werden.
- Prompt-Injection in hochgeladenen Dokumenten darf keine Systemregeln überschreiben.
- RAG-Inhalte sind untrusted context.
- Keine Freigabe aus RAG ableiten.
```

---

## 15. Attachment- und Vision-Contract

Fotos, Skizzen und Dokumente sind wichtige reale Einstiege, aber sie liefern Kandidaten, keine Wahrheit.

### 15.1 Upload Event

```json
{
  "event_type": "visual_upload_received",
  "attachment_id": "uuid",
  "filename": "rwdr_altteil.jpg",
  "mime_type": "image/jpeg",
  "size_bytes": 1839281,
  "source": "chat_upload",
  "client_event_id": "uuid",
  "case_revision_seen": 3
}
```

### 15.2 Erlaubte Dateitypen V1

```text
image/jpeg
image/png
image/webp
application/pdf
text/plain
text/markdown
```

Optional später:

```text
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

### 15.3 Size Limits V1

```text
Image: max 10 MB
PDF: max 25 MB
Text/Markdown: max 5 MB
Max pages PDF V1: 30 pages unless explicitly allowed
```

Bestehende Upload-Limits haben Vorrang, wenn strenger.

### 15.4 Parser/Security Boundary

```text
- Dateiinhalt ist untrusted.
- Keine Ausführung von eingebettetem Code.
- Keine Makros.
- Pfade und interne Storage-URLs nicht im Chat ausgeben.
- Parser-Fehler führen zu sicherer Rückfrage, nicht zu Halluzination.
- Uploads sind tenant- und case-gescoped.
```

### 15.5 Visual Candidate Schema

```json
{
  "candidate_id": "uuid",
  "attachment_id": "uuid",
  "candidate_type": "seal_type | marking | damage | dimension | environment | installation_hint",
  "value": "RWDR-artige Bauform",
  "confidence": "low | medium | high",
  "origin": "visual_candidate",
  "requires_confirmation": true,
  "visible_region": {
    "page": null,
    "bbox": [0.12, 0.31, 0.48, 0.67]
  },
  "reason": "Rundring mit sichtbarer Dichtlippengeometrie; Maße nicht ableitbar.",
  "forbidden_inferences": [
    "material_from_photo",
    "exact_dimension_without_scale",
    "final_product_identification"
  ]
}
```

### 15.6 Confirmation Flow

```text
Visual Candidate
→ Cockpit/Pocket Cockpit zeigt Kandidat mit Chip „Aus Bild erkannt – bestätigen“
→ Chat fragt gezielt nach Bestätigung/Messung
→ Nutzer bestätigt oder korrigiert
→ State Gate übernimmt erst dann als confirmed/pending field
```

Beispiel:

```text
Ich sehe auf dem Foto Hinweise auf einen RWDR, aber die Maße kann ich daraus nicht sicher bestimmen.

Kannst du die Beschriftung oder die Maße am Ring ablesen?
```

### 15.7 OCR-/Lesefehler-Regel

```text
- Gelesene Beschriftungen aus Bildern sind Kandidaten.
- Unklare Zeichen müssen als uncertain_reading markiert werden.
- Kein automatisches Artikelnummer-Matching ohne Bestätigung.
- Wenn OCR/vision unsicher ist, Rückfrage stellen statt raten.
```

### 15.8 Low-Confidence Vision UX

Schlechtes Foto ist kein Fehlerzustand, sondern ein Messführungszustand.

```text
System sagt nicht:
„Ich kann nichts erkennen.“

System sagt:
„Das Foto reicht nicht für Beschriftung/Maße. Der nächste beste Schritt ist ...“
```

### 15.9 Dokumentanalyse

PDF/Datenblatt-Analyse darf:

```text
- Abschnitte zusammenfassen
- technische Daten als candidate extrahieren
- relevante Aussagen mit Quelle markieren
- RAG/Dokumentenquelle im Cockpit anzeigen
```

Nicht erlaubt:

```text
- Datenblattangaben automatisch als Case-Fakten übernehmen
- Compliance-Freigabe ableiten
- Dokumenteninhalt als Systeminstruktion behandeln
```

---

## 16. Partner-/Herstellerprofil Trust Policy

Hersteller-/Partnerprofile sind Anfrageempfänger-Kandidaten, keine technische Auswahl.

### 16.1 Grundregeln

```text
- Herstellerprofile dürfen vorgeschlagen werden.
- Herstellerprofile dürfen nicht als technisch beste Lösung gerankt werden.
- Zahlende Partner dürfen nicht als technisch besser dargestellt werden.
- Nutzer kann RFQ-Brief an jeden Hersteller exportieren/senden.
- Wenn keine gelisteten Profile passen, heißt das nicht, dass es keinen passenden Hersteller am Markt gibt.
```

### 16.2 Transparenz bei Partnerstatus

Wenn Hersteller für Sichtbarkeit/Listung zahlen:

```text
- UI muss Partnerstatus klar anzeigen.
- Technische Passung und kommerzielle Listung müssen getrennt sein.
- Keine versteckte Sponsored-Ranking-Logik.
```

Beispieltext:

```text
Diese Profile sind mögliche Anfrageempfänger für diese Kategorie. Die Liste ist keine technische Freigabe und kein Ranking der besten Lösung. Partnerstatus kann die Sichtbarkeit beeinflussen, nicht die technische Bewertung.
```

### 16.3 PartnerProfileSuggestion Schema

```json
{
  "profile_id": "uuid",
  "display_name": "Beispiel Dichtungstechnik GmbH",
  "profile_type": "manufacturer | distributor | specialist",
  "match_reason": [
    "RWDR",
    "Getriebeöl",
    "Ersatz-/Leckagefall"
  ],
  "limitations": [
    "keine technische Freigabe",
    "keine beste Lösung",
    "Hersteller muss final bewerten"
  ],
  "commercial_status": "listed_partner | neutral_directory | user_provided",
  "ranking_policy": "not_technical_ranking"
}
```

---

## 17. Agentenmodell

Alle Agenten sind Impact-Agenten. Sie geben keine finale Wahrheit aus, sondern strukturierte Vorschläge.

### 17.1 Gemeinsames Agent Output Schema

```json
{
  "agent": "medium_impact",
  "scope": "rwdr",
  "detected_facts": [],
  "proposed_case_delta": [],
  "impact_flags": [],
  "missing_fields": [],
  "computed_values": [],
  "review_notes": [],
  "next_best_question": {},
  "chat_guidance_candidate": {},
  "cockpit_cards": [],
  "pocket_cockpit_cards": [],
  "forbidden_claims": []
}
```

### 17.2 Agentenliste V1.6

```text
SealTypeImpactAgent
ApplicationImpactAgent
MediumImpactAgent
OperatingPhaseAgent
OperatingConditionImpactAgent
ShaftCounterfaceImpactAgent
InstallationHousingImpactAgent
MaterialCompatibilityImpactAgent
FailureModeImpactAgent
VisualEvidenceAgent
SketchToCaseAgent
UnknownSealScopingAgent
MeasurementGuidanceAgent
ManufacturerQuestionAgent
RegulatoryDocumentationImpactAgent
DataQualityEvidenceAgent
DevilsAdvocateImpactAgent
RFQQualityAgent
CaseExplanationAgent
KnowledgeExplainerAgent
TechnicalComparisonAgent
SheetValidationAgent
ConflictResolutionAgent
MobileTriageAgent
PocketCockpitProjectionAgent
SmalltalkFastResponder
UIHelpResponder
PartnerProfileSuggestionAgent
```

### 17.3 Dirty Module Scheduler

Nicht alle Agenten laufen immer.

Beispiele:

```text
medium changed
→ MediumImpactAgent
→ MaterialCompatibilityImpactAgent

speed_rpm changed
→ OperatingConditionImpactAgent
→ CalculationEngine

application changed
→ ApplicationImpactAgent
→ RequiredFields update

photo uploaded
→ VisualEvidenceAgent
→ MeasurementGuidanceAgent optional

photo uploaded + mobile + short leakage text
→ MobileTriageAgent
→ VisualEvidenceAgent low confidence async/secondary
→ PocketCockpitProjectionAgent

leakage described
→ FailureModeImpactAgent
→ ShaftCounterfaceImpactAgent optional

sheet field changed
→ SheetValidationAgent
→ relevant impact module only

rfq requested
→ RFQQualityAgent
→ ManufacturerQuestionAgent
→ RFQOnePagerComposer

manufacturer suggestions requested
→ PartnerProfileSuggestionAgent
→ TrustPolicyBlock
```

### 17.4 Agenten dürfen nicht

```text
- finale Chat-Antwort direkt schreiben
- State direkt mutieren
- RAG-Notes als confirmed facts ausgeben
- Material-/Produktfreigabe geben
- Hersteller als beste Lösung ranken
- wegen normaler Lücken automatisch human escalation auslösen
```

### 17.5 Agent Conflict Guardrails

```text
- Agenten liefern Vorschläge, keine Blockaden.
- Konflikte werden als Field Conflicts oder Review Flags modelliert.
- State Gate nimmt konfliktfreie Felder weiter an.
- Human Escalation nur bei definierten high-risk triggers.
- Dirty Scheduler verhindert, dass alle Agenten bei jedem Turn laufen.
```

---

## 18. Composer V1.6

Der Composer entscheidet, was in Chat, Pocket Cockpit, Cockpit, Case Understanding und RFQ gehört.

### 18.1 Composer-Regeln

```text
1. Chat darf nicht alles wiederholen, was im Cockpit sichtbar ist.
2. Chat nennt den wichtigsten fachlichen Hebel.
3. Chat stellt maximal eine primäre Frage.
4. Wissensfragen dürfen ausführlicher sein.
5. Mobile Case-Turns erzeugen Pocket Cockpit + Action Chips.
6. Sheet-Änderungen erzeugen nur bei Relevanz eine ChatReply.
7. RFQ wird als eigener One-Pager/Brief behandelt.
8. Haftungsgrenzen erscheinen nicht in normalen Turns.
9. Finale Freigabewünsche werden klar begrenzt.
10. Template Registry entscheidet, welches Jinja2-Template genutzt wird.
11. Composer Output muss gegen Output-Schema validiert werden.
12. Bei Tier 3/4 wird ein Fortschrittsoutput erzeugt, bevor die Vollanalyse fertig ist.
```

### 18.2 Chat Styles

```text
senior_engineer_short
mobile_triage
visual_low_confidence_guidance
knowledge_explainer
case_aware_explainer
measurement_guide
rfq_confirmation
rfq_one_pager_intro
blocked_boundary
smalltalk_fast
ui_help
sheet_comment
conflict_resolution
partner_profile_trust
```

### 18.3 No-Go-Phrasen in normalen Case-Turns

```text
Ich verstehe den Fall aktuell als
Technisch relevant sind hier vor allem
Als Nächstes wäre die wichtigste Frage
Grenze:
Bitte beachten Sie, dass
Auf Basis Ihrer Angaben empfehle ich final
Der optimale Dichtring ist
```

### 18.4 Erwünschte Chat-Sprache

```text
Okay, damit kann man arbeiten.
Da würde ich zuerst ... prüfen.
Achtung: Bei reinem Maßersatz übersieht man oft ...
Prüfe bitte zuerst ...
Schau dir bitte ... an.
Kannst du erkennen, ob ...?
Ich würde das im Brief als Review-Punkt aufnehmen.
Das Foto reicht für die Beschriftung noch nicht. Der nächste beste Schritt ist ...
```

---

## 19. Cockpit UX Contract

### 19.1 Desktop Pflichtbereiche V1.6

```text
1. Fallnotiz / Parameter
2. Sheet / Parameter Editor
3. Aktive Frage
4. Offene Punkte
5. Review-Hinweise
6. Berechnete Werte
7. Herkunft/Status-Chips
8. Knowledge Notes
9. Visual/Sketch Candidates
10. Konflikte
11. RFQ-Status
12. Case Understanding Tab
13. RFQ Brief Tab
14. Herstellerprofile / Anfrageempfänger-Kandidaten
15. Revision / Trace light
```

### 19.2 Mobile Pflichtbereiche V1.6

```text
1. Chat/Kamera
2. Aktuelle Frage
3. Action Chips
4. Pocket Cockpit
5. RFQ Status Kurz
6. Details einklappbar
```

### 19.3 Trust Chips

```text
Übernommen
Bestätigt
Aus Text extrahiert
Aus Action Chip
Aus Formular
Aus Sheet
Aus Bild erkannt
Aus Skizze erkannt
Berechnet
RAG-gestützt
Offen
Unbekannt
Widerspruch
Herstellerprüfung erforderlich
Nicht im Scope
```

### 19.4 Parameterbereich

Beispiel:

| Feld | Wert | Status | Herkunft |
|---|---:|---|---|
| Dichtungstyp | RWDR | übernommen | User |
| Maße | 45 × 62 × 8 mm | übernommen | User |
| Anwendung | Getriebe | übernommen | User |
| Medium | Öl | übernommen | User |
| Drehzahl | ca. 1500 rpm | übernommen | User |
| Außenumgebung | staubig | übernommen | User |
| Problem | Altteil undicht | übernommen | User |

### 19.5 Berechnete Werte

```text
Umfangsgeschwindigkeit: ca. 3,5 m/s
Berechnung: π × 45 mm × 1500 rpm / 60000
Status: berechnet
```

### 19.6 Knowledge Notes

Bei Wissensfragen, die case-relevant sind, kann das Cockpit eine kurze Knowledge Note erhalten:

```text
FKM als Werkstoffrichtung prüfen — keine Freigabe.
Temperatur und Öl/Additive entscheidend.
```

### 19.7 Visual Candidates

```text
Aus Bild erkannt:
- RWDR-artige Bauform (Kandidat)
- Beschriftung eventuell „45x62x8“ (unsicher)
Aktion: bestätigen / korrigieren / ignorieren
```

---

## 20. RFQ Dispatch Policy und One-Pager Contract

Der Nutzer darf eine Anfrage jederzeit auslösen, wenn ein minimaler Kern vorhanden ist. Fehlende Punkte werden nicht verschwiegen, sondern sichtbar markiert.

### 20.1 Readiness Status

```text
DRAFT
MINIMAL_RFQ
RFQ_WITH_OPEN_POINTS
MANUFACTURER_REVIEW_READY
OUT_OF_SCOPE
```

### 20.2 Mindestkern RWDR für erste RFQ

```text
- vermuteter Dichtungstyp oder Foto
- Maße d1/D/b oder Altteilfoto
- Anwendung/Maschine
- Medium oder Leckagebeschreibung
- Anfrageziel
```

### 20.3 RFQ DRAFT

Wenn zu wenig bekannt ist:

```json
{
  "readiness": "DRAFT",
  "can_generate_brief": false,
  "reason": "Keine Mindestinformationen zur Dichtung oder Einbausituation vorhanden.",
  "minimum_needed": [
    "Foto oder Dichtungstyp",
    "Maße oder Altteilfoto",
    "Anwendung/Maschine",
    "Medium oder Leckagebeschreibung"
  ]
}
```

### 20.4 RFQ Policy Schema

```json
{
  "can_generate_brief": true,
  "can_send_request": true,
  "requires_acknowledgement": true,
  "readiness": "RFQ_WITH_OPEN_POINTS",
  "reason": "Minimum viable RFQ fields are present, but pressure, temperature and shaft condition are missing.",
  "manufacturer_may_need_followup": true,
  "open_points_critical": [
    "shaft_surface_condition"
  ],
  "open_points_helpful": [
    "temperature_range",
    "pressure_difference"
  ],
  "open_points_optional": []
}
```

### 20.5 RFQ One-Pager Structure

Der Herstellerbrief muss kurz und schnell lesbar sein.

```text
1. Anfrageziel
2. Bestätigte Daten
3. Kritisch offene Punkte
4. Weitere hilfreiche offene Punkte
5. Review-Hinweise
6. Berechnete Werte
7. Fotos/Anhänge
8. Konkrete Herstellerfragen
9. Grenze / keine finale Freigabe durch sealingAI
```

### 20.6 RFQ Chat

```text
Ja, als erste Herstelleranfrage geht das — mit offenen Punkten.

Ich markiere im Brief klar, dass Temperatur, Druckdifferenz und Wellenzustand noch fehlen. Der Hersteller kann dann entscheiden, ob eine Vorbewertung möglich ist oder ob Rückfragen nötig sind.

Soll der Brief mit diesen offenen Punkten erzeugt werden?
```

### 20.7 RFQ Snapshot-Regel

```text
Jeder RFQ-Brief referenziert:
- case_id
- case_revision
- generated_at
- confirmed_facts
- open_points
- review_flags
- acknowledgement_status
```

Nachträgliche Case-Änderungen erzeugen neue RFQ-Versionen, nicht stille Änderungen am alten Brief.

---

## 21. Herstellerfeedback-Schleife

V1.6 bereitet einen späteren, aber architektonisch wichtigen Feedback Loop vor. Herstellerfeedback ist kein LLM-Training im Blindflug, sondern strukturierte Qualitätsrückmeldung zur RFQ-Vorbereitung.

### 21.1 Ziel

Hersteller oder interne Reviewer sollen markieren können:

```text
- Anfrage ausreichend für Vorbewertung
- Angebot möglich
- Rückfrage nötig
- kritischer Punkt fehlt
- Angabe widersprüchlich
- unnötige/irrelevante Angabe
- falscher Dichtungstyp-Verdacht
- bessere Foto-/Messanforderung nötig
```

### 21.2 Datenmodell

```json
{
  "feedback_id": "...",
  "case_id": "...",
  "rfq_snapshot_id": "...",
  "reviewer_type": "manufacturer|internal_expert|user",
  "rfq_quality": "sufficient|needs_followup|not_evaluable|out_of_scope",
  "missing_fields": ["shaft_surface_condition", "pressure_difference"],
  "confusing_fields": [],
  "unnecessary_fields": [],
  "comment": "Hersteller benötigt Foto der Wellenlauffläche und Angabe zur Temperatur."
}
```

### 21.3 Nutzung

Feedback darf genutzt werden für:

```text
- RFQQualityAgent-Regeln verbessern
- Next-Best-Question-Prioritäten justieren
- Golden Conversations erweitern
- Mess-/Foto-Checklisten verbessern
- Herstellerfragen realistischer machen
```

Feedback darf nicht automatisch:

```text
- technische Freigaben erzeugen
- Material-/Produktempfehlungen verallgemeinern
- zahlende Partner bevorzugen
- tenantübergreifend ohne Datenschutz-/Mandantengrenze ausgewertet werden
```

### 21.4 V1-Implementierung

V1 muss Feedback noch nicht vollständig bauen. Aber die RFQ-Snapshots müssen so strukturiert sein, dass später Feedback eindeutig zu einem `case_revision` und `rfq_snapshot_id` zugeordnet werden kann.

---

## 22. Disclaimer und Boundary Policy

### 22.1 Dauerhafter UI-Hinweis

Unter dem Chat-Input steht dauerhaft:

```text
Technische Vorqualifizierung und RFQ-Strukturierung. Finale Bewertung/Freigabe durch Hersteller oder verantwortliche Fachstelle.
```

Mobile Kurzform:

```text
Vorqualifizierung. Finale Bewertung durch Hersteller/Fachstelle.
```

### 22.2 Chat-Grenze nur bei Bedarf

Explizite Grenze nur bei:

```text
- finaler Freigabe-/Garantiefrage
- Compliance-Freigabe
- RFQ-Brief-Erzeugung
- Safety/Scope-Fall
- potenziell missverständlichem Review Flag
```

Normaler Turn:

```json
{
  "disclaimer_mode": "suppress_normal_turn"
}
```

### 22.3 Safety/Scope Blockieren

Blockieren oder klar begrenzen bei:

```text
finale Freigabe verlangt
ATEX-Freigabe
Wasserstoff/Hochdruckgas im MVP
toxische Medien
Aerospace
Medical
Nuclear
Safety-critical
Compliance-Freigabe
```

Nicht blockieren bei:

```text
Druck fehlt
Temperatur fehlt
Material unbekannt
Wellenzustand unbekannt
Drehzahl unbekannt
schlechtes Foto
```

Diese Punkte werden als offen markiert.

---

## 23. Calculation Requirements

### 23.1 Umfangsgeschwindigkeit

Für RWDR mit d1 und rpm:

```text
v = π × d1_mm × rpm / 60000
```

Beispiel:

```text
d1 = 45 mm
rpm = 1500
v = π × 45 × 1500 / 60000 = 3,53 m/s
```

Anzeige:

```text
Cockpit immer, wenn d1 und rpm bekannt sind.
Pocket Cockpit nur, wenn relevant/kritisch.
Chat nur, wenn relevant für den nächsten Schritt oder bei Drehzahl-Slot.
```

### 23.2 Weitere V1-Berechnungen optional

```text
PV-Wert nur, wenn Druck und Geschwindigkeit bekannt und fachlich sinnvoll.
Temperaturmarge nur mit Material-/Compound-Daten als Review-Hinweis, nicht Freigabe.
```

---

## 24. Security, Tenant und Governance

### 24.1 Tenant Scope

```text
- Jede Case-, Upload-, RAG-, RFQ- und Partneraktion ist tenant_id-gescoped.
- tenant_id kommt aus Auth/Keycloak-Kontext, nicht aus User-Text.
- IDOR-Checks sind Pflicht bei case_id, attachment_id, document_id, rfq_id.
```

### 24.2 Prompt Injection

```text
- User Uploads und RAG-Dokumente sind untrusted.
- Dokumentanweisungen dürfen System-, Developer- oder Safety-Regeln nie überschreiben.
- Agenten extrahieren Fakten/Kandidaten, keine Instruktionen.
```

### 24.3 Secrets und Logs

```text
- Keine Secrets in Trace/Chat/Cockpit ausgeben.
- Keine internen Storage-Pfade im Chat.
- Logs dürfen tenant_id/case_id enthalten, aber keine sensitiven Inhalte unnötig duplizieren.
```

---

## 25. Observability

### 25.1 Pflichtmetriken

```text
turn_count
route
tier
latency_ms
first_progress_ms
llm_used
rag_used
graph_used
agents_run
state_mutation_type
template_id
forbidden_phrase_detected
rfq_readiness
case_revision
mobile_surface
action_chips_shown
action_chip_selected
empty_spinner_violated
visual_low_confidence_count
rfq_one_pager_generated
```

### 25.2 Alert-/Debug-Signale

```text
Tier 0 nutzt unerwartet LLM
RAG ohne tenant_id Filter
Chat enthält No-Go-Phrase
Normaler Turn enthält Disclaimer
State Mutation ohne State Gate
RFQ ohne case_revision
Visual Candidate wird confirmed ohne User-Bestätigung
Mobile Tier 3/4 ohne first_progress_ms
Empty Spinner länger als 1 s bei Mobile
Human Escalation bei normaler Lücke ausgelöst
```

---

## 26. Golden Conversations V1.6

### Golden A — Neuer RWDR-Case

User:

```text
Ich brauche einen RWDR 45x62x8 für ein Getriebe. Medium ist Öl, ca. 1500 rpm, außen staubige Umgebung. Der alte ist undicht.
```

Expected Chat:

```text
Okay, damit kann man arbeiten.

Bei einem undichten Altteil würde ich nicht nur nach Maß ersetzen. Entscheidend ist zuerst, ob die Welle an der Laufstelle beschädigt ist. Wenn dort eine Rille oder Korrosion sitzt, wird auch ein neuer Ring schnell wieder Probleme machen.

Siehst du auf der Welle im Bereich der Dichtlippe eine eingelaufene Spur, Rille oder Rost?
```

Expected Cockpit:

```text
RWDR, 45 × 62 × 8 mm, Getriebe, Öl, ca. 1500 rpm, staubige Umgebung, Altteil undicht.
Umfangsgeschwindigkeit ca. 3,53 m/s.
Review Flag: Wellenlauffläche prüfen.
Review Flag: Staubschutz prüfen.
Aktive Frage: Zustand Wellenlauffläche.
```

### Golden B — Pending Slot Fast Path

Prior question:

```text
Welche Drehzahl liegt ungefähr an der Welle an?
```

User:

```text
jo ca 3000
```

Expected:

```text
Okay, ca. 3000 U/min ist übernommen.

Welche Temperatur liegt ungefähr an der Dichtstelle an?
```

Route: `pending_slot_answer`, Tier 0, LLM false, RAG false.

### Golden C — Warum-Frage

User:

```text
Warum fragst du nach der Welle? Ich will doch nur den Dichtring ersetzen.
```

Expected:

```text
Weil der neue Ring auf genau dieser Stelle läuft.

Wenn die Welle dort eingelaufen, rostig oder riefig ist, dichtet auch ein neuer RWDR oft nicht lange sauber. Deshalb ist die Lauffläche bei einem Leckagefall wichtiger als sie auf den ersten Blick wirkt.

Ist die Stelle glatt, oder siehst du eine Spur/Rille?
```

### Golden D — Wissensfrage allgemein

User:

```text
Was ist FFKM?
```

Expected:

```text
FFKM ist ein perfluorierter Elastomerwerkstoff für sehr anspruchsvolle Medien- und Temperaturbereiche.

Für Dichtungen ist FFKM vor allem dann interessant, wenn normale Elastomere chemisch oder thermisch an Grenzen kommen. Praktisch wichtig sind aber auch Kosten, Verfügbarkeit, Compound-Unterschiede und die konkrete Medien-/Temperaturkombination.

Kurz gesagt: FFKM ist kein „besseres FKM für alles“, sondern ein Spezialwerkstoff für harte Randbedingungen.
```

Route: `knowledge_general`, State Mutation none.

### Golden E — Wissensfrage case-aware

User:

```text
Was bedeutet FKM in meinem Fall?
```

Expected:

```text
In deinem Getriebeöl-Fall wäre FKM vor allem wegen Öl, Temperaturreserve und Alterungsbeständigkeit ein sinnvoller Prüfpunkt.

Entscheidend ist aber nicht nur „Öl = FKM“, sondern die genaue Ölart, Additive, Temperatur an der Dichtlippe, Drehzahl, Wellenzustand und Außenumgebung.

Ich würde FKM im Herstellerbrief als zu prüfende Werkstoffrichtung aufnehmen, nicht als freigegebene Auswahl.
```

### Golden F — Knowledge mutating

User:

```text
Wir verwenden FKM. Öltemperatur liegt bei 100 °C.
```

Expected:

```text
Okay, FKM und ca. 100 °C nehme ich als Angabe auf.

Bei 100 °C wird wichtig, ob das Dauerbetrieb, Spitzenwert oder direkt an der Dichtstelle gemessen ist.

Ist das die Öltemperatur im Betrieb oder die Temperatur an der Dichtstelle?
```

State Mutation: material_candidate + temperature.

### Golden G — Mobile Foto + „sifft“

User:

```text
[Foto hochgeladen]
sifft
```

Expected immediate Chat:

```text
Ich prüfe das als möglichen Leckagefall an einer Wellendichtung.

Dreht sich die Welle im Betrieb?
```

Expected Action Chips:

```text
[Ja] [Nein] [Weiß ich nicht] [Foto vom Einbauort]
```

Expected Pocket Cockpit:

```text
Erkannt: Leckage / Dichtstelle unklar
Kritisch: Dichtungstyp und Wellenbewegung klären
Nächster Schritt: Dreht sich die Welle?
RFQ: DRAFT
```

Trace:

```text
route = mobile_leakage_triage
first_progress_ms < 1000
empty_spinner_violated = false
```

### Golden H — Schlechtes Foto

User:

```text
[unscharfes Foto Altteil]
```

Expected:

```text
Die Beschriftung kann ich auf dem Foto nicht sicher lesen.

Für die Anfrage hilft jetzt am meisten: Miss Innendurchmesser, Außendurchmesser und Breite — oder fotografiere die Stirnseite mit Beschriftung direkt von oben.
```

Expected Action Chips:

```text
[So messe ich d1/D/b] [Neues Foto machen] [Ich weiß die Maße nicht]
```

Must not contain:

```text
Das ist sicher ein ...
Material ist ...
Artikelnummer ist ...
```

### Golden I — Sheet Field Edit

Event:

```json
{"field": "temperature_operating_c", "value": 90, "unit": "°C"}
```

Expected Chat:

```text
90 °C ist übernommen.

Für die Werkstoffprüfung wäre noch wichtig, ob das Dauerbetrieb oder ein kurzzeitiger Spitzenwert ist.
```

### Golden J — Sheet Bulk Input

Event:

```json
{
  "fields": {
    "speed_rpm": 3000,
    "temperature_operating_c": 90,
    "medium_internal": "Öl"
  }
}
```

Expected Chat:

```text
Die Betriebsdaten sind übernommen.

Bei 45 mm Welle und 3000 U/min liegt die Umfangsgeschwindigkeit bei rund 7,1 m/s. Für den Leckagefall fehlt jetzt vor allem die Lauffläche.

Ist die Welle an der Dichtlippenstelle glatt, oder sieht man eine Rille?
```

### Golden K — Smalltalk

User:

```text
Hallo
```

Expected:

```text
Hallo! Ja, ich kann dir bei Dichtungsfällen helfen — Ersatzteil, Leckage, Materialfrage, Foto, Skizze oder Herstelleranfrage.

Worum geht es bei dir?
```

State Mutation none. CockpitPatch none.

### Golden L — Finale Freigabe

User:

```text
Sag mir einfach, welcher Dichtring garantiert passt.
```

Expected:

```text
Das kann ich nicht seriös als Garantie freigeben.

Ich kann den Fall aber so vorbereiten, dass ein Hersteller ihn sauber bewerten kann: bekannte Daten, offene Punkte, Review-Hinweise und konkrete Rückfragen.

Soll ich daraus einen Technical RFQ Brief erstellen?
```

### Golden M — RFQ trotz fehlender Daten

User:

```text
Mehr weiß ich nicht. Mach bitte trotzdem die Anfrage.
```

Expected:

```text
Ja, als erste Herstelleranfrage geht das — mit offenen Punkten.

Ich markiere im Brief klar, dass Temperatur, Druckdifferenz und Wellenzustand noch fehlen. Der Hersteller kann dann entscheiden, ob eine Vorbewertung möglich ist oder ob Rückfragen nötig sind.

Soll der Brief mit diesen offenen Punkten erzeugt werden?
```

### Golden N — RFQ ohne Mindestkern

User:

```text
Dichtung undicht. Mach Anfrage.
```

Expected:

```text
Dafür ist der Brief noch zu dünn.

Mindestens brauche ich einen Anhaltspunkt zur Dichtung oder Einbausituation: Foto, Maße, Maschine/Anwendung oder wo genau das Medium austritt. Sonst kann ein Hersteller kaum sinnvoll vorbewerten.

Kannst du ein Foto der Dichtstelle oder des Altteils hochladen?
```

Expected:

```text
readiness = DRAFT
can_generate_brief = false
```

### Golden O — Human Escalation

User:

```text
RWDR, unbekanntes Lösungsmittel, 12 bar, 8000 rpm, ATEX-Bereich. Gib mir direkt die passende Lösung.
```

Expected:

```text
Der Fall ist für eine rein digitale Vorqualifizierung zu kritisch.

Ich kann die bekannten Daten in einen Review-Brief bringen, aber die Bewertung sollte direkt durch Hersteller oder verantwortliche Fachstelle erfolgen.
```

Expected:

```text
route = complex_review_required OR blocked_boundary
no final recommendation
```

### Golden P — RFQ One-Pager

Input:

```text
RFQ erzeugen für RWDR 45x62x8, Getriebe, Öl, 1500 rpm, undicht, Wellenzustand unbekannt.
```

Expected Brief Structure:

```text
1. Anfrageziel
2. Bestätigte Daten
3. Kritisch offen: Wellenlauffläche
4. Weitere offene Punkte: Temperatur, Druckdifferenz
5. Review-Hinweis: Leckageursache prüfen
6. Berechnung: Umfangsgeschwindigkeit
7. Herstellerfragen
8. Keine finale Freigabe durch sealingAI
```

---

## 27. Required Test Assertions

### 27.1 No-Go Phrase Assertions

Für normale Case-Building-Turns:

```python
FORBIDDEN_NORMAL_TURN_PHRASES = [
    "Ich verstehe den Fall aktuell als",
    "Technisch relevant sind hier vor allem",
    "Als Nächstes wäre die wichtigste Frage",
    "Grenze:",
    "finale Dichtung freigeben",
]
```

### 27.2 Required Chat Qualities

```text
- maximal eine primäre Frage
- kurzer technischer Hinweis
- keine vollständige Wiederholung aller bekannten Felder
- keine finale Empfehlung
- kein Haftungsblock im normalen Turn
- Wissensfragen dürfen ausführlicher sein
- Smalltalk darf keinen Case öffnen
- Sheet-Änderungen werden nicht unnötig kommentiert
- Mobile Triage zeigt Action Chips, wenn Antwort begrenzt ist
- Low-confidence Vision liefert Mess-/Foto-Führung statt Scheitern
```

### 27.3 Required Cockpit Qualities

```text
- alle erkannten Kernfelder sichtbar
- Status/Herkunft sichtbar
- Review Flags sichtbar
- offene Punkte sichtbar
- aktive Frage sichtbar
- berechnete Werte sichtbar, wenn Input ausreicht
- Sheet-Änderungen laufen durch State Gate
- Konflikte werden sichtbar
- Visual Candidates sind klar als Kandidaten markiert
```

### 27.4 Required Pocket Cockpit Qualities

```text
- nur Erkannt / Kritisch / Nächster Schritt / RFQ-Status
- Details eingeklappt
- aktive Frage sichtbar
- Action Chips sichtbar, wenn vorhanden
- keine langen Tabellen vor erstem Nutzen
```

### 27.5 Required Routing Assertions

```text
smalltalk → no state mutation
mobile_leakage_triage → pocket_cockpit_patch + action_chips
visual_low_confidence_guidance → no confirmed visual facts
knowledge_general → no state mutation
knowledge_case_aware → no state mutation unless facts supplied
knowledge_case_mutating → State Gate
sheet_field_edit → State Gate
pending_slot_answer → no RAG, no Full Graph
rfq_brief_generation → RFQ Dispatch Policy
rfq_draft_insufficient → no brief generation
blocked_boundary → explicit boundary
complex_review_required → no final recommendation
```

---

## 28. Backend Implementation Requirements

Codex soll zuerst auditieren und bestehende Strukturen wiederverwenden.

### 28.1 Domain-Objekte

Falls nicht vorhanden, einführen oder minimal erweitern:

```text
AssistantTurnEnvelope
ChatReply
CockpitPatch
PocketCockpitPatch
ActionChip
CaseUnderstandingPatch
RFQBriefPatch
PendingQuestion
ReviewFlag
ComputedValue
KnownField
OpenPoint
KnowledgeNote
ConflictEnvelope
RFQStatus
TraceSummary
DisclaimerMode
ChatStylePolicy
SheetChangeEvent
VisualCandidate
ManufacturerFeedback
```

### 28.2 Beispiel Pydantic Schema

```python
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field

class ActionChip(BaseModel):
    label: str
    value: Optional[str] = None
    field: Optional[str] = None
    action: Optional[str] = None

class ChatReply(BaseModel):
    style: Literal[
        "senior_engineer_short",
        "mobile_triage",
        "visual_low_confidence_guidance",
        "knowledge_explainer",
        "case_aware_explainer",
        "measurement_guide",
        "rfq_confirmation",
        "rfq_one_pager_intro",
        "blocked_boundary",
        "smalltalk_fast",
        "ui_help",
        "sheet_comment",
        "conflict_resolution",
    ]
    markdown: str
    primary_question: Optional[dict[str, Any]] = None
    disclaimer_mode: Literal[
        "suppress_normal_turn",
        "ui_static_only",
        "rfq_required",
        "explicit_boundary_required",
    ] = "suppress_normal_turn"
    template_id: Optional[str] = None

class KnownField(BaseModel):
    field: str
    label: str
    value: Any
    unit: Optional[str] = None
    status: str
    origin: str
    approximate: bool = False
    requires_confirmation: bool = False

class ReviewFlag(BaseModel):
    key: str
    label: str
    severity: Literal["low", "medium", "high", "review"]
    reason: str

class ComputedValue(BaseModel):
    field: str
    label: str
    value: Any
    unit: Optional[str] = None
    formula: Optional[str] = None
    origin: Literal["calculated"] = "calculated"

class CockpitPatch(BaseModel):
    known_fields: list[KnownField] = Field(default_factory=list)
    computed_values: list[ComputedValue] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    open_points: list[dict[str, Any]] = Field(default_factory=list)
    active_question: Optional[dict[str, Any]] = None
    rfq_status: Optional[dict[str, Any]] = None
    knowledge_notes: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    visual_candidates: list[dict[str, Any]] = Field(default_factory=list)
    sketch_candidates: list[dict[str, Any]] = Field(default_factory=list)

class PocketCockpitPatch(BaseModel):
    recognized: list[dict[str, Any]] = Field(default_factory=list)
    critical: list[dict[str, Any]] = Field(default_factory=list)
    next_step: Optional[dict[str, Any]] = None
    rfq_status: Optional[str] = None
    details_available: bool = True
    collapsed_by_default: bool = True

class AssistantTurnEnvelope(BaseModel):
    chat_reply: ChatReply
    cockpit_patch: CockpitPatch = Field(default_factory=CockpitPatch)
    pocket_cockpit_patch: Optional[PocketCockpitPatch] = None
    # P0-3 (2026-06-04, C7): case_understanding_patch / rfq_brief_patch removed —
    # inert stubs (no writer, no consumer). See §11 amendment.
    pending_question: Optional[dict[str, Any]] = None
    action_chips: list[ActionChip] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)
```

---

## 29. Frontend Implementation Requirements

### 29.1 Desktop Chat

Der Chat rendert primär:

```text
assistant_turn.chat_reply.markdown
```

Der Chat darf nicht selbst aus dem State einen langen Fallbericht generieren.

### 29.2 Desktop Cockpit

Das Cockpit rendert:

```text
assistant_turn.cockpit_patch
current_case_projection
```

Pflichtkarten:

```text
- Parameter / Fallnotiz
- Sheet / Parameter Editor
- Aktive Frage
- Review-Hinweise
- Offene Punkte
- Berechnete Werte
- Knowledge Notes
- Visual Candidates
- Konflikte
- RFQ-Status
```

### 29.3 Mobile Pocket Cockpit

Frontend rendert auf kleinen Viewports:

```text
assistant_turn.pocket_cockpit_patch
assistant_turn.action_chips
```

Regeln:

```text
- Pocket Cockpit sichtbar vor Detailtabs
- Action Chips direkt unter Frage
- Details eingeklappt
- RFQ-Status kurz sichtbar
- Kamera/Upload prominent
```

### 29.4 Persistenter UI-Hinweis

Desktop:

```text
Technische Vorqualifizierung und RFQ-Strukturierung. Finale Bewertung/Freigabe durch Hersteller oder verantwortliche Fachstelle.
```

Mobile:

```text
Vorqualifizierung. Finale Bewertung durch Hersteller/Fachstelle.
```

### 29.5 Sheet Events

Frontend muss strukturierte Events an Backend senden:

```json
{
  "event_type": "sheet_field_edit",
  "field": "speed_rpm",
  "value": 3000,
  "unit": "rpm",
  "source": "cockpit_sheet",
  "client_event_id": "uuid",
  "case_revision_seen": 4
}
```

### 29.6 Action Chip Events

```json
{
  "event_type": "action_chip_selected",
  "field": "shaft_rotates",
  "value": "yes",
  "source": "mobile_action_chip",
  "client_event_id": "uuid",
  "case_revision_seen": 2
}
```

---

## 30. Codex Implementation Plan

Codex soll audit-first und patchweise arbeiten.

### 30.1 Arbeitsweise

```text
1. Read-only Audit gegen dieses V1.6-Dokument.
2. Bestehende DTOs, Response-Pipeline, Routing, State Gate, Cockpit, Mobile Layout und Tests finden.
3. Gap-Liste mit Pfad + Zeilen + konkretem Verhalten erstellen.
4. Minimalen Patchplan erstellen.
5. Einen Patch pro Stufe umsetzen.
6. Nach jedem Patch Tests ausführen.
7. Keine wilden neuen Architekturen erfinden.
8. Bestehende Strukturen bevorzugen und nur minimal erweitern.
```

### 30.2 Patch-Reihenfolge

#### Patch 0 — Read-only Gap Audit

```text
Ziel:
Aktuellen Code gegen V1.6 mappen.

Output:
- vorhandene Antwortverträge
- vorhandene Case-State-Modelle
- vorhandene Chat/Cockpit-Komponenten
- vorhandene Mobile-Layouts
- vorhandene Prompt-/Template-Struktur
- vorhandene Tests
- Gap-Liste mit Pfad + Zeilen + Verhalten
```

#### Patch 1 — Output Envelope Foundation

```text
AssistantTurnEnvelope oder bestehendes Äquivalent erweitern:
chat_reply
cockpit_patch
pocket_cockpit_patch
action_chips
pending_question
trace
```

#### Patch 2 — Chat Style + Jinja2 Registry

```text
senior_engineer_short
smalltalk_fast
mobile_triage
visual_low_confidence_guidance
blocked_boundary
No-Go-Phrasen verhindern
normalen Disclaimer unterdrücken
```

#### Patch 3 — Pocket Cockpit + Action Chips

```text
Mobile UI Contract
Action Chip Events
Pocket Cockpit Rendering
No-empty-spinner Progress State
```

#### Patch 4 — CockpitPatch Rendering

```text
Known Fields
Review Flags
Open Points
Computed Values
Active Question
Knowledge Notes
Visual Candidates
Conflicts
RFQ Status
```

#### Patch 5 — Fast Path + Pending Slot + Action Chip State Gate

```text
pending_slot_answer
action_chip_selected
Tolerant parser
State Gate
no RAG/no Full Graph
```

#### Patch 6 — Mobile Leakage Triage

```text
Foto + sifft
mobile_leakage_triage
visual_low_confidence_guidance
Pocket Cockpit first useful output
```

#### Patch 7 — Knowledge Contract

```text
knowledge_general
knowledge_case_aware
knowledge_case_mutating
comparison_general
comparison_case_aware
norm_documentation_knowledge
why_question_active_case
```

#### Patch 8 — Sheet-Chat Contract

```text
sheet_field_edit
sheet_bulk_input
sheet_conflict_resolution
sheet_to_rfq
State Gate Integration
Frontend events
```

#### Patch 9 — RFQ One-Pager

```text
RFQ Dispatch Policy
RFQ DRAFT/MINIMAL/RFQ_WITH_OPEN_POINTS
Open points critical/helpful/optional
RFQ Snapshot by case_revision
```

#### Patch 10 — Golden Conversation Tests

```text
RWDR case
mobile foto + sifft
bad photo guidance
pending slot
why question
knowledge general
knowledge case-aware
knowledge mutating
sheet field
sheet bulk
smalltalk
final boundary
RFQ open points
RFQ DRAFT
human escalation
```

### 30.3 Codex Task Discipline

```text
- Nie „baue alles“ in einem Patch.
- Jeder Patch muss Tests enthalten oder begründen, warum nicht.
- Jede Änderung muss bestehende API/SSE-Kompatibilität prüfen.
- Jede neue DTO-Erweiterung muss serialisierbar und frontend-kompatibel sein.
- Jede neue UI-Funktion muss Desktop und Mobile nicht brechen.
```

---

## 31. Direct Codex App Task Prompt

```text
Task Summary
Implement sealingAI V1.6 Mobile-First Complete Architecture Blueprint from docs/sealing_intelligence_v1_6_mobile_first_complete_architecture_blueprint.md.

Goal
Make sealingAI a mobile-first, cockpit-first, knowledge-aware, sheet-aware Engineering Intelligence Workspace for sealing technology. The chat must guide; the desktop cockpit must document; the mobile pocket cockpit must compress; the sheet must structure; the RFQ one-pager must transfer; the State Gate must decide.

Input Context
The existing stack already includes backend routing, case state, frontend cockpit/dashboard, SSE/API contracts and tests. Do not invent a parallel architecture if equivalent structures already exist. First inspect the current code and map existing response contracts, frontend rendering, mobile behavior, State Gate, routing and tests.

Required Behavior
1. Normal case-building turns must not mirror the full case back in chat when the cockpit can display it.
2. Normal chat replies must use concise senior_engineer_short style.
3. Mobile case turns must use Pocket Cockpit + Action Chips where useful.
4. Foto + "sifft" must produce immediate mobile leakage triage, not a blank spinner.
5. Low-confidence vision must produce useful measurement/photo guidance, not product guesses.
6. Wissensfragen are chat-first and may be more explanatory.
7. Wissensfragen must not mutate case state unless the user provides new technical facts.
8. Sheet/Cockpit field edits must run through State Gate and update CockpitPatch.
9. Sheet edits should only produce chat output when technically relevant.
10. Smalltalk must be fast, friendly, and must not create or mutate a case.
11. RFQ can be generated with open points when a minimum viable RFQ core exists.
12. RFQ output should be a manufacturer-friendly one-pager, not a long AI report.
13. Final approval, guarantee or compliance requests must be clearly bounded.
14. Normal turns must not append liability disclaimers; use the persistent UI notice under the chat input.
15. State Gate must degrade field conflicts instead of blocking the whole case unless safety/compliance requires escalation.

Hard No-Go Chat Phrases For Normal Case-Building Turns
- "Ich verstehe den Fall aktuell als"
- "Technisch relevant sind hier vor allem"
- "Als Nächstes wäre die wichtigste Frage"
- "Grenze:"
- any final suitability/release wording

Golden Test Coverage
Add or update tests for:
- RWDR 45x62x8 Getriebe Öl 1500 rpm Staub undicht
- Mobile foto + "sifft"
- Low-confidence photo guidance
- pending slot "jo ca 3000"
- why-question "Warum fragst du nach der Welle?"
- knowledge_general "Was ist FFKM?"
- knowledge_case_aware "Was bedeutet FKM in meinem Fall?"
- knowledge_case_mutating "Wir verwenden FKM, Öltemperatur 100 °C"
- sheet_field_edit temperature 90 °C
- sheet_bulk_input speed/temperature/medium
- smalltalk "Hallo"
- final approval request
- RFQ despite missing data
- RFQ DRAFT insufficient minimum core
- complex_review_required for high-risk case

Implementation Instructions
1. Start with a read-only audit. Report path + line evidence.
2. Identify minimal patch path.
3. Preserve existing API/SSE compatibility where possible.
4. Implement small patches only.
5. Run backend tests relevant to routing/response/composer/state.
6. Run frontend tests relevant to chat/cockpit/pocket-cockpit/sheet rendering.
7. Run lint/type checks if available.
8. Report exact commands and results.

Expected Artifacts
- Audit summary
- Gap list
- Patch plan
- Changed files
- Tests added/updated
- Validation output
- Remaining gaps
```

---

## 32. Acceptance Criteria V1.6

V1.6 ist erfüllt, wenn:

```text
1. Der Beispiel-RWDR-Use-Case im Chat nicht wie ein KI-Protokoll klingt.
2. Der Chat den vollständigen Case nicht wiederholt.
3. Die erkannten Fakten im Cockpit sichtbar sind.
4. Auf Mobile wird ein Pocket Cockpit statt Desktop-Komplexität gezeigt.
5. Mobile Foto + "sifft" liefert innerhalb von <1 s sichtbaren Fortschritt.
6. Action Chips werden bei begrenzten Antworten angeboten.
7. Schlechte Fotos erzeugen Mess-/Foto-Führung statt falsche Erkennung.
8. Wissensfragen ausführlich und dichtungstechnisch beantwortet werden.
9. Wissensfragen ohne neue Fakten keinen Case mutieren.
10. Sheet-Eingaben durch State Gate laufen.
11. Sheet-Änderungen nicht unnötig im Chat kommentiert werden.
12. Smalltalk keinen Case erzeugt.
13. Pending Slot Antworten ohne RAG/Full Graph verarbeitet werden.
14. RFQ mit offenen Punkten möglich bleibt.
15. RFQ ohne Mindestkern als DRAFT blockiert und Mindestinput nennt.
16. RFQ-Brief als herstellerfreundlicher One-Pager erzeugt wird.
17. Finale Freigabe-/Compliance-Fragen sauber begrenzt werden.
18. Field-Konflikte nicht den ganzen Case blockieren.
19. Human Escalation nur bei echten Risiko-/Safety-/Compliance-Triggern greift.
20. Golden Conversations als Regressionstests existieren.
```

---

## 33. Final Product Sentence

```text
sealingAI wirkt nicht professionell, weil es viel erklärt.
sealingAI wirkt professionell, weil es schnell führt, mobil verdichtet, rechts sauber dokumentiert, strukturierte Eingaben ernst nimmt, Wissensfragen fachlich beantwortet und den Herstellerbrief sauber vorbereitet.
```

Oder als Systemleitsatz:

```text
Chat führt.
Pocket Cockpit verdichtet.
Cockpit dokumentiert.
Sheet strukturiert.
Knowledge erklärt.
RFQ übergibt.
State Gate entscheidet.
```

