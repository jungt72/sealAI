# Deterministic Sealing Engine — IST-Audit

Audit date: 2026-05-19
Repo: `/home/thorsten/sealai`
Branch: `redesign/sealai-cockpit-overview`
Commit: `c8328377`
Initial dirty state: clean (`git status --short` returned no rows before audit)
Final dirty state after report write: `?? docs/audits/deterministic_engine_ist_audit.md`

Scope: read-first / audit-only. No source code, tests, migrations, packages, Docker
containers, or productive data were changed during the analysis phase. This report
itself is the only intended filesystem write.

## 1. Executive Verdict

**Verdict: Teilweise, aber nicht professionell vollständig auslegungsfähig.**

Code-Fakt: Es gibt einen backend-geführten governed runtime path mit REST/SSE
entrypoints, LangGraph topology, TurnEnvelope/FinalAnswerContext, final guard,
state reducers, deterministic check registry, calculation registries and cockpit
projection (`backend/app/agent/api/routes/chat.py:1130-1266`,
`backend/app/agent/graph/topology.py:315-365`,
`backend/app/agent/v92/contracts.py:56-83`,
`backend/app/agent/v92/final_guard.py:74-200`,
`backend/app/agent/domain/checks_registry.py:1-86`,
`backend/app/agent/v92/dashboard_contract.py:179-280`).

Inference: The runtime is a real governed skeleton, but the sealing design
truth is not yet a complete deterministic engine. Field truth is split across
observed, normalized, asserted, workspace projections, direct overrides, legacy
services, and frontend fallback projections. Several professional sealing
distinctions exist only as text, interpretation metadata, or UI concepts, not
as canonical backend fields.

**Determinism vs. LLM/UI**

- Deterministic: routing boundary, reducers, assertion/governance derivation,
  registered checks, selected V9.2 calculators, risk/readiness slices and final
  guards (`backend/app/agent/v92/turn_boundary.py:190-295`,
  `backend/app/agent/state/reducers.py:486-648`,
  `backend/app/agent/state/reducers.py:664-815`,
  `backend/app/agent/v92/calculator_registry.py:80-148`,
  `backend/app/agent/v92/orchestrator.py:642-760`).
- LLM-influenced: the productive technical intake node may call an LLM for JSON
  extractions; the governed answer composer may call an LLM for user-visible
  wording after deterministic context is built (`backend/app/agent/graph/nodes/intake_observe_node.py:363-439`,
  `backend/app/agent/communication/governed_answer_composer.py:98-111`,
  `backend/app/agent/communication/governed_answer_composer.py:252-352`).
- UI-derived or fallback: cockpit status/check counts are partly frontend-built,
  and one cockpit hook has a `frontend_placeholder` fallback when backend truth
  is missing (`frontend/src/lib/engineering/buildSealCockpitViewModel.ts:23-54`,
  `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:277-334`,
  `frontend/src/hooks/useCockpitData.ts:166-187`).

**Largest 5 risks**

1. Canonical field model is too narrow for professional pressure truth:
   productive extraction and critical pressure contract use `pressure_bar`,
   with interpretation metadata, but no canonical `pressure_system`,
   `pressure_at_seal`, or `pressure_delta` slot (`backend/app/agent/graph/nodes/intake_observe_node.py:67-86`,
   `backend/app/domain/critical_field_contract.py:132-137`,
   `backend/app/agent/graph/slot_answer_binding.py:158-210`).
2. Known user values can remain non-authoritative: reducers explicitly do not
   assert normalized candidates by confidence alone; only user overrides or
   evidence promote to assertions (`backend/app/agent/state/reducers.py:664-679`,
   `backend/app/agent/state/reducers.py:747-754`).
3. UI can show values/metrics that are not the same as backend asserted truth:
   projections expose normalized parameters, frontend computes five-check
   cockpit status, and frontend placeholder projection exists
   (`backend/app/agent/state/projections.py:230-248`,
   `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:23-54`,
   `frontend/src/hooks/useCockpitData.ts:166-187`).
4. RWDR calculation depth is split: a richer `calculate_rwdr` module exists,
   but the productive graph compute node triggers a narrower cascade from shaft
   diameter and speed and sets engineering path to `rwdr` internally
   (`backend/app/agent/domain/rwdr_calc.py:393-547`,
   `backend/app/agent/graph/nodes/compute_node.py:19-27`,
   `backend/app/agent/graph/nodes/compute_node.py:104-134`,
   `backend/app/agent/graph/nodes/compute_node.py:196-218`).
5. Risk language can mention RWDR surface/runout topics as missing-context
   risk without measured runout evidence; that is acceptable as "missing",
   but not as a claim of high runout (`backend/app/agent/domain/challenge_engine.py:541-568`,
   `backend/app/agent/domain/risk_readiness.py:282-290`).

**Immediate later actions, audit-based**

1. Close field truth first: define acceptance semantics for chat-extracted
   known values vs. candidates, especially temperature, medium, pressure,
   and sealing type.
2. Split pressure semantics backend-side: system pressure, pressure at seal,
   and pressure differential must not share one canonical slot.
3. Add placeholder rejection and invalid FieldStatus handling for medium and
   direct-input text.
4. Make RWDR/sealing type closure consistent across chat slot answers,
   canonical state, workspace projection, and UI.
5. Make cockpit coverage/check status backend-derived and auditable; remove
   production reliance on frontend denominator/fallback truth.

**Screenshot problem assessment**

The screenshot symptoms are plausible from the current code, but not all are
proven from one replay trace. Temperature repetition is plausible because
normalized candidates are not necessarily asserted. System pressure conflation
is a real model limitation. RWDR closure is partially implemented but has
field-name and pending-slot gaps. Placeholder medium acceptance is not blocked
by a visible denylist. Wellenschlag language must be treated as a missing-input
risk unless a runout/eccentricity value exists. The cockpit "62 %" and
"3 von 5" can be frontend-derived from backend projections/checks plus a
hardcoded frontend five-check definition.

## 2. Repo-/Runtime-Karte

