# SealAI V9.2 Clean Transformation Plan

Datum: 2026-05-18

## Phase-0-Befund

- Aktives Repo: `/Users/thorstenjung/Documents/New project/sealai-active`.
- Branch: `redesign/sealai-cockpit-overview`.
- Arbeitsbaum war vor V9.2-Arbeiten bereits dirty in `backend/app/agent/domain/normalization.py`, `backend/app/agent/graph/nodes/intake_observe_node.py`, `backend/app/agent/graph/output_contract_assembly.py`, `backend/app/agent/graph/slot_answer_binding.py`, `backend/app/agent/state/reducers.py` sowie `backend/app/agent/tests/test_communication_scenario_suite.py`.
- Der im Root-`AGENTS.md` genannte V9.1-Konzeptpfad `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md` ist im aktiven Repo nicht vorhanden.
- Primäre Evidenz für diesen Umbau ist daher der Audit `docs/audits/sealai_repo_ist_audit_2026-05-18.md`, der externe Deep-Dive `/Users/thorstenjung/Downloads/deep-research-report(11).md`, die vorhandenen V9.2-Modelle unter `backend/app/agent/v92/` und die produktiven Chat/Stream/Workspace-Pfade.

## Aktueller User-Turn-Flow

```text
frontend useAgentStream
  -> frontend BFF /api/bff/agent/chat/stream
  -> FastAPI /api/agent/chat/stream
  -> event_generator
  -> _resolve_runtime_dispatch
      -> unsafe instruction guard
      -> FastResponder / Knowledge / RFQ readiness / light runtime / active-case side-process
      -> or governed graph
  -> run_governed_graph_turn
      -> LangGraph nodes through output_contract and governed_answer_composer
  -> _assemble_governed_stream_payload
  -> SSE text_chunk/progress/state_update
  -> frontend streamWorkspace
```

## Gefundene Bypass-Pfade

- FastResponder: `backend/app/agent/api/dispatch.py` returns `fast_response`.
- Knowledge: `backend/app/agent/api/dispatch.py` returns `knowledge_response`.
- RFQ readiness: `backend/app/agent/api/dispatch.py` returns `rfq_response`.
- Light runtime: `backend/app/agent/api/streaming.py::_stream_light_runtime`.
- Exploration stream: `backend/app/agent/api/streaming.py::_stream_exploration_reply`.
- Active-case side/process answers: `backend/app/agent/api/routes/chat.py` and `backend/app/agent/api/streaming.py`.
- Runtime-action graph block fallback: `_runtime_action_blocked_graph_payload`.

## Stellen mit sichtbaren technischen Draft-Chunks

- `backend/app/agent/graph/nodes/governed_answer_composer_node.py` emits `governed_answer_text_chunk` if `stream_visible_answer_composer=True`.
- `backend/app/agent/api/governed_runtime.py` currently sets `stream_visible_answer_composer=collect_progress`.
- `backend/app/agent/api/streaming.py::_graph_custom_event_to_sse_payload` converts composer chunks to `text_chunk`.
- `backend/app/agent/api/streaming.py::_stream_governed_graph` has an outside-graph composer fallback that streams chunks before final state update.
- `frontend/src/hooks/useAgentStream.ts` renders `text_chunk` immediately.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts` forwards backend `text_chunk` and synthesizes chunks from final `state_update` when no chunks arrived.

## Guard-Landschaft

- Existing final visible selector: `backend/app/agent/runtime/final_answer_layer.py`.
- Fast-path lexical guard: `backend/app/agent/runtime/output_guard.py`.
- V9.1 final guard pieces: `backend/app/agent/v91/final_answer_guard.py`, `claim_guard.py`, `evidence_gate.py`, `communication_guard.py`.
- V9.2 typed guard state: `CalculationGuardResult`, `StandardsState`, `EvidenceGraphState`, `ReviewState`, `DossierState`.
- Missing target: one V9.2 `FinalOutputGuard` result attached to every answer payload before streaming.

## Implementierungsplan

1. Add `backend/app/agent/v92/contracts.py`
   - `TurnEnvelope`, `FinalAnswerContext`, `NonTechnicalAnswerContext`, `V92DashboardContract`, `AdversarialReviewVerdict`, `FinalGuardResult`, prompt/trace metadata.

2. Add `backend/app/agent/v92/dashboard_contract.py`
   - single backend projection for stream payloads and later durable workspace alignment.
   - attach as `ui.v92_contract` and keep existing `ui.v92` compatibility.

3. Add `backend/app/agent/v92/final_guard.py`
   - central deterministic final guard delegating to legacy V9.1 guards where possible.
   - enforce forbidden finality, suitability, compound/product overclaims, norm conformity, stale calculation visibility and internal leak checks.

4. Add `backend/app/agent/v92/adversarial_review.py`
   - structured reviewer verdict first as deterministic MVP, with prompt-template-ready metadata.
   - no free second chatbot answer.

5. Add `backend/app/agent/v92/revision_composer.py`
   - one bounded revision pass for deterministic downgrades and warnings.
   - no new technical claims.

6. Integrate governed stream path
   - build `TurnEnvelope`, `FinalAnswerContext`, dashboard contract and final guard in `backend/app/agent/api/assembly.py`.
   - disable visible governed technical draft streaming in `backend/app/agent/api/governed_runtime.py`.
   - remove outside-graph governed composer live chunks from `_stream_governed_graph`; compose internally, then guard, then final `state_update`/synthetic BFF stream.

7. Integrate short routes
   - annotate FastResponder, Knowledge, RFQ, light runtime, active-case side/process and unsafe/block paths with `TurnEnvelope` and `NonTechnicalAnswerContext`.
   - keep no-mutation policy visible in trace.

8. Frontend contract
   - extend `frontend/src/lib/contracts/agent.ts` for `turnEnvelope`, `finalAnswerContext`, `nonTechnicalAnswerContext`, `finalGuardResult`, `v92Dashboard`.
   - keep `text_chunk` for nontechnical/direct and BFF synthetic final answer streaming, but add typed progress/event handling.

9. Tests
   - backend unit tests for contracts, guard, reviewer, dashboard projection and no technical pre-guard chunks.
   - frontend tests for stream status vs answer chunks and V9.2 contract passthrough.

10. Legacy cleanup
   - scan direct `answer_markdown`/`reply` returns and direct technical `text_chunk` emissions.
   - keep only thin compatibility adapters that delegate to V9.2 contracts.

## Reihenfolge der ersten Patch-Welle

Die erste Patch-Welle bleibt bewusst klein und stabilisiert die P0-Risiken:

1. contracts and projections;
2. final guard and reviewer verdict;
3. governed stream safety;
4. payload integration for governed and short routes;
5. backend/frontend contract tests where local tooling permits.

Die tiefere LangGraph-Subgraph-Migration und der vollständige Calculator-Registry-Ausbau bleiben nach dieser Welle offen, weil sie fachlich breiter sind als ein sicherer Contract-First-Patch.
