# SealAI V9.1 Gap Audit - Current IST vs Target Concept

## 0. Metadata

- Date: 2026-05-19.
- Repo root: `/home/thorsten/sealai` (`pwd` command output).
- Branch: `redesign/sealai-cockpit-overview` (`git branch --show-current` command output).
- Commit: `a3ec2dfb` (`git rev-parse --short HEAD` command output).
- Pre-audit dirty state: one untracked documentation file, `?? docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md` (`git status --short` command output). This audit treats it as the IST concept input and did not edit it.
- `git diff --check`: no output during baseline, so no tracked whitespace errors were reported.
- Audit mode: read-first / audit-only / gap analysis.
- Created audit file: this file. It did not exist before creation (`ls -l docs/audits/SEALAI_V9_1_GAP_AUDIT.md` returned no output).
- Code diagnostics used: static repository reads and searches only (`find`, `rg`, `nl`, `git`).
- Runtime diagnostics used: no. Tests were discovered but not executed.
- Runtime/service mutation: no migrations, deploy, ingestion, service restart, Docker, nginx, firewall, systemd, DB, Redis, Qdrant, or Paperless writes were run.

## 1. Executive Verdict

Overall alignment: MEDIUM.

SealAI is V9.1-compatible on the hard safety and runtime boundaries: governed graph execution, state layering, deterministic field/check flow, RFQ as a bounded preview/export workflow, final answer guardrails, and no visible technical draft streaming are strongly implemented. The implementation has also evolved beyond V9.1 through V9.2 contracts such as `TurnEnvelope`, a richer `FinalAnswerContext`, dashboard contract, pressure-role modeling, RWDR professional checks, and material evidence-card validation.

The biggest V9.1 gap is Communication Governance. V9.1 makes `CommunicationPlan` and `CommunicationGuard` first-class control surfaces with response moves, answer-first enforcement, one-question behavior, question justification, tab visibility, source disclosure, utility redirection, and DialogueDebt. Current code has named V9.1 adapters and several guards, but the communication policy is thinner and scattered across `v91`, `communication`, composer, reply-composition, and clarification-priority modules.

Best next tuning target: a small Communication Governance hardening patch that expands the current V9.1 `CommunicationPlan`/`CommunicationGuard` adapter layer and adds focused tests for answer-first, one question, question justification, no external utility answer, no tab spam, and recovery behavior.

## 2. Scope and Evidence Sources

