# Repository Map - SealAI

## Verzeichnisbaum (bis Tiefe 3) der relevanten Bereiche

### backend/app
- backend/app/
  - api/
    - routes/
    - v1/
      - dependencies/
      - endpoints/
      - schemas/
  - cli/
  - common/
  - core/
  - models/
  - services/
    - auth/
    - chat/
      - tests/
    - memory/
    - rag/

### frontend
- frontend/
  (Tiefe 3 nicht erreicht)

### langgraph
- langgraph/
  - checkpoint/

### services (unter backend/app/services)
- backend/app/services/
  - auth/
  - chat/
  - memory/
  - rag/

### rag (unter backend/app/services/rag)
- backend/app/services/rag/

### utils (kein spezifischer utils-Ordner gefunden, common/ möglicherweise)

### prompts
- prompts/

### tests
- tests/
- backend/tests/
- backend/app/services/chat/tests/

## Auflistung existierender Graph-/Node-/RAG-/Tool-Module
- langgraph/graph.py: Hauptgraph-Definition
- langgraph/constants.py: Konstanten
- langgraph/checkpoint/: Checkpoint-bezogene Dateien
- backend/app/services/rag/: RAG-Services
- backend/app/services/chat/: Chat-Services
- backend/app/services/memory/: Memory-Services

## Liste der LLM-Prompts (Dateinamen, Pfade)
- prompts/: Enthält Prompt-Dateien (Details siehe Inhalt)

## Liste der Konfig-Dateien (.env, settings, yaml)
- .env
- .env.dev
- .env.example
- .env.prod
- docker-compose.yml
- backend/.env
- backend/requirements.txt