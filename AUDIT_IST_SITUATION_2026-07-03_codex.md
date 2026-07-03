# AUDIT IST-SITUATION 2026-07-03 — Codex Re-Audit sealAI V2

Stand: 2026-07-03  
Branch: `relay/codex-audit-v2-grounding`  
Commit: `6fec68e0`  
Scope: VPS `sealai-vps`, Repo `~/sealai`, Branch-Basis `main`; keine Produktion deployed.

## Kurzfazit

Die beiden vorhandenen Reports vom 2026-07-02 und 2026-07-03 sind in den Hauptbefunden weitgehend verifiziert: die kritischen Compose-Wiring-Gaps aus dem 2026-07-03-Report sind im aktuellen `main` durch `ad40ba98` geschlossen, die Pipeline hat die wesentlichen L2/L3/Guard/Memory-Stufen produktiv verdrahtet, und der auffällige PTFE-Befund ist real.

Der wichtigste zusätzliche Befund ist präziser als im Vorreport: `FK-PTFE-KALTFLUSS` fehlt nicht in Qdrant. Die Karte ist live vorhanden und reviewed, wird bei der generischen PTFE-Frage aber erst deutlich hinter vielen Draft-Claims gerankt. Dadurch bleibt der Top-k-Retrieval-Kanal draft-only und `RetrievalResult.grounded` wird false, obwohl reviewed Wissen existiert.

## Findings

### P1 — Dense-only Qdrant Top-k verdrängt reviewed PTFE-Wissen durch Draft-Masse

**Status:** verifiziert und auf Audit-Branch gefixt.  
**Betroffene Stelle:** `backend/sealai_v2/knowledge/qdrant_retrieval.py`.

Live-Probe vor Fix, gegen Qdrant Collection `sealai_v2_fachkarten`, Query `Bitte gebe mir informationen zu PTFE`:

- Top 1-20: ausschließlich `draft`-Claims, überwiegend generische PTFE-Draft-Karten.
- `FK-PTFE-KALTFLUSS` reviewed erscheint erst auf Rang 69 und 91.
- Exact scroll bestätigt 3 reviewed Payloads zu `FK-PTFE-KALTFLUSS` in Qdrant.
- Pipeline-Result vor Fix: `reviewed 0`, `draft 5/8`, `grounded False`.

Root Cause im Code:

- `stages.ground()` fragt den Retriever mit default `k=5` ab und `RetrievalResult.grounded` hängt an reviewed `grounding_facts`.
- `QdrantFachkartenRetriever._retrieve_sync()` holte exakt `limit=k` aus Qdrant und splittete danach reviewed/draft.
- Bei broad material queries kann dense ranking relevante Draft-Übersichtskarten vor reviewed Safety/Caveat-Karten schieben.

Fix:

- Qdrant holt intern einen begrenzten Kandidatenpool (`min(128, k * 24)`).
- Die ursprünglichen Top-k bleiben erhalten.
- Nur wenn Top-k komplett draft-only ist, werden maximal 2 score-nahe reviewed Claims ergänzt.
- Bei Materialfragen wird reviewed Backfill auf passende Material-Scope/Card-ID priorisiert, damit breite Alternativkarten nicht vor der eigentlichen Materialkarte landen.

Empirischer Nachweis nach Fix, mit Branch-Code im temporären Container im Docker-Netz:

```text
reviewed 2 draft 5 grounded True
REVIEWED FK-PTFE-KALTFLUSS Lösungen: federvorgespannte PTFE-Dichtung, FEP/PFA-ummantelter O-Ring (Elastomerkern) oder PTFE-Compound.
REVIEWED FK-PTFE-KALTFLUSS Ein reiner PTFE-O-Ring dichtet statisch unzuverlässig: Kaltfluss/Kriechen unter Dauerlast, keine elastische Rückstellung.
```

Tests:

```text
cd ~/sealai/backend && python3 -m pytest sealai_v2/tests/test_qdrant_retrieval.py -q
# 11 passed

cd ~/sealai/backend && python3 -m pytest sealai_v2/ -q
# all tests passed
```

