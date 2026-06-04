# Command / Event / View Catalog

Dieser Katalog benennt die fachlichen Bausteine fuer v0.8.3. Er ist kein Implementierungszwang fuer neue Infrastruktur; Commands koennen bestehende Services kapseln, Events koennen vorhandene Mutation-/Audit-Events erweitern, Views koennen Projektionen oder DTOs sein.

## A. Conversation

| Typ | Namen |
|---|---|
| Commands | `ClassifyConversationIntent`, `SelectResponseMode` |
| Events | `UserMessageReceived`, `ConversationIntentClassified`, `ResponseModeSelected` |
| Views | `ConversationFrontdoorView`, `DecisionUnderstandingView` |
| Zweck | Small Talk, Knowledge, governed Inquiry, Support, Complaint und Off-topic sauber trennen. |
| Verbotene Side Effects | Kein Case fuer Greeting/Thanks/Meta; keine persistente Engineering Truth aus Chattext. |

## B. Case

| Typ | Namen |
|---|---|
| Commands | `CreateOrUpdateSealingCase`, `AssignCaseType`, `ProposeCaseFieldCandidate`, `ConfirmCaseField` |
| Events | `CaseCreated`, `CaseTypeAssigned`, `CaseFieldCandidateProposed`, `CaseFieldConfirmed`, `SourceValidationStatusAssigned` |
| Views | `CaseWorkspaceProjection`, `OpenPointsView`, `DecisionUnderstandingView`, `AuditTimelineView` |
| Zweck | Governed Case State, Revision, Feldstatus, offene Punkte und Risiken abbilden. |
| Verbotene Side Effects | LLM darf Felder nicht direkt bestaetigen; Frontend darf Readiness nicht autoritativ berechnen. |

## C. SealType

| Typ | Namen |
|---|---|
| Commands | `NormalizeSealType`, `UpdateSealApplicationProfile` |
| Events | `SealTypeCandidateDetected`, `SealTypeNormalized`, `SealApplicationProfileUpdated` |
| Views | `SealApplicationProfileView`, `TypeSpecificQuestionView` |
| Zweck | Szenario und Dichtungstyp orthogonal halten; Alias-Normalisierung und type-specific Intake ermoeglichen. |
| Verbotene Side Effects | Unsicheren Dichtungstyp nicht vortaeuschen; keine falsche Frageprofile fuer andere SealTypes. |

## D. Knowledge / RAG / Fallback

| Typ | Namen |
|---|---|
| Commands | `AnswerKnowledgeQuestion`, `RunRAGLookup`, `RunLLMResearchFallback` |
| Events | `KnowledgeRAGLookupRequested`, `KnowledgeRAGAnswerFound`, `KnowledgeRAGAnswerMissing`, `LLMResearchFallbackUsed`, `SourceValidationStatusAssigned` |
| Views | `KnowledgeAnswerView`, `SourceValidationBadgeView` |
| Zweck | RAG-first Antworten, sichtbarer RAG-Miss, optionaler nicht validierter Fallback. |
| Verbotene Side Effects | Fallback nicht als bestaetigtes CaseField, Compliance Evidence oder finale Kompatibilitaet speichern. |

## E. Upload / Evidence

| Typ | Namen |
|---|---|
| Commands | `AttachEvidenceDocument`, `ExtractEvidenceCandidates` |
| Events | `EvidenceUploaded`, `DocumentParseAttempted`, `ExtractionCandidateCreated`, `UploadRejected`, `SourceValidationStatusAssigned` |
| Views | `DocumentEvidencePanel`, `SourceValidationBadgeView`, `AuditTimelineView` |
| Zweck | Uploads als Evidence und Kandidaten behandeln, nicht als Instruktion oder Wahrheit. |
| Verbotene Side Effects | Kein Upload-Text darf Systemregeln ueberschreiben; keine automatische Feldbestaetigung kritischer Werte. |

## F. Artifact

| Typ | Namen |
|---|---|
| Commands | `GenerateCustomerReplyDraft`, `GenerateInternalEngineeringNote`, `GenerateFailureAnalysisIntake`, `MarkArtifactStale` |
| Events | `CustomerReplyDraftGenerated`, `InternalEngineeringNoteGenerated`, `FailureAnalysisIntakeGenerated`, `ArtifactMarkedStale` |
| Views | `CustomerReplyDraftView`, `InternalEngineeringNoteView`, `FailureAnalysisIntakeView`, `AuditTimelineView` |
| Zweck | Szenario-Artefakte an Case und `case_revision` binden. |
| Verbotene Side Effects | Kein Artefakt darf finale Freigabe, Haftungszusage oder finale Root Cause enthalten. |

