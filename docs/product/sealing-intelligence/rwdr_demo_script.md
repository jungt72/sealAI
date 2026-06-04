# RWDR MVP Demo Script

## Demo-Ziel

Zeigen, dass `sealing | Intelligence` aus einer unklaren RWDR-Anfrage einen versionierten, exportierbaren `Technical RWDR RFQ Brief` als Grundlage für Herstellerbewertung erstellt.

Kernsatz:

> sealing | Intelligence gibt keine Dichtung frei. Es macht die Anfrage für Hersteller bewertbar.

Ergänzende Einordnung:

> Das System strukturiert bestätigte Angaben, fehlende Informationen, berechnete Werte und Herstellerfragen.

> Material-, Bauform- und Herstellerbewertung bleiben beim Hersteller, Händler oder verantwortlichen Experten.

## Demo-Persona

Instandhaltung, technischer Einkauf oder technischer Vertrieb mit einer eiligen und unvollständigen Anfrage zu einem undichten Radialwellendichtring.

## Demo-Input

```text
Wellendichtring 45x62x8 undicht, Getriebe, Öl, 1500 U/min, staubige Umgebung, dringend.
```

## 5-Minuten-Demo

1. RWDR-Anfrage in den Eingabebereich einfügen.
2. Extrahierte Felder mit Quellenstellen zeigen:
   - `45x62x8`
   - `Getriebe`
   - `Öl`
   - `1500 U/min`
3. Erklären: KI extrahiert, der Nutzer bestätigt.
4. d1/D/b, Anwendung, Medium, Drehzahl und Abdichtaufgabe bestätigen.
5. Druck, Temperatur und Wellenzustand offen lassen oder als unbekannt markieren.
6. `Technical RWDR RFQ Brief` erstellen.
7. `NEEDS_CLARIFICATION` zeigen.
8. Umfangsgeschwindigkeit ca. `3,53 m/s` zeigen.
9. Kritisch fehlende Angaben und Herstellerfragen zeigen.
10. PDF-/Markdown-Export zeigen.

## 10-Minuten-Demo

1. Mit dem 5-Minuten-Ablauf starten.
2. Quellenübersicht erklären: bestätigte extrahierte Felder behalten ihre exakte Quellenstelle.
3. Messhinweise zeigen:
   - Gehäusebohrung D: Innenmessgerät / 3-Punkt-Bore-Gauge
   - Rundlauf: Messuhr
   - Rauheit: Tastschnitt-Profilometer
4. Snapshot-Historie öffnen.
5. Erste Revision mit Export-Revision vergleichen.
6. Erklären, dass Revisionen auditierbar machen, wann Felder bestätigt, verworfen oder als unbekannt markiert wurden.
7. PDF öffnen und folgende Punkte zeigen:
   - Case-ID
   - Revision
   - Status
   - fehlende kritische Angaben
   - berechnete Werte
   - Herstellerfragen
   - Disclaimer
8. Mit der Feedback-Checkliste abschließen.

## Was anklicken?

- Anfragefeld: Demo-Input einfügen.
- Analyse starten.
- Bei jeder liability-bearing Angabe: `Bestätigen`, `Bearbeiten`, `Nicht angegeben / unbekannt` oder `Verwerfen`.
- Brief erstellen.
- Export öffnen.
- Revisionen anzeigen.
- Zwei Revisionen auswählen und vergleichen.

## Was betonen?

- Das System erzeugt keine technische Endentscheidung.
- Der Nutzer entscheidet, welche extrahierten Angaben bestätigt sind.
- Unbestätigte Angaben bleiben offen und werden nicht als bestätigte Fakten exportiert.
- Der Brief reduziert Rückfrageschleifen, indem fehlende Angaben und Messhinweise klar sichtbar werden.
- Hersteller, Händler oder verantwortliche technische Stelle bewerten final.

## Was nicht behaupten?

- Keine Materialentscheidung.
- Keine Produktauswahl.
- Keine Herstellerwahl.
- Keine technische Endentscheidung.
- Keine Aussage, dass eine konkrete Dichtung funktioniert.
- Keine Aussage, dass ein Werkstoff für die Anwendung bewertet wurde.

## Erwartete Fragen und sichere Antworten

**Kann der Brief direkt an den Hersteller gehen?**  
Ja, als strukturierte Anfragegrundlage. Er ersetzt keine Herstellerbewertung.

**Warum müssen Felder bestätigt werden?**  
Weil Maße, Medium, Druck, Temperatur und Drehzahl haftungsrelevante Angaben sind. Das System übernimmt extrahierte Werte nicht stillschweigend.

**Was passiert mit unbekannten Angaben?**  
Sie erscheinen als offene oder fehlende Angaben. Das kann den Status `NEEDS_CLARIFICATION` auslösen.

**Warum ist der Fall nicht automatisch vollständig?**  
Für RWDR-Anfragen fehlen oft Druck, Temperatur, Wellenzustand, Einbausituation oder genaue Medienangaben.

**Gibt das System Werkstoff- oder Bauformvorschläge?**  
Nein. Es listet Review-Themen und Fragen für Herstellerbewertung.

**Was ist der Nutzen für technische Vertriebs- oder Anwendungsteams?**  
Die Anfrage kommt strukturierter an: bestätigte Angaben, offene Punkte, Messhinweise, berechnete Werte und Quellen sind getrennt.

## Erwartetes Ergebnis

Die Demo endet mit einem `Technical RWDR RFQ Brief`, der bestätigte Angaben, unbestätigte Angaben, kritisch fehlende Angaben, berechnete Werte, Review-Themen, Messhinweise, Herstellerfragen, Quellenübersicht, Export-Metadaten und den Disclaimer enthält.
