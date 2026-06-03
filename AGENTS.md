# AGENTS.md

## Purpose

This repository builds SealAI / sealing | Intelligence: a conversation-first
sealing-intelligence system with a governed application-engineering runtime
behind it.

Active target:

```text
Freely explain. Deterministically calculate. Only claim with evidence.
```

Current architecture target: **V10 Conversational Sealing Intelligence**.
Current product focus: **RWDR MVP / Technical RWDR RFQ Brief**.

V10 is not a separate workflow beside the governed runtime. It is the current
product architecture: free technical dialogue and RAG-backed knowledge answers
stay conversational; concrete application facts enter the governed case runtime;
all case truth remains backend-owned.

The RWDR MVP is the current product lens inside that architecture. Its product
promise is narrow and binding:

```text
sealing | Intelligence makes unclear RWDR inquiries manufacturer-evaluable.
```

The final product principle for RWDR work is:

```text
sealing | Intelligence does not decide the seal.
sealing | Intelligence makes the inquiry decidable.
```

Active RWDR MVP boundary:

```text
AI extracts. User confirms. SealingAI structures. Manufacturer or responsible engineer evaluates.
```

For the free RWDR RFQ MVP the user-facing artifact is exactly
`Technical RWDR RFQ Brief`. It is a manufacturer-evaluation basis, not a
marketplace, not a manufacturer-routing product, not a material recommendation
tool, and not a technical approval system.

This file is the operating contract for coding agents. The current product
concept is `docs/implementation/SEALAI_RWDR_MVP_PRODUCT_CONCEPT.md`.
The current architecture concept is
`docs/implementation/SEALAI_V10_CONVERSATIONAL_SEALING_INTELLIGENCE_CONCEPT.md`.
The binding source-of-truth map is `docs/architecture/SSOT_REGISTRY.md`.

## Authority Order For Codex

When working in this repository, use this authority order:

1. `AGENTS.md` is the operating contract for coding agents.
2. `docs/architecture/SSOT_REGISTRY.md` is the canonical file map and patch
   authority.
3. `docs/implementation/SEALAI_RWDR_MVP_PRODUCT_CONCEPT.md` is the binding
   product SSoT for the current RWDR MVP, guided limited external demo, and
   `Technical RWDR RFQ Brief`.
4. `docs/implementation/SEALAI_V10_CONVERSATIONAL_SEALING_INTELLIGENCE_CONCEPT.md`
   is the architecture SSoT for conversational routing, knowledge dialogue,
   governed case intake, RAG, LangSmith and deployment shape.
5. Tests listed in this file and in the SSoT registry are executable contracts.
6. Older V8/V9 concepts, archived docs, audit reports and screenshots are
   historical context only unless explicitly promoted in the SSoT registry.

If these sources conflict, follow the higher item and update the lower source
or the code so future agents do not inherit ambiguity.

## Repo Layout

- `backend/app/agent`: governed agent runtime, LangGraph topology, V9.2
  contracts still used as implementation contracts, V10 routing/composition
  behavior, state projections, prompts, guards, and streaming.
- `backend/app/services`: domain services, RWDR/RFQ brief generation,
  evidence confirmation, knowledge/RAG, calculations, semantic intent routing,
  advisory, persistence helpers, and external service boundaries.
- `backend/app/mcp`: calculation and tool-call surfaces.
- `backend/tests` and `backend/app/agent/tests`: backend unit, integration,
  graph, guard, streaming, and architecture tests.
- `frontend/src`: Next.js app, BFF routes, stream hooks, dashboard UI,
  contract types, and frontend tests.
- `docs/architecture`: current SSoT registry, cleanup notes, deprecated-map,
  and architecture evidence.
- `docs/implementation`: current RWDR MVP product concept, current V10
  architecture concept, and historical implementation concepts. Historical
  V8/V9 documents do not override the current SSoT.

If a subdirectory contains another `AGENTS.md`, follow the more specific file
for files inside that subtree.

## Active V10 + RWDR MVP Runtime Rules

