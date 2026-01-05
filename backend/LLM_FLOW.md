LLM & Prompt Flow Guidelines
=============================

Kurz: zentrale Regeln und Konventionen zur Verwendung von Systemprompts, RAG und Conversation Memory.

1) Single System Message
- Es darf pro LLM‑Aufruf nur eine `SystemMessage` geben. Diese enthält:
  - gerenderten Agentenprompt (Jinja2)
  - optional: kompakte Thread‑Summary (falls vorhanden)
  - optional: top‑k RAG Snippets (token‑budgetiert)

2) Prompt Rendering
- Templates liegen in `backend/app/services/langgraph/prompts` und werden über `render_template(...)` gerendert.
- Verwende `get_agent_prompt(agent_id, context={...})` um gerenderte Prompt‑Texte zu bekommen. Falls `context` `rag_context` oder `rag_docs` enthält, wird der Prompt tokenbewusst zusammengesetzt.

3) Token Budgeting
- Füge `tiktoken` als optionales dependency hinzu. Wenn installiert, verwenden wir genaue Tokenzählung; ansonsten Schätzung (~4 chars/token).
- ENV: `PROMPT_MAX_TOKENS` (Default 3000) steuert Budget beim Zusammenführen von Template + Summary + RAG.

4) Conversation Memory
- Kurze Nutzung: `read_history_raw` liefert ggf. eine kompakte Thread‑Summary als erste Systemnachricht.
- Vor dem Senden an das LLM: entferne SystemMessages aus der History und füge die Summary stattdessen in die SystemMessage ein (vermeidet Duplikate).

5) RAG Policy
- Nur Top‑N relevante Dokumente in `rag_docs` (Default 3–5). Die Auswahl passiert in der RAG‑Orchestrator/Graph Nodes.

6) Errors & Fallbacks
- Template‑Rendering ist fail‑safe: Bei Render‑Fehlern wird der Rohtext gesendet und eine Warnung geloggt.
- Wenn Tokenzählung nicht verfügbar ist, wird eine grobe Char‑Heuristik verwendet.

7) Konfigurationspunkte
- `PROMPT_MAX_TOKENS` – Tokens Limit für system prompt composition
- `OPENAI_MODEL` – model name for token counting
- `WS_*` – WebSocket streaming tunables in `ws_config`

8) Tests
- Füge Unit‑Tests für:
  - Template Rendering + Default Context
  - SystemMessage composition (no duplicates)
  - Token truncation behavior (with and without tiktoken)

Weitere Details: siehe `backend/app/services/langgraph/prompting.py` und `backend/app/services/langgraph/prompt_registry.py`.

