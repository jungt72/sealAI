# RAG System Audit Report — SealAI
**Datum:** 2026-02-23 | **Auditor:** Claude Code (Sonnet 4.6) | **Version:** v4.4.0 (Sprint 9)

---

## 1. Projekt-Übersicht

- **Name**: SealAI — KI-Consulting-Plattform für Dichtungstechnik (hydraulisch/pneumatisch)
- **Beschreibung**: Multi-Agenten-System für die Bedarfsanalyse, Materialempfehlung und Beschaffung von technischen Dichtungen. Nutzt hybride RAG-Suche (Qdrant + BM25) für domänenspezifisches Wissen.
- **Tech Stack**:
  - **Backend**: Python 3.x · FastAPI 0.128 · LangGraph v2 1.0.1 · LangChain 1.0.2 · OpenAI API (gpt-4.1-mini / gpt-5-large)
  - **Vektordatenbank**: Qdrant v1.16.0
  - **Embeddings**: BAAI/bge-base-en-v1.5 (FastEmbed) + Splade_PP_en_v1 (Sparse)
  - **Reranker**: cross-encoder/ms-marco-MiniLM-L-6-v2
  - **Datenbank**: PostgreSQL 15 (Metadata, Long-Term Memory, Audit Log)
  - **Cache**: Redis Stack 7.4.0 (Checkpointing + BM25-Index)
  - **Frontend**: Next.js 16 · NextAuth v5 · Tailwind CSS
  - **Auth**: Keycloak OIDC (JWT)
  - **Proxy**: Nginx 1.29.4 (SSL, Reverse Proxy)
  - **Observability**: Prometheus · LangSmith · Postgres Audit Log

### Ordnerstruktur (Tree-View)

```
sealai/
├── backend/
│   ├── app/
│   │   ├── main.py                          # FastAPI App-Factory, Startup, Middleware
│   │   ├── api/v1/
│   │   │   ├── api.py                       # Router-Aggregator (10 Routers)
│   │   │   └── endpoints/
│   │   │       ├── langgraph_v2.py          # Chat SSE Endpoint
│   │   │       ├── rag.py                   # Dokument Upload/Management
│   │   │       ├── mcp.py                   # Model Context Protocol
│   │   │       └── auth.py, chat_history.py, memory.py, rfq.py, users.py
│   │   ├── langgraph_v2/                    # Kern-KI-Engine
│   │   │   ├── sealai_graph_v2.py           # Graph-Kompilierung & Cache
│   │   │   ├── contracts.py                 # STABLE_V2_NODE_CONTRACT
│   │   │   ├── state/sealai_state.py        # SealAIState Pydantic Model
│   │   │   ├── nodes/                       # 12 Spezialisten-Nodes
│   │   │   │   ├── orchestrator.py
│   │   │   │   ├── profile_loader.py
│   │   │   │   ├── nodes_supervisor.py      # Policy Routing (7 Aktionen)
│   │   │   │   ├── nodes_frontdoor.py       # Intent-Klassifizierung
│   │   │   │   ├── nodes_flows.py           # Spezialisten-Worker
│   │   │   │   ├── nodes_resume.py          # HITL Resume/Reject
│   │   │   │   └── reducer.py
│   │   │   └── tests/                       # Graph Contract & Integration Tests
│   │   ├── services/rag/                    # RAG-Kern-System (Schwerpunkt Audit)
│   │   │   ├── rag_orchestrator.py          # Hybrid-Suche: Qdrant + BM25 (1034 LOC)
│   │   │   ├── rag_ingest.py                # Dokument-Ingestion-Pipeline (1301 LOC)
│   │   │   ├── rag_etl_pipeline.py          # Platinum ETL State Machine (239 LOC)
│   │   │   ├── rag_schema.py                # ChunkMetadata, Domain Enums
│   │   │   ├── bm25_store.py                # Redis BM25 Index Wrapper (269 LOC)
│   │   │   ├── qdrant_bootstrap.py          # Vektordatenbank-Initialisierung (236 LOC)
│   │   │   ├── qdrant_state_machine.py      # Atomare Status-Übergänge (93 LOC)
│   │   │   └── nodes/                       # 5-Phasen RAG-Verarbeitungs-Pipeline
│   │   │       ├── p1_context.py
│   │   │       ├── p2_rag_lookup.py
│   │   │       ├── p3_gap_detection.py
│   │   │       ├── p3_5_merge.py
│   │   │       ├── p4a_extract.py
│   │   │       ├── p4b_calc_render.py
│   │   │       ├── p4_5_quality_gate.py     # 8 Blocker-Checks
│   │   │       └── p5_procurement.py
│   │   ├── services/jobs/worker.py          # Background Job Worker (Row-Level Lock)
│   │   ├── services/audit/audit_logger.py   # Append-Only Postgres Audit
│   │   ├── core/
│   │   │   ├── config.py                    # Pydantic BaseSettings (62 Env-Vars)
│   │   │   └── metrics.py                   # Prometheus (5 Instrumente)
│   │   ├── models/rag_document.py           # SQLAlchemy RagDocument Table
│   │   ├── mcp/knowledge_tool.py            # MCP Tool Discovery & RAG-Wrapper
│   │   └── prompts/                         # 20 Jinja2 Templates
│   ├── tests/                               # Integration Tests
│   ├── constraints.txt                      # 27 gepinnte Abhängigkeiten
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/dashboard/                   # Chat UI
│   │   ├── app/rag/                         # RAG Dokument-Management
│   │   ├── components/dashboard/ChatInterface.tsx
│   │   ├── components/rag/RagUploadPanel.tsx
│   │   └── lib/ragApi.ts                    # RAG API Client
│   └── Dockerfile
├── nginx/default.conf
├── docker-compose.yml
└── CLAUDE.md
```

