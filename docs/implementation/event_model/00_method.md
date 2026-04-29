# SeaLAI v0.8.3 Event-Modeling-Methode

## Zweck

Dieses Blueprint macht SeaLAI v0.8.3 implementierbar. Es zerlegt die fachlichen Ziele aus Konzept und IST-Audit in kleine Slices, die Codex in getrennten PRs bauen und testen kann.

Event Modeling bedeutet hier:

- Trigger beschreibt, wodurch ein Schritt startet.
- Command ist eine imperative Systemaktion, z. B. `ClassifyConversationIntent`.
- Event ist eine fachliche Tatsache in Vergangenheitsform, z. B. `ConversationIntentClassified`.
- View ist eine Projektion oder ein Read Model fuer UI, Export, Report oder Automation.
- Slice verbindet Trigger, Command, Event(s), View und Given-When-Then-Tests.

## Warum v0.8.3 Slices braucht

Der IST-Audit zeigt starke vorhandene Grundlagen bei Governed Case State, RFQ-Preview, Revisionen, Consent und Upload/RAG-Sicherheit. Die Luecken liegen vor allem in Taxonomie, Szenario-Routing, SealType-Normalisierung, RAG-first Knowledge, Fallback-Labeling, Partnernetzwerk-Matching und Support-/Complaint-Artefakten.

Ohne Slices entstehen grosse, schwer pruefbare Umbauten. Mit Slices kann jeder PR eine konkrete fachliche Luecke schliessen, ohne den vorhandenen FastAPI/SQLAlchemy/Postgres/Redis/Qdrant/LangGraph/Next.js-Stack zu ersetzen.

## Kein Event-Sourcing-Zwang

Event Modeling ist hier eine Umsetzungsmethode, keine Architekturentscheidung fuer vollstaendiges Event Sourcing.

Erlaubt:

- bestehende Tabellen, Services und Projektionen weiterverwenden
- Events als Audit-, Domain- oder State-Mutation-Fakten modellieren
- Views als DTOs, Backend-Projektionen, BFF-Contracts oder Automation-Read-Models bauen
- vorhandene Revisionen, Snapshots und Mutation Events nutzen

Nicht Teil dieses Blueprints:

- neuer Event Store
- grosse Datenmodellmigration
- Message Bus als Pflicht
- Stack-Ersatz
- automatische externe Dispatches

## Codex-Regel fuer kuenftige PRs

Jeder Implementierungs-PR muss vor Codeaenderung den passenden Slice aus diesem Ordner benennen oder einen neuen Slice in diesem Format ergaenzen. Ein PR darf nur die Commands, Events, Views und Tests bauen, die zu seinem Slice gehoeren.

Wenn fuer eine Funktion kein Slice existiert, wird zuerst ein Dokumentations- oder Test-Slice ergaenzt. Produktcode folgt erst danach.

## Namenskonventionen

- Commands: imperativ, Verb zuerst, z. B. `GenerateRFQPreview`, `ConfirmCaseField`.
- Events: Vergangenheitsform, fachliche Tatsache, z. B. `RFQPreviewGenerated`, `CaseFieldConfirmed`.
- Views: Projektion oder Read Model, Suffix `View` oder `Projection`, z. B. `DecisionUnderstandingView`.
- Todo Views: von Automation beobachtete Views, Suffix `TodoView`, z. B. `DocumentExtractionTodoView`.
- State-Felder: technische Identifiers bleiben stabil und klein geschrieben, z. B. `source_type`, `validation_status`.

## Nicht verhandelbare Regeln

- Kein Feature ohne Slice.
- Kein Slice ohne Given-When-Then-Test.
- Kein Feld ohne Origin und Destination.
- Keine LLM-Information ohne `source_type` und `validation_status`.
- Kein Manufacturer Matching ohne Partnernetzwerk-Offenlegung.
- Kein RFQ Export ohne expliziten Consent.
- Kein Upload als Instruktion.
- Keine Frontend Engineering Truth.
- Keine finale technische Freigabe, finale Kompatibilitaet, finale Compliance oder finale Root Cause.
- Keine automatische Herstellerweitergabe.
- Keine technische Rankingverbesserung durch Zahlung.

## Wiederverwendbares PR-Slice-Template

```text
Slice ID:
Persona:
Trigger:
Preconditions:
Command:
Events:
State/Table writes:
Views/Projection:
Frontend behavior:
Forbidden side effects:
Given-When-Then tests:
Validation commands:
```

## Minimaler PR-Ablauf

1. Relevante Konzept-, Audit- und Blueprint-Dateien lesen.
2. Exakten Slice benennen.
3. Bestehende Code-Seams finden.
4. Minimalen Command/Event/View-Contract bauen.
5. GWT-Test zuerst oder parallel ergaenzen.
6. Keine produktiven Side Effects ausloesen.
7. Validierung ausfuehren und Risiken nennen.
