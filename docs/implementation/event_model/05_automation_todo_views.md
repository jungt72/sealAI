# Automation Todo Views

Todo Views machen Worker-Arbeit sichtbar. Ein Worker beobachtet eine View und fuehrt genau ein erlaubtes Command aus. Business-Regeln bleiben im Command/Governor, nicht im Worker versteckt.

## DocumentExtractionTodoView

| Aspekt | Definition |
|---|---|
| Observed events | `EvidenceUploaded` |
| Trigger condition | Dokument ist tenant-scoped, Dateityp erlaubt, noch keine Extraktion versucht |
| Worker/service | RAG/document extraction service |
| Command executed | `ExtractEvidenceCandidates` |
| Events emitted | `DocumentParseAttempted`, `ExtractionCandidateCreated` |
| Failure event | `UploadRejected` or `DocumentParseFailed` |
| Retry policy suggestion | Max. 2 Retries fuer transiente Parserfehler; keine Retries bei Policy-/Dateityp-Ablehnung |
| Safety rules | Upload ist Evidence/Kandidat; LLM-Verarbeitung nur bei erlaubter Policy; Pfade redigieren |
| Forbidden side effects | Keine Feldbestaetigung, keine Instruktionsausfuehrung aus Dokumenttext |

## StaleArtifactCheckTodoView

| Aspekt | Definition |
|---|---|
| Observed events | `CaseFieldConfirmed`, `CaseFieldCandidateProposed`, `SealApplicationProfileUpdated`, `CaseTypeAssigned` |
| Trigger condition | Case revision ist groesser als artifact_case_revision |
| Worker/service | Artifact stale checker |
| Command executed | `MarkArtifactStale` |
| Events emitted | `ArtifactMarkedStale` |
| Failure event | `ArtifactStaleCheckFailed` |
| Retry policy suggestion | Idempotent; retry bei DB-Konflikt erlaubt |
| Safety rules | Stale-Status blockiert Consent/Export fuer betroffene Artefakte |
| Forbidden side effects | Keine automatische Regeneration ohne expliziten Trigger |

## RAGLookupTodoView

| Aspekt | Definition |
|---|---|
| Observed events | `UserMessageReceived`, `CompatibilityInquiryCreated`, `KnowledgeRAGLookupRequested` |
| Trigger condition | Intent ist `general_sealing_question` oder fachlicher Supportbedarf; RAG-first erforderlich |
| Worker/service | Knowledge/RAG service |
| Command executed | `RunRAGLookup` |
| Events emitted | `KnowledgeRAGAnswerFound` or `KnowledgeRAGAnswerMissing`, `SourceValidationStatusAssigned` |
| Failure event | `KnowledgeRAGLookupFailed` |
| Retry policy suggestion | Kurzer Retry bei transientem Qdrant/Redis-Fehler; keine Fallback-Antwort ohne Miss/Policy |
| Safety rules | Tenant scope und Knowledge scope pruefen |
| Forbidden side effects | Kein CaseField bestaetigen; keine LLM-Antwort als RAG ausgeben |

## FallbackResearchTodoView

| Aspekt | Definition |
|---|---|
| Observed events | `KnowledgeRAGAnswerMissing` |
| Trigger condition | Fallback enabled, `LLMProcessingAllowed`, Frage ist nicht compliance-final oder safety-final |
| Worker/service | LLM research fallback service |
| Command executed | `RunLLMResearchFallback` |
| Events emitted | `LLMResearchFallbackUsed`, `SourceValidationStatusAssigned` |
| Failure event | `LLMProcessingBlocked` or `LLMFallbackFailed` |
| Retry policy suggestion | Max. 1 Retry; keine Wiederholung bei Policy-Block |
| Safety rules | Label "nicht validiert"; minimaler Kontext; keine Secrets/Dokumente ohne Policy |
| Forbidden side effects | Keine finale technische Freigabe, keine confirmed fields, keine Compliance Evidence |

## ManufacturerFitTodoView

| Aspekt | Definition |
|---|---|
| Observed events | `ManufacturerFitRequested`, `SealApplicationProfileUpdated`, `CaseFieldConfirmed` |
| Trigger condition | Matching angefragt und ausreichendes Case-Profil vorhanden oder Open-Points-Fit erlaubt |
| Worker/service | Manufacturer matching service |
| Command executed | `FilterEligiblePartnerManufacturers`, `ScoreTechnicalFit`, `ComputeManufacturerFitMatrix` |
| Events emitted | `PartnerCandidatesFiltered`, `ManufacturerFitComputed`, `NoSuitablePartnerFound`, `PartnerNetworkDisclosureAttached` |
| Failure event | `ManufacturerFitComputationFailed` |
| Retry policy suggestion | Idempotent; retry bei transientem DB/registry Fehler |
| Safety rules | Nur `active_paid`; Score ohne Zahlungseinfluss; Gaps sichtbar |
| Forbidden side effects | Kein Herstellerkontakt, keine Full-Market-Behauptung, kein paid boost |

## ExportTodoView

| Aspekt | Definition |
|---|---|
| Observed events | `RFQConsentGranted` |
| Trigger condition | Current artifact, no-final-release acknowledged, open points acknowledged if present, export intent true |
| Worker/service | Export generation service |
| Command executed | `GenerateExport` |
| Events emitted | `ExportGenerated` or `ExportBlocked`, `ExternalDispatchBlocked` |
| Failure event | `ExportGenerationFailed` |
| Retry policy suggestion | Idempotent by artifact/revision/consent id; retry safe if no external dispatch |
| Safety rules | Export allowlist; document visibility explicit; no dispatch |
| Forbidden side effects | Keine E-Mail, kein Herstellerdispatch, keine nicht freigegebenen Dokumente |

## AuditEventTodoView

| Aspekt | Definition |
|---|---|
| Observed events | Security-, consent-, upload-, export-, matching- und fallback-relevante Events |
| Trigger condition | Event ist auditpflichtig oder sicherheitsrelevant |
| Worker/service | Audit logger/projection builder |
| Command executed | `RecordAuditEvent` oder bestehende Audit-Projektion aktualisieren |
| Events emitted | `AuditEventRecorded` |
| Failure event | `AuditEventRecordFailed` |
| Retry policy suggestion | Persistenter Retry mit Dead-letter-Status; Audit darf User-Flow nicht stillschweigend verlieren |
| Safety rules | Keine Secrets; Pfade redigieren; tenant_id/user_id nur berechtigt anzeigen |
| Forbidden side effects | Keine fachliche State-Mutation aus Audit-Worker |
