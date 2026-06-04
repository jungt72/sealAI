# SeaLAI Phase 1a Baseline State Capture

**Date:** 2026-04-18  
**Patch:** Sprint 0 Patch 0.3  
**Scope:** Read-only quantitative baseline of backend, frontend, tests, infrastructure, and legacy transition evidence before Sprint 1 persistence foundation work.

This document records command outputs from the current repository state. Each section includes the command used so future reviewers can reproduce the measurement.

## Section 1 — Git State

Commands:

```bash
git rev-parse HEAD
git branch --show-current
git log --oneline -10
git status
```

Output:

```text
b195286b93515209b8c68cbbf8250e7ff8843971
codex/ptfe-rwdr-ssot-implementation
b195286b docs: add COI firewall log per Founder Decision #3
e5c44573 docs: AGENTS.md v3.0 — full authority set, Pre-Gate Classification, Fast Responder boundary, Tenant model, Selective Rewrite awareness
020a1058 plan: phase 1a implementation plan — 6 sprints, audit gates, binding execution contract
da3d8b4f docs: update CLAUDE.md to v5.0 (Supplement v3 in authority set, Fast Responder + operational chapters awareness)
2e761cae docs: add SSoT Supplement v3 (Chapters 44-53, Product North Star implementation)
f4fbe44e docs: update CLAUDE.md to v4.0 for full authority set (Product North Star + Founder Decisions)
4f4cfb98 docs: add Product North Star and Founder Decisions for Phase 1a
e62358b7 audit: phase 1a backend-core transition plan — comprehensive authority-vs-code delta
00419a83 audit: phase 1a backend-core transition plan — comprehensive authority-vs-code delta
c9a90524 docs: update CLAUDE.md to v3.0 for full authority set (supplement v1+v2, depth guide, PTFE-RWDR MVP)
On branch codex/ptfe-rwdr-ssot-implementation
nothing to commit, working tree clean
```

## Section 2 — File Inventory

Commands:

```bash
find backend/app -type f -name "*.py" | wc -l
find frontend -type f \( -name "*.ts" -o -name "*.tsx" \) 2>/dev/null | wc -l

tree -L 2 backend/app 2>/dev/null || find backend/app -maxdepth 2 -type d | sort

for dir in backend/app/agent backend/app/services backend/app/api backend/app/models backend/app/schemas backend/app/domain; do
  if [ -d "$dir" ]; then
    echo "$dir: $(find $dir -name '*.py' -exec wc -l {} + | tail -1 | awk '{print $1}') LOC across $(find $dir -name '*.py' | wc -l) files"
  fi
done
```

Output:

```text
356
5443
```

```text
backend/app
├── __init__.py
├── __pycache__
│   ├── __init__.cpython-311.pyc
│   ├── __init__.cpython-312.pyc
│   ├── conftest.cpython-312-pytest-7.4.4.pyc
│   ├── conftest.cpython-312-pytest-8.3.3.pyc
│   ├── conftest.cpython-312-pytest-8.4.2.pyc
│   ├── conftest.cpython-312-pytest-9.0.2.pyc
│   ├── database.cpython-311.pyc
│   ├── database.cpython-312.pyc
│   ├── diagnostic_qdrant.cpython-312.pyc
│   ├── main.cpython-311.pyc
│   ├── main.cpython-312.pyc
│   └── ws_stream_test.cpython-312.pyc
├── _legacy_v2
│   ├── __pycache__
│   ├── state
│   ├── tests
│   └── utils
├── agent
│   ├── __init__.py
│   ├── __pycache__
│   ├── agent
│   ├── api
│   ├── case_state.py
│   ├── cli.py
│   ├── data
│   ├── documents
│   ├── domain
│   ├── evidence
│   ├── graph
│   ├── hardening
│   ├── manufacturers
│   ├── material_core.py
│   ├── prompts
│   ├── rag
│   ├── run_live.py
│   ├── runtime
│   ├── runtime.py
│   ├── services
│   ├── state
│   ├── sts
│   └── tests
├── api
│   ├── __init__.py
│   ├── __pycache__
│   ├── tests
│   └── v1
├── cli
│   ├── __init__.py
│   └── __pycache__
├── common
│   ├── __pycache__
│   ├── errors.py
│   ├── jinja.py
│   ├── obs.py
│   └── telemetry.py
├── conftest.py
├── core
│   ├── __pycache__
│   ├── config.py
│   ├── memory.py
│   ├── metrics.py
│   └── prompts.py
├── data
│   ├── kb
│   ├── knowledge
│   └── seeds
├── database.py
├── diagnostic_qdrant.py
├── llm
│   ├── factory.py
│   └── registry.py
├── main.py
├── mcp
│   ├── __init__.py
│   ├── __pycache__
│   ├── calc_engine.py
│   ├── calc_schemas.py
│   ├── calculations
│   └── knowledge_tool.py
├── models
│   ├── __pycache__
│   ├── beratungsergebnis.py
│   ├── case_record.py
│   ├── case_state_snapshot.py
│   ├── chat_message.py
│   ├── chat_transcript.py
│   ├── chemical_matrix.py
│   ├── deterministic_norms.py
│   ├── form_result.py
│   ├── inquiry_audit.py
│   ├── inquiry_delivery.py
│   ├── long_term_memory.py
│   ├── material_profile.py
│   ├── postgres_logger.py
│   └── rag_document.py
├── observability
│   ├── __init__.py
│   ├── __pycache__
│   ├── health.py
│   └── metrics.py
├── prompts
│   ├── __pycache__
│   ├── _manifest.yml
│   ├── challenger_gate.j2
│   ├── check_1.1.0.j2
│   ├── confirm_gate.j2
│   ├── discovery_summarize.j2
│   ├── engineering_report.j2
│   ├── fast_brain_system.j2
│   ├── final_answer_composer.j2
│   ├── final_answer_discovery_v2.j2
│   ├── final_answer_explanation_v2.j2
│   ├── final_answer_out_of_scope_v2.j2
│   ├── final_answer_recommendation_v2.j2
│   ├── final_answer_router.j2
│   ├── final_answer_smalltalk_v2.j2
│   ├── final_answer_troubleshooting_v2.j2
│   ├── final_answer_v2.j2
│   ├── frontdoor_discovery_prompt.jinja2
│   ├── frontdoor_system_v2.j2
│   ├── leakage_troubleshooting.j2
│   ├── material_comparison.j2
│   ├── material_scientist_agent.j2
│   ├── mechanical_design_agent.j2
│   ├── out_of_scope_system.j2
│   ├── p1_context_extractor.j2
│   ├── phase_exploration.j2
│   ├── phase_rapport.j2
│   ├── rag_metadata_extractor.j2
│   ├── rag_platinum_extractor.j2
│   ├── rag_synthesizer.j2
│   ├── response_light_summary.j2
│   ├── response_router.j2
│   ├── rfq_template.j2
│   ├── senior_policy_de.j2
│   ├── smalltalk_system.j2
│   ├── supervisor
│   ├── tests
│   └── troubleshooting_explainer.j2
├── schemas
│   ├── __init__.py
│   ├── __pycache__
│   └── mcp.py
├── services
│   ├── __init__.py
│   ├── __pycache__
│   ├── audit
│   ├── auth
│   ├── chat
│   ├── fast_brain
│   ├── history
│   ├── jobs
│   ├── knowledge
│   ├── langgraph
│   ├── memory
│   ├── openai_payload.py
│   ├── prompt_templates
│   ├── rag
│   ├── rfq
│   └── sse_broadcast.py
├── templates
│   └── rfq_template.html
├── tests
│   ├── __pycache__
│   └── evaluation
└── utils
    ├── __pycache__
    ├── jinja_renderer.py
    └── json.py

73 directories, 99 files
```