Residual Risk:

- Der Fix ist bewusst ein Hotfix für reviewed recall unter Dense-only Retrieval. Der robustere Zielzustand bleibt Hybrid Retrieval mit sparse/BM25 oder RRF/Reranking.

### P1 — LangSmith zeigt keine deterministischen Pipeline-Stufen als eigene Spans

**Status:** verifiziert, nicht gefixt.

Codebefund:

- `Pipeline.run()` ist als `@traceable(name="v2_turn", run_type="chain")` instrumentiert.
- `_staged()` schreibt Progress/Timing, erzeugt aber keine LangSmith Child-Spans.
- Live-SDK-Probe in `backend-v2` zeigt aktuelle Runs wie `v2_turn` und mehrere `ChatOpenAI`-LLM-Runs, aber keine Stage-Spans wie `ground`, `compute`, `output_guard`, `verify`.

Warum relevant:

- Für Debugging von Grounding/Guard/Latency muss man derzeit lokale Timing-Logs plus LangSmith LLM-Spans korrelieren.
- Gerade der PTFE-Bug wäre mit einem `ground`-Span inklusive reviewed/draft counts sofort erkennbarer gewesen.

Empfohlener Fix:

- `_staged()` oder die einzelnen Stage-Wrapper als tracebare Child-Runs instrumentieren.
- Keine Inhalte/PII loggen; nur stage name, counts, flags, latencies, verdict status.

Best-practice-Abgleich:

- Die offiziellen LangSmith-Dokumente beschreiben Custom Instrumentation mit `@traceable`, automatischer Nesting-Hierarchie und expliziten Child-Runs für Pipeline-Schritte.

### P2 — Env/Compose: Produktive Kill-Switches und Feature-Flags sind jetzt durchgereicht; eval-only Judge bleibt bewusst nicht live

**Status:** verifiziert.

Live Compose `backend-v2` reicht jetzt u. a. durch:

- `SEALAI_V2_UNDERSTAND_ENABLED`
- `SEALAI_V2_VERIFY_ENABLED`
- `SEALAI_V2_GROUND_ENABLED`
- `SEALAI_V2_COMPUTE_ENABLED`
- `SEALAI_V2_MEMORY_ENABLED`
- `SEALAI_V2_DISTILL_ENABLED`
- `SEALAI_V2_RETRIEVER_BACKEND`
- `SEALAI_V2_QDRANT_URL`
- `SEALAI_V2_RESPONSE_CONTRACT_ENABLED`
- `SEALAI_V2_RESPONSE_CONTRACT_GENERAL_GUARD_ENABLED`
- `SEALAI_V2_MATERIAL_PARAM_TABLE_ENABLED`

Bestätigt gegen `docker-compose.deploy.yml`.

Nicht als Bug gewertet:

- `SEALAI_V2_JUDGE_PROVIDER` und `SEALAI_V2_JUDGE_MODEL` stehen in `.env.prod`, werden aber nicht in `backend-v2` injiziert. Code-Nutzung zeigt: `judge_*` ist eval-only (`backend/sealai_v2/eval/*`), nicht Serve-Path.

### P2 — Pipeline-Wiring ist weitgehend produktiv, aber Coverage/Produktspec bleiben governance-gated

**Status:** verifiziert.

Wired/aktivierbar:

- L2 Retriever + Matrix + Versagensmodi unter `ground_enabled`.
- L3 verifier unter `verify_enabled`.
- Deterministic calc unter `compute_enabled`.
- Memory + Distiller unter `memory_enabled`/`distill_enabled`.
- Response contract + general guard über Flags.
- Material-Parameter-Tabelle über Flag.
- Medium Intelligence über Flag.

Bewusst off / offen:

- `coverage_gate_enabled=false` live.
- `produktspec_enabled=false` live.
- RWDR hat laut Vorreport weiterhin keine reviewed Claims; dieser Re-Audit hat daran nichts geändert.

### P2 — Structured-output-Lücke im `understand` Helper bleibt offen

