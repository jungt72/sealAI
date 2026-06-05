# Produkt-Güte Deep-Dive — Latenz · LangGraph-Orchestrierung · Jinja2 · Verdrahtung

**Datum:** 2026-06-05 · **Modus:** strikt read-only (keine Fixes/Config/Deploy) ·
**Branch:** `demo/rwdr-limited-external` @ `ba460ae8`

**Evidenz-Grammatik:** `[E]` = code-/messbelegt (Pfad:Zeile oder Run-ID) ·
`[A]` = Annahme/geschätzt · `[NV]` = nicht verifizierbar mit vorhandener Datenlage.

**Trenn-Prinzip:** Eine governte Pipeline, die eine herstellerbewertbare RWDR-RFQ
erzeugt, **darf mehr kosten als ein Chatbot**. Jeder Befund wird ausgewiesen als
**Gerechtfertigte Kosten** vs **Verschwendung/Über-Kosten**. Warnung vor verfrühter
Optimierung ist Teil des Berichts (Abschnitt 6).

---

## 0. Live Ground-Truth & Mess-Fenster

Aus dem laufenden Daemon und dem Backend-Container-Env (nicht aus Erinnerung):

- **Backend (in-scope):** `ghcr.io/jungt72/sealai-backend:ccdd4577-20260605-060228`
  `@sha256:045c2c2fc4583b1a13890437cd16006e72409ff4d1acf4313a781172adc4a933` —
  `running healthy` (Image gebaut 2026-06-05 06:02). `[E]`
- **Frontend:** `ghcr.io/jungt72/sealai-frontend:d40d7145-20260604-183558`
  `@sha256:fdb5ced64153aee727b1b2eb7ad8d7fda0dec398c5b8d225cfabfb3ff7cc19d6` — healthy. `[E]`
- **Live-Modelle:** `GENERATION_MODEL=gpt-5-large`, `OPENAI_ROUTER_MODEL`/
  `SEALAI_CONVERSATION_MODEL`/`SEALAI_COMMUNICATION_RUNTIME_MODEL=gpt-5.4-nano`,
  `SEALAI_GATE_MODEL`/`SEALAI_GOVERNED_ANSWER_COMPOSER_MODEL`/
  `SEALAI_KNOWLEDGE_ANSWER_COMPOSER_MODEL=gpt-4o-mini`. `[E]`
- **Feature-Gates live:** `APP_ENV=production`, `SEALAI_LANGGRAPH_CHECKPOINTING=true`,
  `SEALAI_ENABLE_GOVERNED_ANSWER_COMPOSER=true`; `SEALAI_ENABLE_LLM_EXTRACTION` **unset
  → Code-Default `"true"` = aktiv** (`intake_observe_node.py:60-62`). `[E]`
- **Mess-Fenster LangSmith:** Projekt `sealai-production`, 236 Root-Runs,
  2026-05-30 06:45 → 2026-06-05 13:51 (≈7 Tage). Es handelt sich **ausschließlich
  um Owner-Testläufe**, keine echten Nutzer.

**Daten-/Secret-Compliance dieses Berichts:** keine Konversations-/Prompt-Inhalte;
ausschließlich Timings, Knoten-/Span-Namen, Zähler, Modellnamen, Token-Zahlen,
Run-IDs. LangSmith-Abfragen liefen im Backend-Container über das installierte SDK;
LLM-Span-`inputs`/`outputs` wurden bewusst nie ausgelesen.

> **Sofortiger Neben-Befund (Scope A.5, nur Faktenbasis):** Die Live-Tracing-Config
> weicht von den Code-Defaults ab. Env im laufenden Backend:
> `LANGSMITH_CAPTURE_LLM_CONTENT=true`, `LANGSMITH_TRACE_LANGGRAPH_CHILDREN=true`
> (Code-Default beider = `False`, `config.py`), `LANGSMITH_REDACTED_OBSERVATION_SPANS=true`.
> Konsequenz siehe §3.5 — die geparkte Privacy-Entscheidung ist jetzt belegt.

---

## 1. Latenz-Budget pro Route

### 1.1 Gesamt-Dauer pro Root-Run-Typ × Route (7 Tage, `[E]` LangSmith)

| Root-Run | Route (Metadaten) | n | p50 | p90 | p95 | max |
|---|---|---|---:|---:|---:|---:|
| `sealai.governed_graph_turn` | `engineering_case_update` | 17 | **19.59s** | 35.85s | 36.65s | 36.65s |
| `sealai.governed_graph_turn` | `knowledge_case_side_question` | 6 | 7.94s | 52.14s | 52.14s | 52.14s |
| `sealai.governed_graph_turn` | `smalltalk` | 3 | 5.44s | 23.04s | 23.04s | 23.04s |
| `sealai.active_case_side_answer` | `knowledge_case_side_question` | 11 | 11.37s | 33.61s | 36.25s | 36.25s |
| `sealai.runtime_dispatch` | `CONVERSATION` (answer_only) | 77 | 1.83s | 25.63s | 34.33s | 48.99s |
| `sealai.runtime_dispatch` | `GOVERNED` (enter graph) | 45 | 3.37s | 5.53s | 6.64s | 12.04s |
| `ChatOpenAI` (Orphan-Root, s. §2.5) | – | 72 | 1.84s | 4.14s | 9.48s | 23.16s |