```text
backend/app/agent: 63219 LOC across 201 files
backend/app/services: 10639 LOC across 59 files
backend/app/api: 11233 LOC across 48 files
backend/app/models: 495 LOC across 14 files
backend/app/schemas: 14 LOC across 2 files
```

`backend/app/domain` does not exist, so the loop emitted no line for it.

## Section 3 — LangGraph Node Sizes

Commands:

```bash
find backend/app/agent/graph/nodes -name "*.py" 2>/dev/null -exec wc -l {} + | sort -n | tail -20

wc -l backend/app/agent/graph/nodes/intake_observe*.py 2>/dev/null
wc -l backend/app/agent/graph/nodes/matching*.py 2>/dev/null
wc -l backend/app/agent/graph/nodes/output_contract*.py 2>/dev/null
wc -l backend/app/agent/graph/nodes/rfq_handover*.py 2>/dev/null
```

Output:

```text
     1 backend/app/agent/graph/nodes/__init__.py
    57 backend/app/agent/graph/nodes/assert_node.py
    84 backend/app/agent/graph/nodes/normalize_node.py
    93 backend/app/agent/graph/nodes/governance_node.py
   102 backend/app/agent/graph/nodes/dispatch_contract_node.py
   113 backend/app/agent/graph/nodes/export_profile_node.py
   131 backend/app/agent/graph/nodes/manufacturer_mapping_node.py
   135 backend/app/agent/graph/nodes/norm_node.py
   158 backend/app/agent/graph/nodes/compute_node.py
   167 backend/app/agent/graph/nodes/dispatch_node.py
   379 backend/app/agent/graph/nodes/rfq_handover_node.py
   437 backend/app/agent/graph/nodes/evidence_node.py
   454 backend/app/agent/graph/nodes/intake_observe_node.py
   471 backend/app/agent/graph/nodes/matching_node.py
  1335 backend/app/agent/graph/nodes/output_contract_node.py
  4117 total
454 backend/app/agent/graph/nodes/intake_observe_node.py
471 backend/app/agent/graph/nodes/matching_node.py
1335 backend/app/agent/graph/nodes/output_contract_node.py
379 backend/app/agent/graph/nodes/rfq_handover_node.py
```

## Section 4 — Parallel Stack Evidence

Commands:

```bash
ls -la backend/app/services/langgraph/ 2>/dev/null
find backend/app/services/langgraph -name "*.py" 2>/dev/null | wc -l
find backend/app/services/langgraph -name "*.yaml" 2>/dev/null

ls -la backend/app/services/fast_brain/ 2>/dev/null
find backend/app/services/fast_brain -name "*.py" 2>/dev/null | wc -l

find backend/app/services/langgraph/rules -type f 2>/dev/null
for yaml_file in $(find backend/app/services/langgraph/rules -name "*.yaml" 2>/dev/null); do
  echo "$yaml_file: $(wc -l < $yaml_file) lines"
done
```

Output:

```text
total 44
drwxrwsr-x 10 thorsten thorsten 4096 Mar  9 19:24 .
drwxrwsr-x 15 thorsten thorsten 4096 Mar  9 19:24 ..
drwxrwsr-x  2 thorsten thorsten 4096 Jan 22 20:23 __pycache__
drwxrwsr-x  4 thorsten thorsten 4096 Jan  5 19:14 domains
drwxrwsr-x  3 thorsten thorsten 4096 Jan  5 19:14 graph
drwxrwsr-x  2 thorsten thorsten 4096 Mar  6 18:26 prompt_templates
drwxrwsr-x  4 thorsten thorsten 4096 Apr  3 15:37 prompts
drwxrwsr-x  2 thorsten thorsten 4096 Jan  5 19:14 rag
-rw-rw-r--  1 thorsten thorsten 3900 Mar  9 19:24 redis_lifespan.py
drwxrwsr-x  2 thorsten thorsten 4096 Jan  5 19:14 rules
drwxrwsr-x  3 thorsten thorsten 4096 Feb 18 07:18 tools
2
backend/app/services/langgraph/domains/rwdr/schema.yaml
backend/app/services/langgraph/domains/hydraulics_rod/schema.yaml
backend/app/services/langgraph/rules/rwdr.yaml
backend/app/services/langgraph/rules/common.yaml
backend/app/services/langgraph/prompts/registry.yaml
total 36
drwxrwsr-x  3 thorsten thorsten  4096 Apr  3 15:37 .
drwxrwsr-x 15 thorsten thorsten  4096 Mar  9 19:24 ..
-rw-rw-r--  1 thorsten thorsten     0 Mar  9 19:24 __init__.py
drwxrwsr-x  2 thorsten thorsten  4096 Apr  9 12:17 __pycache__
-rw-rw-r--  1 thorsten thorsten 21158 Apr  9 12:17 router.py
2
backend/app/services/langgraph/rules/rwdr.yaml
backend/app/services/langgraph/rules/common.yaml
backend/app/services/langgraph/rules/rwdr.yaml: 18 lines
backend/app/services/langgraph/rules/common.yaml: 15 lines
```

## Section 5 — Legacy Artifact Evidence

Commands:

```bash
ls -d backend/app/**/_legacy* 2>/dev/null
find backend -type d -name "_legacy*" 2>/dev/null
find backend -type d -name "_trash*" 2>/dev/null

ls backend/app/api/v1/endpoints/langgraph_v2.py 2>/dev/null
ls backend/app/api/v1/endpoints/fast_brain_runtime.py 2>/dev/null
ls backend/app/api/v1/endpoints/sse_runtime.py 2>/dev/null
ls backend/app/interaction_policy.py 2>/dev/null

grep -rn "class ResultForm" backend/app/ 2>/dev/null
grep -rn "ResultForm\." backend/app/ 2>/dev/null | head -10
echo "Total ResultForm references: $(grep -rn 'ResultForm' backend/app/ | wc -l)"

grep -rn "class RoutingPath" backend/app/ 2>/dev/null
echo "Total RoutingPath references: $(grep -rn 'RoutingPath' backend/app/ | wc -l)"
```

Output:

```text
backend/app/_legacy_v2
backend/app/api/v1/endpoints/langgraph_v2.py
backend/app/agent/runtime/policy.py:14:class ResultForm(str, Enum):
backend/app/agent/runtime/interaction_policy.py:224:        result_form=ResultForm.DIRECT_ANSWER,
backend/app/agent/runtime/interaction_policy.py:247:        result_form=ResultForm.DETERMINISTIC_RESULT,
backend/app/agent/runtime/interaction_policy.py:268:        result_form=ResultForm.DIRECT_ANSWER,
backend/app/agent/runtime/interaction_policy.py:284:        result_form=ResultForm.DIRECT_ANSWER,
backend/app/agent/runtime/interaction_policy.py:300:        result_form=ResultForm.DIRECT_ANSWER,
backend/app/agent/tests/test_graph_routing.py:135:        (ResultForm.DIRECT_ANSWER.value, RoutingPath.FAST_PATH.value),
backend/app/agent/tests/test_graph_routing.py:136:        (ResultForm.GUIDED_RECOMMENDATION.value, RoutingPath.FAST_PATH.value),
backend/app/agent/tests/test_graph_routing.py:137:        (ResultForm.DETERMINISTIC_RESULT.value, RoutingPath.STRUCTURED_PATH.value),
backend/app/agent/tests/test_graph_routing.py:138:        (ResultForm.QUALIFIED_CASE.value, RoutingPath.STRUCTURED_PATH.value),
backend/app/agent/tests/test_graph_routing.py:147:            ResultForm.DIRECT_ANSWER.value: "Was ist FKM?",
grep: backend/app/agent/agent/__pycache__/policy.cpython-312.pyc: binary file matches
grep: backend/app/agent/__pycache__/runtime.cpython-312.pyc: binary file matches
grep: backend/app/agent/runtime/__pycache__/policy.cpython-312.pyc: binary file matches
grep: backend/app/agent/runtime/__pycache__/interaction_policy.cpython-312.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312-pytest-9.0.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy.cpython-312-pytest-8.4.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312-pytest-7.4.4.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy_0d.cpython-312-pytest-9.0.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy.cpython-312-pytest-9.0.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312-pytest-8.4.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy.cpython-312-pytest-7.4.4.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy_0d.cpython-312-pytest-8.4.2.pyc: binary file matches
Total ResultForm references: 50
backend/app/agent/runtime/policy.py:30:class RoutingPath(str, Enum):
grep: backend/app/agent/agent/__pycache__/policy.cpython-312.pyc: binary file matches
grep: backend/app/agent/__pycache__/runtime.cpython-312.pyc: binary file matches
grep: backend/app/agent/runtime/__pycache__/policy.cpython-312.pyc: binary file matches
grep: backend/app/agent/runtime/__pycache__/interaction_policy.cpython-312.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312-pytest-9.0.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy.cpython-312-pytest-8.4.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312-pytest-7.4.4.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy_0d.cpython-312-pytest-9.0.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy.cpython-312-pytest-9.0.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_graph_routing.cpython-312-pytest-8.4.2.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy.cpython-312-pytest-7.4.4.pyc: binary file matches
grep: backend/app/agent/tests/__pycache__/test_interaction_policy_0d.cpython-312-pytest-8.4.2.pyc: binary file matches
Total RoutingPath references: 74
```