## G. RFQ / Consent / Export

| Typ | Namen |
|---|---|
| Commands | `GenerateRFQPreview`, `GrantArtifactConsent`, `GenerateExport`, `MarkArtifactStale` |
| Events | `RFQPreviewGenerated`, `RFQPreviewFrozenToCaseRevision`, `RFQConsentGranted`, `RFQConsentRejected`, `ExportGenerated`, `ExportBlocked`, `ArtifactMarkedStale`, `ExternalDispatchBlocked` |
| Views | `RFQPreviewView`, `ConsentRequiredView`, `ExportReadyView`, `OpenPointsView` |
| Zweck | Herstellerpruefbare RFQ-Preview mit Revision-Freeze, Stale-Schutz und explizitem Export-Gate. |
| Verbotene Side Effects | Kein Export ohne Consent; kein "An Hersteller senden"; kein automatischer Dispatch. |

## H. Manufacturer Matching

| Typ | Namen |
|---|---|
| Commands | `ComputeManufacturerFitMatrix`, `FilterEligiblePartnerManufacturers`, `ScoreTechnicalFit` |
| Events | `ManufacturerFitRequested`, `PartnerCandidatesFiltered`, `ManufacturerFitComputed`, `NoSuitablePartnerFound`, `PartnerNetworkDisclosureAttached` |
| Views | `ManufacturerFitMatrixView`, `PartnerDisclosureView`, `NoSuitablePartnerView` |
| Zweck | Technischen Fit innerhalb aktiver zahlender SeaLAI-Partner transparent darstellen. |
| Verbotene Side Effects | Keine Full-Market-Neutralitaet, kein paid ranking boost, kein erzwungener Partner bei schlechter Datenlage. |

## I. Support / Compatibility / Complaint / Failure

| Typ | Namen |
|---|---|
| Commands | `QualifyCompatibilityInquiry`, `GenerateCustomerReplyDraft`, `GenerateInternalEngineeringNote`, `GenerateFailureAnalysisIntake` |
| Events | `CompatibilityInquiryCreated`, `CompatibilityMatrixGenerated`, `ComplaintIntakeCreated`, `FailureAnalysisIntakeGenerated`, `CustomerReplyDraftGenerated`, `InternalEngineeringNoteGenerated` |
| Views | `CompatibilityMatrixView`, `CustomerReplyDraftView`, `InternalEngineeringNoteView`, `FailureAnalysisIntakeView`, `DecisionUnderstandingView` |
| Zweck | Technische Anfragen, Reklamationen und Ausfaelle strukturieren, ohne finale Bewertung. |
| Verbotene Side Effects | Keine finale Kompatibilitaet, keine finale Ursache, keine Haftungsanerkennung. |

## J. Security / Audit

| Typ | Namen |
|---|---|
| Commands | `CheckTenantAccess`, `ApproveDocumentVisibility`, `BlockExternalDispatch`, `AssignSourceValidationStatus` |
| Events | `TenantAccessChecked`, `TenantAccessDenied`, `DocumentVisibilityApproved`, `DocumentVisibilityRejected`, `ExternalDispatchBlocked`, `UploadRejected`, `SourceValidationStatusAssigned` |
| Views | `AuditTimelineView`, `DocumentEvidencePanel`, `SourceValidationBadgeView` |
| Zweck | Tenant-Grenzen, Dokumentfreigabe, Pfadredaktion, Consent und Audit nachvollziehbar machen. |
| Verbotene Side Effects | Keine Cross-Tenant-Leaks, keine Secrets, keine internen Pfade in User Views. |

## K. Automation / Todo

| Typ | Namen |
|---|---|
| Commands | `ExtractEvidenceCandidates`, `RunRAGLookup`, `RunLLMResearchFallback`, `ComputeManufacturerFitMatrix`, `GenerateExport`, `MarkArtifactStale` |
| Events | `DocumentParseAttempted`, `ExtractionCandidateCreated`, `KnowledgeRAGLookupRequested`, `LLMResearchFallbackUsed`, `ManufacturerFitComputed`, `ExportGenerated`, `ExportBlocked`, `ArtifactMarkedStale` |
| Views | `AutomationTodoView`, `DocumentExtractionTodoView`, `RAGLookupTodoView`, `FallbackResearchTodoView`, `ManufacturerFitTodoView`, `ExportTodoView`, `StaleArtifactCheckTodoView` |
| Zweck | Worker-Ausfuehrung explizit und pruefbar machen. |
| Verbotene Side Effects | Worker duerfen keine Business-Regeln verstecken, keine Consent-Gates umgehen und keine externen Dispatches starten. |