### Metriken

| Kategorie | Backend | Frontend | Gesamt |
|-----------|---------|----------|--------|
| Quell-Dateien | 193 .py | 16 .tsx/.ts | 209 |
| Lines of Code | ~27.900 | ~1.340 | ~29.240 |
| Templates | 20 .j2 | — | 20 |
| Test-Dateien | ~40 | — | ~40 |
| Konfigurationsdateien | 13 | 6 | 19 |

---

## 2. Architektur-Analyse

### Komponenten

| Komponente | Datei(en) | Beschreibung |
|------------|-----------|--------------|
| **API Gateway** | `api/v1/api.py` + `main.py` | FastAPI Routing, Middleware (CORS, Prometheus), Health-Endpoints |
| **Chat Endpoint (SSE)** | `endpoints/langgraph_v2.py` | POST `/api/v1/langgraph/chat/v2` — Server-Sent Events, LangGraph-Integration |
| **LangGraph v2 Engine** | `langgraph_v2/sealai_graph_v2.py` | Multi-Agenten-Graph: 12 Nodes, HITL via `interrupt_before` |
| **RAG Orchestrator** | `services/rag/rag_orchestrator.py` | Hybrid-Retrieval: Qdrant (Dense+Sparse) + BM25, RRF-Fusion, Reranking |
| **Ingest Pipeline** | `services/rag/rag_ingest.py` | Dokument-Chunking, Embedding, Metadata-Extraktion (LLM+Regex), Qdrant-Upload |
| **Platinum ETL** | `services/rag/rag_etl_pipeline.py` | Strukturierte PDF-Extraktion mit Gatekeeper-Logik (Quarantäne, Physik-Validierung) |
| **BM25 Store** | `services/rag/bm25_store.py` | JSONL-backed BM25-Retrieval als Keyword-Fallback |
| **Qdrant Bootstrap** | `services/rag/qdrant_bootstrap.py` | Collection-Initialisierung, Sparse-Upgrade-Pfad, Fail-Fast |
| **State Machine** | `services/rag/qdrant_state_machine.py` | Atomare VALIDATED→PUBLISHED Übergänge mit Idempotenz |
| **Background Worker** | `services/jobs/worker.py` | Polling-Schleife mit Row-Level-Lock für parallele Ingestion |
| **MCP Tool Layer** | `mcp/knowledge_tool.py` | Scope-gegatete Werkzeuge (mcp:knowledge:read, mcp:erp:read, etc.) |
| **Auth** | `services/auth/` | Keycloak JWT-Validierung, `RequestUser` DI-Injection |
| **Long-Term Memory** | `core/memory.py` | AsyncPostgresStore → LangGraph BaseStore |
| **Audit Log** | `services/audit/audit_logger.py` | Append-Only Postgres `audit_log` Tabelle |
| **Frontend RAG UI** | `app/rag/page.tsx` + `components/rag/` | Dokument-Upload, Status-Übersicht, Health-Check |

### Datenfluss

```
Upload-Fluss:
  User Browser
    → POST /api/v1/rag/upload (multipart/form-data)
    → nginx:443 → backend:8000
    → SHA256-Hash + Extension/Content-Type Whitelist
    → Datei schreiben: /app/data/uploads/{tenant_id}/{doc_id}/
    → RagDocument in Postgres (status=queued)
    → Job in Worker-Queue
    → Background Worker: IngestPipeline.ingest_file()
        ├── PDF: Platinum ETL (LLM Vision Extraktion) + Chunking
        ├── TXT/MD/DOCX: Text Extraktion + Chunking (6000 chars, 200 overlap)
        ├── Metadata: 3-Layer (Tags → Regex → LLM gpt-4.1-mini)
        ├── Embedding: BAAI/bge-base-en-v1.5 (dense) + Splade_PP (sparse)
        └── Qdrant Upsert (Collection: sealai_knowledge)
           + BM25 Store Update (JSONL)
    → Postgres Status Update: indexed

Retrieval-Fluss:
  User Chat
    → POST /api/v1/langgraph/chat/v2 (SSE)
    → profile_loader_node → frontdoor_discovery_node
    → supervisor_policy_node → rag_support_node (nodes_flows.py)
    → RAG Pipeline (P1 → P2 → P3 → P3.5 → P4a → P4b → P4.5 → P5)
        P2 (rag_lookup):
            ├── Query-Builder: "Dichtungswerkstoff für {medium} bei {pressure} bar..."
            ├── Dense Embedding (BAAI/bge-base-en-v1.5)
            ├── Sparse Embedding (Splade_PP_en_v1)
            ├── Qdrant Hybrid Search (RRF Fusion, tenant_id Filter)
            ├── BM25 Suche (Redis-backed JSONL)
            ├── RRF-Fusion (k=60)
            ├── Reranking (cross-encoder/ms-marco-MiniLM-L-6-v2)
            └── Top-K=6, Score-Threshold=0.05
    → final_answer_node (Jinja2 Template → OpenAI LLM)
    → SSE Stream → Frontend → User
```

### Externe Dependencies

| Service | Zweck | Konfiguration |
|---------|-------|---------------|
| **Qdrant** | Vektordatenbank (Dense+Sparse Vectors) | `http://qdrant:6333`, Collection: `sealai_knowledge`, HNSW m=16 |
| **Redis Stack** | LangGraph Checkpointing + BM25 Index | `redis://redis:6379`, Namespace: `sealai:v2:` |
| **PostgreSQL** | Metadata + Long-Term Memory + Audit Log | `postgresql+asyncpg://...` |
| **OpenAI API** | LLM Calls (gpt-4.1-mini, gpt-5-large) + Embeddings | `OPENAI_API_KEY` env var |
| **Keycloak** | OIDC Auth (JWT Validation) | Split-DNS: extern `auth.sealai.net`, intern `keycloak:8080` |
| **LangSmith** | Distributed Tracing (optional) | `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` |
| **AGENT_NORMEN_URL** | Externe Normen-Microservice (optional Fallback) | `http://agent-normen:...` (nicht dokumentiert) |
| **AGENT_MATERIAL_URL** | Externes Material-Microservice (optional Fallback) | `http://agent-material:...` (nicht dokumentiert) |