No `_trash*` directories were emitted by the command. `fast_brain_runtime.py`, `sse_runtime.py`, and top-level `backend/app/interaction_policy.py` were not emitted by the command.

## Section 6 — Feature Flags in Config

Commands:

```bash
find backend/app/core -name "config*.py" -o -name "settings*.py" 2>/dev/null
grep -rE "SEALAI_ENABLE|ENABLE_LEGACY|ENABLE_BINARY_GATE|ENABLE_CONVERSATION" backend/app/core/ 2>/dev/null
```

Output:

```text
backend/app/core/config.py
backend/app/core/config.py:    SEALAI_ENABLE_BINARY_GATE: bool = True
backend/app/core/config.py:    SEALAI_ENABLE_CONVERSATION_RUNTIME: bool = True
backend/app/core/config.py:    ENABLE_LEGACY_V2_ENDPOINT: bool = False
```

## Section 7 — Database Schema State

Command:

```bash
docker compose exec -T postgres pg_dump --schema-only sealai 2>/dev/null > /tmp/sealai_schema_2026-04-18.sql
wc -l /tmp/sealai_schema_2026-04-18.sql 2>/dev/null
grep -E "^CREATE TABLE" /tmp/sealai_schema_2026-04-18.sql 2>/dev/null
```

Output:

```text
0 /tmp/sealai_schema_2026-04-18.sql
```

The dump did not succeed and produced an empty file, so no schema artifact was copied into `audits/`.

Failure-mode check, using the same configured service/database names and no alternate dump command:

```bash
docker compose ps
docker compose exec -T postgres pg_dump --schema-only sealai
```

Output:

```text
service "backend" has neither an image nor a build context specified: invalid compose project
service "backend" has neither an image nor a build context specified: invalid compose project
```

Per Patch 0.3 constraints, no different service name, database name, or dump command was guessed.

## Section 8 — Endpoint Inventory

Commands:

```bash
find backend/app/api -name "*.py" -exec grep -l "APIRouter\|@router" {} + 2>/dev/null
grep -rE "@router\.(get|post|put|delete|patch)" backend/app/api/v1/endpoints/*.py 2>/dev/null | wc -l

for f in $(find backend/app/api/v1/endpoints -name "*.py" 2>/dev/null); do
  endpoints=$(grep -cE "@router\.(get|post|put|delete|patch)" "$f")
  echo "$f: $endpoints endpoints"
done
```

Output:

```text
backend/app/api/v1/api.py
backend/app/api/v1/endpoints/chat_history.py
backend/app/api/v1/endpoints/mcp.py
backend/app/api/v1/endpoints/langgraph_health.py
backend/app/api/v1/endpoints/langgraph_v2.py
backend/app/api/v1/endpoints/memory.py
backend/app/api/v1/endpoints/rag.py
backend/app/api/v1/endpoints/ai.py
backend/app/api/v1/endpoints/system.py
backend/app/api/v1/endpoints/auth.py
backend/app/api/v1/endpoints/rfq.py
backend/app/api/v1/endpoints/ping.py
backend/app/api/v1/endpoints/users.py
backend/app/api/v1/endpoints/state.py
36
backend/app/api/v1/endpoints/chat_history.py: 4 endpoints
backend/app/api/v1/endpoints/__init__.py: 0 endpoints
backend/app/api/v1/endpoints/mcp.py: 1 endpoints
backend/app/api/v1/endpoints/langgraph_health.py: 1 endpoints
backend/app/api/v1/endpoints/langgraph_v2.py: 4 endpoints
backend/app/api/v1/endpoints/memory.py: 3 endpoints
backend/app/api/v1/endpoints/rag.py: 8 endpoints
backend/app/api/v1/endpoints/ai.py: 1 endpoints
backend/app/api/v1/endpoints/system.py: 1 endpoints
backend/app/api/v1/endpoints/auth.py: 1 endpoints
backend/app/api/v1/endpoints/rfq.py: 1 endpoints
backend/app/api/v1/endpoints/ping.py: 1 endpoints
backend/app/api/v1/endpoints/users.py: 1 endpoints
backend/app/api/v1/endpoints/state.py: 9 endpoints
```

## Section 9 — Test Suite State

Approval was requested before running pytest. The approved command completed before the timeout threshold.

Command:

```bash
pytest backend/tests/ --tb=no -q 2>&1 | tail -30
```

Output:

