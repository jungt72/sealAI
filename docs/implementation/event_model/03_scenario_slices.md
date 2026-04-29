# Szenario-Slices

Format pro Slice: Trigger -> Command -> Event(s) -> View -> Given-When-Then. Jeder Slice ist ein kuenftiger Implementierungsanker, nicht automatisch ein eigener PR.

## S-CONV-001 Small Talk without Case

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | "Hallo", "Danke", Meta-Frage ohne technische Falldaten |
| Preconditions | Kein aktiver governed Case noetig |
| Command | `ClassifyConversationIntent`, `SelectResponseMode` |
| Events | `UserMessageReceived`, `ConversationIntentClassified`, `ResponseModeSelected` |
| Views | `ConversationFrontdoorView` |
| State writes | Conversation log optional; kein CaseRecord, keine CaseField-Mutation |
| Source/validation behavior | Kein technischer `source_type` noetig |
| Forbidden side effects | Keine Case-Erstellung, kein RAG, kein LangGraph-Full-Path |
| Given-When-Then tests | Given Greeting, When classified, Then no `CaseCreated` and response mode is `fast_responder` |
| Minimal implementation PR candidate | PR 3 Routing-Taxonomie |

## S-KNOW-001 General sealing knowledge question

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | "Was ist der Unterschied zwischen FKM und EPDM?" |
| Preconditions | Keine konkreten Betriebsdaten als Fallanforderung |
| Command | `AnswerKnowledgeQuestion`, `RunRAGLookup` |
| Events | `KnowledgeRAGLookupRequested`, `KnowledgeRAGAnswerFound` oder `KnowledgeRAGAnswerMissing` |
| Views | `KnowledgeAnswerView`, `SourceValidationBadgeView` |
| State writes | Optional transient/audit; kein CaseField |
| Source/validation behavior | RAG-Hit: `source_type=rag_verified`; Miss: keine erfundene Gewissheit |
| Forbidden side effects | Keine Case-Erstellung, keine finale Einsatzempfehlung |
| Given-When-Then tests | Given general question, When answered, Then no `CaseCreated` and source label is visible |
| Minimal implementation PR candidate | PR 6 Trust Layer |

## S-TRIAGE-001 Frustrated/vague leakage message

| Feld | Inhalt |
|---|---|
| User/Persona | Maintenance / Instandhaltung |
| Trigger | "Diese Dichtung leckt schon wieder." |
| Preconditions | Keine ausreichenden technischen Felder |
| Command | `ClassifyConversationIntent`, `SelectResponseMode` |
| Events | `ConversationIntentClassified`, `ResponseModeSelected` |
| Views | `ConversationFrontdoorView`, `DecisionUnderstandingView` |
| State writes | Optional Case erst, wenn Nutzer reale Fallbearbeitung bestaetigt oder technische Intake beginnt |
| Source/validation behavior | User-Aussage als `user_stated` Kandidat, falls governed Case beginnt |
| Forbidden side effects | Keine Schuldzuweisung, keine finale Ursache, keine 10-Fragen-Liste |
| Given-When-Then tests | Given vague leakage, When triaged, Then empathic response asks one key seal-type question |
| Minimal implementation PR candidate | PR 3 Routing-Taxonomie |

## S-CASE-001 New RFQ case creation

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | "Wir brauchen eine Dichtung fuer Medium X bei 120 C." |
| Preconditions | Reale Anwendung oder RFQ-Absicht erkannt |
| Command | `CreateOrUpdateSealingCase`, `AssignCaseType`, `ProposeCaseFieldCandidate` |
| Events | `CaseCreated`, `CaseTypeAssigned`, `CaseFieldCandidateProposed`, `SourceValidationStatusAssigned` |
| Views | `CaseWorkspaceProjection`, `OpenPointsView` |
| State writes | CaseRecord, revision/snapshot, candidate fields |
| Source/validation behavior | Chatwerte `source_type=user_stated`, `validation_status=candidate` bis Bestaetigung |
| Forbidden side effects | Keine RFQ ohne Revision, keine final suitability |
| Given-When-Then tests | Given RFQ-like input, When processed, Then `case_type=new_rfq` and fields are candidates |
| Minimal implementation PR candidate | PR 4 CaseType/ArtifactType |