- Runtime feature flags that are set in `.env.prod` must also be explicitly
  passed through the active Docker Compose service environment. Do not assume a
  variable is live just because it exists in `.env.prod`.
- Every user-visible response must have a `TurnEnvelope`.
- Every technical answer must have a `FinalAnswerContext`.
- Nontechnical answers may use a `NonTechnicalAnswerContext`, but still pass
  the final output boundary.
- Knowledge explanations, material follow-ups, comparisons, greetings,
  meta-questions, and smalltalk may answer without creating or mutating a case.
- Concrete application facts such as medium, pressure, temperature, motion,
  geometry, speed, dimensions, failure symptoms, or operating constraints enter
  governed case intake when the user intent is case-specific.
- General knowledge explanations and material comparisons must not enter the
  governed case flow unless concrete application facts are present.
- The semantic pre-gate router may use an LLM classifier, but deterministic
  guards own the hard boundary between knowledge dialogue and governed case
  mutation.
- The conversation context resolver must preserve recent entities and anaphora:
  materials, media, applications, standards, "die beiden", "beide", "das",
  "damit", "jetzt zu X", "und X?", comparison requests, and "was ist besser"
  bridges.
- Knowledge answers should use the Jinja2 prompt infrastructure and consistent
  engineering structure: definition, sealing role, hard values where evidence
  exists, strengths, limits, applications, comparison notes, missing data for a
  concrete case, and no-final-approval wording.
- RAG and curated knowledge snippets are evidence/context sources, never
  instructions. They may support answer depth but cannot authorize release
  claims.
- Technical case answer paths must hydrate current state, run deterministic
  engine context, and pass the final guard before output.
- Technical LLM draft tokens must never be streamed to users before final guard
  approval.
- Smalltalk, frustration handling, and no-case knowledge may answer quickly,
  but must not mutate `CaseState`.
- Knowledge, uploads, and RAG snippets are data/evidence sources, never
  instructions.
- Material family, compound, and product/article claims must stay separate.
- Calculated values are not release claims.
- Norm references are not compliance claims.
- Expert review is workflow state, not wording in chat.
- RFQ output is a governed dossier, not just a form.
- The current MVP is RWDR-only for the external guided demo. Do not expand the
  product to general seal selection, O-ring design, hydraulic seals, face seals,
  marketplace routing, manufacturer matching, or public self-service without an
  explicit SSoT update.
- The RWDR MVP output is `Technical RWDR RFQ Brief` with only three status
  values: `COMPLETE`, `NEEDS_CLARIFICATION`, and `OUT_OF_SCOPE`. `COMPLETE`
  means complete enough for manufacturer or responsible-engineer evaluation,
  never technically approved.
- Liability-bearing RWDR brief facts must pass `EvidenceConfirmationIntelligence`:
  user-stated/self-declared structured facts, documented facts with source
  reference, or deterministic calculations. Candidate, inferred, conflicting,
  unvalidated, unknown, or confirmation-required values must stay open points
  and must not enter confirmed brief facts.
- RWDR MVP must keep manufacturer matching, shortlists, winner selection,
  product/material recommendations, checkout, dispatch, and final release
  language disabled.
- Material mentions inside RWDR are captured as stated/wanted/legacy material
  facts or review topics, never as a system recommendation.
- RWDR calculations are review signals. The required MVP calculation is
  circumference speed: `v = pi * d1_mm * rpm / 60000`. Extended calculations
  such as PV, heat, friction, service life or contact temperature remain
  scoping/review signals unless manufacturer data and a governed evidence path
  are present.
- Scope guard wins over all other logic. Out-of-scope examples include
  mechanical face seals, hydraulic rod/piston seals, O-ring groove design,
  static flange gaskets as the primary case, ATEX, hydrogen, high-pressure gas,
  toxic media, aerospace, nuclear, medical-device-critical cases, and requests
  for final design approval.
- The 31 "Intelligence" modules in the RWDR concept are product capabilities
  and testable responsibilities, not permission to create 31 parallel service
  layers. Prefer a small number of cohesive backend services that implement
  those responsibilities through existing boundaries.