`runtime_dispatch` Pre-Gate-Verteilung: `KNOWLEDGE_QUERY` 52, `GREETING` 36,
`DOMAIN_INQUIRY` 32, `BLOCKED` 1, `DEEP_DIVE` 1. `[E]`

**Ausreißer mit Run-ID** (`[E]`):

| Dauer | Typ | Route | Run-ID |
|---:|---|---|---|
| 52.14s | governed_graph_turn | knowledge_case_side_question | `019e9226-50c8-7282-a5ba-d21e406b5605` |
| 48.99s | runtime_dispatch | CONVERSATION (KNOWLEDGE_QUERY) | `019e8983-92bb-7983-8459-8acd2cb8389e` |
| 48.19s | runtime_dispatch | CONVERSATION (KNOWLEDGE_QUERY) | `019e77b8-7dbd-7183-a912-239d7375c623` |
| 36.65s | governed_graph_turn | engineering_case_update | `019e9336-f4d5-7d72-adae-1c0f0367a6dc` |
| 36.25s | active_case_side_answer | knowledge_case_side_question | `019e7c77-50c7-7fc0-9aae-6bdef47ea2aa` |

### 1.2 Span-Zerlegung der governten Turns — der Kern `[E]`

Aggregat über die governten Turns (Kindspans via `read_run(load_child_runs=True)`,
LangGraph-Knoten = `chain`-Spans). **Latenz konzentriert sich auf exakt 3 von 21 Knoten:**

| Knoten | Summe | n | Ø | Rolle |
|---|---:|---:|---:|---|
| `evidence` (RAG) | 131.63s | 17 | **7.74s** | Qdrant+BM25+Rerank (kein LLM) |
| `output_contract` (Composer) | 66.12s | 14 | **4.72s** | governed_answer_composer-LLM (gpt-4o-mini) |
| `intake_observe` | 25.94s | 17 | **1.53s** | Regex + LLM-Extraktion (gpt-4o-mini) |
| **alle 18 übrigen Knoten** | **je ≤0.22s gesamt** | 14–17 | **~0.01s** | rein deterministisch |

Übrige Knoten (zur Vollständigkeit, alle praktisch kostenlos): `v92_engineering`
0.22s, `rfq_handover` 0.16s, `dispatch` 0.11s, `challenge` 0.10s, `governance`
0.09s, `v92_dossier` 0.09s, `normalize`/`medium_intelligence`/`compute`/`assert`
~0.07–0.08s, `matching`/`manufacturer_mapping`/`norm`/`dispatch_contract`/
`turn_boundary`/`export_profile` ~0.05–0.07s, `cycle_increment` 0.01s.

**Beleg-Beispiele (Knoten-Dauer · LLM-Kindspan · Run-ID):** `[E]`
- 52.1s `knowledge_case_side_question`: `evidence` 17.65s + `output_contract` 32.74s
  (darin **1× gpt-4o-mini 32.68s**, 6022 tok-in/101 tok-out — reiner OpenAI-Latenz-
  Ausreißer, normale Token-Menge); `intake_observe` 0.79s. `019e9226…`
- 36.6s `engineering_case_update`: `evidence` **28.0s** + `output_contract` 2.75s;
  **5 LLM-Calls** (4× intake-Extraktion à ~490 tok-in/6 tok-out + 1× Composer) →
  dieser Turn ist **Cycle-gelaufen** (s. §2.2). `019e9336…`
- 19.6s `engineering_case_update`: `evidence` 15.02s, `output_contract` 2.39s,
  `intake_observe` 1.77s. `019e8c1c-a810-7d31-8c7b-330ff817cad5`

**„Leerlauf zwischen Spans"** existiert praktisch nicht: die Knoten laufen strikt
sequenziell, die Summe der drei heißen Knoten ≈ Gesamt-Dauer. Es gibt keinen
nennenswerten Scheduler-/Framework-Overhead zwischen Knoten. → **Parallelisierung
der billigen 18 Knoten bringt nichts** (s. §6). Der einzige reale
Parallelisierungs-Kandidat wäre `evidence` ∥ `intake`-Folgearbeit, aber `evidence`
hängt daten-seitig von `assert` ab (Query aus asserted params) — nicht trivial
entkoppelbar.

### 1.3 LLM-Calls pro Turn × Route `[E]`

- **`intake_observe`** (gpt-4o-mini): 1 Call/Cycle, ~490 tok-in / **6 tok-out**
  (winzige JSON-Extraktion), 0.5–1.7s. Bei Cycle-Wiederholung mehrfach (bis 4×
  beobachtet). `_llm_extract_params`, `intake_observe_node.py:461-482`,
  `max_tokens=512`, JSON-Mode, temp 0.
- **`output_contract`/Composer** (gpt-4o-mini): **1 Call**, ~5500–6100 tok-in /
  ~80–102 tok-out. `GovernedAnswerComposer.compose` →
  `get_async_llm("governed_answer_composer")` (`governed_answer_composer.py:133`).
  Ø 4.72s, Ausreißer bis 32.7s (OpenAI-Latenz, **nicht** Token-bedingt).