- V9.1 target concept: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md`, discovered by the requested `find ... | rg ...` command output.
- Current IST concept: `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md`, discovered by the requested `find ... | rg ...` command output.
- Primary backend areas audited: `backend/app/agent/api`, `backend/app/agent/graph`, `backend/app/agent/state`, `backend/app/agent/runtime`, `backend/app/agent/communication`, `backend/app/agent/domain`, `backend/app/agent/v91`, `backend/app/agent/v92`, `backend/app/services/rag`, `backend/app/services/rfq_preview_service.py`, and `backend/app/domain/critical_field_contract.py`.
- Primary frontend areas audited: `frontend/src/app`, `frontend/src/hooks`, `frontend/src/lib`, and `frontend/src/components/dashboard`.
- Ops/RAG areas audited statically: `paperless`, `ops`, and RAG/Paperless endpoint scripts. No ops commands were executed.

## 3. Summary Matrix

| Area | V9.1 target | Current IST | Status | Priority | Recommendation |
|---|---|---|---|---|---|
| Product identity | Governed Sealing Intelligence, not a generic assistant. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:11-50`. | IST states governed runtime owns truth/checks/RFQ/final guard. Evidence: `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:20-58`. | MATCH | P1 | Keep V9.1 docs updated with V9.2 runtime naming. |
| Non-goals / safety boundary | No weather/travel/news utility, no final suitability/manufacturer/compliance/dispatch claims. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:83-133`. | V9.2 final guard blocks release/suitability/compliance/root-cause/prompt leaks. Evidence: `backend/app/agent/v92/final_guard.py:17-78`, `backend/app/agent/v92/final_guard.py:119-227`. | MATCH | P0 | Keep forbidden wording tests broad. |
| Runtime flow | Semantic boundary -> freedom -> extraction -> governance -> knowledge/RAG -> engines -> question/communication/final guards. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:137-180`. | Governed graph implements turn_boundary -> intake -> normalize -> assert -> medium -> evidence -> compute -> challenge/governance -> RFQ/output/composer. Evidence: `backend/app/agent/graph/topology.py:6-63`, `backend/app/agent/graph/topology.py:301-365`. | EVOLVED_BEYOND_V91 | P0 | Treat V9.2 topology as the current canonical implementation concept. |
| LLM roles | Four LLM roles: semantic boundary, candidate extractor, knowledge/intelligence, final composer. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:184-305`. | Only intake observation and final composer may use LLM in governed graph; other nodes deterministic. Evidence: `backend/app/agent/graph/topology.py:55-60`. | DIFFERENT_BY_DESIGN | P1 | Document that V9.2 replaces some target LLM roles with deterministic routing/adapters. |
| Semantic boundary | Rich semantic decision with intents, relevance, case binding, utility/low-signal handling. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:309-423`. | V9.2 deterministic turn boundary and V9.1 read-only adapter exist. Evidence: `backend/app/agent/v92/turn_boundary.py:1-7`, `backend/app/agent/v92/turn_boundary.py:190-295`, `backend/app/agent/v91/semantic_boundary.py:47-61`. | PARTIAL | P1 | Add explicit mapping coverage and missing low-signal/emotion/utility fields, or document deterministic replacement. |
| Field governance | CandidateFact -> resolver -> normalized/confirmed case truth. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:589-661`. | `CandidateFact`, `FieldGovernanceDecision`, `CaseField`, and layered state exist. Evidence: `backend/app/agent/v91/contracts.py:168-215`, `backend/app/agent/state/models.py:1-20`, `backend/app/agent/state/models.py:115-164`. | MATCH | P0 | Keep reducers as the only case-truth authority. |
| Knowledge policy | Tiered policy, RAG required where evidence is required. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:665-726`. | V9.1 `KnowledgePolicy` exists, RAG is tenant-safe and structured from asserted state. Evidence: `backend/app/agent/v91/contracts.py:152-165`, `backend/app/agent/graph/nodes/evidence_node.py:1-32`, `backend/app/agent/services/real_rag.py:54-86`. | PARTIAL | P1 | Make V9.1 level 0-4 policy explicit in current docs/tests. |
| Medium intelligence | MediumProfile/MediumImpact/tab/chat behavior. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:730-883`. | Medium capability, service, and UI card exist, but state is not the full V9.1 model. Evidence: `backend/app/agent/graph/nodes/medium_intelligence_node.py:78-113`, `backend/app/services/medium_intelligence_service.py:61-95`, `frontend/src/components/dashboard/CaseScreen.tsx:1060-1165`. | PARTIAL | P2 | Add typed MediumProfile/Impact projection or explicitly mark current card as MVP. |
| Material screening | Candidate tiers, no visible percentages, blockers/evidence refs. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:887-1022`. | Material candidates, tab, evidence refs, safety boundary, and no visible score rendering exist; backend still carries internal plausibility score. Evidence: `backend/app/api/v1/schemas/case_workspace.py:360-420`, `frontend/src/components/dashboard/SealCockpit.tsx:1020-1045`, `frontend/src/components/dashboard/SealCockpit.tsx:1614-1665`, `rg "plausibilityScore"` command output. | PARTIAL | P1 | Keep score internal and connect evidence-card-backed status more clearly. |
| Challenge engine | Findings create question needs; challenge does not talk directly. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1064-1116`. | `ChallengeState`/next-best question exists and is used by question planning. Evidence: `backend/app/agent/state/models.py:695-725`, `backend/app/agent/v91/question_planner.py:58-81`. | MATCH | P1 | Add end-to-end behavior tests for challenge -> communication. |
| QuestionPlan | One useful question, why it matters. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1120-1155`. | `QuestionPlan` and adapter exist; tests assert one-question policy. Evidence: `backend/app/agent/v91/contracts.py:218-238`, `backend/app/agent/v91/question_planner.py:8-55`, `backend/app/agent/tests/test_v91_question_plan.py:8-48`. | MATCH | P1 | Strengthen visible question-justification tests. |
| CommunicationPlan | Separate layer with moves, depth, answer-first, source/tab controls. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1159-1332`. | Named `CommunicationPlan` exists but is thin and mostly built from QuestionPlan. Evidence: `backend/app/agent/v91/contracts.py:241-257`, `backend/app/agent/v91/final_answer_context.py:80-91`. | PARTIAL | P1 | Expand schema and enforcement before more product UX tuning. |
| CommunicationGuard | Guard response quality, too many questions, answer-first, utility, tab spam, tone, conflict overwrite. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1336-1367`. | V9.1 guard checks question count, missing planned question, internal artifacts; older communication guard checks claims/evidence/state proposals. Evidence: `backend/app/agent/v91/communication_guard.py:8-32`, `backend/app/agent/communication/guard.py:24-161`. | PARTIAL | P1 | Add central guard findings for every V9.1 communication rule. |
| ClaimGuard / EvidenceGate | Claim levels and evidence gates before output. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1371-1423`. | V9.1 claim/evidence/final guard and stronger V9.2 final guard exist. Evidence: `backend/app/agent/v91/final_answer_guard.py:9-31`, `backend/app/agent/v92/final_guard.py:90-227`. | MATCH | P0 | Keep V9.2 guard canonical. |
| Safety / compliance | Human review and no compliance confirmation without evidence. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1427-1473`. | V9.2 final guard blocks norm/compliance claims with gaps; tests cover standards and suitability blocks. Evidence: `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:101-119`, `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:55-99`. | MATCH | P0 | Keep compliance tests with current product copy. |
| Documents/trust boundary | Documents are evidence, not instructions. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1477-1508`. | Evidence node never uses raw user text, Paperless sync is explicit/tagged, material evidence adapter is dry-run only. Evidence: `backend/app/agent/graph/nodes/evidence_node.py:11-19`, `backend/app/services/rag/paperless.py:208-216`, `backend/app/agent/domain/material_evidence_adapter.py:1-6`. | MATCH/PARTIAL | P1 | Close the gap from document evidence to governed material cards. |
| RFQ | RFQ is a governed result/boundary; no dispatch without explicit action. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1887-1928`. | Preview/consent/export exist; dispatch/external contact disabled. Evidence: `backend/app/agent/communication/rfq_intent.py:45-70`, `backend/app/api/v1/endpoints/rfq.py:61-87`, `backend/app/services/rfq_preview_service.py:494-500`, `backend/app/services/rfq_preview_service.py:577-682`. | EVOLVED_BEYOND_V91 | P0 | Preserve as boundary; add readiness from professional check groups. |
| Cockpit/projections | Tabs show governed state and visible tab updates. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1831-1883`. | Backend exposes evidence fields; frontend generic check model drops compatibility evidence metadata. Evidence: `backend/app/api/v1/schemas/case_workspace.py:648-684`, `frontend/src/lib/engineering/cockpitModel.ts:43-66`, `frontend/src/lib/mapping/workspace.ts:832-859`. | PARTIAL | P1 | Map and render evidence status/refs/limitations in cockpit. |
| RAG/Paperless/Qdrant | Evidence-backed claims where required. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:665-726`, `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1477-1508`. | Paperless/Qdrant/RAG exist and are tenant-bounded; no live production Paperless -> material evidence card persistence. Evidence: `backend/app/services/rag/paperless.py:152-216`, `backend/app/services/rag/paperless.py:428-458`, `backend/app/agent/domain/material_evidence_cards.py:1-6`. | PARTIAL | P2 | Add dry-run endpoint/report before persistence. |
| Evidence cards | V9.1 expects evidence gate; not a full card adapter design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1371-1423`. | Validator and Paperless/RAG-like adapter are more concrete than V9.1 but dry-run only. Evidence: `backend/app/agent/domain/material_evidence_cards.py:167-230`, `backend/app/agent/domain/material_evidence_adapter.py:1-70`. | EVOLVED_BEYOND_V91/PARTIAL | P2 | Update V9.1+ docs with this design and add persistence path later. |
| Tests/evaluation | Golden conversations, acceptance criteria, behavior metrics. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:2068-2118`, `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:2238-2257`. | 291 tracked project tests discovered; V9.1 golden tests exist but are not a full end-to-end communication eval suite. Evidence: tracked-test count command output `291`, `backend/app/agent/tests/test_v91_golden_conversations.py:41-152`. | PARTIAL | P1 | Add golden conversation runner around visible final output. |
| Ops/deploy | V9.1 has no major ops spec beyond safe evidence/RFQ boundaries. | RAG/Paperless scripts and endpoints exist, but this audit did not run them. Evidence: `paperless/scripts/sealai-rag-webhook.sh:4-49`, `ops/bin/sealai-rag-paperless-sync:4-22`. | UNCLEAR | P3 | Audit ops separately if deployment behavior matters. |

