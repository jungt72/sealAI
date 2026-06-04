# SealAI V10 Conversational Sealing Intelligence Concept

## 0. Status

- Date: 2026-05-20
- Status: current SSoT concept for Codex App, Codex CLI, and future patches.
- Applies to repo: `/home/thorsten/sealai`
- Supersedes as product target: V8/V9 concept documents where they conflict
  with this file.
- Does not remove: the existing governed runtime, V9.2 implementation contracts,
  final guard, state reducers, dashboard contract, or RFQ boundaries.

Active principle:

```text
Freely explain. Deterministically calculate. Only claim with evidence.
```

## 1. Product Intent

SealAI should communicate like an experienced sealing engineer.

The user may speak freely: greetings, smalltalk, knowledge questions, material
questions, follow-ups, contextual comparisons, rough ideas, dialect, incomplete
phrases, and concrete case facts are all valid input.

The system must not force every turn into a governed case flow. A user asking
for PTFE, NBR, PEEK, FKM or a comparison should receive a generous knowledge
answer first. A user describing a concrete sealing situation should enter
governed case intake, where state mutation, calculations and risk/readiness
logic are backend-owned.

## 2. Boundary Model

V10 has one product architecture with two runtime modes:

| Mode | User intent | State behavior | Answer behavior |
| --- | --- | --- | --- |
| Conversation / knowledge | Greeting, smalltalk, meta question, material explanation, material follow-up, material comparison, general sealing knowledge | No case creation. No case mutation. Recent entities and chat context may be used for the answer. | Answer directly, explain uncertainty, optionally ask one useful next question. |
| Governed case intake | Concrete application facts or explicit case work: medium, temperature, pressure, motion, geometry, failure mode, constraints, RFQ/readiness | Case state may be proposed and mutated only through governed validation, reducers and persistence. | Hydrate state, run deterministic checks/calculations/RAG as available, guard final answer. |

The LLM may classify, draft, extract and explain. It must not directly mutate
case state or issue final engineering approval.

## 3. Routing And Context

The routing target is semantic, not wording-specific.

Examples that must be treated as knowledge unless concrete case facts are also
present:

- `ich brauche informationen zu PTFE`
- `bitte gebe mir informationen ueber PTFE`
- `was kannst du mir ueber PEEK erzaehlen`
- `bitte jetzt zu NBR`
- `und FKM?`
- `bitte vergleiche beide materialien`
- `was ist besser`
- `unterschied zwischen PTFE und NBR`

The router and context resolver must support:

- materials: PTFE, NBR, FKM, FFKM, EPDM, HNBR, VMQ, FVMQ, PEEK, POM, PA, PE,
  filled PTFE variants and future material aliases;
- anaphora: `die beiden`, `beide`, `das`, `damit`, `dazu`, `im Vergleich`;
- follow-ups: `jetzt zu X`, `und X?`, `mehr dazu`, `vergleich`;
- bridge questions: `welches ist besser fuer meine Anwendung?`;
- concrete case facts that should switch to governed intake only when enough
  application context is actually present.

The conversation context resolver should carry recent domain entities from
chat history into routing/composition. It should never write them into case
state unless the governed case path accepts them as facts.

## 4. Knowledge Answer Standard

Material and sealing-technology knowledge answers should be consistent and
engineer-grade.

Preferred structure:

1. Short definition.
2. Role in sealing technology.
3. Hard technical values where the knowledge base or RAG evidence supports
   them, clearly labeled as typical orientation values rather than universal
   specifications.
4. Strengths.
5. Limits and failure modes.
6. Typical applications.
7. Comparison notes if recent entities exist.
8. Concrete-case bridge: what data is missing for a specific suitability
   assessment.
9. No-final-approval wording.

For material values, answer depth should favor engineering utility: temperature
windows, hardness, density, modulus, tensile strength, elongation, friction,
thermal expansion, conductivity, chemical limits, ageing/weathering,
tribology, creep, extrusion and dynamic constraints where known.

If values are compound-, manufacturer- or test-method-specific, say so. Do not
invent exact values when evidence is not present.

## 5. RAG And Evidence

RAG is part of V10, but it is not an authority bypass.

RAG responsibilities:

- retrieve relevant technical snippets from curated sources and Paperless/Qdrant
  where available;
- support detailed knowledge answers and governed case evidence;
- expose source/context metadata into prompts and LangSmith traces;
- help identify uncertainty and missing data.