```text

=========================== short test summary info ============================
ERROR backend/tests/agent/test_rag_injection.py
ERROR backend/tests/agent/test_selection.py
ERROR backend/tests/agent/test_version_provenance.py
ERROR backend/tests/test_audit_logger.py
ERROR backend/tests/test_golden_set.py
ERROR backend/tests/test_langgraph_compile.py
ERROR backend/tests/test_mcp_calc_engine.py
ERROR backend/tests/test_p4_live_calc.py
ERROR backend/tests/test_paperless_sync.py
ERROR backend/tests/test_param_snapshot.py
ERROR backend/tests/test_parameter_guardrails.py
ERROR backend/tests/test_parameter_lww.py
ERROR backend/tests/unit/test_number_verification.py
!!!!!!!!!!!!!!!!!!! Interrupted: 13 errors during collection !!!!!!!!!!!!!!!!!!!
```

Summary:

| Metric | Count |
|--------|-------|
| Passed | 0 reported |
| Failed | 0 reported |
| Errors | 13 collection errors |
| Timeout | No |

No failures were fixed in this patch.

## Section 10 — Linter / Type Checker Baseline

Commands:

```bash
ruff check backend/app/ 2>&1 | tail -10
ruff check backend/app/ --statistics 2>&1 | head -20
mypy backend/app/ 2>&1 | tail -10
```

Output:

```text
26 |         return jsonable_encoder(obj, custom_encoder={bytes: lambda b: base64.b64encode(b).decode('ascii')})
27 |     except (AttributeError, TypeError) as e:
   |                                           ^
28 |         # If it fails, try other methods
29 |         pass
   |
help: Remove assignment to unused variable `e`

Found 364 errors.
[*] 267 fixable with the `--fix` option (23 hidden fixes can be enabled with the `--unsafe-fixes` option).
warning: Invalid `# noqa` directive on backend/app/agent/tests/test_phase_f_streaming_cut.py:119: expected a comma-separated list of codes (e.g., `# noqa: F401, F841`).
260	F401	[ ] unused-import
 59	E402	[ ] module-import-not-at-top-of-file
 23	F841	[ ] unused-variable
  8	F821	[ ] undefined-name
  6	E701	[ ] multiple-statements-on-one-line-colon
  4	F811	[*] redefined-while-unused
  3	F541	[*] f-string-missing-placeholders
  1	F601	[ ] multi-value-repeated-key-literal