## 4. Detailed Requirement Matrix

| Requirement ID | V9.1 requirement and type | IST/code evidence | Status | Impact | Gap and tuning recommendation |
|---|---|---|---|---|---|
| V91-PRODUCT-01 Governed Sealing Intelligence | Target product identity is governed sealing intelligence, not generic chat. Hard product requirement. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:11-50`. | IST concept says backend owns truth/checks/RFQ/final guard. Evidence: `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:20-40`. Runtime graph enforces governed path. Evidence: `backend/app/agent/graph/topology.py:6-63`. | MATCH | P1 | No gap in principle. Tune docs to say V9.2 is current implementation of the V9.1 product identity. |
| V91-NONGOAL-01 No final suitability/manufacturer/compliance claims | Non-goal/hard safety boundary. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:83-133`. | Final guards block final release, suitability, material compatibility, compliance, and root-cause claims. Evidence: `backend/app/agent/v92/final_guard.py:17-78`, `backend/app/agent/v92/final_guard.py:119-227`. RFQ response forbids dispatch/final approval. Evidence: `backend/app/agent/communication/rfq_intent.py:45-70`. | MATCH | P0 | Keep high-coverage tests; this is safety-critical. |
| V91-RUNTIME-01 Semantic Boundary Manager | Explicit runtime stage. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:137-180`, `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:309-392`. | V9.2 has deterministic `TurnBoundaryDecision`; V9.1 adapter maps current runtime into V9.1 terms. Evidence: `backend/app/agent/v92/turn_boundary.py:190-295`, `backend/app/agent/v91/semantic_boundary.py:47-61`. | PARTIAL | P1 | It is present but not the V9.1 LLM-rich schema. Add missing fields or document deterministic replacement. |
| V91-RUNTIME-02 LLM Freedom / Red Flag Decision | Explicit levels free/guided/restricted/blocked and red flags. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:427-499`. | V9.1 enums and decision exist; red flags are regex/adapted and final guard repeats constraints. Evidence: `backend/app/agent/v91/contracts.py:47-64`, `backend/app/agent/v91/contracts.py:115-129`, `backend/app/agent/v91/semantic_boundary.py:279-337`. | PARTIAL | P0 | Centralize red-flag provenance between boundary, policy, and final guard. |
| V91-LLM-01 Semantic Boundary LLM | LLM classifies intents and low-signal/utility. Future/target role. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:184-216`. | Current boundary is deterministic and regex/hint based. Evidence: `backend/app/agent/v92/turn_boundary.py:1-7`, `backend/app/agent/v92/turn_boundary.py:52-95`. | DIFFERENT_BY_DESIGN | P1 | Decide whether to keep deterministic boundary as evolved design; if yes, update concept instead of adding another LLM. |
| V91-LLM-02 Candidate Extractor LLM | Extracts candidate facts only; no truth mutation. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:219-244`. | Topology allows only `intake_observe_node` LLM for technical observation; state model says LLM only writes ObservedState. Evidence: `backend/app/agent/graph/topology.py:55-60`, `backend/app/agent/state/models.py:1-20`. | MATCH/PARTIAL | P0 | Ensure extraction outputs are consistently projected as V9.1 CandidateFacts at boundaries. |
| V91-LLM-03 Knowledge / Intelligence LLM | Explains domain, does not make final suitability/cert/probability claims. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:248-276`. | Knowledge is partly deterministic/RAG and partly services; material/medium intelligence avoid release claims. Evidence: `backend/app/agent/services/material_intelligence.py:558-647`, `backend/app/services/medium_intelligence_service.py:61-95`. | PARTIAL | P1 | Clarify which knowledge paths may use LLM and when sources are mandatory. |
| V91-LLM-04 Final Composer LLM | Natural answer from final context/communication plan only. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:280-305`. | `GovernedAnswerComposer` is read-only, validates output, and streams only after guard protocol. Evidence: `backend/app/agent/communication/governed_answer_composer.py:105-147`, `backend/app/agent/communication/governed_answer_composer.py:410-440`. | MATCH | P0 | Keep composer tied to `FinalAnswerContext`; add CommunicationPlan depth/moves. |
| V91-STATE-01 RawConversationHistory vs CaseState separation | Raw conversation separate from governed truth. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:502-585`. | State model has layered observed/normalized/asserted/derived/evidence/governance and v91 context. Evidence: `backend/app/agent/state/models.py:1-20`, `backend/app/agent/state/models.py:1218-1295`. | MATCH | P0 | No immediate gap. |
| V91-FIELD-01 CandidateFact governance | CandidateFact schema, field governance, revision events. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:589-661`. | V9.1 CandidateFact and FieldGovernanceDecision exist; central CaseField exists. Evidence: `backend/app/agent/v91/contracts.py:168-215`, `backend/app/agent/state/models.py:115-164`. | MATCH | P0 | Keep central field list authoritative. |
| V91-KNOWLEDGE-01 Tiered Knowledge Policy | Levels 0-4 with RAG optional/recommended/required. Hard design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:665-726`. | Current V9.1 policy has optional/required/disallowed but not exact level 0-4. RAG retrieval is structured and tenant-bound. Evidence: `backend/app/agent/v91/contracts.py:152-165`, `backend/app/agent/graph/nodes/evidence_node.py:126-170`, `backend/app/agent/services/real_rag.py:54-86`. | PARTIAL | P1 | Add explicit level labels to current policy trace or document current simplification. |
| V91-MEDIUM-01 Medium Intelligence | MediumProfile, MediumImpact, tab and chat behavior. Design principle/hard UX requirement. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:730-883`. | Medium node/service/UI exist, registry is small and evidence refs are empty in capability adapter. Evidence: `backend/app/services/medium_intelligence_service.py:102-106`, `frontend/src/components/dashboard/CaseScreen.tsx:1060-1165`. | PARTIAL | P2 | Add typed profile/impact/evidence refs and connect RAG/datasheet support. |
| V91-MATERIAL-01 Material Screening tiers, no percentages | Candidate tiers, no user-visible probabilities/percentages, evidence refs/blockers. Hard UX/safety requirement. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:887-1022`. | Material candidate projection has status/plausibility/internal score/evidence refs; UI renders plausibility labels and hypothesis wording, not scores. Evidence: `backend/app/api/v1/schemas/case_workspace.py:360-420`, `frontend/src/components/dashboard/SealCockpit.tsx:1020-1045`, `rg "plausibilityScore"` command output. | PARTIAL/MATCH | P1 | Main gap is source-backed card status, not visible scoring. |
| V91-QUESTION-01 One useful question | One Pflichtfrage, highest leverage. Hard behavior. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1120-1155`. | `max_questions_policy` hardcoded; tests assert projection. Evidence: `backend/app/agent/v91/contracts.py:229-238`, `backend/app/agent/tests/test_v91_question_plan.py:8-28`. | MATCH | P1 | Add E2E final-output tests, not only model tests. |
| V91-QUESTION-02 Explain why question matters | Question reason required. Hard behavior. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1120-1155`. | `QuestionNeed.why_it_matters` and strategy reason exist. Evidence: `backend/app/agent/v91/contracts.py:218-224`, `backend/app/agent/v91/question_planner.py:35-55`. | PARTIAL | P1 | Guard does not yet require visible question justification. |
| V91-COMM-01 QuestionPlan vs CommunicationPlan separation | Fachlich vs kommunikativ separate. Hard architecture. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1159-1186`. | Both models exist, but CommunicationPlan is largely built from QuestionPlan in final context. Evidence: `backend/app/agent/v91/contracts.py:229-257`, `backend/app/agent/v91/final_answer_context.py:80-91`. | PARTIAL | P1 | Create a real communication planner adapter with independent decisions. |
| V91-COMM-02 CommunicationPlan response moves | `response_moves`, depth, source disclosure, tab visibility, forbidden claims. Hard UX design. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1195-1252`. | Current `CommunicationPlan` has response_mode, depth, tab notice flag, question, reason, forbidden_claims only. Evidence: `backend/app/agent/v91/contracts.py:241-257`. | MISSING/PARTIAL | P1 | Add response moves as typed enum/list and test composer input. |
| V91-COMM-03 Answer-first rule | Answer latest user question before next question where applicable. Hard behavior. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1272-1296`. | `ResponsePolicy.answer_first` exists and final context sets true; enforcement is not explicit in V9.1 guard. Evidence: `backend/app/agent/v91/contracts.py:132-142`, `backend/app/agent/v91/final_answer_context.py:54-67`, `backend/app/agent/v91/communication_guard.py:8-32`. | PARTIAL | P1 | Add guard/test for missing answer-first when user asked a direct knowledge/side question. |
| V91-COMM-04 CommunicationGuard | Guard answer-first, one question, question reason, utility, tab spam, tone, conflict overwrite, length. Hard boundary. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1336-1367`. | V9.1 guard checks only question count, planned question, and internal artifacts. Separate communication guard checks claims/evidence/state contracts. Evidence: `backend/app/agent/v91/communication_guard.py:8-32`, `backend/app/agent/communication/guard.py:24-161`. | PARTIAL | P1 | Expand V9.1 guard with every target finding. |
| V91-CLAIM-01 Claim levels | Explicit claim levels; forbidden final/approval/compliance claims. Hard safety. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1371-1423`. | V9.2 `FinalAnswerContext.allowed_claim_level` and final guard exist. Evidence: `backend/app/agent/v92/contracts.py:123-163`, `backend/app/agent/v92/final_guard.py:90-227`. | MATCH | P0 | Keep current V9.2 guard as canonical. |
| V91-EVIDENCE-01 EvidenceGate | Source-backed claims require evidence. Hard safety. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1371-1423`. | Evidence node, V9.1 evidence gate, and material card validator exist. Evidence: `backend/app/agent/graph/nodes/evidence_node.py:309-437`, `backend/app/agent/v91/evidence_gate.py:18-36`, `backend/app/agent/domain/material_evidence_cards.py:167-230`. | MATCH/PARTIAL | P0 | Main remaining gap is live evidence-card persistence. |
| V91-SAFETY-01 Safety/Compliance/Human Review | Safety/compliance claims require evidence/review. Hard safety. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1427-1473`. | Tests block suitability/product/norm claims; final context requires review when technical context missing. Evidence: `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:55-119`, `backend/app/agent/v92/contracts.py:155-163`. | MATCH | P0 | Keep review state separate from wording. |
| V91-DOCUMENT-01 Documents as evidence, not instruction | Uploads/RAG snippets are evidence only. Hard safety. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1477-1508`. | RAG query is from AssertedState, not raw text; Paperless sync explicit; adapter no side effects. Evidence: `backend/app/agent/graph/nodes/evidence_node.py:11-19`, `backend/app/services/rag/paperless.py:208-216`, `backend/app/agent/domain/material_evidence_adapter.py:1-6`. | MATCH/PARTIAL | P1 | Add tests for document prompt-injection in Paperless/RAG evidence path. |
| V91-RFQ-01 RFQ as boundary/result, no dispatch | RFQ preview/result only, no automatic send. Hard boundary. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1887-1928`. | RFQ preview requires explicit intent; dispatch/external false; consent/export guarded; graph dispatch node has no external send. Evidence: `backend/app/api/v1/endpoints/rfq.py:61-87`, `backend/app/services/rfq_preview_service.py:494-500`, `backend/app/agent/graph/nodes/dispatch_node.py:1-9`. | EVOLVED_BEYOND_V91 | P0 | Keep no-dispatch default; add readiness from professional checks. |
| V91-EVAL-01 Acceptance criteria / golden conversations | Golden conversations, one-question, no overclaim, source-backed claims. Hard evaluation. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:2068-2118`, `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:2238-2257`. | V9.1 golden tests cover NBR knowledge, suitability restriction, approval block, RFQ boundary, weather redirect. Evidence: `backend/app/agent/tests/test_v91_golden_conversations.py:41-152`. Tests discovered: 291 tracked project tests by command output. | PARTIAL | P1 | Add visible-output golden conversation runner with communication metrics. |

## 5. Main Matches

1. Governed runtime topology matches the V9.1 architectural direction and is more concrete in V9.2. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:137-180`, `backend/app/agent/graph/topology.py:6-63`.
2. Technical draft streaming is blocked until final guard approval. Evidence: `backend/app/agent/v92/contracts.py:56-83`, `backend/app/agent/api/governed_runtime.py:182-194`, `backend/app/agent/api/streaming.py:111-150`, `frontend/src/app/api/bff/agent/chat/stream/route.ts:341-347`.
3. Field governance/state layering is strongly aligned. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:502-661`, `backend/app/agent/state/models.py:1-20`, `backend/app/agent/v91/contracts.py:168-215`.
4. Claim/evidence/final guard boundaries are implemented and tested. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1371-1423`, `backend/app/agent/v92/final_guard.py:17-78`, `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:55-119`.
5. RFQ is correctly bounded as preview/export/readiness, not automatic dispatch. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1887-1928`, `backend/app/services/rfq_preview_service.py:494-500`, `backend/app/services/rfq_preview_service.py:577-682`.

## 6. Main Partial Implementations

1. CommunicationPlan exists but is not yet the V9.1 communication control plane. It lacks response moves, explicit answer-first semantics, source disclosure mode, tab update policy, user-control emphasis, and response-depth behaviors. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1159-1332`, `backend/app/agent/v91/contracts.py:241-257`.
2. CommunicationGuard exists but only covers a subset of V9.1 rules. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1336-1367`, `backend/app/agent/v91/communication_guard.py:8-32`.
3. Semantic boundary exists as deterministic V9.2 routing plus V9.1 adapter, not as the exact rich V9.1 SemanticBoundary LLM/schema. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:309-423`, `backend/app/agent/v92/turn_boundary.py:190-295`, `backend/app/agent/v91/contracts.py:93-104`.
4. Medium Intelligence has service/UI support, but not the full V9.1 MediumProfile/MediumImpact evidence-bearing model. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:730-883`, `backend/app/services/medium_intelligence_service.py:61-95`, `frontend/src/components/dashboard/CaseScreen.tsx:1060-1165`.
5. RAG/Paperless and material evidence cards both exist, but there is no live production Paperless/RAG -> persisted Material Evidence Card flow. Evidence: `backend/app/services/rag/paperless.py:428-458`, `backend/app/agent/domain/material_evidence_cards.py:1-6`, `backend/app/agent/domain/material_evidence_adapter.py:1-6`.

## 7. Main Missing Gaps

1. A full V9.1 `CommunicationPlan` schema and planner are missing. Current code has a thin adapter model. Evidence: `backend/app/agent/v91/contracts.py:241-257`, `backend/app/agent/v91/final_answer_context.py:80-91`.
2. A full V9.1 `CommunicationGuard` is missing. Current V9.1 guard does not enforce answer-first, question justification, external utility refusal, tab spam, tone, conflict overwrite, or length. Evidence: `backend/app/agent/v91/communication_guard.py:8-32`.
3. Frontend cockpit evidence visibility is incomplete for compatibility evidence. Backend exposes compatibility/evidence metadata, while frontend check type/mapper drops those fields. Evidence: `backend/app/api/v1/schemas/case_workspace.py:648-684`, `frontend/src/lib/engineering/cockpitModel.ts:43-66`, `frontend/src/lib/mapping/workspace.ts:832-859`.
4. Golden conversation evaluation is not yet a full visible-output behavior suite. Existing V9.1 golden tests are policy/guard focused. Evidence: `backend/app/agent/tests/test_v91_golden_conversations.py:41-152`.
5. Live evidence-card ingestion/persistence is missing by design. The adapter explicitly says no Paperless/Qdrant/DB writes. Evidence: `backend/app/agent/domain/material_evidence_adapter.py:1-6`.

## 8. Evolved Beyond V9.1

1. V9.2 `TurnEnvelope`, `FinalAnswerContext`, `FinalGuardResult`, and dashboard contract are stronger and more explicit than V9.1. Evidence: `backend/app/agent/v92/contracts.py:56-120`, `backend/app/agent/v92/contracts.py:123-228`.
2. Technical streaming hardening is stronger than V9.1 text. Evidence: `backend/app/agent/api/governed_runtime.py:182-194`, `backend/app/agent/api/streaming.py:111-150`, `frontend/src/app/api/bff/agent/chat/stream/route.ts:341-430`.
3. Pressure role modeling is more concrete than V9.1: system pressure, pressure at seal, delta pressure, and ambiguous pressure are central fields. Evidence: `backend/app/domain/critical_field_contract.py:23-49`, `backend/app/agent/domain/checks_registry.py:289-365`.
4. RWDR professional checks are more concrete than V9.1: counterface, roughness, hardness, runout/eccentricity, lubrication, contamination. Evidence: `backend/app/agent/domain/checks_registry.py:367-593`, `backend/app/agent/tests/test_rwdr_professional_checks_patch5.py:68-198`.
5. Material evidence-card validation and dry-run adapter exceed the target concept. Evidence: `backend/app/agent/domain/material_evidence_cards.py:167-230`, `backend/app/agent/domain/material_evidence_adapter.py:1-70`, `backend/app/agent/tests/test_material_evidence_adapter_patch9.py:30-207`.
6. RFQ preview/export/consent/stale revision handling is more concrete than V9.1. Evidence: `backend/app/services/rfq_preview_service.py:506-550`, `backend/app/services/rfq_preview_service.py:577-682`.

These evolved designs should be promoted into the current implementation concept and any V9.1 successor doc. They should not be removed to match older naming.

## 9. Communication Governance Gap

Current state:

- V9.1 target makes communication a separate governed layer after QuestionPlan and before final composer/guards. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1159-1332`.
- Current `QuestionPlan` exists and is well-adapted from strategy. Evidence: `backend/app/agent/v91/question_planner.py:8-55`.
- Current `CommunicationPlan` exists but contains only response mode, depth, boundary/tab flags, primary question, reason, and forbidden claims. Evidence: `backend/app/agent/v91/contracts.py:241-257`.
- Current final context builds `CommunicationPlan` directly from `question_plan`, so communication is not yet an independent decision layer. Evidence: `backend/app/agent/v91/final_answer_context.py:80-91`.
- Current guard logic is distributed: V9.1 guard checks question count/planned question/internal artifacts, legacy communication guard checks claims/evidence/state proposals, reply composition trims multi-question replies, composer validates stream prefix and forbidden approval language, and clarification priority chooses next question. Evidence: `backend/app/agent/v91/communication_guard.py:8-32`, `backend/app/agent/communication/guard.py:24-161`, `backend/app/agent/runtime/reply_composition.py:330-389`, `backend/app/agent/communication/governed_answer_composer.py:432-440`, `backend/app/agent/runtime/clarification_priority.py:49-182`.