| Layer | Datei/Modul | Aufgabe laut Code | produktiv genutzt? | Evidenz | Kommentar |
|---|---|---:|---:|---|---|
| API / Chat entrypoint | `backend/app/agent/api/routes/chat.py` | REST/SSE chat endpoint, runtime dispatch, governed branch, persistence | ja | `backend/app/agent/api/routes/chat.py:1130-1266`, `backend/app/agent/api/routes/chat.py:1279-1292` | Hauptentrypoint fuer Chat. |
| API router | `backend/app/agent/api/router.py` | bindet chat/workspace/history/review/system routes ein | ja | `backend/app/agent/api/router.py:1-35`, `backend/app/agent/api/router.py:56-61` | Kompatibilitaetswrapper vorhanden. |
| Streaming | `backend/app/agent/api/streaming.py` | SSE, progress-only technical stream, final answer after guard | ja | `backend/app/agent/api/streaming.py:111-130`, `backend/app/agent/api/streaming.py:715-883` | Technical draft tokens are converted to internal progress. |
| Dispatch / routing | `backend/app/agent/api/dispatch.py` | Pre-gate, V8/V9 governed routing, active-case detection | ja | `backend/app/agent/api/dispatch.py:166-182`, `backend/app/agent/api/dispatch.py:413-423`, `backend/app/agent/api/dispatch.py:723-787` | Domain inquiry creates/loads governed state. |
| Turn boundary | `backend/app/agent/v92/turn_boundary.py` | deterministic route/policy boundary | ja | `backend/app/agent/v92/turn_boundary.py:1-7`, `backend/app/agent/v92/turn_boundary.py:190-295` | Route/policy is deterministic regex/state logic. |
| LangGraph runtime | `backend/app/agent/graph/topology.py` | graph nodes and edges | ja | `backend/app/agent/graph/topology.py:6-62`, `backend/app/agent/graph/topology.py:315-365` | Topology declares LLM only for observe/composer. |
| Field extraction | `backend/app/agent/graph/nodes/intake_observe_node.py` | regex plus optional LLM JSON extraction | ja | `backend/app/agent/graph/nodes/intake_observe_node.py:1-30`, `backend/app/agent/graph/nodes/intake_observe_node.py:363-439`, `backend/app/agent/graph/nodes/intake_observe_node.py:476-585` | Allowed fields are narrow. |
| Normalization | `backend/app/agent/graph/nodes/normalize_node.py` + reducers | deterministic reduction | ja | `backend/app/agent/graph/nodes/normalize_node.py:39-84`, `backend/app/agent/state/reducers.py:486-648` | Builds normalized/case fields, detects conflicts. |
| Assertion/state mutation | `backend/app/agent/graph/nodes/assert_node.py` + reducers | normalized to asserted claims | ja | `backend/app/agent/graph/nodes/assert_node.py:16-20`, `backend/app/agent/graph/nodes/assert_node.py:50-51`, `backend/app/agent/state/reducers.py:664-815` | Confidence alone does not assert. |
| Persistence | `backend/app/agent/api/loaders.py` | Redis/Postgres governed state load/persist | ja | `backend/app/agent/api/loaders.py:114-135`, `backend/app/agent/api/loaders.py:199-243`, `backend/app/agent/api/loaders.py:428-510` | Live state is materialized. |
| Proposed case delta | `backend/app/agent/domain/case_delta.py` | builds assistant delta from current turn extractions | ja | `backend/app/agent/domain/case_delta.py:28-45`, `backend/app/agent/domain/case_delta.py:69-119`, `backend/app/agent/domain/case_delta.py:128-152` | Assistant delta is proposed, not authoritative. |
| Direct override | `backend/app/agent/api/routes/review.py` | user override and case-delta acceptance | ja | `backend/app/agent/api/routes/review.py:419-512`, `backend/app/agent/api/routes/review.py:514-644` | Separate write path from chat extraction. |
| Deterministic checks | `backend/app/agent/domain/checks_registry.py` | five registered RWDR-oriented checks | ja | `backend/app/agent/domain/checks_registry.py:1-86`, `backend/app/agent/domain/checks_registry.py:133-185` | Check registry exists but small. |
| Calculation engine | `backend/app/services/calculation_engine.py` | formula cascade | ja | `backend/app/services/calculation_engine.py:43-92`, `backend/app/services/calculation_engine.py:124-201` | Deterministic formulas. |
| V9.2 calculators | `backend/app/agent/v92/calculator_registry.py` | registered calculators and guard results | ja | `backend/app/agent/v92/calculator_registry.py:80-148`, `backend/app/agent/v92/calculator_registry.py:420-449` | Registry has surface speed, temp screening, chemical screening. |
| Risk/readiness | `backend/app/agent/domain/risk_readiness.py` + V9.2 orchestrator | missing fields, risks, readiness bands | ja | `backend/app/agent/domain/risk_readiness.py:161-359`, `backend/app/agent/v92/orchestrator.py:718-895` | Useful but incomplete fachlich. |
| Question planner | `backend/app/agent/runtime/clarification_priority.py` | next focus/question priority | ja | `backend/app/agent/runtime/clarification_priority.py:291-363`, `backend/app/agent/runtime/clarification_priority.py:394-491` | One primary question is built later. |
| Pending slot binding | `backend/app/agent/graph/slot_answer_binding.py` | maps short answer to pending field | ja | `backend/app/agent/graph/slot_answer_binding.py:1-6`, `backend/app/agent/graph/slot_answer_binding.py:86-155`, `backend/app/agent/graph/slot_answer_binding.py:158-281` | No sealing-type binding branch found. |
| Communication guard | V9.1/V9.2 guards | claim/evidence/communication/final guard | ja | `backend/app/agent/v91/final_answer_guard.py:1-31`, `backend/app/agent/v92/final_guard.py:74-200` | Pattern/context guard, not full theorem prover. |
| Answer composer | `backend/app/agent/communication/governed_answer_composer.py` | LLM text composer over deterministic context | ja | `backend/app/agent/communication/governed_answer_composer.py:98-111`, `backend/app/agent/communication/governed_answer_composer.py:407-438` | Can phrase technical orientation. |
| Backend cockpit | `backend/app/agent/v92/dashboard_contract.py` | V9.2 dashboard contract | ja | `backend/app/agent/v92/dashboard_contract.py:179-280` | Includes normalized facts too. |
| Workspace projection | `backend/app/api/v1/projections/case_workspace.py` | case workspace from governed state | ja | `backend/app/api/v1/projections/case_workspace.py:1490-1506`, `backend/app/api/v1/projections/case_workspace.py:2720-2825` | Builds checks/cockpit/deep dive. |
| Frontend cockpit | `frontend/src/lib/engineering/buildSealCockpitViewModel.ts` | cockpit view model and status text | ja | `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:23-54`, `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:277-334` | Five-check denominator is frontend constant. |
| Frontend fallback | `frontend/src/hooks/useCockpitData.ts` | fallback cockpit view when backend cockpit missing | ja/conditional | `frontend/src/hooks/useCockpitData.ts:166-187`, `frontend/src/hooks/useCockpitData.ts:236-244` | Labels authority `frontend_placeholder`. |
| Tests | backend/frontend tests | regression coverage | partial | Examples cited in section 9 | Good slices exist, but screenshot regressions not fully covered. |

## 3. End-to-End Trace: User Turn -> State -> Antwort -> Cockpit