## S-SEAL-001 Seal type normalization

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | "RWDR", "WDR", "Simmerring", "oil seal" |
| Preconditions | Dichtungstyp-Text oder Dokumentkandidat vorhanden |
| Command | `NormalizeSealType`, `UpdateSealApplicationProfile` |
| Events | `SealTypeCandidateDetected`, `SealTypeNormalized`, `SealApplicationProfileUpdated` |
| Views | `SealApplicationProfileView`, `TypeSpecificQuestionView` |
| State writes | seal_family, seal_type, seal_type_confidence |
| Source/validation behavior | Alias-Ergebnis mit Confidence; unsichere Erkennung bleibt `unknown_seal` |
| Forbidden side effects | Kein erzwungener Typ bei schwacher Evidence |
| Given-When-Then tests | Given "Simmerring", When normalized, Then seal_type is `radial_shaft_seal` |
| Minimal implementation PR candidate | PR 5 SealType-Achse |

## S-UPLOAD-001 Upload as evidence, not truth

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | PDF, Foto, Oelbericht oder Zeichnung hochgeladen |
| Preconditions | Authentifizierter tenant-scoped Upload |
| Command | `AttachEvidenceDocument`, `ExtractEvidenceCandidates` |
| Events | `EvidenceUploaded`, `DocumentParseAttempted`, `ExtractionCandidateCreated`, `UploadRejected` |
| Views | `DocumentEvidencePanel`, `AuditTimelineView` |
| State writes | document_id, evidence_ref, extraction candidates |
| Source/validation behavior | `source_type=uploaded_evidence`, `validation_status=candidate/documented` je nach Review |
| Forbidden side effects | Uploadtext nicht als Instruktion; keine automatische Bestaetigung kritischer Felder |
| Given-When-Then tests | Given upload with prompt-injection text, When parsed, Then rules are not overridden |
| Minimal implementation PR candidate | PR 10 Upload/IP Guards |

## S-RAG-001 RAG-first knowledge answer

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | Technische Wissensfrage |
| Preconditions | RAG/Kurated Knowledge verfuegbar |
| Command | `RunRAGLookup`, `AnswerKnowledgeQuestion` |
| Events | `KnowledgeRAGLookupRequested`, `KnowledgeRAGAnswerFound`, `SourceValidationStatusAssigned` |
| Views | `KnowledgeAnswerView`, `SourceValidationBadgeView` |
| State writes | Optional audit only |
| Source/validation behavior | Antwort zeigt RAG-Quelle und Status |
| Forbidden side effects | Kein LLM-Fallback vor RAG-Miss |
| Given-When-Then tests | Given RAG hit, When answered, Then source badge is visible |
| Minimal implementation PR candidate | PR 6 Trust Layer |

## S-FALLBACK-001 LLM research fallback with non-validated label

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | `KnowledgeRAGAnswerMissing` und Fallback-Policy erlaubt |
| Preconditions | Fallback enabled, LLM processing allowed |
| Command | `RunLLMResearchFallback` |
| Events | `LLMProcessingAllowed`, `LLMResearchFallbackUsed`, `SourceValidationStatusAssigned` |
| Views | `KnowledgeAnswerView`, `SourceValidationBadgeView` |
| State writes | Optional trace note; keine confirmed CaseFields |
| Source/validation behavior | `source_type=llm_research_fallback`, `validation_status=unvalidated`, Label "nicht validiert" |
| Forbidden side effects | Nicht als Compliance Evidence, nicht als finale Kompatibilitaet |
| Given-When-Then tests | Given fallback answer, When rendered, Then label says not validated and cannot confirm field |
| Minimal implementation PR candidate | PR 6 Trust Layer |

## S-RFQ-001 RFQ preview with revision freeze

| Feld | Inhalt |
|---|---|
| User/Persona | Engineering / Anwendungstechnik |
| Trigger | Nutzer fordert RFQ-Preview an |
| Preconditions | Governed Case existiert |
| Command | `GenerateRFQPreview` |
| Events | `RFQPreviewGenerated`, `RFQPreviewFrozenToCaseRevision` |
| Views | `RFQPreviewView`, `OpenPointsView` |
| State writes | artifact/rfq preview with `case_revision` |
| Source/validation behavior | Werte zeigen confirmed/documented/user_stated/inferred/calculated/conflicting/missing |
| Forbidden side effects | Kein Export, kein Dispatch, keine finale Freigabe |
| Given-When-Then tests | Given case revision 3, When preview generated, Then preview is frozen to revision 3 |
| Minimal implementation PR candidate | PR 7 RFQ v0.8.3 |

