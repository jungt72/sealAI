# SealAI Backend - LangGraph v0.6.10 Migration

## Overview

This backend implements a multi-agent LangGraph system for technical consulting in materials, profiles, and validation domains.

## Architecture

### LangGraph v0.6.10 Implementation

The system uses a messages-first state architecture with minimal fields:
- `messages`: Chat messages with lightweight structure
- `slots`: Small validated parameters (<256 chars, snake_case)
- `routing`: Normalized routing signals
- `context_refs`: Structured references to RAG/tool evidence
- `meta`: Run metadata (thread_id, user_id, trace_id)

### Main Graph Flow

```
entry_frontend → discovery_intake → discovery_summarize → confirm_gate
→ intent_projector → supervisor → resolver → exit_response → END
```

### Domain Subgraphs

Each domain follows: `agent → rag_select → tools_node → synthesis`

- **Material**: Material selection and compatibility analysis
- **Profil**: Profile dimensioning and optimization
- **Validierung**: Compliance and validation checking

### Human-in-the-Loop

- `confirm_gate` provides interrupt capability for user confirmation
- Resume maintains identical state hash
- Redis checkpointer enables persistence

## Configuration

### Environment Variables

```bash
# Redis Checkpointer
REDIS_URL=redis://localhost:6379
CHECKPOINTER_NAMESPACE_MAIN=sealai:main
CHECKPOINTER_NAMESPACE_MATERIAL=sealai:material
CHECKPOINTER_NAMESPACE_PROFIL=sealai:profil
CHECKPOINTER_NAMESPACE_VALIDIERUNG=sealai:validierung
CHECKPOINTER_NAMESPACE_DEBATE=sealai:debate
# LangSmith Observability
LANGCHAIN_API_KEY=your_api_key
LANGCHAIN_PROJECT=sealai-langgraph

# Feature Flag
ENABLE_LANGGRAPH_V06=true
```

### Agent Configuration

Located at `app/langgraph/config/agents.yaml` with full specification:
- Model settings (name, temperature, max_tokens)
- Prompt paths with variants
- RAG configuration (index, top_k, hybrid, filters, cache_ttl)
- Tool configuration (list, timeouts, concurrency, circuit_breaker, retry)
- Limits and budgets

## Prompts

Jinja2-templated prompts located in `app/langgraph/prompts/`:
- Domain-specific agent and synthesis prompts
- Debate role prompts
- Intent projection prompt

All prompts include defined variable contracts for consistent rendering.

## Testing

### Test Suites

- `app/langgraph/tests/`: Core LangGraph functionality
- `tests/`: Integration tests
- `app/services/langgraph/tests/`: Legacy tests

### Key Tests

- `test_state.py`: State validation and merging
- `test_singleflow_entry_to_exit.py`: E2E smoke test
- `test_interrupt_resume.py`: HIL functionality
- `test_resolver_determinism.py`: Deterministic resolution
- `test_toolnode_errors.py`: Tool error handling

## Migration Status

### Phase 1: Foundation ✅ Complete
- State schema with validation
- Graph compilation with Redis checkpointer
- ToolNode implementation
- Basic interrupt/resume

### Phase 2: Enhancement ✅ Complete
- Expanded agent configuration ✅
- Prompt migration with Jinja2 variables ✅
- RAG caching with Redis TTL ✅
- LangSmith observability integration ✅

## Development

### Prerequisites

- Python 3.12+
- Redis server
- OpenAI API access
- RAG indices configured

### Running Tests

```bash
cd backend
python -m pytest app/langgraph/tests/ -v
```

### Building Graph

```python
from app.langgraph.compile import compile_main_graph

graph = compile_main_graph()
# Graph ready for execution
```

## API Integration

- SSE endpoint: `app/api/v1/endpoints/langgraph_sse.py`
- Resume endpoint for interrupt continuation
- Streaming AI messages with evidence references

## Observability

- Structured logging with trace_id propagation
- LangSmith tracing (planned)
- Token/latency metrics (planned)

## Changelog

### v0.6.10 Migration
- **Phase 1**: Initial LangGraph v0.6.10 implementation
- **Phase 2**: Enhanced configuration, prompt migration, RAG caching
- State schema aligned with messages-first architecture
- ToolNode for parallel tool execution
- Redis checkpointer with namespace support
- HIL interrupts with deterministic resume

## Rollback

Set `ENABLE_LANGGRAPH_V06=false` to fall back to legacy implementation.
Individual components can be disabled via configuration.