- **`active_case_side_answer`** & **CONVERSATION-Knowledge**
  (`KnowledgeAnswerComposer`, gpt-4o-mini, **`max_tokens=1800`**,
  `answer_composer.py:52`): lange Antworten (bis ~1589 tok-out gemessen) → 20–46s
  pro Generierung. `composer_attempted` 9/11, `composer_succeeded` 8/11 (im
  active_case-Pfad). `[E]`
- **Sequenziell**, nicht parallel. Pro „Antwort"-Dispatch im Schnitt ~1.1 LLM-Span.

**Redundante Generierung — gemessen, gering:** Verteilung großer Generierungen
(≥400 tok-out) pro Antwort-Turn = `{0: 80, 1: 15, 2: 2}` von 97 Turns → **nur
2/97 (~2 %)** erzeugen eine zweite Vollgenerierung. Ursache `[E]`: Guard-getriggerte
**Repair-Regenerierung** (`answer_composer.py:68-79`, bei `unsafe_answer_markdown`
Zeile 219; analog `governed_answer_composer.py:142-159`). Beleg: Run `019e8983…`
(49s) = 2× gpt-4o-mini je ~1589 tok-out. → **Kein systemischer Treiber, nur Tail.**

### 1.4 Retrieval-Spans `[E]`

- **Qdrant- vs BM25- vs RRF-Anteil ist aus LangSmith NICHT auflösbar:** `evidence`
  ruft `retrieve_evidence` → `real_rag.retrieve_with_tenant` (`real_rag.py:55`),
  das `hybrid_retrieve` und BM25 via `loop.run_in_executor` ausführt
  (`real_rag.py:103-123`, `187-202`). Die interne Tier-Aufteilung wird **nur per
  stdlib `logger.info`** protokolliert (`real_rag.py:129-134`, `204-205`) und ist
  damit **in prod-Docker-Logs unsichtbar** (nur structlog erreicht stdout — bekanntes
  Muster). **Embedding-Spans gesehen: 0** (über 97 Antwort-Turns). `[E]`
- `hybrid_retrieve` (`rag_orchestrator.py`) = Qdrant dense+sparse + BM25 +
  **Cross-Encoder-Rerank** (`ms-marco-MiniLM-L-6-v2`, Zeile 89) mit **`fastembed`**
  (lokale CPU-Modelle, lazy globals `_embedder`/`_sparse_embedder`/`_reranker`,
  Zeile 120-122). → Die 7.74s Ø / 28s max von `evidence` sind **CPU-gebundenes
  lokales Embedding + Reranking + Qdrant/BM25**, synchron im Default-Threadpool. `[E]`
- **Leere Retrievals:** `evidence_refs_count` in Metadaten vorhanden; Tier-Kaskade
  fällt bei <`_TIER1_MIN_HITS` auf BM25, dann leer (fail-open) — Kosten ohne Treffer
  möglich, aus Logs aber nicht quantifizierbar (dark). `[A]`

### 1.5 C8-Trennung: first_progress vs Gesamt — **Mess-Lücke** `[E]`

- `first_progress_ms` / `latency_ms` werden zentral gemessen (`turn_timing.py`,
  ContextVar) und **nur in das SSE-`trace`-Dict** des finalen `state_update`
  gestempelt (`sse_contract.py:109-125`). Sie landen **weder in LangSmith-Metadaten
  noch im stdout-Log** (0 Vorkommen in `docker logs backend`). `[E]`
- **Konsequenz:** Der in Scope A.1 geforderte Abgleich „Eigenmessung vs LangSmith"
  ist **server-seitig nicht durchführbar** — die Eigenmessung wird nach dem Senden
  an den Client verworfen. Das ist selbst ein Befund (§3.6/§5).
- **C8-`<1s`-Contract (first_progress):** technische Turns streamen
  `status_only_until_guarded_final` (Status-Events vor der geguardeten Finalantwort,
  `turn_boundary.py`) → first_progress dürfte `<1s` erfüllt sein `[A]`, **server-
  seitig aber `[NV]`**. **Zeit-bis-Finalantwort** = `governed_graph_turn`-Dauer:
  `engineering_case_update` **p50 19.6s / p95 36.7s** — das ist die reale UX-Zahl.

---

## 2. Orchestrierungs-Karte, Ineffizienzen & Differenz-Analyse

### 2.1 Tatsächliche Topologie `[E]` (`graph/topology.py`)

Strikt **lineare 21-Knoten-DAG**, kein Fan-out, keine Parallelität:

```
turn_boundary → intake_observe → normalize → assert → medium_intelligence →
evidence → compute → v92_engineering → challenge → governance ─┬─(Command.goto)
  ├─ CONTINUE → cycle_increment → (zurück zu) intake_observe   │
  └─ TERMINATE → matching → rfq_handover → dispatch → norm → export_profile →
       manufacturer_mapping → dispatch_contract → v92_dossier → output_contract →
       governed_answer_composer → END
```

Checkpointer: AsyncRedisSaver, Thread `sealai:{tenant}:{owner}:{session}`
(`SEALAI_LANGGRAPH_CHECKPOINTING=true`). Nur 2 Knoten dürfen LLM rufen
(`intake_observe`, `governed_answer_composer`); `evidence` = RAG; Rest deterministisch.

### 2.2 Ineffizienz-Tabelle (real/theoretisch · gemessen/geschätzt · Fix-Richtung)