## S-CONSENT-001 RFQ consent and export gate

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | Nutzer will Export vorbereiten |
| Preconditions | Current RFQ Preview, nicht stale |
| Command | `GrantArtifactConsent`, `GenerateExport` |
| Events | `RFQConsentGranted`, `RFQConsentRejected`, `ExportGenerated`, `ExportBlocked`, `ExternalDispatchBlocked` |
| Views | `ConsentRequiredView`, `ExportReadyView` |
| State writes | Consent record, export artifact if allowed |
| Source/validation behavior | Consent bestaetigt keine technische Eignung |
| Forbidden side effects | Kein Export ohne no-final-release, open-points acknowledgement, export intent |
| Given-When-Then tests | Given open points and missing acknowledgement, When export requested, Then `ExportBlocked` |
| Minimal implementation PR candidate | PR 7 RFQ v0.8.3 |

## S-MATCH-001 Manufacturer fit matrix inside paid partner network

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | "Welche Hersteller passen?" |
| Preconditions | Case has enough profile data; partner capability data exists |
| Command | `FilterEligiblePartnerManufacturers`, `ScoreTechnicalFit`, `ComputeManufacturerFitMatrix` |
| Events | `ManufacturerFitRequested`, `PartnerCandidatesFiltered`, `ManufacturerFitComputed`, `PartnerNetworkDisclosureAttached` |
| Views | `ManufacturerFitMatrixView`, `PartnerDisclosureView` |
| State writes | fit matrix artifact tied to case revision |
| Source/validation behavior | Capabilities self-declared/verified sichtbar; gaps sichtbar |
| Forbidden side effects | Keine unpaid Partner anzeigen, keine paid score boost, kein Dispatch |
| Given-When-Then tests | Given unpaid perfect partner, When filtered, Then partner excluded |
| Minimal implementation PR candidate | PR 9 Matching Backend |

## S-MATCH-002 No suitable partner found

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | Matching angefragt, aber keine ausreichende technische Passung |
| Preconditions | Eligible partner set leer oder unter Fit-Schwelle |
| Command | `ComputeManufacturerFitMatrix` |
| Events | `NoSuitablePartnerFound`, `PartnerNetworkDisclosureAttached` |
| Views | `NoSuitablePartnerView`, `PartnerDisclosureView` |
| State writes | no-fit artifact/projection |
| Source/validation behavior | Missing requirements und gaps sichtbar |
| Forbidden side effects | Kein erzwungener Match, keine Full-Market-Aussage |
| Given-When-Then tests | Given no eligible fit, When matrix computed, Then no suitable partner view shown |
| Minimal implementation PR candidate | PR 9 Matching Backend |

## S-COMPAT-001 Compatibility inquiry for WDR/FKM/oil report/water/sodium/potassium

| Feld | Inhalt |
|---|---|
| User/Persona | Engineering / Anwendungstechnik |
| Trigger | WDR AS 75x95x10 DIN 3760, FKM, FDA, Oelbericht mit Wasser/Natrium/Kalium |
| Preconditions | Inquiry includes medium/report context |
| Command | `QualifyCompatibilityInquiry`, `ProposeCaseFieldCandidate`, `GenerateCustomerReplyDraft`, `GenerateInternalEngineeringNote` |
| Events | `CompatibilityInquiryCreated`, `ExtractionCandidateCreated`, `CompatibilityMatrixGenerated`, `CustomerReplyDraftGenerated`, `InternalEngineeringNoteGenerated` |
| Views | `CompatibilityMatrixView`, `CustomerReplyDraftView`, `InternalEngineeringNoteView` |
| State writes | case_type compatibility_inquiry plus optional complaint_case, candidates for oil values |
| Source/validation behavior | Oelwerte `uploaded_evidence` or `user_stated`; compatibility status not final |
| Forbidden side effects | Keine Grenzwert-Freigabe, keine FKM-Endfreigabe, keine FDA-Behauptung ohne Evidence |
| Given-When-Then tests | Given oil report values, When qualified, Then values are candidates and final compatibility is absent |
| Minimal implementation PR candidate | PR 11 Support/Compatibility |