Missing pieces:

- No typed `response_moves` list in the V9.1 model. Evidence: `backend/app/agent/v91/contracts.py:241-257`.
- No central guard finding for missing answer-first behavior. Evidence: `backend/app/agent/v91/communication_guard.py:8-32`.
- No central guard finding for missing question justification. Evidence: `backend/app/agent/v91/communication_guard.py:8-32`.
- No central guard finding for external utility answers or tab spam. Evidence: `backend/app/agent/v91/communication_guard.py:8-32`.
- `DialogueDebt` exists but no strong resume/tone/side-topic policy was found in the audited guard path. Evidence: `backend/app/agent/v91/contracts.py:271-279`.

Why it matters:

V9.1's product promise is not only "safe output"; it is "experienced sealing engineer communication". If answer-first, one-question, and question-reason behavior depend on scattered salvage logic instead of a central plan/guard, future composer changes can regress product trust without violating the existing claim guard.

Recommended next audit/patch:

- Patch title: "V9.1 CommunicationPlan and CommunicationGuard hardening".
- Files likely affected: `backend/app/agent/v91/contracts.py`, `backend/app/agent/v91/final_answer_context.py`, `backend/app/agent/v91/communication_guard.py`, `backend/app/agent/communication/governed_answer_composer.py`, and focused tests under `backend/app/agent/tests`.
- Tests needed: answer-first, one-question, question justification, external utility redirect, tab spam, recovery after bad composer output, and no conflict-overwrite wording.
- Risk: medium, because guard strictness can force fallback replies; start with tests and explicit findings before changing composer behavior.

