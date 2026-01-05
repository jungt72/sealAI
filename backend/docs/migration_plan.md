# Migration Plan - SealAI LangGraph v0.6.10

## Overview

The current implementation in `backend/app/langgraph/` is already 80% aligned with the target 2025 architecture. This migration plan focuses on closing the remaining gaps to achieve full compliance with the specification.

## Component Mapping: Current → Target

### 1. State Schema ✅ FULLY ALIGNED

**Current:** `backend/app/langgraph/state.py`
- `messages`, `slots`, `routing`, `context_refs`, `meta` ✅
- Full validation with Pydantic ✅
- Merge functions and StateView helper ✅

**Target:** No changes needed - already compliant.

### 2. Graph Structure ✅ MOSTLY ALIGNED

**Current:** `backend/app/langgraph/compile.py`
- Main graph with all required nodes ✅
- Redis checkpointer support ✅
- Subgraph architecture ✅

**Target:** Minor adjustments for configuration loading.

### 3. Configuration (agents.yaml) ⚠️ NEEDS EXPANSION

**Current:** `backend/app/langgraph/config/agents.yaml`
```yaml
material:
  prompt: prompts/material_agent.md
  tools: [material_calculator, standards_lookup]
  rag_indices: [materials]
  model: gpt-4.1-mini
  timeout_s: 20
```

**Target:** Expand to full specification
```yaml
material:
  model:
    name: gpt-4.1-mini
    temperature: 0.1
    max_output_tokens: 2048
  prompt:
    intent|agent|synthesis: prompts/material_agent.md
    variant: default
  rag:
    index_id: materials
    top_k: 5
    hybrid: true
    filters: {domain: material}
    cache_ttl_seconds: 3600
  tools:
    list: [material_calculator, standards_lookup]
    timeout_ms: 30000
    concurrency: 2
    circuit_breaker: {enabled: true, threshold: 5}
    retry: {max_tries: 3, backoff_ms: 1000}
  limits:
    latency_ms: 20000
    rounds: 5
    tokens_out: 2048
  budget:
    max_tool_calls: 10
    max_llm_calls: 5
```

**Migration Steps:**
1. Expand `agents.yaml` with missing keys
2. Update nodes to read expanded config
3. Add validation for new config structure

### 4. Prompting System ⚠️ NEEDS MIGRATION

**Current:** Prompts in `backend/app/services/langgraph/prompts/`
- Legacy structure with mixed naming

**Target:** `backend/app/langgraph/prompts/` with Jinja2 templates

**Migration Steps:**
1. Create `backend/app/langgraph/prompts/` directory structure
2. Migrate existing `.md` files to new location
3. Define variable contracts per node (see Playbook Section 5)
4. Implement A/B variant support
5. Update `jinja_renderer.py` for variable validation

**Variable Contracts to Implement:**
- **intent_projector:** `user_query`, `messages_window`, `slots`
- **material_agent:** `user_query`, `messages_window`, `slots`
- **synthesis:** `user_query`, `slots`, `context_refs`, `tool_results_brief`
- etc. (per Playbook)

### 5. ToolNode Implementation ✅ ALIGNED

**Current:** `backend/app/langgraph/tools/` with ToolNode in subgraphs
- Parallel execution ✅
- Error handling ✅

**Target:** No changes needed.

### 6. RAG Integration ⚠️ NEEDS ENHANCEMENT

**Current:** Basic RAG nodes exist
- References stored in `context_refs` ✅

**Target:** Add caching and advanced features
- Caching with TTL
- Hybrid search configuration
- Filters support

**Migration Steps:**
1. Implement RAG caching layer
2. Add hybrid search support
3. Configure filters per domain
4. Update RAG nodes to use caching

### 7. Memory/Checkpointer ✅ ALIGNED

**Current:** Redis checkpointer with optional namespaces
- Main graph and subgraphs supported ✅

**Target:** Add environment variables
- `REDIS_URL`
- `CHECKPOINTER_NAMESPACE_MAIN`
- `CHECKPOINTER_NAMESPACE_MATERIAL|PROFIL|VALIDIERUNG|DEBATE`

### 8. Human-in-the-Loop ✅ ALIGNED

