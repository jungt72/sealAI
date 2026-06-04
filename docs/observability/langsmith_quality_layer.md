# SealAI LangSmith Quality Layer

Stand: 2026-05-14

SealAI nutzt LangSmith als Observability- und Evaluation-Schicht, nicht als
Source of Truth fuer Governance, Prompts, RFQ-Regeln oder Werkstofflogik.
LangSmith Engine darf Issues, Evaluators, Datasets und PR-Ideen vorschlagen;
Produktionsaenderungen bleiben review- und repo-gesteuert.

## Produktionsregeln

- `LANGSMITH_TRACING=true` aktiviert redigierte Custom-Spans.
- `LANGSMITH_CAPTURE_LLM_CONTENT=false` bleibt der Produktionsstandard. Der
  OpenAI-SDK-Wrapper wird damit nicht aktiviert, damit Prompts,
  Kundentexte, RAG-Ausschnitte und Completions nicht roh in Traces landen.
- `LANGSMITH_TRACE_LANGGRAPH_CHILDREN=false` bleibt der Produktionsstandard.
  SealAI traced den Governed Turn als redigierten Custom-Span; automatische
  LangGraph-Child-Spans werden fuer Production deaktiviert, weil sie sonst
  Graph-State, Interrupt-Payloads und extrahierte Kundendaten enthalten koennen.
  Fuer gezielte Debug-Sessions darf der Wert temporaer aktiviert werden.
- `SEALAI_TRACE_HASH_SALT` muss in Produktivumgebungen stabil und geheim sein.
  Der Wert darf keinen `LANGSMITH_*`-Praefix nutzen, weil LangSmith solche
  Umgebungswerte als Run-Metadaten sichtbar machen kann. Falls der Salt fehlt,
  nutzt der Code `AUTH_SECRET`/`NEXTAUTH_SECRET` als Fallback.
- Vollstaendige LLM-Spans duerfen erst aktiviert werden, wenn ein kontrollierter
  OpenTelemetry-Collector vor LangSmith sitzt und sensible Span-Attribute
  redigiert.

## Trace-Metadaten

Alle SealAI-Quality-Traces erhalten:

- `governance_version=v9.2`
- `engine_review_mode=human_review_required`
- `engine_auto_merge_allowed=false`
- gehashte `tenant_id`, `user_id`, `session_id`, `case_id`, `preview_id`
- fachliche Komponentendaten fuer Router, Governed Graph, RAG und RFQ

## Repo-Evaluators

Der Evaluator-Katalog liegt im Code unter
`app.observability.sealai_quality.evaluator_catalog()` und deckt die
kritischen V9.2-Checks ab:

- `no_final_approval_claims`
- `rfq_boundary_guard`
- `asks_one_next_useful_question`
- `explains_parameter_relevance`
- `uncertainty_not_hidden`
- `no_forced_case_creation`
- `tenant_metadata_present`
- `rag_claim_level_respected`
- `compliance_claim_guard`

Diese Liste ist der Vertragsstand fuer LangSmith Evaluators. LangSmith Engine
kann daraus Online-Evaluators vorschlagen; Uebernahme erfolgt nur nach Review.