1. **Nutzer sendet Text — IMPLEMENTED.** REST `/chat` and SSE `/chat/stream`
   enter `chat_endpoint` / `event_generator` (`backend/app/agent/api/routes/chat.py:1279-1292`,
   `backend/app/agent/api/streaming.py:885-1087`).

2. **API empfaengt — IMPLEMENTED.** Unsafe input guard and runtime dispatch are
   run before branch selection (`backend/app/agent/api/routes/chat.py:1130-1178`).

3. **Klassifikation/Routing — IMPLEMENTED/PARTIAL.** Dispatch calls
   `PreGateClassifier().classify()` and `classify_conversation_route()`.
   Domain inquiry loads governed state and returns `runtime_mode="GOVERNED"`
   (`backend/app/agent/api/dispatch.py:413-423`,
   `backend/app/agent/api/dispatch.py:723-787`). Partial because route truth is
   not the same as application/seal-type truth.

4. **Extraktion — PARTIAL.** `intake_observe_node` performs regex extraction and
   optional LLM JSON extraction from an allowlist (`backend/app/agent/graph/nodes/intake_observe_node.py:67-86`,
   `backend/app/agent/graph/nodes/intake_observe_node.py:246-325`,
   `backend/app/agent/graph/nodes/intake_observe_node.py:363-439`). Missing:
   canonical slots for pressure system/seal/delta and many RWDR geometry/surface
   fields.

5. **Validierung/Normalisierung — PARTIAL.** Normalization parses units and
   pressure interpretation (`backend/app/agent/domain/normalization.py:520-604`,
   `backend/app/agent/domain/normalization.py:1190-1220`). The pressure
   interpretation is metadata on `pressure_bar`, not separate pressure truth
   (`backend/app/agent/graph/slot_answer_binding.py:158-210`).

6. **Mutation/Persistenz — PARTIAL/MISALIGNED.** Graph commit copies slices into
   `GovernedSessionState` and persists Redis/Postgres (`backend/app/agent/api/loaders.py:428-510`,
   `backend/app/agent/api/loaders.py:199-243`). Direct override and case-delta
   endpoints are additional write surfaces (`backend/app/agent/api/routes/review.py:419-644`).
   Inference: there is not one single semantic write path.

7. **Recompute/checks/readiness — PARTIAL.** Compute node runs deterministic
   cascade only when shaft diameter and rpm are asserted (`backend/app/agent/graph/nodes/compute_node.py:196-218`);
   V9.2 orchestrator builds calculation/readiness/risk state (`backend/app/agent/v92/orchestrator.py:642-895`).

8. **Question planning — PARTIAL.** Output assembly builds one structured
   clarification from priority logic (`backend/app/agent/graph/output_contract_assembly.py:481-564`,
   `backend/app/agent/graph/output_contract_assembly.py:1214-1341`). Pending
   slot binding covers medium, pressure, temperature, shaft, speed, but no
   sealing-type branch was found (`backend/app/agent/graph/slot_answer_binding.py:86-281`).

9. **Antwortgenerierung — PARTIAL.** Deterministic reply context is built, then
   optional LLM composer may phrase a visible answer; final layer and V9.2 final
   guard run (`backend/app/agent/api/assembly.py:109-179`,
   `backend/app/agent/api/assembly.py:208-337`,
   `backend/app/agent/communication/governed_answer_composer.py:252-352`).

10. **Streaming/Frontend update — IMPLEMENTED.** Technical draft chunks are not
    streamed as user-visible final content; final payload is emitted after final
    guard (`backend/app/agent/api/streaming.py:111-130`,
    `backend/app/agent/api/streaming.py:840-883`).

11. **Cockpit-Projektion — PARTIAL/MISALIGNED.** Workspace endpoint projects
    governed state (`backend/app/agent/api/routes/workspace.py:148-175`), but
    backend projections can include normalized facts, and frontend may compute
    status/check counts (`backend/app/agent/v92/dashboard_contract.py:61-89`,
    `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:277-334`).

## 4. Canonical Case-State Audit