## S-COMPLAINT-001 Complaint intake

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer oder Manufacturer Partner |
| Trigger | "Kundenreklamation", "Dichtung ausgefallen" |
| Preconditions | Complaint intent detected |
| Command | `CreateOrUpdateSealingCase`, `AssignCaseType`, `GenerateCustomerReplyDraft` |
| Events | `ComplaintIntakeCreated`, `CustomerReplyDraftGenerated` |
| Views | `CustomerReplyDraftView`, `OpenPointsView` |
| State writes | complaint artifact tied to revision |
| Source/validation behavior | Damage and operating data as candidates until confirmed/documented |
| Forbidden side effects | Keine Haftungszusage, keine finale Ursache |
| Given-When-Then tests | Given complaint, When draft generated, Then no liability admission appears |
| Minimal implementation PR candidate | PR 11 Support/Complaint |

## S-FAILURE-001 Failure analysis intake

| Feld | Inhalt |
|---|---|
| User/Persona | Maintenance / Engineering |
| Trigger | Fotos/Schadensbild/Leckagebeschreibung |
| Preconditions | Failure intent detected |
| Command | `GenerateFailureAnalysisIntake` |
| Events | `FailureAnalysisIntakeGenerated` |
| Views | `FailureAnalysisIntakeView`, `OpenPointsView` |
| State writes | failure artifact with damage_pattern, operating_hours candidates |
| Source/validation behavior | Evidence-linked damage observations; hypotheses labelled as hypotheses |
| Forbidden side effects | Keine finale Root Cause, keine Schuldzuweisung |
| Given-When-Then tests | Given failure description, When intake generated, Then root cause remains open |
| Minimal implementation PR candidate | PR 11 Support/Failure |

## S-REPLACE-001 Replacement/reorder with uncertain old part

| Feld | Inhalt |
|---|---|
| User/Persona | Maintenance / Distributor |
| Trigger | "Wir brauchen dasselbe Teil wieder" |
| Preconditions | Old part data partial |
| Command | `AssignCaseType`, `ProposeCaseFieldCandidate` |
| Events | `CaseTypeAssigned`, `CaseFieldCandidateProposed` |
| Views | `CaseWorkspaceProjection`, `OpenPointsView` |
| State writes | replacement candidates, old identifiers, uncertainty |
| Source/validation behavior | Alte Nummern `user_stated` or `documented`, identity needs confirmation |
| Forbidden side effects | Keine Preisgueltigkeit, keine sichere Identitaet vortaeuschen |
| Given-When-Then tests | Given old part number only, When processed, Then identity remains needs confirmation |
| Minimal implementation PR candidate | PR 4 CaseType |

## S-LEGACY-001 Unknown legacy part

| Feld | Inhalt |
|---|---|
| User/Persona | Maintenance |
| Trigger | "Wir haben nur das ausgebaute Teil / Foto" |
| Preconditions | Unclear seal type or dimensions |
| Command | `AssignCaseType`, `NormalizeSealType`, `AttachEvidenceDocument` |
| Events | `CaseTypeAssigned`, `SealTypeCandidateDetected`, `EvidenceUploaded` |
| Views | `SealApplicationProfileView`, `DocumentEvidencePanel`, `OpenPointsView` |
| State writes | unknown_legacy_part case_type, uncertain seal profile |
| Source/validation behavior | Foto/Dokument as evidence; identification candidate only |
| Forbidden side effects | Keine sichere Typ-/Materialidentifikation ohne Evidence |
| Given-When-Then tests | Given unclear photo, When processed, Then `unknown_seal` allowed |
| Minimal implementation PR candidate | PR 5 SealType |

## S-CERT-001 Compliance/certificate request