Found 364 errors.
[*] 267 fixable with the `--fix` option (23 hidden fixes can be enabled with the `--unsafe-fixes` option).
/bin/bash: line 3: mypy: command not found
```

Summary:

| Tool | Result |
|------|--------|
| Ruff | 364 findings |
| Ruff fixable | 267 fixable, plus 23 unsafe hidden fixes |
| Mypy | Not available in shell (`command not found`) |

## Section 11 — Frontend Baseline

Commands:

```bash
ls -la frontend/ 2>/dev/null
find frontend/src -name "*.tsx" 2>/dev/null | wc -l
find frontend/src -name "*.ts" 2>/dev/null | wc -l
```

Output:

```text
total 600
drwxrwsr-x  10 thorsten nogroup   4096 Apr 16 13:01 .
drwxrwsr-x  55 thorsten nogroup  12288 Apr 19 05:38 ..
-rw-rw-r--   1 thorsten nogroup     91 Feb 23 13:27 .dockerignore
-rw-rw-r--   1 thorsten nogroup    459 Apr 16 12:48 .env
-rw-rw-r--   1 thorsten nogroup    292 Mar 26 14:01 .env.bak.2026-03-26_140152
-rw-rw-r--   1 thorsten nogroup    337 Apr  4 05:57 .env.bak.20260404-055724
drwxrwsr-x   9 thorsten nogroup   4096 Apr 16 13:08 .next
-rw-rw-r--   1 thorsten nogroup   1869 Mar 24 10:49 AGENTS.md
-rw-rw-r--   1 thorsten nogroup    866 Apr  3 15:37 Dockerfile
drwxrwsr-x   4 thorsten nogroup   4096 Mar 24 13:26 build
drwxrwsr-x   2 thorsten nogroup   4096 Mar 24 13:39 build_keycloak
drwxrwsr-x   5 thorsten nogroup   4096 Apr 16 13:01 content
-rw-rw-r--   1 thorsten nogroup   1932 Apr  4 08:56 ecosystem.config.js
-rw-rw-r--   1 thorsten nogroup    211 Mar 26 13:44 eslint.config.mjs
-rw-rw-r--   1 thorsten nogroup    321 Apr 16 12:33 index.html
-rw-rw-r--   1 thorsten nogroup    247 Apr 16 12:43 next-env.d.ts
-rw-rw-r--   1 thorsten nogroup    904 Apr 16 13:03 next-sitemap.config.js
-rw-rw-r--   1 thorsten nogroup    999 Apr  3 15:37 next.config.js
drwxrwsr-x 508 thorsten nogroup  20480 Apr 17 05:53 node_modules
-rw-rw-r--   1 thorsten nogroup 284117 Apr 16 07:39 package-lock.json
-rw-rw-r--   1 thorsten nogroup   2033 Apr 16 07:39 package.json
-rw-rw-r--   1 thorsten nogroup     77 Apr 16 06:02 postcss.config.js
drwxrwsr-x   3 thorsten nogroup   4096 Apr 10 05:47 public
drwxrwsr-x   2 thorsten nogroup   4096 Mar 27 20:41 scripts
drwxrwsr-x   8 thorsten nogroup   4096 Apr  3 15:37 src
-rw-rw-r--   1 thorsten nogroup    742 Apr  3 15:37 tsconfig.json
-rw-rw-r--   1 thorsten nogroup 192746 Apr 17 06:19 tsconfig.tsbuildinfo
-rw-rw-r--   1 thorsten nogroup    617 Mar 29 06:27 vitest.config.ts
33
58
```

## Section 12 — Docker / Infrastructure State

Commands:

```bash
docker compose ps 2>/dev/null
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" 2>/dev/null
```

Output from the exact commands:

```text
```

The exact `docker compose ps 2>/dev/null` command exited non-zero with no stdout. A failure-mode check without stderr redirection reported:

```text
service "backend" has neither an image nor a build context specified: invalid compose project
```

`docker ps` required elevated Docker socket access. After approval, the command produced:

```text
NAMES                         IMAGE                                                     STATUS
crm-stack-frontend-1          crm-custom:v16                                            Up 3 days
crm-stack-backend-1           crm-custom:v16                                            Up 3 days
crm-stack-scheduler-1         crm-custom:v16                                            Up 3 days
crm-stack-queue-short-1       crm-custom:v16                                            Up 3 days
crm-stack-websocket-1         crm-custom:v16                                            Up 3 days
crm-stack-queue-long-1        crm-custom:v16                                            Up 3 days
crm-stack-redis-cache-1       redis:6.2-alpine                                          Up 3 days
crm-stack-redis-queue-1       redis:6.2-alpine                                          Up 3 days
crm-stack-db-1                mariadb:10.6                                              Up 3 days (healthy)
erpnext-stack-frontend-1      sealai-erpnext:v16.13.1-22                                Up 3 days
erpnext-stack-scheduler-1     sealai-erpnext:v16.13.1-22                                Up 3 days
erpnext-stack-queue-long-1    sealai-erpnext:v16.13.1-22                                Up 3 days
erpnext-stack-queue-short-1   sealai-erpnext:v16.13.1-22                                Up 3 days
erpnext-stack-backend-1       sealai-erpnext:v16.13.1-22                                Up 3 days
erpnext-stack-websocket-1     sealai-erpnext:v16.13.1-22                                Up 3 days
backend                       ghcr.io/jungt72/sealai-backend:39267dcb-20260414-140255   Up 4 days (healthy)
keycloak                      ghcr.io/jungt72/sealai-keycloak:2026.04.03-1              Up 9 days
prometheus                    4a61322ac110                                              Up 2 weeks
nginx                         nginx:1.29.4                                              Up 2 weeks (healthy)
redis                         redis/redis-stack-server:7.4.0-v8                         Up 2 weeks (healthy)
qdrant                        qdrant/qdrant:v1.16.0                                     Up 2 weeks (healthy)
postgres                      postgres:15                                               Up 2 weeks (healthy)
grafana                       grafana/grafana:latest                                    Up 2 weeks
prelon_postgres               postgres:16-alpine                                        Up 2 weeks (healthy)
erpnext-stack-redis-queue-1   redis:6.2-alpine                                          Up 3 weeks
erpnext-stack-redis-cache-1   redis:6.2-alpine                                          Up 3 weeks
erpnext-stack-db-1            mariadb:10.6                                              Up 3 weeks (healthy)
paperless                     ghcr.io/paperless-ngx/paperless-ngx:2.20.10               Up 3 weeks (healthy)
gotenberg                     gotenberg/gotenberg:8.15.0                                Up 3 weeks
tika                          apache/tika:2.9.2.1                                      Up 3 weeks
```

## Section 13 — Cross-Reference with Phase 1a Audit Report

Previous audit report read:

```text
audits/phase_1a_backend_core_transition_plan_2026-04-17.md
```

Additional cross-reference commands used:

```bash
rg -n "^### Frage" audits/phase_1a_backend_core_transition_plan_2026-04-17.md
sed -n '258,460p' audits/phase_1a_backend_core_transition_plan_2026-04-17.md
grep -rnE "GenericConcept|ProductTerm|ManufacturerProfile|ManufacturerCapabilityClaim" backend/app/ 2>/dev/null | head -20
echo "Total terminology/capability core references: $(grep -rnE 'GenericConcept|ProductTerm|ManufacturerProfile|ManufacturerCapabilityClaim' backend/app/ 2>/dev/null | wc -l)"
grep -rn "sealing_material_family" backend/app/ 2>/dev/null | head -20
echo "Total sealing_material_family references: $(grep -rn 'sealing_material_family' backend/app/ 2>/dev/null | wc -l)"
grep -rnE "engineering_path|EngineeringPath" backend/app/ 2>/dev/null | head -20
echo "Total engineering_path/EngineeringPath references: $(grep -rnE 'engineering_path|EngineeringPath' backend/app/ 2>/dev/null | wc -l)"
find backend/alembic/versions -type f -name "*.py" 2>/dev/null | wc -l
find backend/alembic/versions -type f -name "*.py" 2>/dev/null | sort | tail -20
grep -rnE "mutation_events|outbox|risk_scores|tenant_id" backend/alembic backend/app/models 2>/dev/null | head -40
```

Output highlights:

```text
131:### Frage 1 — Case Model / Persistenz-Kern
161:### Frage 2 — Phase Gates & Output Classes
198:### Frage 3 — LangGraph Boundary
228:### Frage 4 — Schema-Trennung (4 Layer)
258:### Frage 5 — Persistenz (Postgres als SoT, Redis nur transient)
286:### Frage 6 — Moat Compliance (Supplement v2 §37, §38, §43)
326:### Frage 7 — Terminology- & Capability-Modell
349:### Frage 8 — PTFE-RWDR Tiefenmodell (MVP-Depth)
382:### Frage 9 — Parallele Orchestrierungs-Stacks
423:### Frage 10 — Engineering-Path Drift
Total terminology/capability core references: 0
Total sealing_material_family references: 0
Total engineering_path/EngineeringPath references: 29
12
```

| Audit Finding | Measurement in this baseline | Match? |
|---------------|------------------------------|--------|
| Frage 1: Case persistence lacks Phase 1a fields, mutation events, outbox, optimistic locking | Schema dump unavailable, but Alembic/model grep finds 12 migrations and only `tenant_id` on RAG/norm models; no `mutation_events`, `outbox`, or `risk_scores` lines emitted in model/migration grep | YES |
| Frage 2: Three-mode gate exists, but output class model is incomplete and legacy ResultForm remains | Section 5 finds `class ResultForm` and 50 `ResultForm` references; Section 3 confirms `output_contract_node.py` is 1335 LOC | YES |
| Frage 3: LangGraph nodes contain substantial business logic and oversized nodes | Section 3 reports `output_contract_node.py` 1335 LOC, `matching_node.py` 471 LOC, `intake_observe_node.py` 454 LOC, `rfq_handover_node.py` 379 LOC | YES |
| Frage 4: Four-layer schema separation is inverted or incomplete | Section 2 reports `backend/app/schemas` has 14 LOC across 2 files and no `backend/app/domain` line, while `backend/app/agent` has 63219 LOC | YES |
| Frage 5: Postgres persistence foundation lacks mutation/outbox/risk-score tables and case tenant ownership | Section 7 schema dump could not confirm live DB; Section 13 model/migration grep confirms only RAG/norm `tenant_id` hits and no emitted mutation/outbox/risk-score structures | YES |
| Frage 6: Moat layer has no visible sponsored boost, but terminology/capability registry is missing | Section 13 reports `Total terminology/capability core references: 0`; no sponsored/ranking measurement was part of Patch 0.3 commands | PARTIAL YES |
| Frage 7: Terminology and capability model absent | Section 13 reports `Total terminology/capability core references: 0` | YES |
| Frage 8: PTFE-RWDR depth model absent as backend type | Section 13 reports `Total sealing_material_family references: 0` in `backend/app` | YES |
| Frage 9: Parallel orchestration stacks coexist | Section 4 confirms `backend/app/services/langgraph` with YAML rules and `backend/app/services/fast_brain` with Python files; Section 5 confirms `langgraph_v2.py` endpoint exists | YES |
| Frage 10: Engineering-path drift; no central domain enum, legacy RoutingPath remains | Section 5 finds `class RoutingPath` and 74 `RoutingPath` references; Section 13 reports `engineering_path/EngineeringPath` references concentrated in checks/projections/tests | YES |

Authority findings cross-referenced: 10.

## Section 14 — Reproducibility Commands

Commands used for this baseline:

```bash
sed -n '1,240p' audits/phase_1a_implementation_plan_2026-04-18.md
sed -n '1,260p' audits/phase_1a_backend_core_transition_plan_2026-04-17.md
git rev-parse HEAD
git branch --show-current
git log --oneline -10
git status
find backend/app -type f -name "*.py" | wc -l
find frontend -type f \( -name "*.ts" -o -name "*.tsx" \) 2>/dev/null | wc -l
tree -L 2 backend/app 2>/dev/null || find backend/app -maxdepth 2 -type d | sort
for dir in backend/app/agent backend/app/services backend/app/api backend/app/models backend/app/schemas backend/app/domain; do
  if [ -d "$dir" ]; then
    echo "$dir: $(find $dir -name '*.py' -exec wc -l {} + | tail -1 | awk '{print $1}') LOC across $(find $dir -name '*.py' | wc -l) files"
  fi