| # | Ineffizienz | real? | Beleg | Kosten | Fix-Richtung |
|---|---|---|---|---|---|
| O1 | **`evidence` läuft auf JEDEM governten Turn neu** — auch bei `smalltalk`/`knowledge_case_side_question` mit aktivem Case (Assertions persistieren → Query wird neu gebaut & retrieved, kein Query-Hash-Cache) | real | `evidence_node.py:344-378`; smalltalk gov p50 5.44s, max 23s (`019e91bb…`) | **hoch** (7.74s Ø je Turn) | Re-Retrieval überspringen, wenn die EvidenceQuery seit letztem Cycle unverändert → Ergebnis cachen |
| O2 | **Cycle-Loop wiederholt den teuersten Knoten** — `cycle_increment` → zurück zu `intake_observe` re-run inkl. `evidence` | real | Span-Counts 17(intake/evidence) vs 14(tail); `cycle_increment`=3; Run `019e9336…` (5 LLM) | mittel (verdoppelt evidence+intake) | unverändert lassen (Cycle ist korrekt) — aber O1-Cache deckt es mit ab |
| O3 | **`governed_answer_composer`-Knoten = permanenter No-Op** auf jedem governten Turn | real | 0.0s/leer in allen Traces; früher Early-Return `governed_answer_composer_node.py:70-75`; echte Komposition läuft schon **in** `output_contract` (`output_contract_assembly.py:1961-1966`) | ~0 (Klarheit/Doppel-Verdrahtung) | Doppel-Verdrahtung auflösen: Knoten entfernen ODER Aufruf aus `output_contract` herausziehen — nicht beides |
| O4 | **Langer TERMINATE-Schwanz aus RWDR-MVP-deaktivierten Capability-Knoten** (`matching`, `manufacturer_mapping`, `dispatch_contract`, `dispatch`, `export_profile`, `norm`, `v92_dossier`) feuert auf jedem governten Turn | real | je ~0.01s (§1.2) | **~0 Latenz**, aber Komplexität | NICHT als Latenz behandeln; Klarheits-Cleanup nur falls RWDR-Scope es verlangt |
| O5 | State-Serialisierung pro Knoten (`state.model_copy(update=…)`) 21×/Turn | real | Pydantic copy je Knoten | gering (Knoten ~0.01s inkl. copy) | unverändert — kein Bloat messbar |
| O6 | Checkpoint-/Persistenz-Overhead (Redis) | real | nicht separat messbar; Knoten-Summe ≈ Turn | `[NV]` separat, vermutlich gering | nichts tun ohne Messung |

### 2.3 Differenz-Analyse statisch vs Trace (Herzstück) `[E]`

- **Knoten, die FEUERN obwohl sie für die Route bedeutungslos sind:** `evidence`,
  `output_contract`+Composer und der gesamte deterministische Spine laufen auch für
  `smalltalk` (3×) und `knowledge_case_side_question` (6×), sobald ein aktiver Case
  existiert (resume → governed graph). → smalltalk-Turn kostet 5–23s. **Beleg:**
  `019e91bb…` (smalltalk, 23s, evidence-getrieben).
- **Knoten, der NIE echte Arbeit leistet:** terminaler `governed_answer_composer`
  (O3) — existiert im Code, feuert, ist aber strukturell ein No-Op.
- **Knoten, die laut RWDR-MVP deaktiviert sein sollen, aber feuern:** `matching`,
  `manufacturer_mapping` laufen auf jedem TERMINATE (kostenlos). Sie produzieren
  laut Spec keine Matching-/Hersteller-Auswahl — im Trace ~0.01s, also vermutlich
  Pass-Through/No-Op. **Differenz:** statische Karte erwartet „deaktiviert", Trace
  zeigt „läuft, aber leer". Latenz-irrelevant, aber Karten-Hygiene. `[A]` (Inhalt
  nicht inspiziert).
- **Pfad, dessen Trace-Dauer die statische Erwartung sprengt:** `evidence` —
  statisch „deterministischer Retrieval-Knoten", real **7.74s Ø / 28s max**,
  CPU-gebundenes Embedding+Rerank (§1.4). Größte Diskrepanz Erwartung↔Realität.

### 2.4 Urteil gegen „einfachste KORREKTE Struktur"

Die lineare Struktur ist für eine governte Pipeline **korrekt und billig**: 18 von
21 Knoten kosten ~0. Es besteht **kein Anlass für einen Architektur-Umbau** (keine
Subgraphen, kein Map-Reduce, keine Fan-out-Agenten). Die Latenz ist **kein
Topologie-Problem**, sondern ein **Knoten-Problem** (3 heiße Knoten) — gezielte
Eingriffe an `evidence`, am Composer-Modell/-Repair und an der Re-Retrieval-Gating
genügen.

### 2.5 Trace-Struktur-Befund: totale Fragmentierung `[E]`

Jeder Root-Run ist **unparented mit eigener `trace_id`** (122/122 dispatch,
28/28 graph, 72/72 ChatOpenAI, 11/11 side_answer). Ein einzelner governter
User-Turn zerfällt in **mehrere separate LangSmith-Roots**: `runtime_dispatch`
(Routing) + `governed_graph_turn` (Graph) + Orphan-`ChatOpenAI` (Dispatch-Zeit-LLMs:
60× gpt-5.4-nano = Router/Conversation, 12× gpt-4o-mini, alle `depth=0`,
`parent=None`). → **Es gibt keinen End-to-End-Turn-Root**; eine saubere
„Gesamt-Turn-Dauer" lässt sich nicht aus einem Run lesen (nur per thread_id/Zeit
korrelieren). Observability-Befund, latenz-neutral.