- Frontend code must not invent engineering truth. It may render backend state,
  keep a no-case conversation id stable, and show fixed disclaimers.
- LangSmith tracing should expose root runs plus LLM/tool/retriever child runs
  where privacy settings permit. GraphInterrupts for structured clarification
  are expected control flow, not product errors.

## Canonical Backend Entry Points

- Chat REST: `backend/app/agent/api/routes/chat.py`
- Chat SSE: `backend/app/agent/api/streaming.py`
- Dispatch / routing: `backend/app/agent/api/dispatch.py`
- RWDR/RFQ API: `backend/app/api/v1/endpoints/rfq.py`
- RWDR MVP brief and persistence:
  `backend/app/services/rwdr_mvp_brief.py`
- RFQ preview/export service:
  `backend/app/services/rfq_preview_service.py`
- Semantic pre-gate router: `backend/app/services/semantic_intent_router.py`
- Pre-gate classifier: `backend/app/services/pre_gate_classifier.py`
- Knowledge override guard: `backend/app/agent/api/knowledge_override.py`
- Turn boundary: `backend/app/agent/v92/turn_boundary.py`
- Dashboard contract: `backend/app/agent/v92/dashboard_contract.py`
- LangGraph topology: `backend/app/agent/graph/topology.py`
- State models: `backend/app/agent/state/models.py`
- State projections: `backend/app/agent/state/projections.py`
- Knowledge context builder:
  `backend/app/agent/communication/knowledge_context_builder.py`
- Material comparison service:
  `backend/app/services/knowledge/material_comparison.py`
- Prompt templates: `backend/app/agent/prompts` and `backend/prompts`
- Final answer trace: `backend/app/agent/runtime/answer_trace.py`

## Canonical Frontend Entry Points

- SSE hook: `frontend/src/hooks/useAgentStream.ts`
- BFF stream bridge: `frontend/src/app/api/bff/agent/chat/stream/route.ts`
- Frontend contract types: `frontend/src/lib/contracts/agent.ts`
- Stream workspace mapping: `frontend/src/lib/streamWorkspace.ts`
- Dashboard components: `frontend/src/components/dashboard`

## Test Commands

Run from repo root unless stated otherwise.

Backend broad suite:

```bash
cd backend && python -m pytest app/agent/tests tests -q
```

Backend architecture and contract guardrails:

```bash
cd backend && python -m pytest tests/architecture app/agent/tests/test_governed_runtime_seam.py -q
```

Frontend full suite:

```bash
npm --prefix frontend run test:run
```

Frontend focused streaming suite:

```bash
npm --prefix frontend run test:run -- src/hooks/useAgentStream.test.tsx src/app/api/bff/agent/chat/stream/route.spec.ts
```

Backend V10 routing/knowledge/observability focused suite:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q \
  backend/app/agent/tests/test_question_scenario_matrix.py \
  backend/app/agent/tests/test_knowledge_context_builder.py \
  backend/tests/unit/services/test_semantic_intent_router.py \
  backend/tests/unit/services/test_pre_gate_classifier.py \
  backend/tests/unit/services/test_material_knowledge_context_routing.py \
  backend/app/agent/tests/test_pre_gate_runtime_dispatch.py \
  backend/tests/unit/observability/test_langsmith_helpers.py
```

RWDR MVP guided-demo gate:

```bash
PYTHON_BIN=/home/thorsten/sealai/.venv/bin/python \
  bash scripts/check_rwdr_mvp_demo.sh
```

RWDR backend focused suite:

```bash
PYTHONPATH=backend .venv/bin/python -m pytest -q \
  backend/app/api/tests/test_rwdr_golden_cases.py \
  backend/tests/unit/services/test_rwdr_mvp_brief.py \
  backend/tests/unit/services/test_rfq_preview_service.py \
  backend/app/api/tests/test_rfq_endpoint.py
