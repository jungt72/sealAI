# Paperless RAG Operating Convention

## 1. Zweck

Dieses Dokument definiert die produktive Betriebsregel fuer den bestehenden SealAI-Dokumentenworkflow:

- Upload oder Paperless-Sync fuehren in denselben kanonischen Ingestion-Pfad.
- `rag_documents` ist die kanonische Source of Truth fuer:
  - Dokumentstatus
  - Delta-/Aenderungserkennung
  - normierte Ingestion-Route (`route_key`)
  - Source-Provenance (`source_system`, `source_document_id`, `source_modified_at`)
- Qdrant und BM25 spiegeln diese Wahrheit nur fuer Retrieval.

Was ausdruecklich nicht mehr gemacht wird:

- keine operative Redis-Queue fuer den RAG-Pfad
- keine zweite Routing-Wahrheit in UI, Paperless oder Retrieval
- keine Datei-Endung als alleinige fachliche Route-Entscheidung
- keine Vollreingestion unveraenderter Paperless-Dokumente

## 2. Kanonischer Workflow

### Upload

`Upload -> rag_documents -> DB-Worker -> rag_ingest -> Qdrant/BM25 -> hybrid_retrieve`

Konkretes Verhalten:

- Upload legt oder aktualisiert einen `rag_documents`-Eintrag.
- `route_key` wird am Einstieg einmalig backendseitig bestimmt.
- Der Eintrag wird auf `processing` gesetzt.
- Der DB-pollende Worker verarbeitet den Eintrag.
- `rag_ingest` waehlt den Ingest-Pfad anhand von `route_key`.
- Qdrant und BM25 erhalten die normierten Metadaten.

### Paperless

`Paperless -> rag_documents -> DB-Worker -> rag_ingest -> Qdrant/BM25 -> hybrid_retrieve`

Konkretes Verhalten:

- Paperless-Sync ist ein Pull in denselben Backend-Pfad.
- `source_system=paperless`, `source_document_id` und `source_modified_at` werden in `rag_documents` gepflegt.
- `route_key` wird aus Paperless-Tags backendseitig bestimmt.
- Geaenderte Dokumente werden ueber denselben `rag_documents`-Eintrag erneut ingestiert.

### Delta-Verhalten

- Neues Dokument:
  - wird ingestiert
- Geaendertes Dokument:
  - wird erneut ingestiert
- Unveraendertes Dokument:
  - wird uebersprungen
- `rag_documents` bleibt die einzige Delta-/Status-SoT

### Route-Verhalten

- `product_datasheet` und `material_datasheet`:
  - spezialisierter PDF-Pfad
- `technical_knowledge`, `standard_or_norm`, `general_technical_doc`:
  - generischer Pfad

## 3. Finale Route-Taxonomie

### `product_datasheet`

Gehoert dazu:

- produktnahe Datenblaetter
- Dichtungstypen
- Produktserien- oder Typenbeschreibungen mit klarer Produktnaehe

Gehoert nicht dazu:

- reine Werkstoff-/Compounddatenblaetter
- Normen
- allgemeine Fachartikel

Ingest-Pfad:

- spezialisierter PDF-Pfad

Typische Beispiele:

- Wellendichtring-Datenblatt
- O-Ring-Produktdatenblatt
- Produktfamilienblatt eines Dichtungstyps

### `material_datasheet`

Gehoert dazu:

- Werkstoffdatenblaetter
- Compounddatenblaetter
- polymer- oder materialnahe technische Stammdokumente

Gehoert nicht dazu:

- Produktkataloge ohne Werkstofffokus
- Normen
- allgemeine technische Ratgeber

Ingest-Pfad:

- spezialisierter PDF-Pfad

Typische Beispiele:

- PTFE-Compounddatenblatt
- FKM-Materialdatenblatt
- Werkstoffspezifikation eines Compounds

### `technical_knowledge`

Gehoert dazu:

- Fachwissen
- Application Notes
- technische Leitfaeden
- Engineering-Hintergrunddokumente

Gehoert nicht dazu:

- bindende Normen
- produkt- oder werkstoffspezifische Datenblaetter

Ingest-Pfad:

- generischer Pfad

Typische Beispiele:

- Application Note zur Dichtungsauslegung
- Leitfaden zu Reibung und Verschleiss
- technischer Engineering-Guide

### `standard_or_norm`

Gehoert dazu:

- Normen
- Standards
- Spezifikationen mit normativem Charakter

Gehoert nicht dazu:

- allgemeine Fachartikel
- Produktbroschueren
- werkstoffnahe Herstellerdatenblaetter

Ingest-Pfad:

- generischer Pfad

Typische Beispiele:

- DIN-/EN-/ISO-Dokument
- ASME- oder VDI-Standard
- technische Spezifikation mit Normcharakter

### `general_technical_doc`

Gehoert dazu:

- sonstige technische Dokumente ohne klaren Produkt-, Material- oder Normschwerpunkt
- generische technische PDFs

Gehoert nicht dazu:

- Dokumente mit klarer Zuordnung zu einer der vier anderen Routen

Ingest-Pfad:

- generischer Pfad

Typische Beispiele:

- Lieferanteninfo mit technischem Kontext
- technische Broschuere ohne klare Route
- allgemeines Hersteller-PDF

## 4. Finale Paperless-Tag-Konvention

### Grundregel

Pro Dokument genau ein explizites `route:*`-Tag setzen.

Erlaubte Route-Tags:

- `route:product_datasheet`
- `route:material_datasheet`
- `route:technical_knowledge`
- `route:standard_or_norm`
- `route:general_technical_doc`

### Optional beschreibende Tags

Diese Tags sind zulaessig und hilfreich, entscheiden aber nicht bindend ueber die Route:

- Hersteller-/Lieferantentags
  - `freudenberg`
  - `skf`
  - `simrit`
- Fachgebietstags
  - `ptfe`
  - `fkm`
  - `tribology`
  - `emissions`
- Nutzungstags
  - `application_note`
  - `guide`
  - `supplier`
  - `compound`

### Route erzwingen

Nur `route:*`-Tags gelten als explizite Routen-Erzwingung.

### Zu vermeidende Tags

Diese Tags sollten nicht als alleinige fachliche Steuerung benutzt werden:

- `product`
- `material`
- `standard`
- `pdf`
- `technical_doc`

Grund:

- sie koennen Keyword-Fallbacks triggern, sind aber im Betrieb weniger eindeutig als ein explizites `route:*`-Tag

### Mischdokumente

Bei Mischdokumenten gilt:

- route nach primaerem Retrieval-Zweck setzen
- nicht nach Nebenkapitel

Beispiele:

- Produktdatenblatt mit kleinem Normhinweis:
  - `route:product_datasheet`
- Application Note mit Materialbeispielen:
  - `route:technical_knowledge`
- Spezifikation mit Herstellerlogo, aber normativem Fokus:
  - `route:standard_or_norm`

### Default-Verhalten ohne klare Route

Wenn kein explizites `route:*`-Tag gesetzt ist und auch Kategorie/Filename nicht klar sind:

- Default ist `general_technical_doc`

### 10 konkrete Praxisbeispiele

1. `route:product_datasheet, freudenberg, rotary_seal`
2. `route:material_datasheet, ptfe, compound, supplier`
3. `route:technical_knowledge, application_note, tribology`
4. `route:standard_or_norm, din, emissions`
5. `route:general_technical_doc, supplier, brochure`
6. `route:product_datasheet, oring, fkm`
7. `route:material_datasheet, nbr, material`
8. `route:technical_knowledge, guide, installation`
9. `route:standard_or_norm, iso, specification`
10. `route:general_technical_doc, manufacturer, technical_info`

## 5. Betriebsregeln

### Neues Dokument

- in Paperless hochladen oder direkt per Upload einstellen
- genau ein `route:*`-Tag setzen, falls Paperless genutzt wird
- Sync oder Upload ausloesen
- Dokument landet in `rag_documents` und wird vom Worker verarbeitet

### Geaendertes Dokument

- wenn `source_document_id` gleich bleibt und Quelle oder Inhalt geaendert ist:
  - Reingest ueber denselben `rag_documents`-Eintrag

### Unveraendertes Dokument

- wird nicht erneut ingestiert

### Falsch getaggtes Dokument

- Tag in Paperless korrigieren
- Dokument aendern oder Reingest anstossen
- die korrigierte Route ersetzt die alte normierte `route_key`

### Reingest

- Reingest ist nur fuer geaenderte oder falsch klassifizierte Dokumente gedacht
- Unveraendertes Dokument nicht kuenstlich erneut ingestieren

### Standards/Normen

- immer `route:standard_or_norm`
- nicht ueber Produkt- oder Materialroute einsortieren

### Fachwissen / Application Notes

- immer `route:technical_knowledge`
- auch dann, wenn Material- oder Produktbeispiele enthalten sind

### Produktdatenblaetter

- immer `route:product_datasheet`
- gilt fuer produktnahe, typnahe, seriennahe Dokumente

### Werkstoff-/Compounddatenblaetter

- immer `route:material_datasheet`
- gilt fuer material- oder compoundzentrierte Dokumente

## 6. Troubleshooting

### Dokument wird nicht ingestiert

- pruefen, ob ein `rag_documents`-Eintrag angelegt wurde
- pruefen, ob `status` auf `processing` oder `indexed` wechselt
- pruefen, ob der Worker laeuft

### Dokument landet im falschen Pfad

- `route_key` im `rag_documents`-Eintrag pruefen
- Paperless-Tags pruefen
- sicherstellen, dass genau ein explizites `route:*`-Tag gesetzt ist

### Retrieval findet Dokument nicht

- pruefen, ob Dokument `indexed` ist
- pruefen, ob Qdrant/BM25-Metadaten vorhanden sind
- pruefen, ob Retrieval-Filter auf `route_key`, `category`, `tags`, `source_system` zu eng sind

### Dokument wurde trotz Aenderung nicht neu verarbeitet

- pruefen, ob `source_modified_at` oder Dateiinhalte sich real geaendert haben
- pruefen, ob das Dokument ueber dieselbe `source_document_id` erkannt wurde

### Falsche oder fehlende Tags

- Tag-Konvention korrigieren
- danach Reingest ausloesen oder Quelle erneut aendern

## 7. Freeze-Hinweis

Der technische Kernpfad dieses Workflows ist abgeschlossen:

- `rag_documents` bleibt die kanonische SoT
- `route_key` bleibt die normierte Route-Wahrheit
- der DB-Worker bleibt der einzige operative Verarbeiter
- der RAG-Pfad wird nicht weiter architektonisch umgebaut

Weitere Aenderungen an diesem Kernpfad sollten nur noch erfolgen bei:

- echten Bugs
- klar abgegrenzter Scope-Erweiterung
- bewusst freigegebenem Folgeprojekt
