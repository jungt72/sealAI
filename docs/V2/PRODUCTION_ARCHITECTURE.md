# sealingAI V2 Production Architecture

Stand: 2026-07-10. Dieses Dokument beschreibt den produktiven Soll- und Ist-Vertrag. Historische
Eval-Berichte bleiben als Messartefakte erhalten und sind keine aktuelle Systembeschreibung.

## Architekturentscheidung

sealingAI ist ein modularer Monolith mit einem separaten, langlebigen Worker:

- FastAPI API-Prozess fuer synchrone Nutzerinteraktion
- Worker fuer Outbox, Ingestion und Index-Synchronisierung
- Postgres als fachliches System of Record
- Qdrant als vollstaendig abgeleiteter Dense-/Sparse-Retrieval-Index
- Paperless/Object-Storage-Lane fuer unveraenderliche Originaldokumente
- Keycloak fuer Identitaet und Tenant-Kontext
- Prometheus fuer Betriebsmetriken; LangSmith nur mit metadatenbasierter, produktionssicherer
  Redaction

Microservices und LangGraph sind fuer den bekannten Fachprozess bewusst nicht Teil des Onlinepfads.
Der Ablauf ist ein deterministischer DAG; Framework-Orchestrierung wuerde hier zusaetzliche
Fehler-, Versions- und Tracingflaechen schaffen, ohne fachliche Variabilitaet zu loesen.

## Onlinepfad

1. JWT und Tenant fail-closed validieren.
2. revisionierten `CaseStateV2` laden; Chattranskript ist nicht die fachliche Wahrheit.
3. deterministisch routen und bekannte Pflichtfeldluecken vor Retrieval beantworten.
4. freigegebene Claims aus Postgres ueber den aus Postgres ableitbaren Qdrant-Index laden.
5. Berechnungen und Grenzpruefungen deterministisch ausfuehren.
6. einmalig D0/D1/S0/S1/C1/C2/H1 waehlen.
7. hoechstens ein passendes Antwortmodell aufrufen; C1/C2 gehen direkt zum Frontier-Tier.
8. internes `TechnicalAnswer` per nativem JSON Schema erzeugen und lokal semantisch validieren.
9. unbekannte Evidenz-IDs oder Schemafehler hoechstens einmal reparieren, danach abbrechen.
10. sichtbaren deutschen Text deterministisch rendern und alle deterministischen Guards ausfuehren.
11. nur bei S1 die technischen Claims durch den selektiven LLM-Verifier pruefen.
12. Turn, Revision, Policy, Modell-Tier und Reviewstatus atomar protokollieren.

## Modellpolitik

- Standard: `mistral-small-2603`, Reasoning `none` oder `high` nach Policy.
- Frontier: konfigurierbares, eval-gebundenes OpenAI-Modell; aktuell `gpt-5.5`.
- Verifier: Mistral Small 4 im selektiven S1-Pfad.
- Keine Router-LLM-Selbsteinschaetzung und keine feste L1/L3-Kaskade fuer jeden Turn.
- Keine erfundenen oder Preview-spezifischen Modellnamen im Produktionsvertrag. Neue Modelle werden
  erst nach sealingAI-eigenem Champion/Challenger-Replay aktiviert.

Providerclients sind pro Anbieter geteilt, begrenzen Parallelitaet, takten Aufrufstarts und beachten
Provider-Reset-Header. Offene Retry-Schleifen sind verboten.

## Evidenz und Wissen

Dokumentversionen, Claims, Review-Events und der Qdrant-Outbox-Zustand liegen in Postgres. Automatisch
extrahierte Claims beginnen als Draft und koennen einen menschlich geprueften Claim nicht
herabstufen. Qdrant-Treffer werden vor Verwendung gegen den Ledger revalidiert. Der Index kann aus
Postgres neu aufgebaut werden.

## Cache und Streaming

Der D0-Cache ist nur fuer exakt gleiche, vollstaendig validierte Low-Risk-Wissensantworten ohne Case
State, Risk Flag oder untrusted Content zulaessig. Der Key bindet Tenant, Wissensstand, Policy,
Standardmodell und strukturierte Antwortversion. Fallbezogene oder semantisch aehnliche Antworten
werden nicht gecacht.

SSE ist ueber `X-SealingAI-Stream-Version: 1` versioniert. S0-Smalltalk darf finale Deltas streamen;
strukturierte oder risikoreiche Antworten streamen Status und liefern das Ergebnis atomar nach
Validierung. Das Frontend lehnt unbekannte Streamversionen ab.

## Releasevertrag

Ein V2-Release erfordert:

- sauberen, exakten Git-Commit und unveraenderliches OCI-Image mit Revision und Tree-Hash
- ueber GitHub Actions signierte und beim Deploy tokenfrei per Sigstore/Rekor
  verifizierte SLSA-Provenance und SPDX-2.3-SBOM
- gruenen Python-/Frontend-/Architekturvertrag
- adjudizierten Eval-REPLAY fuer exakt denselben Tree-Hash, L1 und Runtime-Profile-Hash
- geprueftes Backup, Alembic-Migration, Ledger-Bootstrap und vollstaendig geleerte Index-Outbox
- internen und oeffentlichen Health-Smoke, Worker-Smoke, Kernel-Smoke und Restart-Smoke
- Deployment-Ledger mit Rollback-Image und Backupreferenz

Der Runtime-Profile-Hash wird aus dem aufgeloesten Compose-Service berechnet, damit Compose-Defaults
und reale Containerumgebung identisch an den Replay gebunden sind.