---

## 3. Jinja2-Bewertung inkl. Doktrin-Grenz-Verdikt

### 3.1 Inventar `[E]`
~101 Templates über mehrere Verzeichnisse: canonical `app/agent/prompts/` (Hot-Path,
Renderer/Communication/Knowledge/Gate), `app/agent/templates/` (Chat/RFQ/Knowledge-
Export), **Legacy `app/prompts/`** (final_answer-Varianten, Agent-Personas,
`challenger_gate.j2`, Manifest), `backend/prompts/templates/` (Legacy),
`app/services/rag/templates/` (Report-Export). **Wildwuchs:** doppelte
`rfq_template.j2` und `engineering_report.j2` (verschiedene Subsysteme, gleiche
Namen); 6 `final_answer_*`-Varianten hinter einem Router-Template. Keine exakten
Duplikate.

### 3.2 Lade-/Render-Mechanik `[E]`
- Canonical `PromptRegistry` = **Modul-Singleton**, `Environment(StrictUndefined,
  trim_blocks, lstrip_blocks)` einmal gebaut (`app/agent/prompts/__init__.py:49-55,114`).
- Legacy-Loader (`common/jinja.py`, `utils/jinja_renderer.py`, `rag/render.py`) via
  `@lru_cache(maxsize=1)`. `PromptBuilder`/`PromptLoader` instanz-gecached.
- **Keine Hot-Path-Rekompilierung:** kein `from_string()` im Turn-Loop; `get_template`
  liefert Jinja2-kompilierte, gecachte Templates. `intake/observe.j2` wird pro
  Extraktion gerendert (billig, kompiliert gecacht). → **Kompilierungs-Kosten auf dem
  Hot-Path: vernachlässigbar.**

### 3.3 Multi-Output-Envelope-Rendering `[E]`
Chat-Reply rendert **einmal** pro Turn; RFQ/PDF/Report rendern separat **on demand**
(Export, nicht im Turn). Kein Mehrfach-Render / Render-then-reparse gefunden. Der
`response_renderer` ist Struktur-Scrubbing, kein Re-Render.

### 3.4 **Doktrin-Grenz-Verdikt** `[E]`

> **`challenger_gate.j2` = tote/inerte Vorlage, KEIN aktives Doktrin-Leck am Guard
> vorbei.**