**Status:** zusätzlicher Befund, nicht gefixt.

`stages.understand()` fordert JSON per Prompt und parst mit `json.loads()`, validiert aber nicht über providerseitige Structured Outputs / JSON Schema. Fallback ist safe (`Intent.UNKLAR`), aber die Qualität und Messbarkeit der Annotation bleibt schwächer als nötig.

Empfehlung:

- Für OpenAI-kompatible Provider, wo unterstützt, `response_format` / Structured Outputs mit strict JSON Schema nutzen.
- Für Mistral/kompatible Pfade Capability-gated fallback behalten.

Best-practice-Abgleich:

- OpenAI empfiehlt Structured Outputs statt JSON mode, wenn Schema-Adherence benötigt wird.

## Code Changes

Commit: `6fec68e0` (`fix(v2): backfill reviewed qdrant grounding`)

Geändert:

- `backend/sealai_v2/knowledge/qdrant_retrieval.py`
  - reviewed backfill für Qdrant Dense-only Retrieval.
  - score-bound, max 2 reviewed facts, material-aware selection.
- `backend/sealai_v2/tests/test_qdrant_retrieval.py`
  - Tests für Backfill, Score-Schwelle, Material-Scope-Priorisierung und No-op bei bereits reviewed Top-k.

Nicht geändert:

- Keine Compose-/Env-Dateien.
- Kein Deploy.
- Keine Produktion neu gestartet.

## Verification Log

- `ssh sealai-vps 'cd ~/sealai && git switch -c relay/codex-audit-v2-grounding'`
- Prior reports gelesen: `AUDIT_IST_SITUATION_2026-07-02.md`, `AUDIT_IST_SITUATION_2026-07-03.md`.
- Docker/Compose live geprüft: `backend-v2`, `qdrant`, `postgres`, `redis`, `keycloak`, `nginx`, `frontend` healthy bzw. running.
- Env/Settings/Compose Sweep per AST/Regex durchgeführt.
- Qdrant PTFE Ranking live geprüft: reviewed `FK-PTFE-KALTFLUSS` auf Rang 69/91 vor Fix.
- Exact Qdrant scroll bestätigt reviewed `FK-PTFE-KALTFLUSS` Payloads.
- LangSmith live geprüft: `LANGSMITH_TRACING=true`, Projekt `sealai-production`, Runs sichtbar.
- Targeted tests grün: `sealai_v2/tests/test_qdrant_retrieval.py`.
- Full backend suite grün: `python3 -m pytest sealai_v2/ -q`.

## Quellen / Best-Practice-Abgleich

- LangSmith Custom Instrumentation: `@traceable` für einzelne Funktionen; nested child runs werden automatisch unter einem traced parent gruppiert. https://docs.langchain.com/langsmith/annotate-code
- Qdrant Hybrid Queries: dense + sparse/Fusion (`rrf`, `dbsf`) zur Kombination semantischer und lexicaler Signale. https://qdrant.tech/documentation/search/hybrid-queries/
- Qdrant Hybrid Search with Reranking: Hybrid Retrieval + Reranking für bessere Präzision auf Kandidatenpools. https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/
- OpenAI Structured Outputs: Schema-Adherence via JSON Schema/`strict: true`, empfohlen gegenüber JSON mode, wenn möglich. https://developers.openai.com/api/docs/guides/structured-outputs

## Offene Items

1. Qdrant Retrieval auf echten Hybrid-Modus ausbauen: dense + sparse/BM25, Fusion/RRF, optional rerank. Der Backfill-Fix ist kein Ersatz dafür.
2. LangSmith Stage-Spans ergänzen: `recall`, `ground`, `compute`, `contract`, `guard`, `verify`, `exfil`, `remember` mit PII-armen Metadaten.
3. RWDR-reviewed Claim-Lücke schließen und evalseitig absichern.
4. `understand` auf providerseitige Structured Outputs umstellen, mit fallback für Provider ohne Schema-Support.
5. Coverage-Gate und Produktspec erst nach adjudicated eval und Owner-Freigabe aktivieren.
