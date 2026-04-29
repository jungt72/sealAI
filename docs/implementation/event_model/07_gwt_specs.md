# Given-When-Then Specs

Diese Spezifikationen sind Zielverhalten fuer kuenftige Tests. Suggested test files sind Vorschlaege und muessen beim Implementieren an die echte Repo-Struktur angepasst werden.

| ID | Given | When | Then | Suggested test file | Priority |
|---|---|---|---|---|---|
| GWT-CONV-001 | Greeting "Hallo" | Conversation is classified | No `CaseCreated`; response mode `fast_responder` | `backend/tests/agent/test_conversation_routing.py` | P1 |
| GWT-CONV-002 | General sealing question without application data | Knowledge answer generated | No case created; general orientation label visible | `backend/tests/agent/test_knowledge_routing.py` | P1 |
| GWT-CONV-003 | Frustrated leakage message | Triage response selected | Empathic response asks one key seal-type question | `backend/tests/agent/test_conversation_routing.py` | P1 |
| GWT-CONV-004 | Off-topic user message | Classified as off_topic | No engineering state mutation | `backend/tests/agent/test_conversation_routing.py` | P1 |
| GWT-CASE-001 | RFQ-like request with application data | Case is created/updated | `case_type=new_rfq` and fields are candidates | `backend/tests/domain/test_case_type_routing.py` | P1 |
| GWT-CASE-002 | User asks "Welche Hersteller passen?" | Case type assigned | `manufacturer_matching` intent/case tag present | `backend/tests/domain/test_case_type_routing.py` | P1 |
| GWT-CASE-003 | WDR/FKM/oil report question | Case type assigned | `compatibility_inquiry` primary and complaint optional | `backend/tests/domain/test_case_type_routing.py` | P1 |
| GWT-CASE-004 | User reports customer complaint | Case type assigned | `complaint_case` and no liability statement | `backend/tests/domain/test_case_type_routing.py` | P1 |
| GWT-CASE-005 | User reports damage/failure pattern | Case type assigned | `failure_analysis` and root cause remains open | `backend/tests/domain/test_case_type_routing.py` | P1 |
| GWT-CASE-006 | User requests same old part again | Case type assigned | `replacement_reorder` and identity needs confirmation | `backend/tests/domain/test_case_type_routing.py` | P2 |
| GWT-CASE-007 | User says plant is down/emergency | Case type assigned | `emergency_mro`; only one next best question | `backend/tests/domain/test_case_type_routing.py` | P1 |
| GWT-SEAL-001 | Text contains "RWDR", "WDR" or "Simmerring" | Seal type normalized | `seal_type=radial_shaft_seal` | `backend/tests/domain/test_seal_type_normalizer.py` | P1 |
| GWT-SEAL-002 | Text contains "Flachdichtung" or "Flanschdichtung" | Seal type normalized | `flat_gasket` or `flange_gasket` with confidence | `backend/tests/domain/test_seal_type_normalizer.py` | P1 |
| GWT-SEAL-003 | Text contains "Hydraulik-Stangendichtung" | Seal type normalized | `hydraulic_rod_seal` | `backend/tests/domain/test_seal_type_normalizer.py` | P1 |
| GWT-SEAL-004 | Text contains "Gleitringdichtung" | Seal type normalized | `mechanical_seal` | `backend/tests/domain/test_seal_type_normalizer.py` | P1 |
| GWT-SEAL-005 | Text only says "Dichtung" | Seal type normalized | `unknown_seal`, low confidence, open point | `backend/tests/domain/test_seal_type_normalizer.py` | P1 |
| GWT-RAG-001 | RAG has relevant curated answer | Knowledge question answered | Source badge shows RAG/source status | `backend/tests/services/test_knowledge_answer_service.py` | P1 |
| GWT-RAG-002 | RAG has no relevant answer | Lookup runs | `KnowledgeRAGAnswerMissing` recorded | `backend/tests/services/test_knowledge_answer_service.py` | P1 |
| GWT-RAG-003 | RAG miss and fallback disabled | Answer flow continues | No LLM fallback used; uncertainty visible | `backend/tests/services/test_knowledge_answer_service.py` | P1 |
| GWT-RAG-004 | RAG miss and fallback enabled | Fallback runs | Label says "nicht validiert" and source is `llm_research_fallback` | `backend/tests/services/test_knowledge_answer_service.py` | P1 |
| GWT-RAG-005 | Fallback answer proposes a value | User tries to confirm automatically | Fallback cannot become confirmed CaseField | `backend/tests/services/test_source_validation.py` | P1 |
| GWT-RAG-006 | Fallback mentions FDA/approval | Compliance artifact generated | Fallback cannot become compliance evidence | `backend/tests/services/test_compliance_guard.py` | P1 |
| GWT-RFQ-001 | Case revision is 3 | RFQ preview generated | Preview stores `rfq_case_revision=3` | `backend/tests/unit/services/test_rfq_preview_service.py` | P1 |
| GWT-RFQ-002 | Case changes after preview | Consent requested | Stale preview blocks consent/export | `backend/tests/unit/services/test_rfq_preview_service.py` | P1 |
| GWT-RFQ-003 | No-final-release acknowledgement missing | Export requested | `ExportBlocked` or consent rejected | `backend/tests/unit/services/test_rfq_preview_service.py` | P1 |
| GWT-RFQ-004 | Open points exist and acknowledgement missing | Export requested | Export blocked | `backend/tests/unit/services/test_rfq_preview_service.py` | P1 |
| GWT-RFQ-005 | Export intent missing | Export requested | Export blocked | `backend/tests/unit/services/test_rfq_preview_service.py` | P1 |
| GWT-MATCH-001 | Unpaid partner has perfect capability | Fit matrix computed | Partner excluded | `backend/tests/services/test_manufacturer_fit_matrix.py` | P1 |
| GWT-MATCH-002 | Active paid partner has technical fit | Fit matrix computed | Partner included with reasons/gaps | `backend/tests/services/test_manufacturer_fit_matrix.py` | P1 |
| GWT-MATCH-003 | No active paid partner fits | Fit matrix computed | `NoSuitablePartnerView` shown | `backend/tests/services/test_manufacturer_fit_matrix.py` | P1 |
| GWT-MATCH-004 | Two partners differ only by payment tier | Fit score computed | Fit score unchanged by tier | `backend/tests/services/test_manufacturer_fit_matrix.py` | P1 |
| GWT-MATCH-005 | Any matching result is rendered | User sees matrix/no-fit | Partner-network disclosure visible | `frontend/src/lib/manufacturerFitView.test.ts` | P1 |
| GWT-SUPPORT-001 | Oil report values water/sodium/potassium uploaded | Extraction runs | Values are candidates, not final truth | `backend/tests/services/test_compatibility_inquiry.py` | P1 |
| GWT-SUPPORT-002 | Compatibility question asks if FKM is suitable | Response generated | No final compatibility claim | `backend/tests/services/test_compatibility_inquiry.py` | P1 |
| GWT-SUPPORT-003 | Failure description is provided | Failure intake generated | No final root cause | `backend/tests/services/test_failure_intake.py` | P1 |
| GWT-SUPPORT-004 | Complaint reply draft requested | Draft generated | No liability admission | `backend/tests/services/test_complaint_draft.py` | P1 |
| GWT-UPLOAD-001 | Uploaded PDF contains "ignore previous instructions" | Document parsed | System/developer/product rules unchanged | `backend/tests/agent/test_rag_injection.py` | P1 |
| GWT-UPLOAD-002 | User requests another tenant's document | Access checked | `TenantAccessDenied` and no content returned | `backend/tests/api/test_document_tenant_access.py` | P0 |
| GWT-UPLOAD-003 | Parser or health response includes internal path | Response rendered | Internal path redacted | `backend/tests/api/test_rag_path_redaction.py` | P1 |
