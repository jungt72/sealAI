# Field Origin Destination Matrix

Jedes Feld braucht Ursprung, Command, Event, State-Ziel, View-Ziel und eine explizite Grenze, wofuer es nie verwendet werden darf.

| Field | Origin | Command | Event | State / table / projection target | View / artifact destination | Validation requirement | Must never be used for |
|---|---|---|---|---|---|---|---|
| message_text | User message | `ClassifyConversationIntent` | `UserMessageReceived` | Conversation/session log | `ConversationFrontdoorView` | Tenant/user context | confirmed case truth |
| conversation_intent | Classifier | `ClassifyConversationIntent` | `ConversationIntentClassified` | Routing projection | `ConversationFrontdoorView` | Deterministic/LLM confidence tracked | engineering approval |
| response_mode | Router | `SelectResponseMode` | `ResponseModeSelected` | Runtime routing | `ConversationFrontdoorView` | Must match intent | case truth |
| case_creation_decision | Backend router | `CreateOrUpdateSealingCase` | `CaseCreated` or no event | Case service | `CaseWorkspaceProjection` | No case for small talk/general knowledge | forced persistence |
| case_type | Router/user scenario | `AssignCaseType` | `CaseTypeAssigned` | CaseRecord/payload/projection | `CaseWorkspaceProjection` | Confidence and multi-tag support | seal type |
| case_revision | Case governor | `CreateOrUpdateSealingCase` | `CaseCreated`, field events | CaseRecord/snapshot | RFQ/artifact views | Monotonic per case | stale artifact reuse |
| urgency | User statement/context | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField | `OpenPointsView` | user_stated until confirmed | automatic dispatch |
| side / buyer_or_manufacturer_context | User/org context | `AssignCaseType` | `CaseTypeAssigned` | Case projection | `DecisionUnderstandingView` | Tenant/role checked | cross-tenant visibility |
| seal_family | Seal normalizer | `NormalizeSealType` | `SealTypeNormalized` | SealApplicationProfile | `SealApplicationProfileView` | Confidence required | final suitability |
| seal_type | User/doc alias | `NormalizeSealType` | `SealTypeNormalized` | SealApplicationProfile | `TypeSpecificQuestionView` | Alias confidence; unknown allowed | forced type-specific truth |
| seal_type_confidence | Normalizer | `NormalizeSealType` | `SealTypeNormalized` | SealApplicationProfile | `SealApplicationProfileView` | Numeric/band confidence | hiding uncertainty |
| application_domain | User/doc/RAG | `UpdateSealApplicationProfile` | `SealApplicationProfileUpdated` | CaseField/profile | `DecisionUnderstandingView` | source_type and validation_status | compliance proof |
| motion_type | User/doc/inferred | `UpdateSealApplicationProfile` | `SealApplicationProfileUpdated` | CaseField/profile | `TypeSpecificQuestionView` | confirmed or candidate | final design release |
| dimensions | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField EngineeringValue | `RFQPreviewView` | Unit normalization, evidence refs | final manufacturing approval |
| standard_refs | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField | `RFQPreviewView` | Documented or user_stated | compliance proof |
| medium | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField | `DecisionUnderstandingView`, RFQ | source_type, status | final compatibility |
| temperature | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | EngineeringValue | RFQ/open points | unit normalized | final suitability |
| pressure | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | EngineeringValue | RFQ/open points | unit normalized | final design release |
| speed | User/doc/calculation input | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | EngineeringValue | RFQ/profile | unit normalized | LLM calculation authority |
| movement | User/doc | `UpdateSealApplicationProfile` | `SealApplicationProfileUpdated` | Profile/CaseField | `SealApplicationProfileView` | source/status | final seal selection |
| material | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField | RFQ/compatibility | Material family vs compound separated | final material recommendation |
| certification_requirement | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField | RFQ/compliance note | Evidence required | final compliance proof |
| compliance_requirement | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField | Compliance checklist | Evidence required | compliance approval |
| damage_pattern | User/photo/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | CaseField/artifact | `FailureAnalysisIntakeView` | Evidence-linked candidate | final root cause |
| operating_hours | User/doc | `ProposeCaseFieldCandidate` | `CaseFieldCandidateProposed` | EngineeringValue | Failure intake | unit normalized/status | liability decision |
| oil_analysis_values | Uploaded report/user | `ExtractEvidenceCandidates` | `ExtractionCandidateCreated` | Extraction candidates/CaseField candidates | `CompatibilityMatrixView` | Evidence refs, units, method | final compatibility |
| water_value | Uploaded report/user | `ExtractEvidenceCandidates` | `ExtractionCandidateCreated` | EngineeringValue candidate | `CompatibilityMatrixView` | unit/method/source | Grenzwert-Freigabe |
| sodium_value | Uploaded report/user | `ExtractEvidenceCandidates` | `ExtractionCandidateCreated` | EngineeringValue candidate | `CompatibilityMatrixView` | unit/method/source | final material release |
| potassium_value | Uploaded report/user | `ExtractEvidenceCandidates` | `ExtractionCandidateCreated` | EngineeringValue candidate | `CompatibilityMatrixView` | unit/method/source | final compatibility |
| document_id | Upload endpoint | `AttachEvidenceDocument` | `EvidenceUploaded` | Document table/storage metadata | `DocumentEvidencePanel` | Tenant ownership | cross-tenant access |
| evidence_ref | Upload/extraction | `AttachEvidenceDocument` | `EvidenceUploaded` | Evidence link table/json | RFQ/artifacts | Tenant and visibility checked | external sharing without consent |
| extraction_candidate | Parser/LLM if allowed | `ExtractEvidenceCandidates` | `ExtractionCandidateCreated` | Candidate table/json | Evidence panel/case candidate view | Never auto-confirm critical values | confirmed case truth |
| uploaded_filename | User upload | `AttachEvidenceDocument` | `EvidenceUploaded` | Document metadata | `DocumentEvidencePanel` | Sanitized/redacted | path disclosure |
| source_type | Governor | `AssignSourceValidationStatus` | `SourceValidationStatusAssigned` | Field envelope/artifact | `SourceValidationBadgeView` | Required for technical info | hidden trust |
| validation_status | Governor | `AssignSourceValidationStatus` | `SourceValidationStatusAssigned` | Field envelope/artifact | `SourceValidationBadgeView` | Required for technical info | final truth if candidate |
| rag_query | Knowledge service | `RunRAGLookup` | `KnowledgeRAGLookupRequested` | Audit/transient | `KnowledgeAnswerView` | Tenant/knowledge scope | secret leakage |
| rag_answer | RAG system | `AnswerKnowledgeQuestion` | `KnowledgeRAGAnswerFound` | Knowledge response | `KnowledgeAnswerView` | Source refs/status | final case field |
| rag_miss | RAG system | `RunRAGLookup` | `KnowledgeRAGAnswerMissing` | Knowledge response/audit | `KnowledgeAnswerView` | Explicit miss | hallucinated certainty |
| llm_fallback_answer | LLM fallback | `RunLLMResearchFallback` | `LLMResearchFallbackUsed` | Trace/candidate note | `KnowledgeAnswerView` | `unvalidated` label | compliance evidence |
| fallback_label | Fallback renderer | `RunLLMResearchFallback` | `SourceValidationStatusAssigned` | Response metadata | `SourceValidationBadgeView` | Visible "nicht validiert" | hidden source |
| rfq_preview_id | RFQ service | `GenerateRFQPreview` | `RFQPreviewGenerated` | RFQ/artifact table | `RFQPreviewView` | Tenant/case revision | dispatch id |
| rfq_case_revision | RFQ service | `GenerateRFQPreview` | `RFQPreviewFrozenToCaseRevision` | RFQ/artifact table | `RFQPreviewView` | Must equal frozen revision | stale export |
| open_points | Governor/readiness | `GenerateRFQPreview` | `RFQPreviewGenerated` | Projection/artifact | RFQ/open points | Derived backend-side | hidden risk |
| consent_no_final_release | User checkbox/API | `GrantArtifactConsent` | `RFQConsentGranted` or rejected | Consent record | `ConsentRequiredView` | Required true | export if false |
| consent_open_points_understood | User checkbox/API | `GrantArtifactConsent` | `RFQConsentGranted` or rejected | Consent record | `ConsentRequiredView` | Required if open points | export if false |
| consent_export_intent | User checkbox/API | `GrantArtifactConsent` | `RFQConsentGranted` or rejected | Consent record | `ConsentRequiredView` | Required true | silent sharing |
| export_allowed | Consent gate | `GenerateExport` | `ExportGenerated` or `ExportBlocked` | Export artifact/status | `ExportReadyView` | Current preview and consent | automatic dispatch |
| partner_id | Partner registry | `FilterEligiblePartnerManufacturers` | `PartnerCandidatesFiltered` | Matching projection | `ManufacturerFitMatrixView` | active_paid required | unpaid inclusion |
| active_paid | Admin/partner status | `FilterEligiblePartnerManufacturers` | `PartnerCandidatesFiltered` | Partner capability table/config | `PartnerDisclosureView` | Eligibility only | fit score boost |
| capability_match | Capability service | `ScoreTechnicalFit` | `ManufacturerFitComputed` | Fit matrix | `ManufacturerFitMatrixView` | capability evidence level | paid ranking |
| fit_score | Fit scoring | `ScoreTechnicalFit` | `ManufacturerFitComputed` | Fit matrix | `ManufacturerFitMatrixView` | Payment-independent | sponsorship ranking |
| fit_reasons | Fit scoring | `ScoreTechnicalFit` | `ManufacturerFitComputed` | Fit matrix | `ManufacturerFitMatrixView` | Explainable reasons | hidden ranking |
| gaps | Fit/readiness | `ScoreTechnicalFit` | `ManufacturerFitComputed` | Fit matrix | `ManufacturerFitMatrixView` | Missing info visible | forced match |
| no_suitable_partner | Matching service | `ComputeManufacturerFitMatrix` | `NoSuitablePartnerFound` | Matching projection | `NoSuitablePartnerView` | Based on threshold/gaps | full-market claim |
| partner_network_disclosure | Matching service | `ComputeManufacturerFitMatrix` | `PartnerNetworkDisclosureAttached` | Matching artifact/projection | `PartnerDisclosureView` | Always visible | hidden lead selling |
| artifact_type | Scenario/artifact service | `GenerateRFQPreview` etc. | Artifact generated event | Artifact table/json | Artifact views | Stable enum/registry | generic blob truth |
| artifact_id | Artifact service | Artifact command | Artifact generated event | Artifact table/json | Artifact views | Tenant/case checked | cross-tenant access |
| artifact_case_revision | Artifact service | Artifact command | Artifact generated event | Artifact table/json | Artifact views | Revision frozen | stale consent/export |
| artifact_status | Artifact service | `MarkArtifactStale` | `ArtifactMarkedStale` | Artifact status | Artifact views | current/stale/superseded | current truth if stale |
| stale_status | Stale checker | `MarkArtifactStale` | `ArtifactMarkedStale` | Artifact projection | RFQ/artifact views | Case revision comparison | export if stale |