### Design Patterns

- **Multi-Agenten-Graph (LangGraph)**: Supervisor-Pattern mit spezialisierten Worker-Nodes
- **Repository Pattern**: `BM25Repository`, `AsyncPostgresStore` abstrahieren Storage-Details
- **Strategy Pattern**: RAG-Retrieval mit austauschbaren Embedding-Modellen
- **State Machine**: VALIDATED → PUBLISHED → DEPRECATED (Qdrant-Dokument-Lebenszyklus)
- **Pipeline Pattern**: 8-phasige RAG-Node-Pipeline (P1–P5)
- **CQRS-ähnlich**: Upload/Ingest (Write) strikt getrennt von Retrieval (Read)
- **Observer Pattern**: Fire-and-forget Audit Log via `asyncio.create_task()`
- **Circuit Breaker**: Retry mit Exponential Backoff für Qdrant (3 Versuche, 5s Timeout)
- **Template Method (Jinja2)**: Intent-basierte Prompt-Auswahl zur Laufzeit

---

## 3. Technologie-Stack Details

### Vector Database

- **Typ**: Qdrant v1.16.0
- **Deployment**: Docker Container (intern: `qdrant:6333`)
- **Collection**: `sealai_knowledge` (einzige Collection, Multi-Tenant via Payload-Filter)
- **Vektor-Konfiguration**:
  - Dense: `BAAI/bge-base-en-v1.5` → 768 Dimensionen, Cosine Distanz
  - Sparse: `prithivida/Splade_PP_en_v1` → variabel (dot product)
- **HNSW**: `m=16`, `ef_construct=100`
- **Indexing-Threshold**: 10.000 Punkte
- **Timeout**: 5.0s (konfigurierbar), 3 Retry-Versuche
- **Storage**: Persistent Volume `qdrant_storage:/qdrant/storage`

### Embeddings

| Modell | Typ | Dimensionen | Verwendung |
|--------|-----|-------------|------------|
| `BAAI/bge-base-en-v1.5` | Dense (FastEmbed) | 768 | Primäre semantische Suche |
| `prithivida/Splade_PP_en_v1` | Sparse (SPLADE) | variabel | Sekundäre Keyword-basierte Suche |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | CrossEncoder | — | Reranking (Sigmoid normalisiert) |

- **Multi-Vector**: Ja (Named Vectors: `"dense"`, `"sparse"`)
- **Model Cache**: `/app/data/models` (konfigurierbar via `EMBEDDINGS_CACHE_FOLDER`)
- **Lazy Loading**: Embedder werden bei erstem Aufruf geladen, dann gecacht

### LLM Integration

| LLM | Verwendung | Konfiguration |
|-----|-----------|---------------|
| `gpt-4.1-mini` | Metadata-Extraktion, Routing, Supervisor | `RAG_DYNAMIC_METADATA_LLM_MODEL` |
| `gpt-5-large` | Final Answer Generation | `GENERATION_MODEL` env |
| `gpt-5-nano` | Router (Intent) | `OPENAI_ROUTER_MODEL` env |

- **Integration**: LangChain + openai SDK (openai==2.3.0)
- **Prompt Management**: Jinja2 Templates (20 Dateien), intent-basierte Template-Auswahl
- **Temperaturen**: 0.0 für Routing/Extraktion (deterministisch)
- **Streaming**: SSE via LangGraph `astream_events()`

### Dokument-Verarbeitung

| Format | Parser | Strategie |
|--------|--------|-----------|
| PDF | pypdf + LLM Vision (Platinum ETL) | Strukturierte Extraktion → Chunking |
| TXT/MD | Python `read_text()` | Direktes Chunking |
| DOCX | python-docx | Text-Extraktion → Chunking |

**Chunking-Strategie:**
- Max Chunk-Größe: **6.000 Zeichen** (`RAG_MAX_CHUNK_CHARS`)
- Overlap: **200 Zeichen** (`RAG_CHUNK_OVERLAP`)
- Kontext-Prefix: `[Document: {filename}]` an jeden Chunk vorangestellt
- Chunk-ID: UUID5 aus `(tenant_id, document_id, chunk_index)` → reproduzierbar
- Deduplizierung: SHA256 Hash des Chunk-Textes

**3-Layer Metadata-Extraktion:**
1. **Tag-basiert**: Schlüssel-Wert-Paare aus Upload-API-Parameter
2. **Regex**: Materialkürzel (NBR-90), Shore-Härte, Temperaturbereich
3. **LLM**: gpt-4.1-mini füllt Lücken, extrahiert `entity` und `material_family`

### Orchestration

- **LangGraph**: v1.0.1 mit `langgraph-checkpoint-redis 0.1.2`
- **Checkpointing**: `AsyncRedisSaver`, Namespace `sealai:v2:`, Fallback: `MemorySaver`
- **HITL**: `interrupt_before=["human_review_node"]`
- **RAG Nodes**: Eigenentwickelte 5-Phasen-Pipeline

### Frontend/Dashboard

- **Framework**: Next.js 16, TypeScript, Tailwind CSS
- **Auth**: NextAuth v5 mit Keycloak Provider
- **RAG Features**:
  - Dokument-Upload UI (`/rag`)
  - Kategorie + Tags + Sichtbarkeit (public/private)
  - Health-Check pro Dokument
  - Re-Ingest bei Fehler
  - Status-Anzeige (queued/processing/indexed/error)