## 10. Semantic Boundary / Freedom Policy Gap

Current state:

- V9.1 target expects a rich SemanticBoundaryDecision and LLM Freedom/Red Flag decision. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:309-499`.
- Current V9.2 boundary is deterministic, centralized, and audit-friendly. Evidence: `backend/app/agent/v92/turn_boundary.py:1-7`, `backend/app/agent/v92/turn_boundary.py:190-295`.
- Current V9.1 adapter maps the current V7/V8 runtime decision into V9.1 vocabulary and explicitly states it is read-only. Evidence: `backend/app/agent/v91/semantic_boundary.py:47-61`.
- V9.1 semantic intent enum covers smalltalk, process/meta, knowledge, material knowledge/comparison, case intake, pending slot, side question, correction, suitability, RFQ/export, safety/compliance, utility, low signal, blocked, unclear. Evidence: `backend/app/agent/v91/contracts.py:12-29`.

Missing pieces:

- Current `SemanticBoundaryDecision` has a single intent and lacks the target's richer detected-intents list, user-emotion/low-signal details, external utility booleans, and explicit response path fields. Evidence: `backend/app/agent/v91/contracts.py:93-104`.
- Red flags are present but distributed across V9.1 adapter regexes, V9.2 turn boundary, composer checks, and final guard. Evidence: `backend/app/agent/v91/semantic_boundary.py:25-44`, `backend/app/agent/v91/semantic_boundary.py:279-337`, `backend/app/agent/v92/final_guard.py:17-78`.
- The V9.1 "Semantic Boundary LLM" role is not implemented as an LLM; this appears different by design, because V9.2 deliberately makes turn boundary deterministic. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:184-216`, `backend/app/agent/v92/turn_boundary.py:1-7`.