- **Befund:** `app/prompts/challenger_gate.j2` enthält tatsächlich Eignungs-/
  Ausschluss-/Empfehlungs-Verdikte als Template-Logik („…strikt AUSGESCHLOSSEN",
  „MUSS … empfehlen/vorschlagen", PV-Grenzwert-Imperative). Es ist im Manifest
  registriert (`app/prompts/_manifest.yml:7-8`) und sein Text wird als Variable
  `challenger_gate_text` in `final_answer_composer.j2`, `material_scientist_agent.j2`,
  `mechanical_design_agent.j2` konsumiert (`{% if challenger_gate_text %}…`).
- **Entscheidender Test (Invocation-Grep über `*.py`):** **Kein** Python-Code
  rendert diese Legacy-Composer-Templates oder setzt jemals `challenger_gate_text`
  (Grep-Treffer: 0 außerhalb von Templates/Tests). Die live genutzten
  PromptBuilder-Konsumenten (`user_facing_reply.py:246`, `conversation_runtime.py:212-215`)
  bauen ausschließlich `_prompt_builder.conversation()` — **nicht** den
  final_answer/Material-Scientist-Pfad.
- **Live-Composer-Realität:** Die governte Antwort entsteht über
  `GovernedAnswerComposer` (`build_governed_answer_composer_messages`, gpt-4o-mini)
  bzw. `KnowledgeAnswerComposer` — beide doktrin-bewusst und durch L1/L2-Guards
  abgesichert. Die Verdikt-Sprache von `challenger_gate.j2` kann den Output **nicht**
  erreichen, weil die Variable nie gefüllt und das Template nie gerendert wird.
- **Verdikt:** **Aufräum-/Latenz-Risiko (inert), nicht Guard-Bypass.** Empfehlung:
  als Dead-Prompt-Cleanup entfernen (`challenger_gate.j2` + die drei nie-gerenderten
  Legacy-Composer-Templates), **nicht** „reparieren". Kein HALT, keine Doktrin-Änderung.
- **Gegenrichtung (LLM-Phrasierung leckt in Template-Logik?):** Nicht gefunden — die
  canonical Templates verwenden gebundene Sprache; Generierung passiert im Composer,
  nicht im Template.

### 3.5 Privacy-Faktenbasis (Scope A.5, nur Dokumentation)
- Live: `LANGSMITH_CAPTURE_LLM_CONTENT=true` → der `wrap_openai`-Pfad
  (`observability/langsmith.py:197-219`) erfasst LLM-Roh-`inputs`/`outputs` auf den
  `ChatOpenAI`-Spans. Die `@traceable`-Sanitizer (`sealai_quality.sanitize_*`,
  redacted message/content/prompt-Keys, gehashte Identitäten) greifen auf den
  **Chain**-Spans — die **gewrappten LLM-Spans** tragen die Roh-I/O. `[A]` (LLM-Span-
  I/O bewusst nicht inspiziert; Schluss aus Flag + Verdrahtung).
- **`LANGSMITH_REDACTED_OBSERVATION_SPANS=true` deckt die `wrap_openai`-LLM-Spans
  NICHT ab.** Dieses Flag gated nur die separaten, explizit emittierten
  `sealai.redacted_observation`-Chain-Spans (`langsmith.py:100-104,389`). Der
  Sanitizer-Pfad (`sanitize_trace_inputs/outputs`) hängt ausschließlich an den
  `@traceable`-Chain-Spans (`langsmith.py:299-300`); `wrap_openai_client`
  (`langsmith.py:205-210`) gibt blankes `wrap_openai(client)` **ohne** Sanitizer
  zurück. → Der **scheinbare** Redaction-Schutz wirkt genau dort **nicht**, wo die
  Roh-I/O liegt (die LLM-SDK-Spans). `[E]` Verdrahtung; `[A]` Roh-I/O bewusst nicht
  inspiziert.
- `LANGSMITH_TRACE_LANGGRAPH_CHILDREN=true` → LangGraph-State-Snapshots als Kindspans
  (können extrahierte Felder/Evidence enthalten). `redacted_observation`-Spans sind
  sichtbar (Redaction aktiv).
- **Entscheidungsvorlage (vor Pilot-Start zu entscheiden, hier NICHT entschieden).**
  Aktuell (nur Owner-Tests) unkritisch; vor echtem Nutzer-Traffic ist eine der drei
  Optionen zu wählen:

  | Option | Maßnahme | Debugbarkeits-Verlust |
  |---|---|---|
  | **A. Capture aus** | `LANGSMITH_CAPTURE_LLM_CONTENT=false` (Code-Default) | **hoch** — verbatim Prompt/Response auf LLM-Spans weg; auffällige Turns nur noch lokal/über gezieltes Logging reproduzierbar |
  | **B. Redaction auf LLM-Spans ausweiten** | Sanitizer auch auf den `wrap_openai`-Pfad (Custom-Wrapper, da `wrap_openai` kein `process_inputs/outputs` annimmt) | **mittel** — Span-Form/Token/Timing + redacted/gehashter Inhalt bleiben, verbatim Text weg; Engineering-Aufwand |
  | **C. AVV + Consent** | Capture an lassen, rechtlich decken: AVV mit LangChain/LangSmith + Nutzer-Consent + Retention-Policy | **keiner** — volle Roh-I/O bleibt; Kosten: Vertrag/Consent-UX/Retention, Daten verlassen weiterhin an US-Processor |

---

## 4. Verdrahtungs-Smells auf dem Hot-Path

| # | Smell | real? | Beleg | Bewertung |
|---|---|---|---|---|
| W1 | **Semantic-Router-LLM ohne Timeout** | real | `dispatch.py:724` `await refine_pre_gate_classification(...)` ohne `wait_for`; `semantic_intent_router.py:245/277/295` `responses.create`/`chat.completions.create`, kein Timeout | gpt-5.4-nano-Call auf (fast) jedem Turn, unbeschränkter Tail → verzögert first_progress; Orphan-`ChatOpenAI` bis 9–14s belegt |
| W2 | **`evidence` = CPU-sync Embedding+Rerank, lazy-loaded, untraced** | real | `real_rag.py:114` `run_in_executor`; `rag_orchestrator.py:89,120-122` Cross-Encoder + fastembed globals; Prewarm `prewarm_embeddings()` **nicht aus `main.py` lifespan gerufen** (`[A]` — `warmup_on_start` Inhalt nicht final geprüft) | Cold-Start-Spikes + Default-Threadpool-Contention bei Parallel-Turns; #1 Latenz-Sink |
| W3 | **Guard-Repair = 2. Vollgenerierung** | real, selten | `answer_composer.py:68-79`, `governed_answer_composer.py:142-159`; **2/97 Turns** | Sicherheitsmechanismus (doktrin-nah) → bei Änderung HALT-Klasse |
| W4 | **`_load_existing_governed_state_for_v7` 5 Aufrufstellen** | real | `rg -c` = 5 in `dispatch.py` (754/822/856/968 + 1) | Bedingte Zweige; worst-case mehrfacher Redis-Load/Turn; Redis schnell → geringe reale Kosten |
| W5 | **Composer max_tokens=1800 auf langsamem gpt-4o-mini** | real | `answer_composer.py:52` | lange Wissensantworten (bis 1589 tok-out) → 20–46s pro Generierung; inhärent, nicht redundant |
| W6 | **Tier-Timings nur stdlib-`logger.info` (prod-dark)** | real | `real_rag.py:129,204,233` | RAG-Latenz operativ unsichtbar (kein structlog) |
| – | Sync-in-async (time.sleep/requests/.invoke), N+1-Queries, `copy.deepcopy` | **nicht gefunden** | — | RAG korrekt in Executor offloaded; 18ms-Streaming-Pausen (`streaming.py`) sind bewusste UI-Pacing, kein Bug |

---

## 5. Priorisierter Nachschärfungs-Backlog (sortiert nach Wirkung-pro-Aufwand)

| Rang | Maßnahme | Erwarteter Gewinn | Aufwand | Risiko/Blast-Radius | Abnahme-Metrik (gemessen) |
|---|---|---|---|---|---|
| **1** | **`evidence` Re-Retrieval gaten/cachen** (O1): überspringen, wenn EvidenceQuery-Hash unverändert seit letztem Cycle; Ergebnis im State cachen | governte Folge-Turns & smalltalk/side-question mit aktivem Case: −5…−8s je Turn | mittel | **mittel (Stale-Evidence)** — nur `evidence_node`, fail-open bleibt | **Latenz:** governed_graph_turn `smalltalk`/`knowledge_case_side_question` p50 sinkt von 5.4/7.9s → Ziel <2s; `evidence`-Span feuert nur bei Query-Änderung. **Korrektheit (Regressionstest, MUSS):** bei geänderter EvidenceQuery / Case-Mutation feuert `evidence` neu — **kein Cache-Treffer mit veralteter Evidence**; die Cache-Invalidierung deckt alle retrieval-relevanten Inputs ab (asserted params, Medium, Query) |
| **2** | **fastembed+Reranker im Startup prewarmen + RAG-Tier-Timings auf structlog** (W2/W6) | eliminiert Cold-Start-Spikes; macht #1-Sink sichtbar | niedrig | niedrig | erste Retrieval nach Deploy kein Ausreißer mehr; `evidence` p95 < (Baseline 36s) deutlich; tier1/tier2-Dauer in prod-Logs sichtbar |
| **3** | **Semantic-Router-LLM mit `asyncio.wait_for` + deterministischem Fallback kappen** (W1) | begrenzt first_progress-Tail | sehr niedrig | niedrig (Fallback existiert) | kein Router-Span > N s; CONVERSATION-Dispatch p90 (25.6s) sinkt |
| **4** | **Composer-Modell/Token überdenken**: kürzeres `max_tokens` für Wissensantworten oder schnelleres Modell für die Schreib-Passage (W5) | −Sekunden auf jeder langen Antwort | mittel | **mittel (Qualität/Doktrin-nah)** | active_case_side_answer/CONVERSATION p50 (11.4/1.8s, p95 34–36s) sinkt ohne Qualitätsabfall (Eval) |
| **5** | **End-to-End-Turn-Trace + Server-seitige first_progress/latency persistieren** (§2.5/§1.5) | echte C8-Observability, Alarmierbarkeit | mittel | niedrig | ein Root-Run pro Turn; first_progress/latency in Metadaten/structlog abfragbar |
| **6** | **Dead-Prompt-Cleanup**: `challenger_gate.j2` + 3 nie-gerenderte Legacy-Composer-Templates entfernen (§3.4); `governed_answer_composer`-Doppel-Verdrahtung auflösen (O3) | Klarheit, eliminiert latentes Doktrin-Risiko | niedrig | niedrig | Grep-frei; Knoten-Karte ohne No-Op-Knoten |
| 7 | Guard-Repair-Kosten senken (kürzere Repair-Generierung) (W3) | −~24s auf den ~2% Repair-Turns | niedrig | **HALT-Klasse (Doktrin)** | nur nach `doctrine-reviewer`-Freigabe |

---

## 6. Schlussverdikt (3 Sätze)

1. **Produkt-Güte heute:** Die governte Pipeline ist **strukturell korrekt und
   überraschend schlank** — 18 von 21 Graph-Knoten kosten ~0, es gibt keinen
   Architektur-Schmerz; die reale Latenz (engineering-Turn **p50 ~20s / p95 ~37s**,
   Wissens-Tail bis ~49s) entsteht fast vollständig in **drei** Stellen: RAG-`evidence`
   (CPU-Embedding+Rerank, 7.7s Ø), dem gpt-4o-mini-Composer und der `intake`-Extraktion.
2. **Die 3 lohnendsten Hebel:** (a) Re-Retrieval von `evidence` bei unveränderter
   Query gaten/cachen, (b) Embedding/Reranker beim Start prewarmen **und** die
   RAG-Tier-Timings sichtbar machen, (c) den ungekappten Semantic-Router-LLM mit
   Timeout+Fallback begrenzen — alle drei gezielt, geringer Blast-Radius, messbar.
3. **Bewusst NICHT anfassen:** den linearen deterministischen Spine (kostenlos —
   keine Parallelisierung „um der Eleganz willen"), die Hybrid+Rerank-Retrieval-
   Qualität und die Guard-Repair-Sicherheitsschleife (doktrin-nah); `challenger_gate.j2`
   nur **löschen**, nicht reparieren (es ist inert, kein Leck).

---

## 7. Tier-0-Retrieval-Guard-Status in Prod (kritisch · Pre-Pilot-Blocker)

> **Verdikt (1 Satz):** Der Tier-0-Fail-closed-Guard greift im laufenden Prod-Backend
> **nur teilweise** — der primäre Funnel feuert und der Flag-Default ist fail-safe,
> aber **zwei von drei** Enforcement-Punkten (Cascade-Close + dispatch re-raise)
> fehlen im deployten Image `ccdd4577`. → **Pre-Pilot-Blocker, kein Backlog-Item.**

### 7a. Image-vs-HEAD-Differenz `[E]`
- Laufendes Prod-Image = `@sha256:045c2c…` = Commit **`ccdd4577`** (Merge PR #85,
  Parked-Items-Closeout). Es ist zugleich der **Pre-Deploy-Rollback-Anker** des
  Deploy-Gates (ops.md: Anker = Live-Image aus dem laufenden Daemon, nie Erinnerung)
  — bestätigt aus §0 (Daemon). `[E]`
- Die Bucket-4-Tier-0-Härtungs-Commits sind **NICHT** im Image:
  `git merge-base --is-ancestor 538302ea ccdd4577` → false;
  `… 972db6df ccdd4577` → false. Beide sind aber **Vorfahr von HEAD `ba460ae8`**
  (`… 538302ea/972db6df ba460ae8` → true). `[E]`
- `538302ea` = „close the Tier-0 BM25 cascade bypass at the retrieval funnel (B1/B2)";
  `972db6df` = „re-raise TierViolation in the knowledge RAG retriever (audit #3)".
  Beide liegen im Bereich `ccdd4577..ba460ae8`, der noch nicht deployt ist. `[E]`

### 7b. Code-Default `SEALAI_TIER0_RETRIEVAL_GUARD` bei unset `[E]`
- `retrieval_guard_enabled()` (`turn_tier.py:58-61`):
  `raw = (os.getenv("SEALAI_TIER0_RETRIEVAL_GUARD") or "1").strip().lower()` →
  **unset ⇒ `"1"` ⇒ nicht in `{0,false,no,off}` ⇒ `True` (enforced)**. D.h. exakt
  wie beim LLM_EXTRACTION-Befund: **`unset ≠ aus`**. Der Env-Default schwächt den
  Guard nicht — er ist fail-safe.
- `enforce_retrieval_allowed` (`turn_tier.py:64-80`) ist **nicht** unconditional,
  sondern **tier-gated + flag-gated**: No-op außer der deklarierte Tier == `TIER_0`
  (Zeile 70), dann Kill-Switch-gegated (Zeile 72), sonst `raise TierViolation`
  (Zeile 78). Die Tier-Deklaration reitet auf einem ContextVar, gesetzt aus der
  Route bei Turn-Eintritt. → Der Flag-Pfad ist korrekt fail-safe; der Befund liegt
  **nicht** am Flag, sondern an der Image-Differenz (7a).

### 7c. Greift der Guard im laufenden Prod-Backend? → **teilweise** `[E]`
- **Vorhanden im Image `ccdd4577`:** der primäre Funnel-Call
  `rag_orchestrator.hybrid_retrieve` → `enforce_retrieval_allowed("rag_hybrid")`
  (`rag_orchestrator.py:996-998`, per `git show ccdd4577:…` bestätigt). Ein
  Tier-0-Turn, der `hybrid_retrieve` direkt erreicht, wirft dort `TierViolation`.
- **Fehlt im Image:** (1) der BM25-**Cascade-Close** (`real_rag.py:89`, aus
  `538302ea`) → der Cascade-/`retrieve_with_tenant`-Pfad ist im Image **unguarded**,
  der B1/B2-Bypass offen; (2) der **dispatch re-raise** (`dispatch.py:181-186`, aus
  `972db6df`) → im Image schluckt der broad `except Exception` in
  `_knowledge_rag_retriever` eine `TierViolation` und degradiert **still zu `[]`**
  (leeres Wissensergebnis), statt laut zu scheitern. `[E]`
- **Praktische Exposition:** Beide Lücken sind Defense-in-Depth-Backstops; ein
  Tier-0-Turn erreicht Retrieval nur über einen **Routing-Bug** (Tier-0 routet
  normal zu Greeting/Meta/Blocked und nie zum Retriever, vgl. Commit-Message
  `972db6df`). Tritt dieser Routing-Bug aber ein, würde Prod heute **nicht
  fail-closed** reagieren: Cascade-Pfad ungeschützt, Knowledge-Dispatch-Pfad
  maskiert die Violation. Die Härtung existiert auf HEAD, ist aber **nicht live**.
- **Live-Env-Wert** von `SEALAI_TIER0_RETRIEVAL_GUARD` in diesem Bericht nicht
  unabhängig bestätigt (operator-owned `.env`, nicht gelesen) `[NV]`; irrelevant
  für das Verdikt, da unset = enforced (7b).

### 7d. Konsequenz (Befund, kein Fix)
**Pre-Pilot-Blocker, nicht Backlog:** HEAD `ba460ae8` deployen, damit alle drei
Enforcement-Punkte live sind, **bevor** echter Nutzer-Traffic startet. Das Flag
muss dafür **nicht** gesetzt werden (unset = enforced); vor Deploy lediglich
prüfen, dass `.env.prod` es nicht auf einen Off-Wert (`0/false/no/off`) pinnt.
Kein Fix/Deploy im Rahmen dieses Berichts.

---

### Anhang — Reproduzierbarkeit
Alle Latenz-/Span-Zahlen aus LangSmith-Projekt `sealai-production` via
`docker exec -i backend python` mit installiertem `langsmith`-SDK (Root-Runs,
`read_run(load_child_runs=True)`); ausschließlich Timings/Namen/Zähler/Token/Run-IDs
ausgewertet, keine `inputs`/`outputs`. Code-Belege gegen Backend-Image
`@sha256:045c2c2f…` (HEAD `ba460ae8`).