**Current:** `confirm_gate` with interrupt
- Resume functionality ✅

**Target:** No changes needed.

### 9. Resolver & Supervisor ✅ ALIGNED

**Current:** Deterministic resolver, fan-out supervisor
- Rule-based resolution ✅

**Target:** No changes needed.

### 10. Testing ✅ COMPREHENSIVE

**Current:** Full test suite implemented
- All required tests present ✅

**Target:** Add new tests for enhanced features
- `test_prompts_exist_and_bind.py`
- `test_rag_ref_only.py`
- `test_toolnode_parallelism.py`

## Phase-Based Migration Strategy

### Phase 1: Foundation (Current Status)
- ✅ State schema
- ✅ Graph structure
- ✅ ToolNode
- ✅ Checkpointer
- ✅ Basic tests

**Effort:** Minimal - already implemented

### Phase 2: Enhancement
1. **Configuration Expansion** (Priority: High)
   - Expand `agents.yaml` schema
   - Update config loading

2. **Prompt Migration** (Priority: High)
   - Create new prompts directory
   - Migrate templates with variable contracts
   - Implement variants

3. **RAG Enhancement** (Priority: Medium)
   - Add caching layer
   - Implement hybrid search
   - Add filters

4. **Observability** (Priority: Medium)
   - LangSmith tracing
   - Token/latency metrics
   - Error tracking

5. **Additional Tests** (Priority: Low)
   - New test cases for enhanced features

## File-Level Changes

### New Files to Create
- `backend/app/langgraph/prompts/debate/initiator.md`
- `backend/app/langgraph/prompts/debate/pro_agent.md`
- `backend/app/langgraph/prompts/debate/contra_agent.md`
- `backend/app/langgraph/prompts/debate/moderator.md`
- `backend/app/langgraph/prompts/debate/judge.md`
- `backend/app/langgraph/prompts/material/material_agent.md`
- `backend/app/langgraph/prompts/profil/profil_agent.md`
- `backend/app/langgraph/prompts/validierung/validierung_agent.md`
- `backend/app/langgraph/prompts/intent_projector.md`
- `backend/app/langgraph/prompts/synthesis.md`
- `docs/README.md` (migration guide)

### Files to Modify
- `backend/app/langgraph/config/agents.yaml` - Expand schema
- `backend/app/langgraph/subgraphs/*/nodes/rag_select.py` - Add caching
- `backend/app/langgraph/utils/jinja_renderer.py` - Variable validation
- `backend/app/langgraph/compile.py` - Config loading
- `backend/README.md` - Add migration docs

### Files to Migrate (Move/Rename)
- `backend/app/services/langgraph/prompts/*.md` → `backend/app/langgraph/prompts/`
- Update all imports accordingly

## Risk Assessment

### Low Risk
- Configuration expansion
- Prompt migration
- Additional tests

### Medium Risk
- RAG caching implementation
- Observability integration

### High Risk
- None - all changes are additive/infrastructure

## Success Criteria

### Post-Migration Validation
- All existing tests pass
- New configuration loads correctly
- Prompts render with variables
- RAG caching works
- Deterministic resolver behavior maintained
- State size remains minimal
- Interrupt/resume functionality preserved

### Performance Targets
- No regression in latency
- Token usage within estimates
- Memory usage stable

## Rollback Plan

Since changes are additive and feature-flagged:
- `ENABLE_LANGGRAPH_V06=false` falls back to legacy
- Individual components can be disabled
- Database migrations not required
- Redis keys use new namespaces

## Timeline Estimate

- **Phase 1:** Already complete (0 days)
- **Configuration:** 2-3 days
- **Prompt Migration:** 3-4 days
- **RAG Enhancement:** 2-3 days
- **Observability:** 1-2 days
- **Testing:** 1-2 days

**Total:** 9-14 days for full migration

## Dependencies

- Redis server for checkpointer
- OpenAI API access
- RAG indices configured
- LangSmith for observability (optional)

## Next Steps

1. Begin with configuration expansion
2. Migrate prompts with variable contracts
3. Implement RAG caching
4. Add observability
5. Comprehensive testing
6. Documentation updates