# Changelog

## [Unreleased]
### Added
- Unified LangGraph IO layer (`backend/app/langgraph/io/*`) with frozen Pydantic schemas, validators, and unit normalization utilities.
- New discovery → intent → router → synthese → safety graph (`backend/app/langgraph/graph_chat.py`) plus SSE API (`backend/app/api/routes/chat.py`).
- Legacy agent adapters, observability helpers (`backend/app/common/obs.py`), and comprehensive contract/smoke tests.
- Benchmark suite (`benchmarks/routing/*.yaml`) and runner (`scripts/run_benchmarks.py`) for routing KPIs.

### Changed
- SSE endpoint now lives under `/chat/stream` with JWT validation and Redis checkpointer support.
- Core routing nodes migrated to typed IO models, ensuring no untyped dicts flow between graph stages.

### Known Issues
- `Makefile` requires indentation fix at line 99; CI runs for tests/benchmarks pending.

