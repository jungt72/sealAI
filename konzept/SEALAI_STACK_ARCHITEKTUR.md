# SeaLAI — Runtime & Infrastructure Reference

**Version:** 3.0  
**Datum:** 2026-04-16  
**Status:** REFERENCE ONLY — Runtime & Infrastructure Authority  
**Geltungsbereich:** Infrastruktur, Laufzeit, Service-Topologie, Deployment, Ops, technische Betriebsgrenzen

> Dieses Dokument beschreibt ausschließlich die physische und logische Laufzeitumgebung von SeaLAI.
> Es ist **nicht** die bindende Quelle für Domain-Logik, Request-Typen, Engineering-Pfade,
> Datenmodell, Risk Scores, Readiness, Output Classes oder Implementierungsreihenfolge.
>
> **Verbindliche Hierarchie:**
> 1. `konzept/sealai_ssot_architecture_plan.md` — einzige bindende Architektur-SSoT
> 2. `AGENTS.md` — bindender Arbeitsvertrag für Codex
> 3. `konzept/SEALAI_KONZEPT_FINAL.md` — abgeleitetes Produkt- und Business-Konzept
> 4. `konzept/SEALAI_STACK_ARCHITEKTUR.md` — Runtime- und Infrastruktur-Referenz

---

## 1. Zweck dieses Dokuments

Dieses Dokument dient als technische Referenz für:

- Service-Landschaft
- Runtime-Topologie
- Netzwerk- und Integrationsgrenzen
- Authentifizierung und Sitzungsführung
- RAG-Infrastruktur
- PDF-/Export-Infrastruktur
- Monitoring / Observability
- Deployment- und Ops-Rollen
- technische Betriebsannahmen

Dieses Dokument dient **nicht** als Quelle für:

- fachliche Routing-Logik
- Request-Type-Logik
- Engineering-Pfade
- Norm-Gates
- Chemical Compatibility
- RCA / Retrofit / Risk Engine
- Output-Claim-Grenzen
- Readiness / RFQ-Regeln
- Codex-Implementierungsreihenfolge

Für diese Inhalte gilt ausschließlich die SSoT.

---

## 2. Systemrolle von SeaLAI

SeaLAI ist ein webbasiertes System für:

- technische Interaktion via Chat + Cockpit
- strukturierte Fallbearbeitung
- engineering-nahe Datenaggregation
- norm- und pfadbezogene Vorqualifikation
- Herstelleranfrage-Vorbereitung
- PDF-/JSON-Artefakterzeugung
- dokumentengestützte Wissensnutzung via RAG

Die Laufzeitarchitektur trennt sauber zwischen:

- **Benutzeroberfläche**
- **API / Orchestrierung**
- **State / Persistenz**
- **Dokumenten- und Wissensschicht**
- **Export-/Artefakt-Schicht**
- **Monitoring / Betrieb**

---

## 3. Verbindliche Infrastrukturprinzipien

### 3.1 Backend-first
Die fachliche Wahrheit liegt im Backend.  
Frontend ist Renderer, Interaktionsschicht und Cockpit-Projektion.

### 3.2 Service-Trennung
SeaLAI trennt bewusst zwischen:
- API / LangGraph / Domain Engine
- Session / Checkpoint / Cache
- relationaler Persistenz
- Vektor-Retrieval
- Dokumentenmanagement
- PDF-Rendering
- Identity / Auth
- Monitoring

### 3.3 Dokumente sind Datenquellen, keine Instruktionen
Dokumenteninhalt wird extrahiert, versioniert und als Daten behandelt.
Dokumente dürfen keine Instruktionsquelle für das Orchestrierungssystem sein.

### 3.4 Runtime-Dokument ist untergeordnet
Dieses Dokument beschreibt, **wie** das System läuft — nicht **was fachlich gilt**.

---

## 4. Service-Übersicht

| Service | Rolle | Bemerkung |
|---|---|---|
| `frontend` | Web-UI / Chat / Cockpit | Next.js-basierte Benutzeroberfläche |
| `backend` | API / Orchestrierung / Domain Runtime | FastAPI + LangGraph + Regel-/Berechnungsschicht |
| `nginx` | Reverse Proxy / TLS / Routing | öffentlicher Einstiegspunkt |
| `keycloak` | Auth / OIDC / JWT | Benutzer- und Rollenverwaltung |
| `redis` / `redis-stack-server` | Session / Checkpoint / Cache | Kurzfristiger Laufzeitstate, Graph-Checkpointing |
| `postgres` | persistente Geschäfts- und Audit-Daten | Cases, Snapshots, Audit, Konfigurationsbezug |
| `qdrant` | Vektorbasierte Wissenssuche | Hybrid Retrieval / Embeddings |
| `paperless-ngx` | Dokumentenverwaltung / RAG-Admin | Upload, Klassifikation, Tagging |
| `tika` | Dokumenten-Extraktion | Text-/OCR-nahe Extraktion |
| `gotenberg` | PDF-Erzeugung | Inquiry-/RFQ- und Berichtsdokumente |
| `prometheus` | Metrik-Sammlung | technische Betriebsmetriken |
| `grafana` | Dashboards / Visualisierung | Monitoring / Ops |
| `OpenAI API` | LLM-Ausführung | Sprachverstehen, Strukturierung, Rendering |