done
find backend/app/agent/graph/nodes -name "*.py" 2>/dev/null -exec wc -l {} + | sort -n | tail -20
wc -l backend/app/agent/graph/nodes/intake_observe*.py 2>/dev/null
wc -l backend/app/agent/graph/nodes/matching*.py 2>/dev/null
wc -l backend/app/agent/graph/nodes/output_contract*.py 2>/dev/null
wc -l backend/app/agent/graph/nodes/rfq_handover*.py 2>/dev/null
ls -la backend/app/services/langgraph/ 2>/dev/null
find backend/app/services/langgraph -name "*.py" 2>/dev/null | wc -l
find backend/app/services/langgraph -name "*.yaml" 2>/dev/null
ls -la backend/app/services/fast_brain/ 2>/dev/null
find backend/app/services/fast_brain -name "*.py" 2>/dev/null | wc -l
find backend/app/services/langgraph/rules -type f 2>/dev/null
for yaml_file in $(find backend/app/services/langgraph/rules -name "*.yaml" 2>/dev/null); do
  echo "$yaml_file: $(wc -l < $yaml_file) lines"
done
ls -d backend/app/**/_legacy* 2>/dev/null
find backend -type d -name "_legacy*" 2>/dev/null
find backend -type d -name "_trash*" 2>/dev/null
ls backend/app/api/v1/endpoints/langgraph_v2.py 2>/dev/null
ls backend/app/api/v1/endpoints/fast_brain_runtime.py 2>/dev/null
ls backend/app/api/v1/endpoints/sse_runtime.py 2>/dev/null
ls backend/app/interaction_policy.py 2>/dev/null
grep -rn "class ResultForm" backend/app/ 2>/dev/null
grep -rn "ResultForm\." backend/app/ 2>/dev/null | head -10
echo "Total ResultForm references: $(grep -rn 'ResultForm' backend/app/ | wc -l)"
grep -rn "class RoutingPath" backend/app/ 2>/dev/null
echo "Total RoutingPath references: $(grep -rn 'RoutingPath' backend/app/ | wc -l)"
find backend/app/core -name "config*.py" -o -name "settings*.py" 2>/dev/null
grep -rE "SEALAI_ENABLE|ENABLE_LEGACY|ENABLE_BINARY_GATE|ENABLE_CONVERSATION" backend/app/core/ 2>/dev/null
docker compose exec -T postgres pg_dump --schema-only sealai 2>/dev/null > /tmp/sealai_schema_2026-04-18.sql
wc -l /tmp/sealai_schema_2026-04-18.sql 2>/dev/null
grep -E "^CREATE TABLE" /tmp/sealai_schema_2026-04-18.sql 2>/dev/null
docker compose ps
docker compose exec -T postgres pg_dump --schema-only sealai
find backend/app/api -name "*.py" -exec grep -l "APIRouter\|@router" {} + 2>/dev/null
grep -rE "@router\.(get|post|put|delete|patch)" backend/app/api/v1/endpoints/*.py 2>/dev/null | wc -l
for f in $(find backend/app/api/v1/endpoints -name "*.py" 2>/dev/null); do
  endpoints=$(grep -cE "@router\.(get|post|put|delete|patch)" "$f")
  echo "$f: $endpoints endpoints"
done
pytest backend/tests/ --tb=no -q 2>&1 | tail -30
ruff check backend/app/ 2>&1 | tail -10
ruff check backend/app/ --statistics 2>&1 | head -20
mypy backend/app/ 2>&1 | tail -10
ls -la frontend/ 2>/dev/null
find frontend/src -name "*.tsx" 2>/dev/null | wc -l
find frontend/src -name "*.ts" 2>/dev/null | wc -l
docker compose ps 2>/dev/null
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}" 2>/dev/null
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}"
rg -n "^### Frage" audits/phase_1a_backend_core_transition_plan_2026-04-17.md
sed -n '258,460p' audits/phase_1a_backend_core_transition_plan_2026-04-17.md
grep -rnE "GenericConcept|ProductTerm|ManufacturerProfile|ManufacturerCapabilityClaim" backend/app/ 2>/dev/null | head -20
echo "Total terminology/capability core references: $(grep -rnE 'GenericConcept|ProductTerm|ManufacturerProfile|ManufacturerCapabilityClaim' backend/app/ 2>/dev/null | wc -l)"
grep -rn "sealing_material_family" backend/app/ 2>/dev/null | head -20
echo "Total sealing_material_family references: $(grep -rn 'sealing_material_family' backend/app/ 2>/dev/null | wc -l)"
grep -rnE "engineering_path|EngineeringPath" backend/app/ 2>/dev/null | head -20
echo "Total engineering_path/EngineeringPath references: $(grep -rnE 'engineering_path|EngineeringPath' backend/app/ 2>/dev/null | wc -l)"
find backend/alembic/versions -type f -name "*.py" 2>/dev/null | wc -l
find backend/alembic/versions -type f -name "*.py" 2>/dev/null | sort | tail -20
grep -rnE "mutation_events|outbox|risk_scores|tenant_id" backend/alembic backend/app/models 2>/dev/null | head -40
```

## Section 15 — Baseline Status Summary

The current baseline is consistent with the Phase 1a Audit Report from 2026-04-17. The backend has 356 Python files under `backend/app`, with a large LangGraph-era implementation surface: `backend/app/agent` alone contains 63219 LOC across 201 files, and graph nodes total 4117 LOC. The oversized nodes most relevant for Sprint 2 planning are `output_contract_node.py` at 1335 LOC, `matching_node.py` at 471 LOC, `intake_observe_node.py` at 454 LOC, and `rfq_handover_node.py` at 379 LOC.

Parallel stack evidence remains present: `backend/app/services/langgraph` exists with YAML rules and domain schemas, `backend/app/services/fast_brain` exists, `_legacy_v2` exists, and `langgraph_v2.py` remains exposed under API endpoints. Legacy classification artifacts remain present: `ResultForm` has 50 grep references and `RoutingPath` has 74 grep references. Feature flags still include `SEALAI_ENABLE_BINARY_GATE`, `SEALAI_ENABLE_CONVERSATION_RUNTIME`, and `ENABLE_LEGACY_V2_ENDPOINT`.

The requested live schema dump could not be captured because the exact `docker compose exec -T postgres pg_dump --schema-only sealai` command failed against an invalid compose project and produced an empty file; no schema artifact was committed. The requested test baseline stops during collection with 13 errors. Ruff reports 364 findings, and `mypy` is not installed in the shell. Frontend inventory reports 33 `.tsx` and 58 `.ts` files under `frontend/src`, while the broader frontend tree contains 5443 TypeScript/TSX files due to generated/dependency content. This baseline is therefore a current-state reference, not a readiness signal, and it supports Sprint 1 focus on persistence foundation before later classification and stack-consolidation work.