Recommended next audit/patch:

- Do not add a second semantic boundary runtime.
- Add a mapping/audit table from V9.1 intent classes to V9.2 `TurnRoute` plus V9.1 adapter intents.
- If missing product behavior is real, add deterministic fields for low-signal/frustration/utility instead of introducing a new LLM router.

## 11. Medium / Material / Evidence Gap

Current state:

- V9.1 target expects Medium Intelligence and Material Screening as bounded, evidence-aware product capabilities. Evidence: `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:730-1022`.
- Medium Intelligence exists as deterministic capability plus service and UI. Evidence: `backend/app/agent/graph/nodes/medium_intelligence_node.py:78-113`, `backend/app/services/medium_intelligence_service.py:61-95`, `frontend/src/components/dashboard/CaseScreen.tsx:1060-1165`.
- Material Intelligence exists as read-only candidate projection with safety boundary and candidate materials. Evidence: `backend/app/agent/services/material_intelligence.py:558-647`, `backend/app/api/v1/schemas/case_workspace.py:360-420`.
- Material/medium compatibility precheck is conservative and explicitly not final approval/release. Evidence: `backend/app/agent/domain/compatibility_precheck.py:1-5`, `backend/app/agent/domain/checks_registry.py:606-693`.
- Material evidence-card validator/adapter is stronger than the V9.1 target but dry-run only. Evidence: `backend/app/agent/domain/material_evidence_cards.py:1-6`, `backend/app/agent/domain/material_evidence_adapter.py:1-6`.

Missing pieces:

- MediumProfile/MediumImpact are not yet the primary typed state model. Evidence: target `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:730-883`; current service model `backend/app/services/medium_intelligence_service.py:8-55`.
- Material evidence from Paperless/RAG is not yet converted/persisted as governed Material Evidence Cards. Evidence: `backend/app/services/rag/paperless.py:428-458`, `backend/app/agent/domain/material_evidence_adapter.py:1-6`.
- Material candidate `plausibility_score` exists internally and tests assert it, but UI uses labels rather than visible scores. Evidence: `backend/app/agent/tests/test_material_intelligence.py:30-143`, `frontend/src/components/dashboard/SealCockpit.tsx:1020-1045`, `rg "plausibilityScore"` command output.

Recommended next audit/patch:

- First make cockpit evidence visible for compatibility/material checks.
- Then add a Paperless/RAG material evidence-card dry-run endpoint/report.
- Only after review, add persistence into governed evidence cards.

## 12. Frontend/Cockpit Evidence Visibility Gap

Backend fields available:

- Backend `EngineeringCheckResult` includes `compatibility_status`, `evidence_status`, `evidence_refs`, `evidence_summary`, `evidence_limitations`, and `final_approval_claim_allowed`. Evidence: `backend/app/api/v1/schemas/case_workspace.py:648-684`.
- Backend projection builds check results from the registered check registry. Evidence: `backend/app/api/v1/projections/case_workspace.py:1840-1856`.

Frontend mapping/rendering status:

- Frontend `EngineeringCheckResult` does not include compatibility/evidence metadata. Evidence: `frontend/src/lib/engineering/cockpitModel.ts:43-66`.
- Frontend workspace mapper drops those backend fields. Evidence: `frontend/src/lib/mapping/workspace.ts:832-859`.
- Frontend does render material candidates/evidence in the Material tab and RFQ evidence refs in RFQ pane, but generic cockpit checks lose the compatibility evidence context. Evidence: `frontend/src/components/dashboard/SealCockpit.tsx:1614-1665`, `frontend/src/components/dashboard/RfqPane.tsx:650-651`.

Recommended next audit/patch:

- Patch title: "Cockpit compatibility evidence visibility".
- Files likely affected: `frontend/src/lib/engineering/cockpitModel.ts`, `frontend/src/lib/mapping/workspace.ts`, `frontend/src/components/dashboard/SealCockpit.tsx`, and frontend tests.
- Tests needed: mapper preserves `compatibility_status`, `evidence_status`, `evidence_refs`, `evidence_summary`, `evidence_limitations`, and UI renders a compact evidence/status line without implying approval.
- Risk: low-to-medium; product copy must stay scoped to evidence status, not release claim.

## 13. Test/Evaluation Gap

Current tests:

- Tracked project test file count from command output: 291.
- V9.1 golden policy tests exist for NBR knowledge/no case mutation, FKM/water-glycol governed suitability, final approval block, RFQ no dispatch, and weather utility redirect. Evidence: `backend/app/agent/tests/test_v91_golden_conversations.py:41-152`.
- V9.1 question-plan tests exist. Evidence: `backend/app/agent/tests/test_v91_question_plan.py:8-48`.
- V9.1 final-answer guard tests cover planned single question, final suitability block, multi-question block, and unknown evidence ref. Evidence: `backend/app/agent/tests/test_v91_final_answer_guard.py:25-69`.
- V9.2 runtime contract tests cover no direct technical streaming, final guard blocks, nontechnical smalltalk, and governed runtime no visible composer streaming. Evidence: `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:34-80`, `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:193-278`.

Missing evaluation:

- No full V9.1 golden conversation runner was found that scores visible final answers across answer-first, one-question, question reason, no tab spam, no utility answer, no false RFQ/readiness, and evidence visibility in one artifact.
- Existing V9.1 golden tests are valuable but mostly assert policy objects and guard outcomes, not full streamed user-visible conversation behavior. Evidence: `backend/app/agent/tests/test_v91_golden_conversations.py:41-152`.

Recommended suite:

- Golden set 1: no-case knowledge answer first, no case mutation.
- Golden set 2: active case side question answer first, then resume one blocker.
- Golden set 3: direct suitability request, screening-only language, one evidence gap.
- Golden set 4: off-topic utility/weather redirect without utility answer.
- Golden set 5: RFQ send request, no dispatch, consent/export boundary.
- Golden set 6: material candidate cockpit evidence visible but no final approval claim.

## 14. Prioritized Tuning Roadmap

### P0 - Safety/correctness

1. Patch title: "Red flag provenance consolidation".
   - Why: red flags are present but distributed, which can make safety regressions harder to audit.
   - Likely files: `backend/app/agent/v91/semantic_boundary.py`, `backend/app/agent/v92/final_guard.py`, tests under `backend/app/agent/tests`.
   - Tests needed: suitability, compliance, RFQ dispatch, document claim, stale calculation.
   - Risk: medium; avoid weakening existing final guard.

2. Patch title: "Document prompt-injection evidence test".
   - Why: V9.1 says documents are evidence, never instructions.
   - Likely files: tests around `backend/app/agent/graph/nodes/evidence_node.py` and RAG upload/Paperless fixtures.
   - Tests needed: malicious document text cannot become instruction or case truth.
   - Risk: low.

### P1 - Product trust/UX

1. Patch title: "V9.1 CommunicationPlan and CommunicationGuard hardening".
   - Why: it is the main V9.1 product-critical gap.
   - Likely files: `backend/app/agent/v91/contracts.py`, `backend/app/agent/v91/final_answer_context.py`, `backend/app/agent/v91/communication_guard.py`, `backend/app/agent/tests/test_v91_final_answer_guard.py`, `backend/app/agent/tests/test_v91_golden_conversations.py`.
   - Tests needed: answer-first, one question, question reason, utility redirect, no tab spam, repair/recovery.
   - Risk: medium.

2. Patch title: "Cockpit compatibility evidence visibility".
   - Why: backend evidence status is lost before the cockpit can build trust.
   - Likely files: `frontend/src/lib/engineering/cockpitModel.ts`, `frontend/src/lib/mapping/workspace.ts`, `frontend/src/components/dashboard/SealCockpit.tsx`.
   - Tests needed: frontend mapper and render tests.
   - Risk: low-to-medium.

### P2 - Capability depth

1. Patch title: "Paperless/RAG material evidence-card dry-run endpoint".
   - Why: RAG/Paperless and card validator exist, but there is no governed operator-visible bridge.
   - Likely files: `backend/app/api/v1/endpoints/rag.py`, `backend/app/agent/domain/material_evidence_adapter.py`, tests under `backend/app/agent/tests`.
   - Tests needed: no persistence, safe provenance, invalid/downgraded card report.
   - Risk: medium because it touches evidence boundaries.

2. Patch title: "RFQ readiness from professional check groups".
   - Why: RFQ is well bounded, but readiness can become more professional by using RWDR/check metrics.
   - Likely files: `backend/app/agent/communication/rfq_intent.py`, `backend/app/services/rfq_preview_service.py`, check metric projections.
   - Tests needed: blocker mapping from professional checks to RFQ preview/open points.
   - Risk: medium.