| Feld | Inhalt |
|---|---|
| User/Persona | User / Buyer |
| Trigger | "Reicht FDA?", "Brauche EU 1935/2004 Zertifikat" |
| Preconditions | Compliance/certificate intent |
| Command | `AssignCaseType`, `ProposeCaseFieldCandidate`, `GenerateInternalEngineeringNote` |
| Events | `CaseTypeAssigned`, `CaseFieldCandidateProposed`, `InternalEngineeringNoteGenerated` |
| Views | `InternalEngineeringNoteView`, `OpenPointsView`, `SourceValidationBadgeView` |
| State writes | certification_requirement, compliance_requirement candidates |
| Source/validation behavior | Compliance needs documented evidence; material family not certificate |
| Forbidden side effects | Keine Compliance-Freigabe ohne Nachweis |
| Given-When-Then tests | Given FDA material mention, When processed, Then compliance proof remains open |
| Minimal implementation PR candidate | PR 12 Compliance Guards |

## S-EMERGENCY-001 Emergency MRO triage

| Feld | Inhalt |
|---|---|
| User/Persona | Maintenance |
| Trigger | "Anlage steht", "Notfall", "brauchen heute Ersatz" |
| Preconditions | Emergency intent |
| Command | `ClassifyConversationIntent`, `AssignCaseType`, `SelectResponseMode` |
| Events | `ConversationIntentClassified`, `CaseTypeAssigned`, `ResponseModeSelected` |
| Views | `ConversationFrontdoorView`, `OpenPointsView` |
| State writes | urgency candidate/high, emergency_mro case_type if case begins |
| Source/validation behavior | Urgency `user_stated`; no technical shortcut |
| Forbidden side effects | Keine Bestellung, kein Dispatch, nur wichtigste naechste Frage |
| Given-When-Then tests | Given emergency, When triaged, Then only one most important question asked |
| Minimal implementation PR candidate | PR 4 CaseType |

## S-DRAWING-001 Drawing review shallow intake

| Feld | Inhalt |
|---|---|
| User/Persona | Engineering |
| Trigger | Zeichnung hochgeladen oder "Kann das gefertigt werden?" |
| Preconditions | Drawing-review intent |
| Command | `AssignCaseType`, `AttachEvidenceDocument` |
| Events | `CaseTypeAssigned`, `EvidenceUploaded`, `DocumentParseAttempted` |
| Views | `DocumentEvidencePanel`, `OpenPointsView` |
| State writes | drawing_review case_type, evidence_ref |
| Source/validation behavior | Zeichnung is evidence, manufacturability not final |
| Forbidden side effects | Keine finale Herstellbarkeitsfreigabe |
| Given-When-Then tests | Given drawing upload, When classified, Then shallow intake not final review |
| Minimal implementation PR candidate | PR 4 CaseType |

## S-QUOTE-001 Quote comparison shallow intake

| Feld | Inhalt |
|---|---|
| User/Persona | Buyer |
| Trigger | "Welche von drei Angeboten passt?" |
| Preconditions | Quote comparison intent |
| Command | `AssignCaseType`, `AttachEvidenceDocument` |
| Events | `CaseTypeAssigned`, `EvidenceUploaded` |
| Views | `OpenPointsView`, `DocumentEvidencePanel` |
| State writes | quote_comparison case_type, quote evidence refs |
| Source/validation behavior | Angebotsdaten documented/candidate; technical equivalence open |
| Forbidden side effects | Keine billigste-Option-Empfehlung, keine finale Gleichwertigkeit |
| Given-When-Then tests | Given multiple quotes, When intake, Then comparison remains evidence-based and non-final |
| Minimal implementation PR candidate | PR 4 CaseType |

## S-SUBST-001 Material substitution shallow intake

| Feld | Inhalt |
|---|---|
| User/Persona | Engineering / Buyer |
| Trigger | "PFAS-freie Alternative zu FKM/PTFE?" |
| Preconditions | Material substitution intent |
| Command | `AssignCaseType`, `ProposeCaseFieldCandidate`, `RunRAGLookup` |
| Events | `CaseTypeAssigned`, `CaseFieldCandidateProposed`, `KnowledgeRAGLookupRequested` |
| Views | `KnowledgeAnswerView`, `OpenPointsView` |
| State writes | material, medium, substitution requirement candidates |
| Source/validation behavior | Substitution risk as orientation; manufacturer review required |
| Forbidden side effects | Keine pauschale Materialfreigabe |
| Given-When-Then tests | Given substitution request, When answered, Then manufacturer review required is visible |
| Minimal implementation PR candidate | PR 6 Trust Layer |