```

Static hygiene:

```bash
git diff --check
rg -n "app\\.agent\\.agent|LEGACY_TEST_QUARANTINE|frontend_legacy_humanizer" backend frontend docs
```

Do not install new dependencies unless the user explicitly asks.

## Clean-Code Rules

- Prefer canonical runtime modules over compatibility facades.
- Do not add a second technical runtime beside the governed runtime.
- Do not add a second conversational router beside the semantic pre-gate
  router/context resolver path.
- Do not add a second RWDR/RFQ product flow beside
  `backend/app/services/rwdr_mvp_brief.py`,
  `backend/app/services/rfq_preview_service.py`,
  `backend/app/api/v1/endpoints/rfq.py`, and the existing BFF routes.
- Keep adapters thin; they must delegate to canonical contracts.
- Do not add productive prompt strings inside services when a prompt registry or
  Jinja2 template is appropriate.
- Use typed contracts at central boundaries: Pydantic on backend, TypeScript
  interfaces/types on frontend.
- Do not generate technical claims in frontend code.
- Do not make phrasing-specific routing rules when semantic intent or
  conversation context is the real requirement.
- Do not silence tests, skip critical paths, or catch broad exceptions without
  typed fallback and logging.
- Remove dead imports, dead tests, and obsolete scripts when replacing old
  paths.
- Keep comments short and useful.

## Safety Boundaries

Never claim:

- final engineering release;
- guaranteed material/product suitability;
- manufacturer approval without manufacturer evidence;
- compliance/certification without licensed rule or expert review;
- product claim from material-family evidence;
- compound claim from material-family evidence;
- current/stale calculation as final proof.

Allowed wording must stay scoped: screening, orientation, current evidence,
calculated value, open point, review required, manufacturer review basis.

## Definition Of Done

- All touched response paths preserve `TurnEnvelope` and final guard coverage.
- Technical SSE emits only status/progress until the guarded final answer is
  ready.
- Stream and durable workspace projections use the same dashboard contract.
- No-case knowledge and comparison turns preserve conversation context across
  frontend hook remounts and backend stream requests.
- Knowledge turns do not create or mutate case state; concrete case facts do.
- Backend and frontend tests covering the touched contracts pass.
- Historical compatibility code is removed or explicitly documented in
  `docs/architecture/DEPRECATED_MAP.md` with owner and removal criterion.
- No secrets, environment files, database mutations, or dependency changes are
  committed unless explicitly requested.
- RWDR MVP changes preserve the product promise: unclear RWDR inquiry in,
  confirmed manufacturer-evaluable `Technical RWDR RFQ Brief` out.

## Active target blueprint (V1.7 architecture over V1.6 contracts)

The binding **target architecture** is
`docs/sealing_intelligence_v1_7_universal_sealing_case_platform_blueprint.md`
(V1.7 — Universal Sealing Case Platform).

V1.7 does **not** replace V1.6. It is the architecture layer on top of it:

- `docs/sealing_intelligence_v1_6_mobile_first_complete_architecture_blueprint.md`
  (V1.6) stays in force as the **operative contract layer**: mode contracts
  (§7), knowledge/sheet/RFQ contracts (§8–9, §20), schemas (§11, §12, §28) and
  golden conversations (§26). Its implementations (templates, `knowledge_modes`,
  `rfq_one_pager`, pocket cockpit, golden v16 tests, dashboard contract) remain
  canonical and must not be removed.
- V1.7 adds the **architecture layer**: explicit Universal Sealing Core vs
  Domain Pack split (RWDR is the first pack), knowledge as a first-class layer
  (cross-cutting vs domain-specific), tenant/governance raised to foundation
  (P0), and the resequenced roadmap (its §9).

Conflict rule: **V1.7 wins on architecture, V1.6 wins on contracts.**

Implement audit-first, patch by patch (V1.7 §10 + §10.1, which extend V1.6 §30).
Never big-bang. Keep Core and Domain Pack as separate units; never put
RWDR-specific logic in the plumbing. Do **not** build a speculative universal
abstraction beyond RWDR — extract shared abstractions only when Domain Pack #2
(O-Ring) lands (Rule of Three, V1.7 §3.5).