### P3 - Maintainability/docs

1. Patch title: "Current implementation concept update for V9.2 evolved design".
   - Why: V9.1 target is superseded in important runtime details.
   - Likely files: `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md`, `docs/architecture/DEPRECATED_MAP.md`.
   - Tests needed: none beyond doc lint/static hygiene.
   - Risk: low.

2. Patch title: "Semantic boundary mapping doc".
   - Why: avoids adding a second runtime to satisfy old V9.1 naming.
   - Likely files: architecture docs and V9.1 adapter tests.
   - Tests needed: intent mapping tests.
   - Risk: low.

## 15. Recommended Next Step

Do the "V9.1 CommunicationPlan and CommunicationGuard hardening" patch next.

Reason: it is the largest gap against the V9.1 target, it is product-critical for trust, and it is small enough to patch without rewriting the governed runtime. Start by expanding the V9.1 `CommunicationPlan` model and `CommunicationGuard` findings while keeping existing final guard and V9.2 runtime contracts intact.

## 16. Appendix - Evidence Index

- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:11-50` - product identity.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:83-133` - non-goals and boundaries.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:137-180` - target runtime flow.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:184-305` - target LLM roles.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:309-499` - semantic boundary and freedom/red flags.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:502-726` - state, field governance, knowledge policy.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:730-1022` - medium and material intelligence.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1120-1367` - QuestionPlan, CommunicationPlan, CommunicationGuard.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1371-1508` - claim/evidence/document safety.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:1831-1928` - tabs and RFQ boundary.
- `docs/implementation/SEALAI_V9_1_FINAL_KONZEPT.md:2068-2257` - evaluation and acceptance criteria.
- `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:20-40` - IST summary strengths/gaps.
- `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:165-190` - IST conversation/runtime lifecycle.
- `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:191-240` - IST deterministic engine and cockpit.
- `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:241-284` - IST RAG/Paperless/evidence card gaps.
- `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:286-328` - IST RFQ/frontend gaps.
- `docs/architecture/SEALAI_CURRENT_IMPLEMENTATION_CONCEPT.md:329-382` - IST tests and tuning candidates.
- `backend/app/agent/graph/topology.py:6-63` and `backend/app/agent/graph/topology.py:301-365` - governed graph topology.
- `backend/app/agent/api/governed_runtime.py:182-194` - no visible composer streaming.
- `backend/app/agent/api/streaming.py:111-150` - backend transforms draft chunks into internal progress only.
- `frontend/src/app/api/bff/agent/chat/stream/route.ts:341-430` - BFF drops draft text and streams final state text once.
- `backend/app/agent/v92/contracts.py:56-120` and `backend/app/agent/v92/contracts.py:123-228` - V9.2 TurnEnvelope, final context, dashboard.
- `backend/app/agent/v92/turn_boundary.py:1-7` and `backend/app/agent/v92/turn_boundary.py:190-295` - deterministic turn boundary.
- `backend/app/agent/v92/final_guard.py:17-78` and `backend/app/agent/v92/final_guard.py:90-227` - final output guard.
- `backend/app/agent/v91/contracts.py:12-165`, `backend/app/agent/v91/contracts.py:168-293` - V9.1 policy contracts.
- `backend/app/agent/v91/semantic_boundary.py:47-61`, `backend/app/agent/v91/semantic_boundary.py:155-215`, `backend/app/agent/v91/semantic_boundary.py:279-337` - V9.1 adapter/freedom mapping.
- `backend/app/agent/v91/communication_guard.py:8-32` - V9.1 communication guard scope.
- `backend/app/agent/communication/guard.py:24-161` - older communication contract guard.
- `backend/app/agent/runtime/reply_composition.py:330-389` - reply salvage and one-question trimming.
- `backend/app/agent/communication/governed_answer_composer.py:105-147`, `backend/app/agent/communication/governed_answer_composer.py:432-440` - final composer and stream-prefix validation.
- `backend/app/agent/services/material_intelligence.py:558-647` - material candidate projection.
- `backend/app/api/v1/schemas/case_workspace.py:360-420` and `backend/app/api/v1/schemas/case_workspace.py:648-684` - material and engineering check schemas.
- `frontend/src/lib/engineering/cockpitModel.ts:43-66` and `frontend/src/lib/mapping/workspace.ts:832-859` - frontend evidence metadata drop.
- `frontend/src/components/dashboard/SealCockpit.tsx:1020-1045` and `frontend/src/components/dashboard/SealCockpit.tsx:1614-1665` - material tab rendering.
- `backend/app/agent/graph/nodes/evidence_node.py:1-32`, `backend/app/agent/graph/nodes/evidence_node.py:309-437` - structured evidence retrieval.
- `backend/app/agent/services/real_rag.py:54-86`, `backend/app/agent/services/real_rag.py:190-229` - tenant-safe 3-tier RAG.
- `backend/app/services/rag/paperless.py:152-216`, `backend/app/services/rag/paperless.py:428-458` - explicit/tagged Paperless sync and evidence refs.
- `backend/app/agent/domain/material_evidence_cards.py:1-6`, `backend/app/agent/domain/material_evidence_cards.py:167-230` - dry-run evidence-card validation.
- `backend/app/agent/domain/material_evidence_adapter.py:1-70` - dry-run adapter no side effects.
- `backend/app/agent/communication/rfq_intent.py:45-70`, `backend/app/agent/communication/rfq_intent.py:284-347` - RFQ readiness boundary.
- `backend/app/api/v1/endpoints/rfq.py:61-87`, `backend/app/api/v1/endpoints/rfq.py:229-260` - explicit RFQ preview and result contract.
- `backend/app/services/rfq_preview_service.py:494-550`, `backend/app/services/rfq_preview_service.py:577-682` - RFQ preview/consent/export boundaries.
- `backend/app/agent/tests/test_v91_golden_conversations.py:41-152` - V9.1 golden policy tests.
- `backend/app/agent/tests/test_v91_question_plan.py:8-48` - QuestionPlan tests.
- `backend/app/agent/tests/test_v91_final_answer_guard.py:25-69` - final answer guard tests.
- `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:34-80`, `backend/app/agent/tests/v92/test_v92_runtime_contracts.py:193-278` - V9.2 runtime/final guard tests.