- **Chat**: SSE-basiertes Streaming, Markdown-Rendering (react-markdown + remark-gfm)

---

## 4. Code-Qualität Analyse

### Bewertung (1-5 Sterne)

| Kriterium | Bewertung | Kommentar |
|-----------|-----------|-----------|
| **Struktur & Organisation** | ⭐⭐⭐⭐⭐ | Klare Layer-Trennung, saubere Modul-Hierarchie |
| **Type Safety** | ⭐⭐⭐⭐☆ | Pydantic v2 durchgehend, wenige `Any`-Typen |
| **Error Handling** | ⭐⭐⭐⭐☆ | Retry-Logik, Custom Exceptions, Graceful Degradation |
| **Testing** | ⭐⭐⭐☆☆ | ~40 Testdateien vorhanden, aber ETL-Quarantäne ungetestet |
| **Dependencies** | ⭐⭐⭐⭐⭐ | 27 Dependencies vollständig gepinnt in `constraints.txt` |
| **Code-Style** | ⭐⭐⭐⭐☆ | Konsistent, Ruff vorhanden; 2 Debug-Prints im Prod-Code |
| **Dokumentation** | ⭐⭐⭐⭐☆ | CLAUDE.md sehr detailliert; inline-Docs teils lückenhaft |
| **Skalierbarkeit** | ⭐⭐⭐⭐☆ | Async durchgehend; kein Rate-Limiting per Tenant |

### Stärken

- **Pydantic v2 überall**: `ChunkMetadata`, `SealAIState`, `Config` sind durchgehend typisiert
- **Gepinnte Dependencies**: `constraints.txt` mit 27 exakten Versionen — reproduzierbare Builds
- **Async First**: FastAPI + SQLAlchemy async + LangGraph async — keine Blocking-Calls im Hot Path
- **Graceful Degradation**: Qdrant Fehler → BM25 Fallback → externe Microservices → Keyword Scroll
- **Strukturiertes Logging**: structlog durchgehend verwendet (wo Debug-Prints fehlen)
- **Row-Level Locking**: Background Worker nutzt `with_for_update(skip_locked=True)` — sicher für Parallelbetrieb

### Kritikpunkte

1. **2 Debug-Prints im Produktionscode** (`rag_orchestrator.py:599`, `:839`):
   ```python
   print(f"DEBUG RAG RAW HITS: Found {len(hits)} hits. Top score: {top_score}")
   print(f"DEBUG: Final Qdrant Filter: {qdrant_filter}")
   ```
2. **Fehlende Fehlerbehandlung für Jinja2-Rendering** in `rag_etl_pipeline.py:217`
3. **Material Family Feld-Inkonsistenz**: Kommentar "Fix 2: eng.material_family aus additional_metadata befüllen" deutet auf jüngeres Refactoring hin
4. **Kein Rate-Limiting** für Upload-Endpunkt (per Tenant oder global)
5. **BM25 JSONL unbegrenzt wachsend** — kein automatisches Cleanup oder Größenbegrenzung
6. **Externe Fallback-Microservices nicht dokumentiert** (`AGENT_NORMEN_URL`, `AGENT_MATERIAL_URL`)
7. **`visibility`-Feld nicht im Retrieval-Filter** erzwungen (nur soft enforcement)

---

## 5. Feature-Analyse

### Ingestion

- ✅ **PDF-Upload** mit Platinum ETL (strukturierte LLM-Extraktion)
- ✅ **TXT/MD/DOCX-Upload** (Basis-Chunking)
- ✅ **Batch-Upload** über Background Worker (asynchron)
- ✅ **Metadata-Extraktion**: 3-Layer (Tags → Regex → LLM)
- ✅ **Duplikat-Erkennung**: SHA256 pro Tenant (Upload wird abgelehnt)
- ✅ **Multi-Tenant-Isolation**: Dateipfad + Payload-Filter pro Tenant
- ✅ **Status-Tracking**: queued → processing → indexed/error (Postgres)
- ✅ **Re-Ingest**: Fehlgeschlagene Dokumente können neu eingereiht werden
- ✅ **Versionierung/State Machine**: VALIDATED → PUBLISHED → DEPRECATED (atomar)
- ✅ **Quarantäne-Handling**: Physikfehler, unquantifizierte Bedingungen → isoliert
- 🟡 **Virus-Scanning**: Nicht implementiert
- 🟡 **OCR für gescannte PDFs**: Nicht explizit implementiert (nur Text-PDFs)
- ❌ **Zip/Bulk-Upload**: Kein Batch-API-Endpunkt

### Retrieval

- ✅ **Semantische Suche** (Dense Vectors, BAAI/bge-base-en-v1.5)
- ✅ **Sparse/Keyword-Suche** (SPLADE, Qdrant native sparse)
- ✅ **Hybrid Search** mit RRF-Fusion (Dense + Sparse + BM25)
- ✅ **BM25 Fallback** (Redis-backed JSONL)
- ✅ **Reranking** (CrossEncoder, sigmoid-normalisiert)
- ✅ **Tenant-Scoping** (Payload-Filter auf `tenant_id`)
- ✅ **Score-Threshold** (0.05 konfigurierbar)
- ✅ **Top-K Konfiguration** (RAG_FINAL_K=6, RAG_HYBRID_K=12)
- ✅ **Retry-Logik** (3 Versuche, Exponential Backoff)
- ✅ **Externe Microservice Fallback** (NORMEN, MATERIAL Agenten)
- 🟡 **Visibility-Filter** (`public`/`private`) — implementiert aber nicht vollständig erzwungen
- 🟡 **Facetten/Filter-API**: Nur über `metadata_filters` in MCP Tool