---

## 5. Gesamt-Topologie

```text
                         INTERNET
                             │
                     ┌───────▼────────┐
                     │     nginx      │
                     │ TLS · Routing  │
                     │ SSE Pass-Through│
                     └──┬──────────┬──┘
                        │          │
               ┌────────▼──┐  ┌────▼──────────────┐
               │ frontend  │  │     backend       │
               │ Next.js   │  │   FastAPI         │
               │ Chat+UI   │  │   LangGraph       │
               └────┬──────┘  └────────┬──────────┘
                    │                  │
         ┌──────────┴──────────────────┴────────────────────┐
         │                 Service Layer                    │
         │                                                  │
         │  ┌─────────────┐   ┌──────────────────────────┐  │
         │  │    Redis    │   │         Qdrant           │  │
         │  │ checkpoint  │   │ vector retrieval / RAG   │  │
         │  │ session     │   └────────────┬─────────────┘  │
         │  │ cache       │                │                │
         │  └─────────────┘                │                │
         │                                 │                │
         │  ┌─────────────┐   ┌────────────▼─────────────┐  │
         │  │ PostgreSQL  │   │      Paperless-ngx       │  │
         │  │ cases       │   │ docs / tags / admin      │  │
         │  │ audit       │   └────────────┬─────────────┘  │
         │  │ snapshots   │                │                │
         │  └─────────────┘         ┌──────▼──────┐         │
         │                          │    Tika     │         │
         │                          │ extraction  │         │
         │                          └─────────────┘         │
         │                                                  │
         │  ┌─────────────┐   ┌──────────────────────────┐  │
         │  │ Gotenberg   │   │ Keycloak                 │  │
         │  │ PDF render  │   │ OIDC / JWT / roles       │  │
         │  └─────────────┘   └──────────────────────────┘  │
         │                                                  │
         │  ┌─────────────┐   ┌──────────────────────────┐  │
         │  │ Prometheus  │   │ Grafana                  │  │
         │  │ metrics     │   │ dashboards               │  │
         │  └─────────────┘   └──────────────────────────┘  │
         └──────────────────────────────────────────────────┘
                              │
                     ┌────────▼────────┐
                     │   OpenAI API    │
                     │ LLM execution   │
                     └─────────────────┘
```

---

## 6. Laufzeitrollen der Hauptkomponenten

### 6.1 Frontend

Frontend ist verantwortlich für:

- Chat-Eingabe und -Darstellung
- Cockpit- und Fallvisualisierung
- Rendering von Status, Blockern, Provenienz und Progress
- Starten von UI-Aktionen
- SSE-Konsum
- Auth-Session-gebundene Benutzerinteraktion

Frontend ist nicht verantwortlich für:

- fachliche Pfadentscheidung
- Risk Score Berechnung
- Readiness-Berechnung
- Normaktivierung
- RFQ-Reife-Festlegung

### 6.2 Backend

Backend ist verantwortlich für:

- API-Exposition
- Orchestrierung
- Regel- und Berechnungslogik
- Zustandsübergänge
- Persistenzintegration
- RAG-Abfragen
- Output-Kontrolle
- Exportvorbereitung
- Audit- und Revisionslogik

### 6.3 nginx

nginx ist verantwortlich für:

- TLS-Termination
- Reverse Proxy
- Routing zu Frontend / Backend
- SSE-kompatibles Pass-Through
- Header- und Timeout-Management
- technische Zugangskontrolle auf Infrastruktur-Ebene

### 6.4 Redis

Redis ist verantwortlich für:

- Graph-/Session-Checkpointing
- kurzlebige Laufzeitdaten
- Cache-Funktionen
- idempotente Zwischenzustände, falls konfiguriert

### 6.5 PostgreSQL

PostgreSQL ist verantwortlich für:

- Cases
- Revisionen
- Snapshots
- Audit-Trail
- Export- und Inquiry-Metadaten
- längerfristige, relationale Systemdaten

### 6.6 Qdrant

Qdrant ist verantwortlich für:

- semantische Dokumentrepräsentation
- RAG-Retrieval
- Hybrid-/Vektor-Suche
- dokumentenbezogene Evidence-Retrieval-Funktionen

### 6.7 Paperless-ngx

Paperless ist verantwortlich für:

- Dokumentaufnahme
- Dokumentorganisation
- Tagging
- RAG-Admin-Workflow
- Wissensbasis-Pflege durch Admins

### 6.8 Tika

Tika ist verantwortlich für:

- Extraktion von Text aus Dokumenten
- OCR-nahe Vorverarbeitung / Inhaltsgewinnung
- technische Textbereitstellung für Ingestion

### 6.9 Gotenberg

Gotenberg ist verantwortlich für:

- HTML-zu-PDF-Rendering
- reproduzierbare Dokumenterzeugung
- inquiry-/report-nahe Artefakte

### 6.10 Keycloak

Keycloak ist verantwortlich für:

- Authentifizierung
- Rollen- und Clientverwaltung
- OIDC-/JWT-Flow
- zentrale Identitätsverwaltung

### 6.11 Prometheus / Grafana

Diese Komponenten sind verantwortlich für:

- technische Metriken
- Dashboarding
- Systembeobachtung
- Betriebsdiagnose

---

## 7. Hauptdatenflüsse

### 7.1 User Request Flow
```text
Browser
  → frontend
  → nginx
  → backend
  → LangGraph / domain runtime
  → Redis / Postgres / Qdrant / OpenAI
  → backend response
  → SSE / JSON zurück an frontend
```

### 7.2 Dokumenten-Ingestion-Flow
```text
Admin
  → Paperless Upload
  → Tagging / Dokumentverwaltung
  → Tika-Extraktion
  → Backend Ingest Trigger / Webhook
  → Chunking / Embedding
  → Qdrant Upsert
```

### 7.3 Inquiry-/PDF-Flow
```text
Case / State / Export request
  → backend export preparation
  → HTML render
  → Gotenberg PDF render
  → artifact persistence / caching
  → delivery / download / manufacturer handover
```

### 7.4 Auth-Flow
```text
User
  → frontend login
  → Keycloak
  → token issuance
  → frontend / backend authenticated requests
  → backend JWT validation
```

---

## 8. RAG-Infrastruktur

### 8.1 Rolle der RAG-Schicht

Die RAG-Schicht unterstützt SeaLAI bei:

- dokumentengestützter Evidenz
- Norm-/Hersteller-/Datenblatt-Kontext
- Material-/Medium-/Anwendungswissen
- herkunftsmarkierten Hinweisen

### 8.2 RAG ist nicht die Domain-SSoT

Die RAG-Schicht ist:

- Evidence- und Kontext-Layer

Sie ist nicht:

- direkte Regel-Engine
- direkte Freigabeinstanz
- Quelle finaler Confirmed-Werte ohne Promotion

### 8.3 Paperless-Tagging

Paperless darf strukturierte Tags tragen, z. B. für:

- Dokumenttyp
- Medium
- Material
- Dichtungstyp
- Normreferenzen
- Quelle
- Branche

Die genaue semantische Nutzung dieser Tags wird durch die bindende SSoT und die jeweils implementierte Ingestion-/Retrieval-Logik definiert.

---

## 9. PDF- und Export-Infrastruktur

### 9.1 Rolle

SeaLAI erzeugt strukturierte Artefakte als:

- PDF
- maschinenlesbarer JSON-Export
- inquiry-/RFQ-nahe Lieferobjekte

### 9.2 Gotenberg als Rendering-Dienst

Gotenberg ist nur der technische Renderer.
Die inhaltliche Struktur der Exporte wird nicht in diesem Dokument festgelegt, sondern in:

- SSoT
- Export-Contract
- Backend-Implementierung

### 9.3 Wichtige Betriebsanforderungen

- reproduzierbare Generierung
- stabile Templates
- Revisionsbezug
- technische Auditierbarkeit
- ggf. idempotente Generierung / Cache-Nutzung

---

## 10. Authentifizierung und Rollen

### 10.1 Auth-Prinzip

SeaLAI nutzt eine zentrale OIDC-/JWT-basierte Authentifizierung.

### 10.2 Rollenbeispiele

Die genaue Geschäftslogik je Rolle wird außerhalb dieses Dokuments festgelegt.
Infrastrukturseitig relevant sind Rollen wie:

- Endnutzer
- Hersteller
- Admin
- technische Betriebsrolle

### 10.3 Wichtige Anforderungen

- eindeutige Benutzeridentität
- Backend-validierte Tokens
- keine fachliche Autorisierung nur im Frontend
- rollenbezogener Zugang zu Admin-/Ingest-/Ops-Bereichen

---