| Feld / Slot | existiert im Schema? | Einheit / Typ | FieldStatus / Provenance | Validator / Alias | mutierbar durch wen | UI sichtbar? | Testabdeckung | Evidenz / Befund |
|---|---:|---:|---:|---:|---|---:|---:|---|
| `request_type` | partial | routing enum/context | no CaseField slot | route classifiers | dispatch | indirect | partial | Runtime dispatch/turn boundary classify route, not case slot: `backend/app/agent/api/dispatch.py:413-423`, `backend/app/agent/v92/turn_boundary.py:190-295`. |
| `application_type` | partial | hints/profile | no canonical asserted slot found | context hint regex | reducers/orchestrator | indirect | partial | Motion/application hints derive from text: `backend/app/agent/state/context_hint_derivation.py:7-47`; V9.2 seal system infers family/type: `backend/app/agent/v92/orchestrator.py:335-405`. |
| `seal_type` | partial/misaligned | frontend/legacy name | CaseField possible generically | legacy alias | overrides/UI | yes | partial | Critical contract contains `seal_type`, extractor allowlist uses `sealing_type`: `backend/app/domain/critical_field_contract.py:9-20`, `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| `sealing_type` | yes | text/normalized | EngineeringValue through reducers | RWDR aliases | intake/override | yes | partial | RWDR regex and V9.2 raw mapping exist: `backend/app/agent/domain/normalization.py:1043-1055`, `backend/app/agent/v92/orchestrator.py:357-365`. Pending slot binding missing branch: `backend/app/agent/graph/slot_answer_binding.py:243-281`. |
| `seal_principle` | no canonical slot found | n/a | n/a | not found after search | n/a | no | no | Search terms: `seal_principle|Dichtprinzip` in productive backend did not reveal a canonical state field; current code uses type/family/path. |
| `medium` | yes | text + classification | FieldStatus exists generally; classification status | medium registry | intake/override/case delta | yes | partial | Medium extraction/classification: `backend/app/agent/domain/medium_registry.py:360-415`, `backend/app/agent/domain/medium_registry.py:431-506`. No explicit placeholder denylist found for `das medium`. |
| `temperature_operating` | misnamed | productive field `temperature_c` | EngineeringValue | unit normalization | intake/override | yes | partial | `temperature_c` extracted from `30 grad`: `backend/app/agent/domain/normalization.py:1190-1199`; allowlist: `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| `temperature_min/max` | partial | critical contract has min/max | not in intake allowlist | limited | direct/other paths unclear | partial | unclear | Critical fields include `temperature_min_c`/`temperature_max_c`, but intake allowlist does not: `backend/app/domain/critical_field_contract.py:23-43`, `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| `pressure_system` | missing canonical | n/a | n/a | system pressure only interpretation | n/a | UI text only | no | Not found as productive canonical slot after search `pressure_system|pressure_at_seal|pressure_delta|seal_pressure`; only text/tests and `system_pressure` interpretation occur (`backend/app/agent/domain/normalization.py:506`, `backend/app/agent/graph/slot_answer_binding.py:158-210`). |
| `pressure_at_seal` | missing canonical | n/a | n/a | direct_at_seal interpretation | n/a | UI text only | partial as interpretation | Same as above; productive slot remains `pressure_bar` (`backend/app/domain/critical_field_contract.py:132-137`). |
| `pressure_delta` | missing canonical | n/a | n/a | differential interpretation | n/a | UI text only | partial as interpretation | Same as above. |
| `pressure_bar` | yes | bar | EngineeringValue interpretation | unit normalization | intake/override/case delta | yes | yes | Pressure normalization and interpretation: `backend/app/agent/domain/normalization.py:570-579`; pressure fields contract: `backend/app/domain/critical_field_contract.py:132-137`. |
| `shaft_diameter_mm` | yes | mm | EngineeringValue | unit normalization | intake/override | yes | yes | Extracted and used for compute: `backend/app/agent/domain/normalization.py:1213-1220`, `backend/app/agent/graph/nodes/compute_node.py:196-218`. |
| `rpm` / `speed_rpm` | yes as `speed_rpm` | rpm | EngineeringValue | unit normalization | intake/override | yes | yes | Extractor/checks use `speed_rpm`: `backend/app/agent/domain/normalization.py:1213-1220`, `backend/app/agent/domain/checks_registry.py:89-101`. |
| `circumferential_speed` | derived | m/s | calculation result | formula | compute | yes | yes | Formula in calculation engine and V9.2 calculator: `backend/app/services/calculation_engine.py:124-129`, `backend/app/agent/v92/calculator_registry.py:80-148`. |
| `shaft_surface_roughness_Ra` | partial/misaligned | critical `shaft_roughness_ra_um`; extractor broad text | status generic | no robust extractor found | direct/UI mostly | yes | partial | Contract has roughness; normalization supports `surface_roughness_ra_um`; intake allowlist only `counterface_surface`: `backend/app/domain/critical_field_contract.py:73-87`, `backend/app/agent/domain/normalization.py:590-604`, `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| `shaft_hardness` | partial | critical `shaft_hardness_hrc` | generic | no productive extractor in allowlist | direct/UI mostly | yes | partial | Contract has hardness, RWDR calc can use it, but intake allowlist lacks numeric hardness: `backend/app/domain/critical_field_contract.py:73-87`, `backend/app/agent/domain/rwdr_calc.py:149-187`, `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| `counterface_condition` | partial | text `counterface_surface` | generic | broad text | intake/direct | yes | partial | Allowlist includes `counterface_surface`; challenge engine treats counterface missing for rotary: `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`, `backend/app/agent/domain/challenge_engine.py:467-568`. |
| `runout` / `wellenschlag` | partial | critical `runout_mm`, but extractor broad `tolerances` | generic | limited | direct/UI mostly | yes | partial | Contract has runout; normalization has broad tolerance pattern, not robust numeric slot in intake allowlist: `backend/app/domain/critical_field_contract.py:149-160`, `backend/app/agent/domain/normalization.py:1095-1098`, `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| `eccentricity` | partial | critical `eccentricity_mm` | generic | limited | direct/UI mostly | partial | partial | Same evidence as runout. |
| `axial_movement` | missing/unclear | n/a | n/a | not in allowlist | n/a | possible UI text not canonical | no | Not found in extractor allowlist or critical field list sections cited above. |
| `lubrication` | partial | text | generic | critical contract | intake allowlist no dedicated field | yes | partial | Operating contract includes lubrication; risk/readiness uses critical fields: `backend/app/domain/critical_field_contract.py:23-43`, `backend/app/agent/domain/risk_readiness.py:50-62`. |
| `contamination` | yes/partial | text | generic | allowlist | intake/direct | yes | partial | Allowlist has contamination: `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| `installation_space` | partial | text | generic | V9.2 optional | direct/LLM maybe | yes | partial | V9.2 rotary optional fields include installation space, but intake allowlist uses `installation` and `geometry_context`: `backend/app/agent/v92/orchestrator.py:147-155`, `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`. |
| housing/bore/groove dimensions | partial | critical contract + UI fields | generic | limited | direct/UI | yes | partial | Critical geometry fields exist; productive intake allowlist does not include all: `backend/app/domain/critical_field_contract.py:46-70`, `frontend/src/components/dashboard/ParameterWorkspaceTab.tsx:187-229`. |
| `material` | yes | text + material mapping | generic | normalization/material intelligence | intake/direct | yes | partial | Allowlist and material normalization: `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`, `backend/app/agent/domain/normalization.py:757-895`. |
| lifecycle / leakage / friction priorities | partial | requirement fields | generic | no full engine found | UI/direct mostly | partial | partial | Contract has requirement fields; no complete deterministic design objective engine found: `backend/app/domain/critical_field_contract.py:103-120`. |
| evidence/provenance | yes/partial | Provenance model | FieldStatus generic | evidence gates | backend | partial | yes/partial | Models define Provenance/EngineeringValue; reductions currently assert without evidence in override path: `backend/app/agent/state/models.py:128-164`, `backend/app/agent/state/reducers.py:702-745`. |

## 5. Screenshot-Regression: Root Cause Analysis

### A. Temperatur 30 °C erneut abgefragt

- Repro from code: `30 grad` can be parsed as `temperature_c`
  (`backend/app/agent/domain/normalization.py:1190-1199`).
- Exakte Ursache: not fully proven without replay trace.
- Code-Fakt: normalized candidates are not asserted by confidence alone; missing
  core fields can remain blocking unknowns (`backend/app/agent/state/reducers.py:664-679`,
  `backend/app/agent/state/reducers.py:747-809`).
- Gegenbeleg/partial guard: challenge tests ensure normalized temperature is
  not repeated as missing in one engine slice (`backend/app/agent/tests/test_challenge_engine.py:90-117`).
- Inference: repetition likely occurs where answer/cockpit logic reads asserted
  or another projection instead of normalized/known state, or where user text
  was not promoted to a user override.
- Severity: P1.
- Later patch seam: assertion/known-value policy in reducers plus full chat
  regression.
- Future test: free-text `30 grad` in active case -> no next question for
  temperature; cockpit and chat use same known state.

### B. "Das ist der Systemdruck" nicht sauber eingeordnet

- Code-Fakt: pending pressure answer can detect `systemdruck` and stores
  `pressure_context`, but target field remains `pressure_bar`
  (`backend/app/agent/graph/slot_answer_binding.py:158-210`).
- Code-Fakt: critical pressure fields are `pressure_nominal`,
  `pressure_peak`, `pressure_bar`, `pressure_profile`; no canonical
  `pressure_system`, `pressure_at_seal`, `pressure_delta`
  (`backend/app/domain/critical_field_contract.py:132-137`).
- Code-Fakt: normalization recognizes `system_pressure` as interpretation
  (`backend/app/agent/domain/normalization.py:506`).
- Ursache: pressure role is metadata, not distinct state.
- Severity: P0 for professional design.
- Later patch seam: canonical pressure role fields and migration adapter from
  `pressure_bar.interpretation`.
- Future test: `das ist der Systemdruck` sets system pressure/context, leaves
  direct seal pressure open, and asks one justified follow-up.

### C. RWDR nicht als geschlossener Dichtungstyp behandelt

- Code-Fakt: RWDR aliases normalize to radial shaft seal/sealing type
  (`backend/app/agent/domain/normalization.py:1043-1055`,
  `backend/app/agent/v92/orchestrator.py:357-365`).
- Code-Fakt: productive extractor allowlist uses `sealing_type`; other contracts
  and UI also use `seal_type` in places (`backend/app/agent/graph/nodes/intake_observe_node.py:67-86`,
  `backend/app/domain/critical_field_contract.py:9-20`).
- Code-Fakt: pending slot resolver branches for medium, pressure, temperature,
  shaft, speed; no sealing-type branch found (`backend/app/agent/graph/slot_answer_binding.py:243-281`).
- Ursache: partly implemented detection, but canonical naming and pending answer
  closure are not unified.
- Severity: P1.
- Later patch seam: one canonical seal-type slot adapter; add pending
  `seal_type_value` binding.
- Future test: pending question for Dichtungstyp + `einen RWDR` closes
  `sealing_type` and does not ask Dichtungstyp again.

### D. Platzhalter "das medium" zählt möglicherweise als Medium

- Code-Fakt: medium extraction/classification accepts raw candidates and unknown
  captures become `mentioned_unclassified` with `requires_confirmation`
  (`backend/app/agent/domain/medium_registry.py:360-415`,
  `backend/app/agent/domain/medium_registry.py:497-506`).
- Code-Fakt: no explicit denylist for `das medium` was found after search
  `das medium|placeholder|Platzhalter|medium.*unknown`.
- Code-Fakt: user override fields for `medium` are privileged by intake/reducers
  (`backend/app/agent/graph/nodes/intake_observe_node.py:106-122`,
  `backend/app/agent/state/reducers.py:486-547`,
  `backend/app/agent/state/reducers.py:702-745`).
- Inference: exact phrase capture depends on extractor/LLM/direct-input path,
  but there is no visible guard that makes placeholder-like medium text invalid.
- Severity: P1.
- Later patch seam: placeholder/unknown denylist in medium normalization and
  override validation.
- Future test: `medium="das medium"` -> invalid/unknown, not known, no RFQ
  readiness credit.

### E. Wellenschlag-/RWDR-Risikoaussage ohne belegten Wert

- Code-Fakt: challenge engine can mention `Rundlauf` as missing counterface
  context for rotary/RWDR when speed/diameter imply dynamic concern
  (`backend/app/agent/domain/challenge_engine.py:541-568`).
- Code-Fakt: risk readiness adds RWDR surface/runout missing risk when path is
  RWDR and fields are absent (`backend/app/agent/domain/risk_readiness.py:282-290`).
- Code-Fakt: richer RWDR calc can evaluate runout, but productive compute node
  does not feed runout into that calculation path (`backend/app/agent/domain/rwdr_calc.py:149-187`,
  `backend/app/agent/graph/nodes/compute_node.py:104-134`).
- Ursache: generic missing-risk language is implemented; claim "hoher
  Wellenschlag liegt vor" would not be supported unless a runout/eccentricity
  field is present.
- Severity: P0 if phrased as fact, P2 if phrased as missing data/risk to check.
- Later patch seam: risk claim evidence gate that separates "missing/unknown"
  from "measured high".
- Future test: no `runout_mm`/`eccentricity_mm` -> only "Rundlauf unbekannt /
  prüfen", never "hoher Wellenschlag".

### F. "62 % geklärt" und "3 von 5 Checks" unklar

- Code-Fakt: frontend cockpit has exactly five calculation definitions
  (`frontend/src/lib/engineering/buildSealCockpitViewModel.ts:23-54`).
- Code-Fakt: frontend computes calculation count and status text:
  `Gerechnet ${calculationCount} von ${CALCULATION_DEFINITIONS.length}`
  (`frontend/src/lib/engineering/buildSealCockpitViewModel.ts:277-334`).
- Code-Fakt: coverage percent uses backend workspace completeness when present,
  else frontend rounded coverage score (`frontend/src/lib/engineering/buildSealCockpitViewModel.ts:281-286`).
- Code-Fakt: mock cockpit contains similar "61 % geklärt" / "3 von 5 Checks"
  text (`frontend/src/lib/engineering/sealCockpitMock.ts:13-19`,
  `frontend/src/lib/engineering/sealCockpitMock.ts:57-83`).
- Ursache: not purely backend-derived/auditable in the view model.
- Severity: P1.
- Later patch seam: backend returns check registry identity, denominator, count,
  coverage explanation; frontend renders only.
- Future test: status strip values equal backend contract fields; no frontend
  hardcoded denominator in production path.

## 6. Deterministische Engine Capability Matrix

| Capability | Soll | IST | Status | Evidenz | Risiko | kleinster Patch-Seam | Tests |
|---|---|---|---|---|---|---|---|
| Request Type Detection | deterministic route | regex/state boundary + dispatch | IMPLEMENTED | `backend/app/agent/v92/turn_boundary.py:190-295`, `backend/app/agent/api/dispatch.py:413-423` | route != technical design truth | keep | route golden tests |
| Application Classification | rotary/hydraulic/static/O-ring | hints + V9.2 family inference | PARTIAL | `backend/app/agent/state/context_hint_derivation.py:7-47`, `backend/app/agent/v92/orchestrator.py:335-405` | weak app truth | backend classifier slot | app scenarios |
| Seal Type / Principle | type + principle | `sealing_type`, type aliases; no principle slot found | PARTIAL | `backend/app/agent/domain/normalization.py:1043-1055`, `backend/app/domain/critical_field_contract.py:9-20` | repeated questions/misalignment | canonical adapter | RWDR closes question |
| Canonical Field Model | complete engineering slots | broad FieldStatus model, narrow productive allowlist | PARTIAL | `backend/app/agent/state/models.py:115-164`, `backend/app/agent/graph/nodes/intake_observe_node.py:67-86` | lost nuance | extend state contract first | schema tests |
| Unit Normalization | deterministic units | temp/pressure/rpm/mm/roughness partial | PARTIAL | `backend/app/agent/domain/normalization.py:520-604`, `backend/app/agent/domain/normalization.py:1190-1220` | alias gaps | normalizer tests | unit tests |
| Provenance per Field | every field auditable | model exists; some paths generic/user override | PARTIAL | `backend/app/agent/state/models.py:128-164`, `backend/app/agent/state/reducers.py:702-745` | false authority | provenance-required validators | mutation tests |
| Placeholder Rejection | invalid placeholders | no explicit medium denylist found | MISSING | `backend/app/agent/domain/medium_registry.py:497-506` | fake known fields | medium normalizer | placeholder test |
| Conflict Detection | corrections/conflicts | reducer conflict detection | PARTIAL | `backend/app/agent/state/reducers.py:567-592` | field-specific conflicts incomplete | reducer extensions | conflict golden tests |
| Stale Invalidation | dependent stale facts | dependency map and marking exist | PARTIAL | `backend/app/agent/state/reducers.py:71-101`, `backend/app/agent/state/reducers.py:963-1038` | coverage unclear | targeted stale tests | critical field changes |
| Missing Input Policy | required by application/type | core + RWDR type-sensitive + V9.2 required | PARTIAL | `backend/app/agent/state/reducers.py:145-178`, `backend/app/agent/v92/orchestrator.py:55-79` | incomplete professional RWDR | field matrix | RWDR missing tests |
| Question Prioritization | one highest-value question | implemented single strategy | PARTIAL | `backend/app/agent/graph/output_contract_assembly.py:481-564` | source mismatch | planner reads canonical known state | no repeat tests |
| Question Justification | every question explains why | meta reasons exist | IMPLEMENTED/PARTIAL | `backend/app/agent/graph/output_contract_assembly.py:178-270`, `backend/app/agent/runtime/clarification_priority.py:113-191` | reasons generic | domain-specific reasons | reason assertion |
| Formula Registry | deterministic formulas | calculation engine + V9.2 registry | IMPLEMENTED/PARTIAL | `backend/app/services/calculation_engine.py:124-201`, `backend/app/agent/v92/calculator_registry.py:420-449` | limited formulas | register transparently | formula tests |
| Check Registry | deterministic checks | five registered checks | PARTIAL | `backend/app/agent/domain/checks_registry.py:28-86` | cockpit overstates completeness | backend status contract | 5-check tests |
| Risk Engine | evidence-based risks | missing/numeric/simple risk rules | PARTIAL | `backend/app/agent/domain/risk_readiness.py:182-290`, `backend/app/agent/domain/challenge_engine.py:334-609` | generic risk can read as fact | evidence-gated claim types | risk wording tests |
| Readiness Engine | deterministic RFQ/readiness | governance/action readiness/readiness bands | PARTIAL | `backend/app/agent/domain/readiness.py:47-171`, `backend/app/agent/v92/orchestrator.py:718-760` | criteria split | one backend readiness source | readiness tests |
| Evidence Gate | claim refs/evidence | V9.1/V9.2 guards | PARTIAL | `backend/app/agent/v91/evidence_gate.py:8-36`, `backend/app/agent/v92/final_guard.py:111-159` | does not verify all engineering semantics | claim taxonomy | evidence tests |
| Claim Guard | blocks release/suitability | regex/context final guard | IMPLEMENTED/PARTIAL | `backend/app/agent/v91/claim_guard.py:8-67`, `backend/app/agent/v92/final_guard.py:16-62` | false certainty outside patterns | structured claim validator | adversarial tests |
| RFQ / Briefing Readiness | governed dossier | RFQ state + V9.2 dossier nodes exist | PARTIAL | `backend/app/agent/graph/topology.py:355-365`, `backend/app/agent/state/models.py:773-829` | not complete design release | RFQ gate tests | RFQ golden |
| Cockpit Projection | backend-derived only | backend contract plus frontend view computation/fallback | MISALIGNED | `backend/app/agent/v92/dashboard_contract.py:179-280`, `frontend/src/hooks/useCockpitData.ts:166-187` | UI-schein | backend-only metrics | frontend contract tests |
| Trace / Audit Log | mutation events | case events and service audit validation exist | PARTIAL | `backend/app/agent/state/models.py:1125-1160`, `backend/app/services/case_service.py:549-708` | live endpoint less strict | align live/service validation | audit tests |
| Regression Tests | screenshot cases | many slice tests, missing full e2e | PARTIAL | see section 9 | regressions survive | golden scenarios | section 9 |

## 7. LLM Boundary Audit

**Deterministically created technical statements**

- Turn policy and streaming policy are deterministic (`backend/app/agent/v92/turn_boundary.py:190-295`,
  `backend/app/agent/v92/runtime_contract.py:181-235`).
- Normalized/asserted/governance state derives through reducers (`backend/app/agent/state/reducers.py:486-815`).
- Registered checks and V9.2 calculators are deterministic (`backend/app/agent/domain/checks_registry.py:133-185`,
  `backend/app/agent/v92/calculator_registry.py:80-148`).
- V9.2 engineering/readiness/risk update is deterministic and fail-open
  additive (`backend/app/agent/graph/nodes/v92_engineering_node.py:1-27`,
  `backend/app/agent/v92/orchestrator.py:1192-1216`).

**LLM-created or LLM-influenced technical text**

- Intake may use LLM JSON mode for fields from a whitelist
  (`backend/app/agent/graph/nodes/intake_observe_node.py:363-439`).
- Governed composer is enabled by default unless env disables it and uses an LLM
  for text-only answer composition (`backend/app/agent/communication/governed_answer_composer.py:98-111`,
  `backend/app/agent/communication/governed_answer_composer.py:252-352`).
- Composer fallback/orientation text contains technical RWDR topics such as
  Gegenlaufflaeche, Rundlauf, Druck, Reibwaerme and Schmierung
  (`backend/app/agent/communication/governed_answer_composer.py:760-797`).

**Where LLM can currently assert technical truth**

Code-Fakt: Topology says only observe/composer are allowed LLM nodes, and
composer must not write technical truth/readiness/deltas/cockpit
(`backend/app/agent/graph/topology.py:55-62`,
`backend/app/agent/graph/nodes/governed_answer_composer_node.py:59-65`).

Inference: The LLM cannot directly mutate asserted state through composer, but
it can produce user-visible technical wording. Final guards catch forbidden
patterns and some evidence/claim issues, but they do not prove every engineering
sentence is backed by a specific field.

**Existing guards**

- V9.1 claim/evidence/communication guards
  (`backend/app/agent/v91/claim_guard.py:8-67`,
  `backend/app/agent/v91/evidence_gate.py:8-36`,
  `backend/app/agent/v91/communication_guard.py:8-32`).
- V9.2 final guard for forbidden claims, compound/product claims, stale or
  failed calculations, standards gaps and review-required context
  (`backend/app/agent/v92/final_guard.py:74-200`).
- Runtime contract attaches TurnEnvelope and dashboard/final context
  (`backend/app/agent/v92/runtime_contract.py:376-539`).
- Streaming prevents user-visible technical draft tokens
  (`backend/app/agent/api/streaming.py:111-130`, `backend/app/agent/api/streaming.py:840-883`).

**Missing guard behavior**

- No field-level evidence gate was found that maps each risk sentence to an
  input field vs. missing-input finding.
- No canonical guard was found that forbids treating `system_pressure` as
  pressure at the seal; current guard relies on wording/context.
- No placeholder invalidation guard was found for medium values like
  `das medium`.

## 8. Fachliche Auslegungstiefe RWDR / rotierende Welle

| Fachlicher Auslegungspunkt | im Code vorhanden? | im State vorhanden? | in Checks vorhanden? | in Rueckfragenlogik? | UI sichtbar? | Test vorhanden? | Evidenz | Luecke |
|---|---:|---:|---:|---:|---:|---:|---|---|
| Anwendung rotierend | partial | hints/path | indirect | yes | yes | partial | `backend/app/agent/state/context_hint_derivation.py:7-47`, `backend/app/agent/v92/orchestrator.py:147-155` | no strong classifier state |
| RWDR/PTFE-RWDR type | partial | `sealing_type` | path-dependent | partial | yes | yes/partial | `backend/app/agent/domain/normalization.py:1043-1055`, `backend/app/agent/v92/orchestrator.py:357-365` | pending answer and naming gaps |
| Medium | yes/partial | yes | risk partial | yes | yes | yes/partial | `backend/app/agent/domain/medium_registry.py:431-506` | placeholder and exact medium qualification |
| Temperatur | yes | `temperature_c` | temp headroom/window | yes | yes | yes | `backend/app/agent/domain/checks_registry.py:62-74`, `backend/app/agent/v92/calculator_registry.py:158-261` | min/max/profile incomplete in intake |
| Druck | partial | `pressure_bar` + interpretation | pressure window/PV | yes | yes | yes/partial | `backend/app/agent/domain/checks_registry.py:39-51`, `backend/app/agent/graph/slot_answer_binding.py:158-210` | no separate system/seal/delta slots |
| Drehzahl | yes | `speed_rpm` | surface speed/DN | yes | yes | yes | `backend/app/services/calculation_engine.py:124-135`, `backend/app/agent/graph/nodes/compute_node.py:196-218` | speed profile/transients missing |
| Wellendurchmesser | yes | `shaft_diameter_mm` | surface speed/DN | yes | yes | yes | same as speed | tolerances not tied |
| Umfangsgeschwindigkeit | derived | calculation result | yes | n/a | yes | yes | `backend/app/agent/v92/calculator_registry.py:80-148` | limited acceptance context |
| Gegenlaufflaeche | partial | text | no numeric registry | yes | yes | partial | `backend/app/agent/domain/challenge_engine.py:467-568` | no structured surface condition model |
| Rauheit Ra | partial | contract/normalizer | limited | indirect | yes | partial | `backend/app/domain/critical_field_contract.py:73-87`, `backend/app/agent/domain/normalization.py:590-604` | not in productive allowlist as numeric slot |
| Haerte | partial | contract/RWDR calc | not productive compute | indirect | yes | partial | `backend/app/domain/critical_field_contract.py:73-87`, `backend/app/agent/domain/rwdr_calc.py:149-187` | not in compute node inputs |
| Einlaufspuren | partial | broad text | no | indirect | yes | unclear | `backend/app/agent/graph/nodes/intake_observe_node.py:67-86` | no structured condition/risk |
| Rundlauf/Wellenschlag | partial | critical fields | missing-risk only | indirect | yes | partial | `backend/app/domain/critical_field_contract.py:149-160`, `backend/app/agent/domain/risk_readiness.py:282-290` | no robust extraction/check in productive path |
| Exzentrizitaet | partial | critical field | limited | indirect | partial | partial | `backend/app/domain/critical_field_contract.py:149-160` | same as runout |
| Axialbewegung | no clear canonical | no | no | no | possible text | no | not found in cited contracts/allowlist | missing for professional RWDR |
| Schmierung | partial | critical text | risk text | yes | yes | partial | `backend/app/domain/critical_field_contract.py:23-43`, `backend/app/agent/domain/challenge_engine.py:569-588` | no quantitative lubrication state |
| Verschmutzung | yes/partial | text | risk partial | yes | yes | partial | `backend/app/agent/graph/nodes/intake_observe_node.py:67-86`, `backend/app/domain/critical_field_contract.py:23-43` | no particle/severity model |
| Einbauraum | partial | text | limited | yes | yes | partial | `backend/app/agent/v92/orchestrator.py:147-155` | no full geometry constraints |
| Werkstoff | yes/partial | material field | material screening partial | yes | yes | partial | `backend/app/agent/v92/calculator_registry.py:264-352` | compound/product separation still limited |
| Lebensdauer/Leckage/Reibung | partial | requirement fields | limited | limited | partial | no/partial | `backend/app/domain/critical_field_contract.py:103-120` | no deterministic objective solver |
| Montagebedingungen | partial | installation text | limited | yes | yes | partial | `backend/app/agent/graph/nodes/intake_observe_node.py:67-86` | no structured assembly risk model |
| Betriebsprofil | partial | duty_profile | limited | yes | yes | partial | `backend/app/agent/graph/nodes/intake_observe_node.py:67-86` | no cycle/duration profile checks |

Inference: The current system can orient a rotary/RWDR case and perform a small
set of deterministic screening checks. It cannot yet conduct a professional,
complete RWDR design because the state model and productive extraction/checks
do not fully represent pressure role, surface system, tolerances, runout,
axial movement, lubrication regime, contamination severity, geometry envelope,
objectives, and evidence gates.

## 9. Test Coverage Gap

**Relevant existing tests**

- Reducer confidence/assertion/conflict behavior:
  `backend/app/agent/tests/test_reducers.py:226-232`,
  `backend/app/agent/tests/test_reducers.py:427-455`,
  `backend/app/agent/tests/test_reducers.py:496-509`.
- Pending medium short-answer binding:
  `backend/app/agent/tests/test_pending_medium_short_answer_binding.py:85-151`,
  `backend/app/agent/tests/test_pending_medium_short_answer_binding.py:178-191`.
- Governed state persists pending question/slot binding:
  `backend/app/agent/tests/test_governed_state_persistence_pending_question.py:10-67`.
- Pressure context scenario:
  `backend/app/agent/tests/test_communication_scenario_suite.py:86-120`.
- Output contract pressure context question:
  `backend/app/agent/tests/graph/test_output_contract_node.py:630-685`.
- Next-best-question service known-field behavior:
  `backend/tests/unit/services/test_next_best_question_service.py:72-108`,
  `backend/tests/unit/services/test_next_best_question_service.py:285-306`.
- Compute node deterministic trigger:
  `backend/app/agent/tests/graph/test_compute_node.py:79-183`.
- Case workspace check projection:
  `backend/app/agent/tests/test_case_workspace_projection.py:309-379`.
- V9.2 runtime guard/contract:
  `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:220-278`.

**Missing critical regression tests**

1. Free-text temperature `30 grad` in governed chat becomes known enough that
   temperature is not asked again across chat and cockpit.
2. `das ist der Systemdruck` sets a system-pressure role and keeps pressure at
   seal or differential open when needed.
3. Pending Dichtungstyp question + `einen RWDR` closes canonical
   `sealing_type`/seal-type projection.
4. `medium = "das medium"` is invalid/unknown, never readiness credit.
5. Wellenschlag risk statement requires `runout_mm`/`eccentricity_mm` value for
   measured-high claims; otherwise only missing/unknown wording.
6. Cockpit percentage and "Checks vorhanden" are fully backend-derived.
7. Full governed turn emits at most one new mandatory technical question and
   includes a reason.

**Recommended Golden Scenarios**

1. Nutzer gibt Temperatur 30 °C an -> System fragt Temperatur nicht erneut.
2. Nutzer sagt "das ist der Systemdruck" -> `pressure_system`/context is set,
   `pressure_at_seal` remains open if required; follow-up explains difference.
3. Nutzer sagt "einen RWDR" -> seal type is closed; no repeated type question.
4. Medium = "das medium" -> invalid/unknown, not valid medium.
5. Risk to Wellenschlag only with runout/eccentricity evidence.
6. Cockpit percent/check count are backend-state/check-registry derived.
7. One mandatory question per turn, with reason.

## 10. Priorisierter Patch-Plan — noch NICHT implementieren

| Patch ID | Ziel | betroffene Dateien | warum dort? | Vorbedingung | Akzeptanzkriterien | Tests | Risiko | Abhaengigkeiten |
|---|---|---|---|---|---|---|---|---|
| P0-1 | Known-slot truth and no repeat questions | `backend/app/agent/state/reducers.py`, `backend/app/agent/runtime/clarification_priority.py`, `backend/app/agent/graph/output_contract_assembly.py` | Repetition emerges from normalized/asserted/question state boundary | agree acceptance policy for user text | known temp/medium/type not re-asked | golden 1, 7 | medium | none |
| P0-2 | Placeholder rejection / invalid FieldStatus | `backend/app/agent/domain/medium_registry.py`, `backend/app/agent/domain/normalization.py`, override endpoint validation | placeholder must fail before assertion/override | define denylist and invalid status behavior | `das medium`, `unknown`, `?` do not count known | golden 4 | low/medium | P0-1 compatible |
| P0-3 | RWDR canonical closure | `backend/app/agent/graph/slot_answer_binding.py`, `backend/app/agent/domain/normalization.py`, workspace mapping | pending answer gap and `seal_type`/`sealing_type` mismatch | choose canonical public/internal names | `einen RWDR` closes seal type everywhere | golden 3 | medium | P0-1 |
| P0-4 | Systemdruck vs Dichtungsdruck | state model/critical field contract, normalization, slot binding, question planner, workspace schema | current `pressure_bar` cannot represent roles | introduce canonical role model carefully | system/seal/delta separated; no seal-pressure inference | golden 2 | high | migration/adapter plan |
| P1-1 | State-based question planner with reasons | clarification priority/output contract | planner must use same canonical known state | P0 field truth | one best question, no repeats, reason present | golden 1,2,3,7 | medium | P0s |
| P1-2 | Transparent check/readiness registry | `checks_registry`, workspace projection, frontend cockpit view model | denominator/count must come from backend | stable check contract | UI renders backend `available/total/status` | golden 6 | medium | none |
| P1-3 | Risk claims evidence-gated | risk_readiness/challenge_engine/final guard | separate measured value from missing risk | claim taxonomy | high-runout claim blocked without value | golden 5 | medium | P0-4 helpful |
| P2-1 | Backend-derived cockpit only | workspace projection, `useCockpitData`, cockpit view model | remove frontend truth fallback in production | P1-2 contract | no production `frontend_placeholder` authority | frontend contract tests | medium | P1-2 |
| P2-2 | RWDR field/check depth expansion | field contract, intake, calculators/checks, tests | professional design needs surface/tolerance/lubrication/objectives | P0/P1 stable slots | new fields are unknown until evidenced; checks transparent | RWDR golden suite | high | P0-4, P1-3 |

Files **not** to touch in first patch to avoid a big bang: frontend layout
components beyond rendering contract, RFQ export/dossier nodes, Docker/infra,
database migrations, and broad prompt rewrites. The first patch should stay at
the backend field/question truth boundary.

## 11. Final Verdict

**Real productively present today**

- Governed chat runtime, streaming final guard boundary, state slices,
  reducers, persistence, proposed case delta, direct override endpoints,
  deterministic formula/check registries, V9.2 engineering/readiness projection,
  and frontend cockpit rendering paths.

**Only partially present**

- Professional application/seal-type classification, canonical field truth,
  pressure role semantics, medium validity, provenance enforcement, conflict
  handling, RWDR-specific design depth, risk claim evidence gating, and
  backend-only cockpit metrics.

**Scheinfunktionalitaet / UI-risk**

- Cockpit check count and status strip are partly computed in frontend from a
  hardcoded five-check definition (`frontend/src/lib/engineering/buildSealCockpitViewModel.ts:23-54`,
  `frontend/src/lib/engineering/buildSealCockpitViewModel.ts:277-334`).
- Frontend placeholder cockpit projection can render when backend cockpit truth
  is missing (`frontend/src/hooks/useCockpitData.ts:166-187`).
- UI can display normalized/candidate values that are not necessarily asserted
  engineering truth (`backend/app/agent/v92/dashboard_contract.py:61-89`,
  `backend/app/agent/state/projections.py:230-248`).

**Strongest blocker for professional sealing design**

The canonical backend field model and acceptance semantics are not strong
enough. A professional engine needs distinct, validated, provenance-bearing
slots for application, seal type/principle, pressure roles, surface/tolerance
system, operating profile, material/evidence level and objectives. Today those
are split between narrow productive slots, interpretation metadata, free text,
legacy services and UI fields.

**First patch to implement after audit**

Start with P0-1 plus P0-2: field truth / no-repeat semantics and placeholder
rejection. Those are lower risk than pressure model migration and will directly
address the observed "known value asked again" and placeholder defects.

**Audit-only note**

No tests were run during this audit. The report is based on static file reads,
targeted ripgrep searches, and code/test inspection.