### RAG Features

- ✅ **Source/Citation Tracking**: `sources`-Feld in State, Metadaten pro Chunk
- ✅ **Multi-Dokument-Synthese**: Mehrere Quellen werden zusammengeführt
- ✅ **Konversations-History**: Via LangGraph Checkpointing (Redis)
- ✅ **Streaming Responses**: SSE via LangGraph `astream_events()`
- ✅ **Gap-Detection**: P3-Phase erkennt fehlende kritische Parameter
- ✅ **Quality Gate**: 8 Blocker-Checks (P4.5) vor finaler Antwort
- ✅ **Domain-Klassifizierung**: `material | standard | product | troubleshooting`
- ✅ **Coverage-Ratio**: Überspringe RAG wenn Profil-Coverage < 0.2
- 🟡 **Halluzination-Prevention**: Check_1.1.0.j2 Sicherheits-Gate vorhanden, aber kein Grounding-Scoring

### Dashboard Features

- ✅ **Dokument-Management** (Upload, Liste, Löschen, Re-Ingest)
- ✅ **Status-Anzeige** pro Dokument
- ✅ **Health-Check** pro Dokument (Qdrant + Filesystem Konsistenz)
- ✅ **Kategorie + Tags** pro Dokument
- ✅ **Sichtbarkeit** (public/private) einstellbar
- ✅ **Chat Interface** mit Markdown-Rendering
- ✅ **Streaming** (SSE-basiert)
- 🟡 **Analytics/Metrics**: Prometheus vorhanden, aber kein Dashboard
- ❌ **Such-Interface** für Admin (kein direktes RAG-Query UI)
- ❌ **Bulk-Upload** im Frontend

---

## 6. Konfiguration & Deployment

### Environment Setup

**62 Konfigurationsvariablen** (Pydantic BaseSettings in `core/config.py`):

| Gruppe | Key Variablen | Pflicht |
|--------|---------------|---------|
| **LLM** | `OPENAI_API_KEY`, `GENERATION_MODEL`, `OPENAI_ROUTER_MODEL` | Ja |
| **Datenbank** | `DATABASE_URL`, `POSTGRES_SYNC_URL` | Ja |
| **Redis** | `REDIS_URL`, `REDIS_PASSWORD` | Ja |
| **Qdrant** | `QDRANT_URL`, `QDRANT_COLLECTION` (default: `sealai_knowledge`) | Ja |
| **Auth** | `KEYCLOAK_ISSUER`, `KEYCLOAK_CLIENT_ID`, `KEYCLOAK_CLIENT_SECRET` | Ja |
| **RAG** | `RAG_DENSE_MODEL`, `RAG_FINAL_K` (6), `RAG_SCORE_THRESHOLD` (0.05) | Nein |
| **Storage** | `RAG_UPLOAD_DIR` (`/app/data/uploads`), `EMBEDDINGS_CACHE_FOLDER` | Nein |
| **Feature Flags** | `RAG_BM25_ENABLED`, `RAG_SPARSE_ENABLED`, `WARMUP_ON_START` | Nein |
| **Observability** | `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | Nein |

### Deployment-Strategie

**Docker Compose (7 Services mit Health-Checks):**

| Service | Image | Health-Check | Abhängigkeiten |
|---------|-------|--------------|----------------|
| `postgres` | postgres:15 | `pg_isready` | — |
| `redis` | redis/redis-stack-server:7.4.0-v8 | `redis-cli PING` | — |
| `qdrant` | qdrant/qdrant:v1.16.0 | HTTP GET `/healthz` | — |
| `keycloak` | custom (Postgres-Backend) | HTTP GET `/health/ready` | postgres |
| `backend` | custom | GET `/api/v1/langgraph/health` (30s start) | postgres, redis, qdrant |
| `frontend` | custom (Next.js) | GET `/api/health` | — |
| `nginx` | nginx:1.29.4 | — | backend, frontend |

**Nginx-Konfiguration (Sicherheits-Features):**
- HTTPS-only (HTTP 301 Redirect)
- HSTS: 31.536.000s (1 Jahr) + includeSubdomains
- X-Frame-Options: SAMEORIGIN
- X-Content-Type-Options: nosniff
- SSE-Optimierung: `proxy_buffering off`, `proxy_read_timeout 300s`

### Monitoring

| Tool | Zweck | Konfiguration |
|------|-------|---------------|
| **Prometheus** | HTTP-Metriken (5 Instrumente) | GET `/metrics`, Path-Normalisierung |
| **LangSmith** | Distributed Tracing | `LANGCHAIN_TRACING_V2=true` |
| **Audit Log** | Sicherheits-Audit (Postgres) | `audit_log` Tabelle, Fire-and-Forget |
| **structlog** | Strukturiertes Logging | JSON-Format in Produktion |

**Prometheus Metriken:**
- `http_requests_total` (method, path, status)
- `http_request_duration_seconds` (method, path)
- + 3 weitere custom Instrumente

### Skalierbarkeit

- ✅ **Async First**: FastAPI + SQLAlchemy async — kein Blocking im Request-Pfad
- ✅ **Background Worker**: Entkoppelt von Request-Handling, Row-Level-Lock
- ✅ **Redis Checkpointing**: Zustandspersistenz skaliert horizontal
- ✅ **Qdrant**: Horizontal skalierbar (Sharding in Qdrant v1.x)
- 🟡 **Caching**: Embedding-Cache für Modelle, aber kein Query-Result-Cache
- ❌ **Rate Limiting**: Kein per-Tenant oder globales Rate-Limit für Uploads
- ❌ **Load Balancing**: Nginx nur als Single-Point (kein Backend-Cluster)

---

## 7. Daten-Modelle

### Core Models

```python
# backend/app/services/rag/rag_schema.py

