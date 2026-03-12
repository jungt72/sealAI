# RWDR Selector Runtime Implementation

Diese Datei beschreibt die reale Implementierung im kanonischen Pfad `backend/app/agent`.

## Schichten

- `backend/app/agent/domain/rwdr.py`
  - Verträge und zentrale Konfiguration.
- `backend/app/agent/domain/rwdr_core.py`
  - deterministische Ableitung der RWDR-Core-Signale.
- `backend/app/agent/domain/rwdr_decision.py`
  - deterministische Hard-Stop-, Review-, Warning-, Modifier- und Type-Class-Entscheidung.
- `backend/app/agent/agent/rwdr_orchestration.py`
  - Flow-Steuerung fuer Stage 1, Stage 2, Stage 3 sowie Merge und Re-Evaluation.
- `backend/app/agent/agent/rwdr_patch_parser.py`
  - eng begrenzter Feldparser fuer einfache, explizite Einzelantworten.
- `backend/app/agent/agent/graph.py`
  - Orchestrierungspunkt; entscheidet nur, ob der RWDR-Pfad oder der bestehende Agent-Pfad ausgefuehrt wird.
- `backend/app/agent/api/router.py`
  - reiner Transport-Layer fuer REST/SSE; keine RWDR-Fachlogik.
- `backend/app/agent/agent/sync.py`
  - Read-model-/Projektionsebene fuer `working_profile["rwdr"]` und Transport-Payloads.

## Aktive Integrationspunkte

- `ChatRequest.rwdr_input`
  - vollstaendiger strukturierter RWDR-Input.
- `ChatRequest.rwdr_input_patch`
  - partieller strukturierter Patch fuer mehrturnige Vervollstaendigung.
- `sealing_state["rwdr"]`
  - kanonischer Runtime-State fuer Flow, Draft, Input, Derived und Output.
- `working_profile["rwdr"]`
  - stabile Projektion fuer laufende Anzeige und Debugging.

## Flow

1. Strukturierter Vollinput oder Patch wird in `rwdr_orchestration.merge_rwdr_patch(...)` gemerged.
2. `rwdr_orchestration.evaluate_rwdr_flow(...)` bestimmt fehlende Stage-1-/Stage-2-Felder.
3. Wenn noetig, wird aus `next_field` eine gezielte Rueckfrage erzeugt.
4. `rwdr_patch_parser.parse_rwdr_patch_for_field(...)` darf nur das aktuell angeforderte Feld uebernehmen.
5. Erst bei ausreichender Vollstaendigkeit laufen `derive_rwdr_core(...)` und `decide_rwdr_output(...)`.

## Verbotene Anti-Patterns

- Keine RWDR-Fachlogik in `router.py`.
- Keine neue RWDR-Monolithik in `logic.py`.
- Keine breite Freitext-Extraktion statt typed Patch-Pfad.
- Keine parallelen Sources of Truth neben DTOs, Config, Core und Decision.