## 11. Session, Checkpoints und Persistenz

### 11.1 Redis

Redis hält kurzlebige oder laufzeitkritische Zustände wie:

- Graph-Checkpoint
- Session-nahe Zustände
- Cache-Artefakte

### 11.2 PostgreSQL

Postgres hält:

- persistente Cases
- Revisionen
- Snapshots
- Audit
- Export-Referenzen
- Inquiry-/Delivery-Metadaten

### 11.3 Prinzip

Kurzfristige Laufzeitverfügbarkeit und langfristige Nachvollziehbarkeit sind getrennt.

---

## 12. SSE und Streaming

### 12.1 Rolle

Streaming ist zentral für:

- natürliches Chat-Erlebnis
- Progress-Signale
- Cockpit-Aktualisierung
- kontrolliertes Rendering

### 12.2 Infrastruktur-Anforderung

SSE darf nicht durch Proxy-Buffering zerstört werden.

### 12.3 nginx-Anforderung

nginx-Konfiguration muss:

- Buffering für relevante Streaming-Pfade deaktivieren
- Read-Timeouts passend setzen
- HTTP/1.1 und Header korrekt weitergeben
- kein stilles Caching für Event Streams erzwingen

---

## 13. Monitoring und Observability

### 13.1 Ziele

- technische Sichtbarkeit
- Fehlerdiagnose
- Performance-Überwachung
- Kosten-/Latenztransparenz
- Ingestion-/RAG-Gesundheit
- Service-Verfügbarkeit

### 13.2 Metrikbereiche

- API-Latenzen
- LLM-Latenzen
- Request-Verteilung
- Redis-/Checkpoint-Gesundheit
- Qdrant-Nutzung
- Paperless-/Ingestion-Freshness
- Export-/PDF-Erfolgsrate
- Fehlerklassen
- ggf. Business-nahe technische Conversion-Metriken

### 13.3 Tracing

LangGraph-/LLM-nahe Traces und technische Request-Traces sollen sauber korrelierbar sein.

---

## 14. Deployment-Grundsätze

### 14.1 Service-Isolation

Services bleiben logisch getrennt und über klar definierte Schnittstellen verbunden.

### 14.2 Build-/Release-Prinzip

Deployments erfolgen reproduzierbar und mit nachvollziehbarer Konfigurationsbasis.

### 14.3 Keine Domain-Wahrheit in Deploy-Dateien

docker-compose, nginx, .env, Release-Skripte und Runtime-Konfiguration definieren:

- Infrastruktur
- Dienste
- Modell-/Runtime-Defaults
- Adressen / Secrets / Features

Sie definieren nicht die fachliche Architekturwahrheit.

---

## 15. Sicherheitsprinzipien

### 15.1 Dokumente

- Uploads isoliert behandeln
- Parsing begrenzen
- Dokumente nicht als Prompt-Instruktionen behandeln
- Raw / Extracted / Derived logisch trennen

### 15.2 Secrets

- keine Secrets im Code
- Konfiguration über Umgebungsvariablen / Secret-Management
- Admin-/Service-Tokens getrennt verwalten

### 15.3 API / Netzwerk

- interne Dienste nicht unnötig öffentlich exponieren
- Admin-Pfade schützen
- externe Angriffsfläche klein halten

---

## 16. Was dieses Dokument ausdrücklich nicht regelt

Dieses Dokument regelt nicht:

- Request Types
- Engineering Paths
- Output Classes
- Phase Gates
- State Regression
- Formula Library
- Risk Scores
- Readiness
- Chemical Compatibility
- RCA / Retrofit Handover
- Normmodule
- Manufacturer Matching Logik
- RFQ-Fachregeln

Dafür gilt ausschließlich:
`konzept/sealai_ssot_architecture_plan.md`

---

## 17. Dokumentenpflege-Regel

Wenn sich:

- Service-Landschaft
- Runtime-Topologie
- Deploy-Logik
- Auth-/RAG-/PDF-/Monitoring-Infrastruktur

ändern, dann wird dieses Dokument aktualisiert.

Wenn sich dagegen ändern:

- fachliche Routing-Regeln
- Datenmodell
- Output-/Risk-/Readiness-Regeln
- Norm-Gates
- RCA-/Retrofit-/Compatibility-Logik

dann wird nicht dieses Dokument, sondern die SSoT aktualisiert.

---

## 18. Schlussregel

`SEALAI_STACK_ARCHITEKTUR.md` beschreibt, wie SeaLAI läuft.
Die SSoT beschreibt, wie SeaLAI fachlich denkt und entscheidet.

Nur wenn diese Trennung sauber bleibt, bleibt Codex eindeutig geführt und das System langfristig wartbar.
