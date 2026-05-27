# Phase 9 - Executive Summary

## Kurzfassung

SealingAI ist in diesem Repository kein einzelner Algorithmus, sondern eine conversation-first Runtime mit einem gouvernierten Backend-Pfad fuer technische Dichtungsfaelle. Das System trennt Wissen/Smalltalk von Case Intake, sammelt technische Fakten, normalisiert sie, leitet Assertions ab, zieht Evidenz/RAG hinzu, rechnet deterministische Kennwerte, bewertet Governance/Readiness und laesst sichtbare technische Antworten durch einen finalen Guard.

Der deterministische Kern liegt hauptsaechlich hier:

- `backend/app/agent/state/reducers.py`
- `backend/app/agent/domain/normalization.py`
- `backend/app/services/calculation_engine.py`
- `backend/app/agent/domain/rwdr_calc.py`
- `backend/app/agent/v92/calculator_registry.py`
- `backend/app/agent/graph/nodes/compute_node.py`
- `backend/app/agent/graph/nodes/governance_node.py`
- `backend/app/agent/graph/nodes/matching_node.py`
- `backend/app/agent/graph/output_contract_assembly.py`
- `backend/app/agent/v92/final_guard.py`
- `backend/app/agent/state/persistence.py`
- `backend/app/services/case_service.py`

Der Kern ist konzeptionell gut gemeint, aber aktuell nicht hart genug isoliert. LLM, RAG, Zeit, Random IDs, Set-Ordering und Snapshot-Vergleich koennen in oder nahe an deterministische Entscheidungs- und Persistenzpfade gelangen.

## Kann man Replayability heute vertrauen?

Nein, nicht voll. Es gibt gute Teiltests, aber keinen durchgehenden Replay-Beweis vom gleichen kanonischen Input zur gleichen kanonischen Ausgabe. Kritisch ist, dass `normalized_at` aus der Wall Clock in normalisierte technische Werte gelangt und diese normalisierte State-Slice in den Decision-Basis-Hash eingeht.

## Kann man Idempotency heute vertrauen?

Nur eingeschraenkt. `CaseService.write_snapshot` dedupliziert, wenn `basis_hash` und komplettes `state_json` gleich sind. Das ist fuer denselben State-Objektpfad getestet, aber nicht fuer zwei frisch erzeugte, semantisch gleiche States mit unterschiedlichen Zeit-/UUID-Feldern.

## Kann man stabiler Seal/Hash-Erzeugung heute vertrauen?

Nein. Es existiert ein `decision_basis_hash`, aber kein vollstaendig kanonischer, signierter Seal. Der aktuelle Hash ist eher ein kompakter Fingerprint ausgewaehlter State-Slices als ein verifizierbarer technischer Seal.

## Top 10 Risiken

1. Wall-clock `normalized_at` kann den Decision-Basis-Hash veraendern.
2. `set`-Iteration in `reduce_observed_to_normalized` kann Output-Reihenfolge veraendern.
3. LLM-Extraction ist im governed Intake standardmaessig aktiv.
4. Semantic Intent Router kann per LLM Routing zwischen Wissen und Case beeinflussen.
5. RAG kann Assertions und Evidenzstatus veraendern.
6. RAG/BM25/FactCard-Ranking hat unvollstaendige Tie-Breaker.
7. Snapshot-Idempotency vergleicht komplettes `state_json` inklusive volatiler Felder.
8. Case-Nummern nutzen Datum plus Count und sind race-anfaellig.
9. Redis Checkpointer kann auf In-Memory fallbacken und Replay/Durability veraendern.
10. Mehrere Fail-open-Pfade liefern leere/partielle Ergebnisse statt typisiert degradierter State.

## Top 10 empfohlene Massnahmen

1. Vor jedem Patch Golden-/Replay-Tests einfuehren.
2. `normalized_at`, UUIDs und Trace-Zeit aus kanonischem Hash ausschliessen oder explizit injizieren.
3. Einen `build_canonical_decision_basis(state)` einfuehren.
4. Reducer-Felditeration stabil sortieren.
5. Tie-Breaker fuer RAG/BM25/FactCard-Ranking ergaenzen.
6. LLM/RAG-Boundary-Outputs vollstaendig snapshotten: Prompt, Modell, Raw Output, Source IDs, Scores.
7. Snapshot-Idempotency auf kanonische Nutzdaten statt volles volatile `state_json` stuetzen.
8. Case-Nummernerzeugung DB-sicher machen oder Retry auf Unique-Konflikt ergaenzen.
9. Typed degraded states fuer RAG/Compute/LLM-Ausfaelle einfuehren.
10. Engine-, Schema-, Prompt-, Model- und Calculator-Versionen in Replay-Bundle und Hash-Basis aufnehmen.

## Top 5 fehlende Tests

1. Full canonical replay: gleiche Inputs, gleiche Evidenz, gleiche Config, gleiche kanonische Ausgabe.
2. Hash-Stabilitaet trotz unterschiedlichem `normalized_at` und Random IDs.
3. Reducer- und Ranking-Stabilitaet ueber unterschiedliche `PYTHONHASHSEED` und shuffled equal-score inputs.
4. Idempotency mit zwei frisch erzeugten, semantisch gleichen States.
5. Concurrent case creation/write fuer gleiche Session und Monatsnummern.

## Sofort empfohlener naechster Schritt

Patchphase nur mit Stage 0 beginnen: Charakterisierungs- und Golden-Tests schreiben. Noch keine Architektur-Umbauten, keine Migrationen und keine Optimierungen.

## Was noch nicht geaendert werden sollte

- Keine RAG-Caches einfuehren, bevor Tie-Breaker und Corpus-Versionierung sauber sind.
- Keine LLM-Pfade "optimieren", bevor Boundary-Snapshots existieren.
- Keine Persistenz-/Migrationsthemen anfassen, bevor Canonical Hash und Idempotency-Tests stehen.
- Keine Frontend-Logik nutzen, um technische Wahrheit zu korrigieren.
- Keine breiten Refactors am Graph, solange die deterministischen Invarianten nicht testgesichert sind.

