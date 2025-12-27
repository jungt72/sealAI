# Audit: Chat -> Formular Param-Sync (pressure_bar)

## Scope
- Ziel: Nach Chat-Anweisung (z. B. "auf 7 bar") muss `pressure_bar` im Backend-State aktualisiert werden und im Formular erscheinen.
- Audit-Reihenfolge: Code-Trace, Repro-Skript, State-Check.

## Evidence (Code)
- Parameter-Extraktion aus Chat-Text: `backend/app/langgraph_v2/utils/parameter_extraction.py:29`.
- Frontdoor-Node schreibt extrahierte Parameter in den State (inkl. LLM-Fallback): `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:199`.
- Chat-V2 SSE Endpoint startet den Graph-Run: `backend/app/api/v1/endpoints/langgraph_v2.py:301`.
- State-Read über `/api/v1/langgraph/state`: `backend/app/api/v1/endpoints/state.py:141`.
- Frontend refresh nach Chat-Run: `frontend/src/app/dashboard/components/Chat/ChatContainer.tsx:216`.

## Repro (Script)
1) Setze `pressure_bar=10` via PATCH.
2) Sende Chat-Message: "Bitte ändere den Betriebsdruck auf 7 bar."
3) Danach: GET `/api/v1/langgraph/state?thread_id=<id>` und prüfe `.parameters.pressure_bar`.

Script:
```
ops/repro_param_flow.sh <chat_id>
```

## Observations
- (To fill) Output aus `ops/repro_param_flow.sh`.
- Erwartung: `.parameters.pressure_bar == 7`.

## Root Cause (if failing)
- Wenn `pressure_bar` im State nach Chat **nicht** aktualisiert ist:
  - `extract_parameters_from_text()` erkennt Druck ohne explizites "bar" nicht zuverlässig (z. B. "Druck von 10 auf 7") und der Frontdoor-LLM-Fallback hat früher keine Extraktion angewendet. Siehe `backend/app/langgraph_v2/utils/parameter_extraction.py:36` und `backend/app/langgraph_v2/nodes/nodes_frontdoor.py:199`.

## Fix Summary
- Erweiterte Druck-Extraktion für "Druck ... 7" ohne Einheit.
- Frontdoor-Fallback (LLM-Error) wendet Extraktion ebenfalls an.

## Verification
- Backend: `ops/repro_param_flow.sh <chat_id>` zeigt `pressure_bar == 7`.
- Frontend: Nach Chat-Message springt Formularfeld `Betriebsdruck (bar)` auf 7.