RAG must not:

- override state reducers;
- mutate case truth;
- authorize final suitability;
- transform a material-family statement into a compound/product claim;
- transform a norm reference into a compliance claim.

## 6. Governed Case Runtime

The governed runtime remains mandatory for real application data.

Concrete case examples:

- `Ich habe Hydraulikoel, 90 C, rotierende Welle, 8 bar`
- `RWDR fuer Welle 50 mm, 3000 rpm, HLP46`
- `Dichtung faellt nach 200 Stunden aus, Medium ist Wasser-Glykol`

For these turns, the backend may propose state deltas, normalize fields, run
calculations, evaluate checks, retrieve evidence and ask the next missing
question. Mutation must go through governed validation and state reducers.

The frontend must not invent engineering truth. It may render workspace state,
chat messages, disclaimers and backend-provided projections.

## 7. Prompt And Jinja2 Use

Jinja2 is appropriate for V10 because it makes the prompt contract inspectable,
testable and versionable.

Use Jinja2 templates for:

- semantic pre-gate classifier instructions;
- free conversation acknowledgement/open-invite responses;
- knowledge answer composition;
- governed final answer composition;
- runtime-action blocked/bridge wording;
- case-intake clarification wording.

Avoid hard-coding productive answer strings in service logic when a prompt
template or registry exists.

## 8. Observability And LangSmith

V10 should be observable enough to debug real behavior, not only root chain
success.

Expected LangSmith visibility:

- route/pre-gate classification;
- route family and runtime action;
- case creation allowed/blocked flags;
- graph allowed/blocked flags;
- conversation/thread/session id hash;
- LLM child runs for classifiers and composers where privacy settings allow;
- retriever/tool child runs where used;
- RAG snippets or redacted evidence metadata where appropriate.

Expected interpretation:

- Structured clarification interrupts may appear as GraphInterrupt child runs;
  they are expected control flow, not automatically product errors.
- Knowledge turns should show answer-only/conversation routing and no case
  mutation.
- Governed turns should show graph/runtime involvement and state projection.

## 9. Deployment SSoT

Current production shape on the VPS:

- Nginx is the public edge.
- SealAI frontend is the Docker `frontend` service behind Nginx via
  `frontend:3000`.
- Backend is the Docker `backend` service behind Nginx via `backend:8000`.
- Keycloak is behind Nginx via `keycloak:8080`.
- The previous PM2-managed host Next.js process `sealai-frontend` on
  `172.17.0.1:3000` is retired and must not be restarted.

Frontend container env must include both Auth.js/Keycloak variables and the
BFF backend origin, including:

- `AUTH_SECRET` / `NEXTAUTH_SECRET`
- `AUTH_URL` / `NEXTAUTH_URL`
- `KEYCLOAK_CLIENT_ID`
- `KEYCLOAK_CLIENT_SECRET`
- `KEYCLOAK_ISSUER`
- `SEALAI_BACKEND_ORIGIN=http://backend:8000`

## 10. Regression Tests

The V10 route/knowledge regression suite must cover at least:

- greeting: no case creation, friendly short answer;
- `ich brauche informationen ueber PTFE`: knowledge route, no governed fallback;
- reformulated PTFE question: same route family;
- PTFE then `bitte jetzt zu NBR`: follow-up resolves material;
- PTFE and NBR then `bitte vergleiche die beiden`: comparison resolves both;
- PTFE and PEEK then `bitte vergleiche beide materialien`: no FKM drift;
- bridge question `welches ist besser fuer meine Anwendung?`: cautious answer
  and next useful missing question;
- concrete case with medium/temperature/pressure/motion: governed intake.

Focused commands:

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

```bash
npm --prefix frontend run test:run -- \
  src/hooks/useAgentStream.test.tsx \
  src/app/api/bff/agent/chat/stream/route.spec.ts
```

## 11. Definition Of Done For Future Patches

A patch is not V10-complete unless:

- knowledge turns remain knowledge turns across varied phrasing;
- contextual comparisons resolve recent entities;
- case state is untouched for no-case knowledge;
- concrete application data still enters governed intake;
- final answers are guarded;
- RAG is used as evidence/context, not as command text;
- LangSmith traces show enough route/session/child-run detail to audit the
  behavior;
- Browser or API validation proves the production path uses the current Docker
  frontend, not stale host chunks.