class ChunkMetadata(BaseModel):
    tenant_id: str
    doc_id: str                          # Legacy (Kompatibilität)
    document_id: str                     # Kanonisch
    chunk_id: str                        # UUID5 aus (tenant:doc:index) — reproduzierbar
    chunk_hash: str                      # SHA256 des Textes (Deduplizierung)
    source_uri: str                      # Dateipfad
    source_type: SourceType              # manual | upload | crawl
    domain: Domain                       # material | standard | product | troubleshooting
    chunk_index: int
    entity: Optional[str]                # Produkt-/Materialname
    aspect: list[str]                    # Feature-Tags
    language: Optional[str]              # ISO-639-1 (de, en)
    source_version: Optional[str]        # Datenblatt-Version
    effective_date: Optional[str]        # Publikationsdatum
    material_code: str                   # z.B. "NBR-90", "FKM-75"
    source_url: Optional[str]
    shore_hardness: int                  # Default: 70
    temp_range: TempRange                # {min_c: float, max_c: float}
    additional_metadata: Dict[str, Any]  # Dynamische Felder
    title: Optional[str]
    page_number: Optional[int]
    text: str
    created_at: float
    visibility: str                      # public | private
    eng: EngineeringProps                # {material_family: Optional[str]}
```

### Vector DB Schema

```python
# Collection: "sealai_knowledge"
# Vector Config:
#   - Named vector "dense":  dim=768, distance=Cosine
#   - Named vector "sparse": SPLADE sparse format
# HNSW: m=16, ef_construct=100

# Qdrant Payload pro Punkt:
{
    "metadata": ChunkMetadata.model_dump(),
    "text": str,
    "source": str,
    "filename": str,
    "tenant_id": str,                    # Pflichtfeld für Tenant-Scoping
    "document_id": str,
    "visibility": "public" | "private",
    "material_code": str,                # Regex-extrahiert
    "source_url": Optional[str],
    "shore_hardness": int,
    "temp_range": {"min_c": float, "max_c": float},
    "additional_metadata": dict,
    "document_meta": {                   # Nur Platinum ETL
        "status": "VALIDATED" | "PUBLISHED" | "DEPRECATED",
        "logical_document_key": str,
        "version_id": int,
        "pipeline_version": "V5.2-Platinum"
    }
}
```

### API Models

```python
# backend/app/models/rag_document.py (SQLAlchemy)
class RagDocument(Base):
    __tablename__ = "rag_documents"

    document_id: String (PK)
    tenant_id: String (indexed)
    status: String (queued|processing|indexed|error, indexed)
    visibility: String (default="private")
    enabled: Boolean (server_default=True)
    filename: Optional[String]
    content_type: Optional[String]
    size_bytes: Optional[Integer]
    category: Optional[String]
    tags: Optional[JSON]
    sha256: String (unique per tenant via constraint)
    path: Text
    error: Optional[Text]
    ingest_stats: Optional[JSON]   # {elapsed_ms, file_size}
    created_at: DateTime (auto)
    updated_at: DateTime (auto)
```

```typescript
// frontend/src/lib/ragApi.ts
interface RagDocumentItem {
    document_id: string;
    filename?: string;
    content_type?: string;
    size_bytes?: number;
    category?: string;
    tags?: string[];
    visibility?: string;
    status?: string;
    error?: string;
    ingest_stats?: object;
}

