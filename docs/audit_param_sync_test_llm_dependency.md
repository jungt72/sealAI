# Audit: Param Sync Tests vs. LLM Dependency

## Scope
- Endpoints: `POST /api/v1/langgraph/parameters/patch`, `GET/POST /api/v1/langgraph/state`, `POST /api/v1/langgraph/chat/v2`.
- Graph build: `backend/app/langgraph_v2/sealai_graph_v2.py`.
- LLM initialization points: `backend/app/langgraph_v2/sealai_graph_v2.py`, `backend/app/langgraph_v2/nodes/nodes_discovery.py`, `backend/app/langgraph_v2/utils/llm_factory.py`.

## Findings
- `create_sealai_graph_v2(...)` builds the graph and registers `final_answer_node` as `_build_final_answer_chain()`.
- `_build_final_answer_chain()` creates a `ChatOpenAI(...)` immediately. This happens during graph compilation, not execution.
- `get_sealai_graph_v2()` is called by `/parameters/patch` and `/state` to fetch the compiled graph and checkpointer. Even though these endpoints do not execute LLM nodes, the graph build currently triggers `ChatOpenAI` initialization and requires `OPENAI_API_KEY`.

## Why tests unnecessarily need OpenAI
- Param sync tests call `get_sealai_graph_v2()` indirectly via `/parameters/patch` and `/state`.
- Graph compilation instantiates `ChatOpenAI` in `_build_final_answer_chain()`.
- `ChatOpenAI` reads `OPENAI_API_KEY` at init time, so missing env causes failures even though no LLM call is made.

## Minimal change with smallest blast radius
- Make LLM initialization lazy for `final_answer_node` so graph compilation does not create `ChatOpenAI`.
- Keep node behavior and streaming intact when the node is actually executed.
- No changes to endpoint logic or state/checkpointer usage.
