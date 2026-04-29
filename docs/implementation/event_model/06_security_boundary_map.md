# Security und Trust Boundary Map

Diese Map beschreibt Grenzen, die kuenftige PRs testen muessen. Severity: P0 kritisch, P1 hoch, P2 mittel.

| Boundary | Risk | Required command/event/view behavior | Tests that must exist | Severity | Related future PRs |
|---|---|---|---|---|---|
| Tenant isolation | Cross-tenant Case-, RFQ-, Upload- oder Artifact-Leak | `CheckTenantAccess` vor Read/Write; `TenantAccessChecked` oder `TenantAccessDenied`; Views filtern tenant-scoped | Cross-tenant document/case/RFQ access blocked | P0 | PR 2 Test Harness, PR 12 Security |
| Keycloak/NextAuth identity | Client-provided IDs umgehen Serverauth | Backend nutzt serverseitige identity/tenant claims, nicht Client-Vertrauen | Spoofed tenant_id ignored/denied | P0 | PR 12 Security |
| User vs Manufacturer Partner visibility | Partner sieht nicht freigegebene Kundendaten | `DocumentVisibilityApproved` vor Partner-View; default `DocumentVisibilityRejected` | Partner cannot access unshared artifact | P0 | PR 9 Matching, PR 12 Security |
| Upload/document IP safety | Kundendokumente werden als Instruktion oder unkontrolliert an LLM verarbeitet | `AttachEvidenceDocument`, `ExtractEvidenceCandidates`; `LLMProcessingAllowed` nur bei Policy; `UploadRejected` bei Verletzung | Prompt injection in upload ignored; LLM default-off where configured | P1 | PR 10 Upload/IP |
| RAG/LLM processing boundary | RAG-Miss wird durch unmarkierte LLM-Antwort ersetzt | `KnowledgeRAGAnswerMissing` muss vor `LLMResearchFallbackUsed`; Badge sichtbar | Fallback disabled gives no fallback; enabled is labelled | P1 | PR 6 Trust Layer |
| LLM fallback not validated | Fallback wird Case Truth oder Compliance Evidence | `SourceValidationStatusAssigned` mit `source_type=llm_research_fallback`, `validation_status=unvalidated` | Fallback cannot confirm field or compliance | P1 | PR 6 Trust Layer |
| RFQ consent | Export ohne bewusste Einschraenkungen | `GrantArtifactConsent` required; `RFQConsentRejected` bei missing no-final/open-points/export intent | Missing acknowledgement blocks export | P0 | PR 7 RFQ |
| RFQ export | Falsche Revision oder nicht freigegebene Dokumente im Export | `RFQPreviewFrozenToCaseRevision`; stale -> `ExportBlocked`; document allowlist | Stale preview blocks consent/export | P0 | PR 7 RFQ |
| No automatic dispatch | Unerlaubte Herstellerkontaktaufnahme | `ExternalDispatchBlocked` default; Export ist Datei/Artifact, kein Versand | Export does not send | P0 | PR 7 RFQ, PR 12 Security |
| Partner-network disclosure | Nutzer glaubt an Full-Market-Ranking | `PartnerNetworkDisclosureAttached` in jeder Matching View | Disclosure visible in matrix and no-fit | P1 | PR 9 Matching |
| No paid technical ranking | Zahlung beeinflusst Fit Score | `FilterEligiblePartnerManufacturers` uses `active_paid`; `ScoreTechnicalFit` ignores tier | Payment tier does not change score | P1 | PR 9 Matching |
| Compliance overclaim prevention | FDA/ATEX/Food/Pharma/Trinkwasser wird ohne Evidence behauptet | Compliance fields remain requirements/evidence; views show open proof | FDA mention not compliance proof | P1 | PR 12 Compliance |
| Support/complaint liability boundary | Antwortentwurf erkennt Haftung an oder behauptet Ursache | Draft generators use no-liability/no-final-root-cause guard | Complaint draft has no liability admission | P1 | PR 11 Support |
| Path redaction | Interne Pfade/Storage-Struktur sichtbar | Upload/RAG/health errors redact paths | Internal paths redacted in errors | P1 | PR 10 Upload/IP |
| Secret handling | Secrets in Logs/Docs/Responses | Never print values; audit only key names if needed | Secret-like values masked/not exposed | P0 | PR 12 Security/Ops |
| Audit events | Sicherheitsschritte nicht nachvollziehbar | Security/consent/export/fallback/matching events in `AuditTimelineView` | Audit timeline includes blocked/allowed decisions | P2 | PR 12 Security |

## Pflicht-Security-Events

| Event | Bedeutung |
|---|---|
| `TenantAccessChecked` | Server hat Tenant-/User-/Org-Grenze geprueft. |
| `TenantAccessDenied` | Zugriff auf fremden oder unberechtigten Scope blockiert. |
| `DocumentVisibilityApproved` | Dokument darf fuer einen konkreten View/Export/Recipient sichtbar sein. |
| `DocumentVisibilityRejected` | Dokument bleibt verborgen. |
| `PartnerNetworkDisclosureAttached` | Matching-View enthaelt Partnernetzwerk-Grenze. |
| `PartnerNetworkDisclosureAcknowledged` | Nutzer hat Disclosure in einem spaeteren Consent-Flow bestaetigt, falls erforderlich. |
| `RFQConsentGranted` | Alle Consent-Gates fuer aktuelles Artifact erfuellt. |
| `RFQConsentRejected` | Consent unvollstaendig oder stale. |
| `ExportGenerated` | Export artifact erzeugt, ohne externen Versand. |
| `ExportBlocked` | Export wegen Consent, Stale, Tenant oder Dokumentgrenze blockiert. |
| `ExternalDispatchBlocked` | Externer Versand wurde nicht ausgefuehrt. |
| `LLMProcessingAllowed` | Policy erlaubt LLM-Verarbeitung fuer diesen Kontext. |
| `LLMProcessingBlocked` | Policy verbietet LLM-Verarbeitung. |
| `UploadRejected` | Upload durch Policy, Typ, Groesse, Tenant oder Parsergrenze abgelehnt. |

## Implementierungsregel

Jeder PR, der Dokumente, RFQ, Export, Matching, Partner-Sicht, LLM-Fallback, Compliance oder Complaint-Drafts beruehrt, muss im Patch-Report eine IP-/Security-Notiz enthalten.