interface RagHealthCheck {
    document_id: string;
    tenant_id: string;
    status: string;
    collection: string;
    filesystem: { path: string; exists: boolean };
    qdrant: { points: number; error?: string };
    is_consistent: boolean;
    issues: string[];
}
```

---

## 8. Vergleich mit Best Practices

| Kategorie | Status | Bewertung |
|-----------|--------|-----------|
| **Chunking-Strategie** | ✅ | Sinnvoll: 6000 Zeichen mit Overlap, Kontext-Prefix, semantisch |
| **Embedding-Qualität** | ✅ | BAAI/bge-base-en-v1.5 = State-of-Art für Retrieval (MTEB Top-10) |
| **Hybrid Retrieval** | ✅ | Best Practice: Dense + Sparse + BM25, RRF-Fusion |
| **Reranking** | ✅ | CrossEncoder als zweite Stufe = Industry Standard |
| **Source Tracking** | ✅ | Vollständige Metadaten pro Chunk, Chunk-ID reproduzierbar |
| **Multi-Tenant** | ✅ | Payload-Filter korrekt implementiert |
| **Error Handling** | ✅ | Retry mit Backoff, Graceful Degradation, Custom Exceptions |
| **Streaming** | ✅ | SSE via LangGraph astream_events() |
| **Async Processing** | ✅ | FastAPI async + Background Worker |
| **Testing** | 🟡 | Vorhanden aber Lücken (ETL-Quarantäne, State Machine) |
| **Logging** | 🟡 | structlog vorhanden, aber 2 Debug-Prints im Prod-Code |
| **Rate Limiting** | ❌ | Fehlt vollständig für Upload-Endpunkte |
| **Virus Scanning** | ❌ | Kein In-Process oder externes Scanning |
| **OCR Support** | ❌ | Nur Text-PDFs, keine gescannten Dokumente |
| **Query Caching** | ❌ | Kein Result-Caching für häufige Abfragen |
| **Visibility Enforcement** | 🟡 | Feld vorhanden, aber nicht im Retrieval-Filter erzwungen |

---

## 9. Kritische Lücken & Risiken

### 🔴 HIGH Priority

**H1 — Debug-Prints im Produktionscode (`rag_orchestrator.py:599`, `:839`)**
```python
# Aktuell (SCHLECHT):
print(f"DEBUG RAG RAW HITS: Found {len(hits)} hits. Top score: {top_score}")
print(f"DEBUG: Final Qdrant Filter: {qdrant_filter}")
```
- **Risiko**: Unstrukturierte Logs, Performance-Overhead, PII/Tenant-Daten in Logs
- **Fix**: Ersetzen durch `logger.debug(...)` mit structlog

**H2 — Kein Rate-Limiting für Uploads**
- **Risiko**: Ein Tenant kann die Worker-Queue und Qdrant-Kapazität erschöpfen
- **Fix**: `slowapi` + Redis-backed Token-Bucket per Tenant (z.B. 10 Uploads/Minute)

**H3 — Visibility-Feld nicht im Retrieval-Filter erzwungen**
- **Risiko**: Private Dokumente könnten theoretisch in Queries anderer User auftauchen wenn `tenant_id` Filter fehlschlägt
- **Fix**: Visibility-Filter als Pflichtbedingung in `_build_qdrant_filter()` implementieren

**H4 — BM25 JSONL-Dateien wachsen unbegrenzt**
- **Risiko**: Disk-Space-Erschöpfung in `/app/data/uploads/tmp/bm25/`
- **Fix**: Max-Size-Limit + automatisches Cleanup alter Dokumente

### 🟡 MEDIUM Priority

**M1 — Fehlende Tests für Platinum ETL Quarantäne-Logik**
- `rag_etl_pipeline.py` hat keine Unit-Tests für PHYSICS_VIOLATION, RANGE_DETECTED, PARSE_ERROR Pfade
- Risiko: Regressionen beim ETL-Refactoring unbemerkt

**M2 — Externe Fallback-Microservices nicht dokumentiert**
- `AGENT_NORMEN_URL` und `AGENT_MATERIAL_URL` sind im Code referenziert, aber API-Kontrakt unbekannt
- Risiko: Silent Failure wenn Microservices unavailable (kein Circuit Breaker)

**M3 — Sparse Embedding Fehlerbehandlung**
- Wenn Splade-Modell nicht lädt → stiller Fallback auf Dense-Only ohne Warning im Log
- Risiko: Retrieval-Qualitätsverschlechterung unbemerkt

**M4 — doc_id / document_id Dualismus in ChunkMetadata**
- Beide Felder existieren (`doc_id` als Legacy, `document_id` als kanonisch)
- Risiko: Inkonsistente Queries; `doc_id` wird möglicherweise an manchen Stellen noch verwendet

**M5 — Jinja2 Rendering ohne Try/Except**
- `rag_etl_pipeline.py:217` verwendet `StrictUndefined` — Template-Fehler werfen Exceptions
- Risiko: Kompletter Ingest-Fehler bei defektem Template

**M6 — Kein Backup-Mechanismus für Qdrant**
- Keine Qdrant-Snapshot-Konfiguration im Docker Compose
- Risiko: Datenverlust bei Qdrant-Container-Ausfall

### 🟢 LOW Priority

**L1 — Kein OCR für gescannte PDFs**
- Nur Text-PDFs unterstützt; gescannte Dokumente erzeugen leere Chunks
- Fix: Tesseract/AWS Textract Integration

**L2 — Kein Virus-Scanning**
- In-Process PDF-Parsing ohne Sandboxing
- Fix: ClamAV oder S3 Malware Scanning

**L3 — Model Cache nicht im Docker Volume**
- `EMBEDDINGS_CACHE_FOLDER=/app/data/models` ist im Docker-Image, kein persistentes Volume
- Risiko: Modelle werden bei jedem Neustart neu heruntergeladen (1-2 GB)

**L4 — Keine Größenbegrenzung für BM25-Index-Rebuild**
- Rebuild nach jedem Upsert ist O(n) — bei 100.000+ Dokumenten problematisch
- Fix: Batch-Rebuild + Dirty-Flag-Pattern

**L5 — Fehlende Dokumentation für externe Microservices**
- `AGENT_NORMEN_URL`, `AGENT_MATERIAL_URL` API-Kontrakt undokumentiert

---

## 10. Verbesserungsvorschläge

### Quick Wins ⚡ (< 1 Tag)

1. **Debug-Prints entfernen** (`rag_orchestrator.py:599`, `:839`):
   ```python
   # Vorher:
   print(f"DEBUG RAG RAW HITS: ...")
   # Nachher:
   logger.debug("rag.raw_hits", count=len(hits), top_score=top_score)
   ```

2. **Qdrant Volume für Embeddings-Cache** in `docker-compose.yml`:
   ```yaml
   volumes:
     - models_cache:/app/data/models  # Verhindert Re-Download bei Restart
   ```

3. **Jinja2 Rendering mit Try/Except** in `rag_etl_pipeline.py`:
   ```python
   try:
       rendered = template.render(ctx)
   except jinja2.TemplateError as e:
       logger.error("etl.render_failed", doc_id=doc_id, error=str(e))
       raise IngestError(f"Template render failed: {e}") from e
   ```

4. **Visibility im Retrieval-Filter erzwingen**:
   ```python
   # In _build_qdrant_filter(): Visibility als AND-Bedingung hinzufügen
   # für private Docs: visibility IN ("public", "private") für den eigenen Tenant
   # für fremde Tenants: nur visibility == "public"
   ```

5. **doc_id Feld deprecaten**: Alle Stellen auf `document_id` migrieren, `doc_id` als `@deprecated` markieren

### Short-term 📅 (1-2 Wochen)

1. **Rate-Limiting für Upload-Endpunkt**:
   ```python
   from slowapi import Limiter
   limiter = Limiter(key_func=get_tenant_id)

   @router.post("/upload")
   @limiter.limit("20/minute")
   async def upload_document(...): ...
   ```

2. **Unit-Tests für Platinum ETL Quarantäne** (`test_rag_etl_quarantine.py`):
   - Test: `PHYSICS_VIOLATION` (Druck > 1000 bar → quarantined)
   - Test: `RANGE_DETECTED` (50-100 bar → uses min=50)
   - Test: `PARSE_ERROR` (malformed number → quarantined)
   - Test: `UNQUANTIFIED_CONDITION` ("kurzzeitig" → quarantined)

3. **BM25 Cleanup-Mechanismus**:
   ```python
   async def cleanup_bm25_store(max_size_mb: int = 500):
       """Entfernt gelöschte Dokumente aus JSONL, erzwingt Größenlimit"""
   ```

4. **Qdrant Snapshot-Backup** im Docker Compose:
   ```yaml
   # Cronjob oder separater Container für tägliche Snapshots
   # POST /collections/sealai_knowledge/snapshots
   ```

5. **Circuit Breaker für externe Fallback-Microservices**:
   ```python
   from circuitbreaker import circuit

   @circuit(failure_threshold=3, recovery_timeout=60)
   async def _call_normen_agent(query: str) -> list: ...
   ```

6. **Sparse Embedding Fehler-Logging**:
   ```python
   # Bei Fallback auf Dense-Only:
   logger.warning("rag.sparse_unavailable", reason=str(e),
                   fallback="dense_only")
   ```

### Long-term 🎯 (1-3 Monate)

1. **OCR-Integration für gescannte PDFs**:
   - Tesseract (Open Source) oder AWS Textract (Cloud)
   - Preprocessing: Deskewing, Denoising vor OCR
   - Confidence-Score für OCR-Qualität in Metadata

2. **Query-Result-Caching**:
   - Redis-Cache für häufige Retrieval-Queries (TTL: 5-15 Minuten)
   - Cache-Key: `(tenant_id, query_hash, top_k, filters)`
   - Invalidierung bei neuen Ingestions

3. **Virus-Scanning**:
   - ClamAV als Docker Sidecar oder
   - S3 + AWS Macie für Cloud-Deployments

4. **Grafana-Dashboard** für Qdrant + RAG Metriken:
   - Retrieval-Latenz Histogramm
   - Score-Verteilung (Qualitätstrend)
   - Ingest-Queue-Tiefe
   - Fehlerquote pro Tenant

5. **Semantic Chunking** (statt Fixed-Size):
   - `langchain_experimental.text_splitter.SemanticChunker`
   - Bewahrt semantische Grenzen (Paragraphen, Abschnitte)
   - Erhöht Retrieval-Qualität für technische Dokumente

6. **Multi-Collection-Strategie**:
   - Separate Collections: `sealai_materials`, `sealai_standards`, `sealai_products`
   - Ermöglicht domain-spezifische HNSW-Konfiguration
   - Verhindert Cross-Domain-Interferenz bei Suche

7. **A/B Testing für Retrieval-Konfigurationen**:
   - Online Evaluation mit Klick-Through-Rate
   - RAGAS-Metriken (Faithfulness, Answer Relevancy, Context Recall)
   - Automatisierter Golden-Set-Test bei Konfigurationsänderungen

---

## 11. Gesamt-Bewertung

**Score: 8.2 / 10**

### Stärken

- **Hybrid Retrieval (Best-in-Class)**: Dense + Sparse + BM25 + RRF + Reranking — State-of-Art-Pipeline
- **Platinum ETL**: Strukturierte PDF-Extraktion mit Gatekeeper-Logik ist technisch beeindruckend
- **Saubere Architektur**: Klare Schichtentrennung, Single Responsibility, async durchgehend
- **Production-Grade Infra**: 7 Docker Services mit Health-Checks, HSTS, TLS, Audit Log, Prometheus
- **Multi-Tenant by Design**: `tenant_id` als Pflichtfeld in allen Daten-Operationen
- **Dependency-Management**: 27 gepinnte Versionen — reproduzierbar und deterministisch
- **Atomic State Machine**: VALIDATED → PUBLISHED atomarer Übergang schützt vor Race Conditions
- **Vollständige Observability-Suite**: Prometheus + LangSmith + Audit Log + structlog

### Schwächen

- **Debug-Prints im Prod-Code**: Kritisch, sofort zu beheben
- **Kein Rate-Limiting**: Sicherheitslücke für Multi-Tenant-Betrieb
- **Test-Coverage-Lücken**: ETL-Quarantäne und State Machine ohne Tests
- **Visibility-Enforcement**: Feld definiert aber nicht im Retrieval-Filter
- **BM25 ohne Cleanup**: Wächst unbegrenzt
- **Keine OCR**: Schränkt Dokumenttypen ein (nur Text-PDFs)

### Production-Readiness

**Teilweise Production-Ready** — System ist grundsätzlich produktionstauglich, aber folgende Punkte sollten vor produktivem Multi-Tenant-Einsatz behoben werden:
1. Debug-Prints entfernen (H1)
2. Rate-Limiting implementieren (H2)
3. Visibility-Filter erzwingen (H3)
4. BM25-Cleanup implementieren (H4)

### Empfehlung

**Refactor (keine Komplett-Neuentwicklung notwendig)**

Das System hat eine solide architektonische Grundlage. Die identifizierten Issues sind:
- 4 High-Priority-Fixes (alle umsetzbar in < 1 Woche)
- 6 Medium-Priority-Verbesserungen (1-2 Wochen)
- 5 Low-Priority / Long-Term Enhancements

Kein Rebuild erforderlich. Die RAG-Pipeline-Architektur (5-Phasen P1-P5), das Hybrid-Retrieval und der Platinum-ETL sind konkurrenzfähige Implementierungen.

---

*Audit erstellt mit Claude Code (Sonnet 4.6) · 2026-02-23*
