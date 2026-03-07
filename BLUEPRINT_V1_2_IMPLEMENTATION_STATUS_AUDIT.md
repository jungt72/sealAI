# BLUEPRINT v1.2 Implementation Status Audit

Normative Referenz: `konzept/01_sealingai_blueprint_v1.2.docx`  
Audit-Basisdatum: 2026-03-07  
Prüfmodus: read-only, evidenzbasiert, Blueprint v1.2 als Soll-Spezifikation

## 1. Executive Verdict

Grobe Umsetzungsnähe: **38%**

Einstufung: **architecturally non-compliant**

Die Codebasis enthält belastbare Vorstufen fuer LangGraph-v2, Keycloak-Scoping, Cycle-Staleness, HITL-Checkpoints und RFQ-Hard-Gates. Gegen die normative v1.2-Spezifikation verfehlt sie aber mehrere Pflichtgrenzen auf Architektur-Ebene, nicht nur im Naming.

Die 5 wichtigsten Gründe:

1. **Das v1.2-Fünf-Schichtenmodell ist nicht formal erzwungen.** `observed_inputs` existiert, aber es gibt keinen eigenen zentralen Normalized-Layer; Nutzer-/Patch-Daten werden direkt in `working_profile.engineering_profile` promoted. Evidenz: `backend/app/api/v1/endpoints/langgraph_v2.py:3248-3308` schreibt `merged` direkt nach `working_profile.engineering_profile`.
2. **Normative Enumerationen driften systematisch.** Blueprint fordert z.B. `identity_confirmed`, `family_only`, `compound_required`, `claim_type`, `conflict_severity=SOFT|INFO|FALSE_CONFLICT`; der Code verwendet stattdessen u.a. `confirmed|probable|family_only`, `compound_specific|family_level`, `WARNING`, `UNKNOWN`. Evidenz: `backend/app/langgraph_v2/state/sealai_state.py:349-420`, `backend/app/langgraph_v2/utils/candidate_semantics.py:7-13`.
3. **Der Result Contract ist kein v1.2-konformer Result Contract.** Es fehlen Pflichtfelder wie `contract_id`, `snapshot_parent_revision`, `release_status`, `rfq_admissibility`, `blockers`, `conflicts`, `evidence_coverage`, `compound_specificity_required`. Evidenz: `backend/app/langgraph_v2/state/sealai_state.py:324-346`.
4. **Die RAG-/Claim-Governance ist nicht v1.2-konform formalisiert.** Es gibt keine zentrale `EvidenceClaim`-/`claim_type`-Schicht; `p2_rag_lookup` arbeitet mit Dokument-Hits/Snippets statt claim-basiertem Vector Retrieval. Evidenz: `backend/app/services/rag/nodes/p2_rag_lookup.py:115-129`, keine `claim_type`-Definition im v2-State.
5. **RFQ-/Checkpoint-Logik ist nur teilweise blueprint-konform.** Der Hard-Gate gegen blocking unknowns ist vorhanden, aber `rfq_draft` wird trotzdem gebaut und Checkpoint-Trigger orientieren sich nicht streng an den Blueprint-Bedingungen (`Depth >= 2`, `ready|provisional`). Evidenz: `backend/app/langgraph_v2/nodes/answer_subgraph/node_finalize.py:374-391`, `backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py:355-390`.

## 2. Compliance Scorecard

| Audit-Dimension | Status | Confidence | wichtigste Evidenz |
|---|---|---:|---|
| A. State-Schichtenmodell | DRIFTED | High | `backend/app/api/v1/endpoints/langgraph_v2.py:3248-3308` promoted Patch direkt nach `engineering_profile`; `backend/app/langgraph_v2/state/sealai_state.py:680-692` hat kein separates normalized/asserted-Modell |
| B. Governance Enumerations | DRIFTED | High | `backend/app/langgraph_v2/state/sealai_state.py:349-420`, `backend/app/langgraph_v2/utils/candidate_semantics.py:7-13` |
| C. Intent / Normalization / Profile Builder | PARTIAL | High | `backend/app/services/rag/nodes/p1_context.py:449-567`, `backend/app/langgraph_v2/utils/parameter_patch.py:105-187` |
| D. Risk-Driven Completeness Engine | PARTIAL | Medium | `backend/app/langgraph_v2/nodes/nodes_supervisor.py:143-275` |
| E. Gates / RFQ-Admissibility | PARTIAL | High | `backend/app/langgraph_v2/utils/rfq_admissibility.py:21-172`, `backend/app/langgraph_v2/nodes/answer_subgraph/node_finalize.py:374-391` |
| F. Cycle Control / Obsolescence | PARTIAL | High | `backend/app/langgraph_v2/utils/assertion_cycle.py:42-122` |
| G. Human-in-the-Loop Checkpoints | PARTIAL | High | `backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py:355-390` |
| H. RAG / Claim Governance | DRIFTED | High | `backend/app/services/rag/nodes/p2_rag_lookup.py:37-54,115-129`; kein zentrales `claim_type`-Modell |
| I. Conflict Resolver v1.2 | PARTIAL | High | `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py:369-424,517-594,831-863` |
| J. Result Contract / Clusters / Spec / RFQ Draft | DRIFTED | High | `backend/app/langgraph_v2/state/sealai_state.py:324-346`, `backend/app/langgraph_v2/utils/candidate_semantics.py:149-184` |
| K. Definition of Done | DRIFTED | Medium | Sammelbefund über A-J; einzelne DoD-Punkte belegt unten |

## 3. Evidence by Dimension

### A. STATE-SCHICHTENMODELL

**Blueprint-Soll**  
Observed -> Normalized -> Asserted -> Governance -> Cycle Control muss als Pflichtpfad erzwungen sein. Kein Agent darf direkt von Raw/User/Freitext nach `asserted_*` schreiben.

**Ist-Umsetzung im Code**  
Es gibt `observed_inputs`, Identitäts-Metadaten und Cycle-Felder. Es gibt aber keinen zentralen, formalisierten Normalized-Layer mit v1.2-Feldgrenzen; das "asserted" Ziel ist faktisch `working_profile.engineering_profile`. Nutzer-Patches werden direkt dorthin promoted.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/state/sealai_state.py:680-692`  
  Exzerpt: `observed_inputs: Dict[str, Any]`, `extracted_parameter_identity`, `current_assertion_cycle_id`, `state_revision`, `asserted_profile_revision`, `snapshot_parent_revision`  
  Befund: Beobachtungs- und Cycle-Metadaten existieren, aber kein separates `normalized_*`-Objekt und kein v1.2-`analysis_cycle_id`.

- `backend/app/services/rag/nodes/p1_context.py:533-567`  
  Exzerpt: `stage_extracted_parameter_patch(...)` schreibt `extracted_parameter_identity` und `observed_inputs`, aber `working_profile_update` enthält nur `extracted_params`; `engineering_profile` bleibt leer bei `new_case`.  
  Befund: Observed/Staging ist partiell sauber.

- `backend/app/api/v1/endpoints/langgraph_v2.py:3248-3308`  
  Exzerpt: `promote_parameter_patch_to_asserted(...)` und danach `updates = {"working_profile": {"engineering_profile": merged, ...}}`  
  Befund: Expliziter Direktpfad von User-Patch in asserted Zielobjekt.

- `backend/app/langgraph_v2/utils/parameter_patch.py:602-651`  
  Exzerpt: `promote_parameter_patch_to_asserted(...): "Promote a sanitized patch into asserted parameters"`  
  Befund: Der Direkt-Promotionspfad ist benannt und implementiert.

**Gap-Bewertung**  
**Hartes v1.2-Gap.** Die Architektur kennt Staging, aber keine formale `Normalized -> Asserted`-Trennung gemäss Blueprint. `release_status` lebt zudem nur innerhalb des RFQ-Admissibility-Contracts statt als State-Pflichtfeld des Governance-Layers.

**Risiko, wenn so belassen**  
Unklare Nachvollziehbarkeit, stilles Überspringen von Normalisierung/Governance, höhere Gefahr von Freitext-zu-Assertion-Leaps und Audit-Unschärfe.

### B. GOVERNANCE ENUMERATIONS

**Blueprint-Soll**  
Die normativen Enumerationen müssen zentral definiert, validiert und ohne Drift verwendet werden.

**Ist-Umsetzung im Code**  
Enums/Literals existieren, aber mit deutlicher Drift in Bezeichnern und Semantik.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/state/sealai_state.py:392-405`  
  Exzerpt: `release_status: Literal["inadmissible","precheck_only","manufacturer_validation_required","rfq_ready"]`  
  Befund: `release_status` ist nahe am Blueprint, aber als Teil des RFQ-Vertrags modelliert statt als eigenes Governance-State-Feld.

- `backend/app/langgraph_v2/state/sealai_state.py:417-420`  
  Exzerpt: `identity_class: Literal["confirmed", "probable", "family_only", "unresolved"]`  
  Befund: Blueprint fordert `identity_confirmed|identity_probable|identity_family_only|identity_unresolved`.

- `backend/app/langgraph_v2/utils/candidate_semantics.py:7-13`  
  Exzerpt: `compound_specific`, `family_level`, `material_class`, `document_hit`, `unresolved`  
  Befund: Blueprint fordert `family_only|subfamily|compound_required|product_family_required`.

- `backend/app/langgraph_v2/state/sealai_state.py:349-372`  
  Exzerpt: `conflict_type` enthält `UNKNOWN`; `severity` enthält `WARNING`, aber kein `SOFT`, kein `FALSE_CONFLICT` als Severity.  
  Befund: Konflikt-Taxonomie driftet von Blueprint.

**Gap-Bewertung**  
**Systemische Drift.** Die Enumerationen sind nicht blueprint-identisch und damit keine fachlich saubere v1.2-Implementierung.

**Risiko, wenn so belassen**  
Kontrakt-/UI-/Test-Drift, Fehlmapping zwischen Governance-Regeln und Laufzeitwerten, erschwerte Compliance-Audits.

### C. INTENT / NORMALIZATION / PROFILE BUILDER

**Blueprint-Soll**  
2-stufiger Intent-Layer, deterministischer Validator, 3-Stufen-Normalisierung mit `identity_class`, `identity_unresolved => Rueckfrage Pflicht`, strikte Trennung normalized vs asserted.

**Ist-Umsetzung im Code**  
Intent-/Extraktionslogik existiert. Identitätsklassifikation existiert ebenfalls. Die 3-Stufen-Normalisierung des Blueprints ist aber nicht formal umgesetzt; Confidence-/Ambiguity-Routing existiert nur fragmentarisch.

**Konkrete Evidenz**

- `backend/app/services/rag/nodes/p1_context.py:274-282`  
  Exzerpt: `_invoke_extraction(...); llm.with_structured_output(_P1Extraction, ...)`  
  Befund: LLM-Extraktion vorhanden.

- `backend/app/langgraph_v2/utils/parameter_patch.py:105-171`  
  Exzerpt: `_build_identity_record(...)` setzt `identity_class`, `lookup_allowed`, `promotion_allowed`.  
  Befund: Es gibt eine regelbasierte Identity-Klassifikation.

- `backend/app/services/rag/nodes/p2_rag_lookup.py:45-81`  
  Exzerpt: `_strip_unconfirmed_identity_fields(...)` blankt nicht-`confirmed` Felder für RAG-Queries aus.  
  Befund: Lookup-Gating ist partiell wirksam.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_prepare_contract.py:647-665`  
  Exzerpt: non-confirmed identity-guarded fields werden aus `resolved_parameters` entfernt.  
  Befund: Auch die Contract-Seite hat ein Identity-Gate.

**Gap-Bewertung**  
**Teilweise umgesetzt.** Gute Vorstufe fuer Identity-Gates, aber kein blueprint-konformer IntentValidator mit `>=0.85 / 0.60-0.85 / <0.60`, keine formale 3-Stufen-Normalisierung, keine saubere `NormalizedProfile`-Schicht.

**Risiko, wenn so belassen**  
Uneinheitliches Routing, nicht nachvollziehbare Confidence-Schwellen, starke Abhängigkeit von verteilten Guardrails statt von einer normativen Pipeline.

### D. RISK-DRIVEN COMPLETENESS ENGINE

**Blueprint-Soll**  
Echte risk-driven completeness engine mit 7 Kategorien fehlender Information, Depth Levels (`precheck`, `prequalification`, `critical review`) und Priorisierung der technisch folgenreichsten nächsten Frage.

**Ist-Umsetzung im Code**  
Es gibt Missing-Parameter-Logik und risikobasierte Priorisierung einzelner Fragen. Das bleibt aber feldzentriert und bildet weder die 7 Kategorien noch die Depth-Level formal ab.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/nodes/nodes_supervisor.py:143-179`  
  Exzerpt: `_infer_missing_params(...)`, `_compute_coverage(...)`, `recommendation_ready = coverage_score >= _READY_THRESHOLD`  
  Befund: Kernlogik ist Coverage-/Missing-Feld-basiert.

- `backend/app/langgraph_v2/nodes/nodes_supervisor.py:196-222`  
  Exzerpt: `_get_dynamic_priority(...)` gewichtet Fragen bei hohem Druck/Temperatur höher.  
  Befund: Risiko-basierte Priorisierung existiert, aber nur als Zusatzheuristik.

- `backend/app/langgraph_v2/nodes/nodes_supervisor.py:225-275`  
  Exzerpt: `_derive_open_questions(...)` baut Fragen aus `missing_params` und `missing_critical_parameters`.  
  Befund: Keine formale 7-Kategorien-Engine, kein next-question contract.

**Gap-Bewertung**  
**Partielle Vorstufe, nicht blueprint-konform.**

**Risiko, wenn so belassen**  
Kritische Unknowns und Komfortlücken bleiben semantisch vermischt; das System priorisiert nicht deterministisch entlang der v1.2-Zulässigkeitslogik.

### E. GATES / RFQ-ADMISSIBILITY

**Blueprint-Soll**  
Deterministische Gates; kein RFQ bei `unknowns_release_blocking`; klare Trennung `inadmissible|provisional|ready` sowie `release_status`.

**Ist-Umsetzung im Code**  
Der Hard-Gate gegen Blocking Unknowns ist real implementiert. Gleichzeitig driftet die Gesamtlogik: `manufacturer_validation_required` kann neben `status="inadmissible"` stehen, und ein `rfq_draft` wird auch im inadmissible-Fall gebaut.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/utils/rfq_admissibility.py:92-151`  
  Exzerpt: `active_blockers` aus `unknowns_release_blocking` und `BLOCKING_UNKNOWN`-Konflikten erzwingen `status = "inadmissible"` und `reason = "blocking_unknowns"`.  
  Befund: Die harte Sperrregel ist umgesetzt.

- `backend/app/langgraph_v2/tests/test_rfq_admissibility_hard_gate.py:181-210`  
  Exzerpt: Test bestätigt, dass `BLOCKING_UNKNOWN` Konflikte `status == "inadmissible"` erzwingen.  
  Befund: Lokal getestete Hard-Gate-Implementierung.

- `backend/app/langgraph_v2/tests/test_rfq_admissibility_hard_gate.py:213-239`  
  Exzerpt: `release_status == "manufacturer_validation_required"` bei gleichzeitigem inadmissible-Status.  
  Befund: Semantische Drift gegenüber Blueprint-Zustandsmodell.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_finalize.py:374-391`  
  Exzerpt: `_build_rfq_draft(...)` wird immer aufgerufen; `RFQDraft(...)` entsteht unabhängig von `status`.  
  Befund: Blueprint sagt "Kein RFQ darf erzeugt werden", hier wird trotzdem ein RFQ-Draft erzeugt.

**Gap-Bewertung**  
**Partiell compliant, aber nicht v1.2-konform.** Der Hard-Gate ist gut, die RFQ-Artefakterzeugung und Statussemantik sind es nicht.

**Risiko, wenn so belassen**  
Benutzer oder Folgekomponenten können inadmissible RFQ-Artefakte als zulässige Beschaffungsbasis missverstehen.

### F. CYCLE CONTROL / OBSOLESCENCE

**Blueprint-Soll**  
Neue `analysis_cycle_id` bei relevanten Änderungen; Snapshot-Revision gebunden; alte Contracts obsolet; `superseded_by_cycle` und stale-prevention verdrahtet.

**Ist-Umsetzung im Code**  
Cycle/Staleness ist eine der stärkeren Teilumsetzungen. Die Form driftet aber: es werden Integer-Zyklen statt blueprint-IDs verwendet; Contract-Felder bleiben unvollständig.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/utils/assertion_cycle.py:42-68`  
  Exzerpt: `next_cycle_id = current_cycle_id + 1`; bestehender Contract wird `obsolete=True`, `obsolete_reason=...`, `superseded_by_cycle = f"cycle_{session_id}_{next_cycle_id}"`.  
  Befund: Obsoleszenzmechanismus real vorhanden.

- `backend/app/langgraph_v2/utils/assertion_cycle.py:82-121`  
  Exzerpt: `state_revision`, `asserted_profile_revision`, `snapshot_parent_revision`, `derived_artifacts_stale=True`; `sealing_requirement_spec=None`, `rfq_draft=None`.  
  Befund: Stale-Artefakte werden aktiv invalidiert.

- `backend/app/langgraph_v2/state/sealai_state.py:324-346`  
  Exzerpt: `AnswerContract` hat `analysis_cycle_id`, `obsolete`, `obsolete_reason`, `superseded_by_cycle`, aber kein `snapshot_parent_revision`.  
  Befund: Contract bleibt untermodelliert gegenüber Blueprint.

**Gap-Bewertung**  
**Strukturell vielversprechend, aber drifted.**

**Risiko, wenn so belassen**  
Auditierbarkeit und Cross-Component-Bindung bleiben unscharf; cycle-bound ja, aber nicht blueprint-scharf.

### G. HUMAN-IN-THE-LOOP CHECKPOINTS

**Blueprint-Soll**  
`snapshot_confirmation`, `rfq_confirmation`, `draft_conflict_resolution` als echte Interrupts, korrekt getriggert, resumable und loop-safe.

**Ist-Umsetzung im Code**  
Alle drei Checkpoints existieren und sind als echte Interrupt-/Resume-Punkte verdrahtet. Die Triggerbedingungen weichen aber von v1.2 ab.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/sealai_graph_v2.py:359-413`  
  Exzerpt: Knoten `snapshot_confirmation_node`, `rfq_confirmation_node`, `draft_conflict_resolution_node` sind im Graph registriert und an `final_answer_node` rückgekoppelt.  
  Befund: Echte Graph-Knoten vorhanden.

- `backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py:355-365`  
  Exzerpt: `snapshot_confirmation` triggert bei neuem `spec_id != confirmed_spec_id`, sonst Resume/Interrupt.  
  Befund: Trigger basiert auf Spec-ID-Differenz, nicht auf Blueprint-Kriterium "Completeness Gate positiv, Depth >= 2".

- `backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py:381-390`  
  Exzerpt: `rfq_confirmation` triggert sobald `rfq_draft and rfq_admissibility and not is_rfq_confirmed`.  
  Befund: Kein harter Filter auf `ready` oder `provisional`.

- `backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py:397-408`  
  Exzerpt: `draft_conflict_resolution` triggert bei offenen Konflikten; `_resolve_open_conflicts` markiert sie nach Approval als `RESOLVED`.  
  Befund: Resume-/Re-trigger-Mechanik existiert real.

**Gap-Bewertung**  
**Teilweise umgesetzt.** Die Interrupt-Mechanik ist real, die Blueprint-Triggersemantik nicht.

**Risiko, wenn so belassen**  
Zu frühe oder fachlich falsche Checkpoints; inadmissible oder unzureichend qualifizierte Artefakte können unnötig in den HITL-Pfad gelangen.

### H. RAG / CLAIM GOVERNANCE

**Blueprint-Soll**  
Structured DB deterministisch, Vector Store claim-basiert, Graph nur heuristisch, heuristische Pfade dürfen Gates nie überschreiben.

**Ist-Umsetzung im Code**  
Deterministische Norm-/Limit-Lookups existieren. Identity-Gating vor RAG existiert. Eine formale Claim-Governance-Schicht (`EvidenceClaim`, `claim_type`, source_rank-basierte Gate-Tragfähigkeit) fehlt jedoch; Retrieval arbeitet mit Dokument-Hits/Snippets.

**Konkrete Evidenz**

- `backend/app/services/rag/nodes/p2_rag_lookup.py:37-54`  
  Exzerpt: Identity-guarded fields dürfen nur bei `identity_class == "confirmed"` als Query-Signal dienen.  
  Befund: Gute Schutzmaßnahme.

- `backend/app/services/rag/nodes/p2_rag_lookup.py:115-129`  
  Exzerpt: `_build_sources_from_hits(...)` baut `Source(snippet=..., source=..., metadata={"score": ...})` aus Hit-Dokumenten.  
  Befund: Retrieval ist dokument-/chunk-orientiert, nicht claim-basiert.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py:809-829`  
  Exzerpt: Deterministische Post-Checks (`chemical_resistance_lookup`, `material_limits_lookup`) können Draft-Claims als `SOURCE_CONFLICT` hart markieren.  
  Befund: Deterministische Nachkontrolle existiert, aber nicht in einer formalen Claim-Governance-Schicht.

- `backend/app/services/knowledge/factcard_store.py:271-278`  
  Exzerpt: `source_rank_for(...)` existiert.  
  Befund: Source-Ranking ist vorhanden, aber im v2-Conflict-/Gate-Pfad nicht sichtbar verdrahtet.

**Gap-Bewertung**  
**Drifted.** Gute deterministische Einzelkontrollen, aber kein blueprint-konformes Claim-Modell.

**Risiko, wenn so belassen**  
Schwer prüfbare Belastbarkeit einzelner Aussagen; fehlende klare Trennung zwischen deterministisch, evidenzbasiert plausibel und heuristisch.

### I. CONFLICT RESOLVER v1.2

**Blueprint-Soll**  
7 Konfliktarten, 7 Severity-Klassen, Scope-Prüfung vor Evidenzhierarchie, `FALSE_CONFLICT`, Escalation nach `BLOCKING_UNKNOWN` oder `RESOLUTION_REQUIRES_MANUFACTURER_SCOPE`.

**Ist-Umsetzung im Code**  
Mehrere Konfliktarten sind real implementiert, inkl. `SCOPE_CONFLICT`, `ASSUMPTION_CONFLICT`, `TEMPORAL_VALIDITY_CONFLICT`, `COMPOUND_SPECIFICITY_CONFLICT`. Die Umsetzung bleibt aber regel-/post-check-getrieben statt als klarer Resolver mit Evidenzhierarchie und source-rank-basierter Entscheidung.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py:369-424`  
  Exzerpt: `_check_specificity_conflicts(...)` erzeugt `COMPOUND_SPECIFICITY_CONFLICT` mit `RESOLUTION_REQUIRES_MANUFACTURER_SCOPE`.  
  Befund: Eskalation in Manufacturer-Scope existiert.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py:517-556`  
  Exzerpt: `_check_scope_conflicts(...)` erzeugt `SCOPE_CONFLICT` aus vager/bedingter Draft-Sprache mit `severity="WARNING"`.  
  Befund: Scope-Konflikte existieren, aber eher als Sprachheuristik statt Gueltigkeitssphären-Abgleich.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py:559-594`  
  Exzerpt: `_check_temporal_validity_conflicts(...)` erzeugt `TEMPORAL_VALIDITY_CONFLICT`.  
  Befund: Temporale Konflikte sind real.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py:679-683`  
  Exzerpt: `FALSE_CONFLICT type always acts as DISMISSED`.  
  Befund: `FALSE_CONFLICT` wird verarbeitet.

- `backend/app/langgraph_v2/state/sealai_state.py:365-372`  
  Exzerpt: Severities sind `INFO|WARNING|HARD|CRITICAL|BLOCKING_UNKNOWN|RESOLUTION_REQUIRES_MANUFACTURER_SCOPE`.  
  Befund: Blueprint-`SOFT` und `FALSE_CONFLICT` als Severity fehlen; `WARNING` ist Drift.

**Gap-Bewertung**  
**Partielle Implementierung mit Taxonomie-Drift.**

**Risiko, wenn so belassen**  
Uneinheitliche Konfliktbewertung; fehlende Evidenzhierarchie kann zu falscher Priorisierung zwischen Norm, Hersteller und Heuristik führen.

### J. RESULT CONTRACT / CANDIDATE CLUSTERS / REQUIREMENT SPEC / RFQ DRAFT

**Blueprint-Soll**  
Vollständiger, cycle-gebundener Result Contract mit Pflichtfeldern; Candidate Clusters semantisch exakt; SealingRequirementSpec und RFQDraft mit Pflichtfeldern und specificity-governed Sprache.

**Ist-Umsetzung im Code**  
Es existieren `AnswerContract`, `SealingRequirementSpec` und `RFQDraft`. Das Datenmodell bleibt aber deutlich unter dem Blueprint.

**Konkrete Evidenz**

- `backend/app/langgraph_v2/state/sealai_state.py:324-346`  
  Exzerpt: `AnswerContract` enthält `analysis_cycle_id`, `resolved_parameters`, `candidate_clusters`, `governance_metadata`, `obsolete...`  
  Befund: Es fehlen `contract_id`, `snapshot_parent_revision`, `release_status`, `rfq_admissibility`, `scope_of_validity` als Pflichtfeld des Contracts, `blockers`, `conflicts`, `evidence_coverage`, `compound_specificity_required`.

- `backend/app/langgraph_v2/utils/candidate_semantics.py:149-184`  
  Exzerpt: `plausibly_viable` nur wenn `governed=True and specificity=="compound_specific"`; sonst `viable_only_with_manufacturer_validation`.  
  Befund: Das widerspricht Blueprint, wo `plausibly_viable` gerade family/subfamily mit Rank>=2 sein kann.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_prepare_contract.py:879-895`  
  Exzerpt: `SealingRequirementSpec(...)` wird gebaut, aber `material_specificity_required` wird aus internen Werten wie `compound_specific`/`family_only` gemischt.  
  Befund: Spec vorhanden, aber mit Enumeration-Drift.

- `backend/app/langgraph_v2/nodes/answer_subgraph/node_finalize.py:381-391`  
  Exzerpt: `RFQDraft(... buyer_contact={}, operating_context_redacted=dict(sealing_requirement_spec.get("operating_envelope") or {}))`  
  Befund: `buyer_contact` bleibt leer; Redaction reduziert sich auf Envelope-Kopie, nicht auf explizit anonymisierten Kontext.

**Gap-Bewertung**  
**Deutliche Modell- und Semantikdrift.**

**Risiko, wenn so belassen**  
Nachgelagerte Komponenten konsumieren Artefakte, die wie v1.2-Contracts aussehen, die normative Tragfähigkeit aber nicht haben.

### K. DEFINITION OF DONE CHECK

**Blueprint-Soll**  
Die DoD-Punkte sind einzeln erfüllt.

**Ist-Umsetzung im Code**

1. **Kein RFQ bei `unknowns_release_blocking`**  
   Teilweise erfüllt. Hard-Gate vorhanden (`backend/app/langgraph_v2/utils/rfq_admissibility.py:144-151`), aber `rfq_draft` wird trotzdem gebaut (`backend/app/langgraph_v2/nodes/answer_subgraph/node_finalize.py:479-495`).

2. **Kein outward-facing Spec ohne `scope_of_validity`**  
   Teilweise erfüllt. `GovernanceMetadata.scope_of_validity` existiert (`backend/app/langgraph_v2/state/sealai_state.py:252-259`), aber der Contract selbst trägt dieses Pflichtfeld nicht (`backend/app/langgraph_v2/state/sealai_state.py:324-346`).

3. **Keine Werkstoff-Familienausgabe ohne `specificity_level`**  
   Nicht erfüllt. Es gibt nur interne `specificity`-Werte (`compound_specific`, `family_level`, ...), kein blueprint-konformes `specificity_level` (`backend/app/langgraph_v2/utils/candidate_semantics.py:7-13`).

4. **Jeder Contract ist cycle-gebunden und revisionsreferenziert**  
   Teilweise erfüllt. Cycle-Bindung/Obsoleszenz vorhanden, aber `snapshot_parent_revision` fehlt im Contract (`backend/app/langgraph_v2/state/sealai_state.py:324-346`).

5. **Jeder Konflikt ist typisiert nach 7 Typen und 7 Severity-Klassen**  
   Nicht erfüllt. Types/Severities driften (`backend/app/langgraph_v2/state/sealai_state.py:349-372`).

6. **Jeder heuristische Graph-Hinweis ist `heuristic_warning`**  
   Nicht nachweisbar; entsprechendes Claim-Modell fehlt.

7. **Jeder technisch wirksame Wert ist als Observed/Normalized/Asserted klassifiziert**  
   Nicht erfüllt. Observed und teilweises Identity-Staging existieren, aber keine formale Normalized-/Asserted-Schichtung.

8. **Kein Agent schreibt direkt von `observed_inputs` nach `asserted_*`**  
   Nicht erfüllt. Der Patch-Pfad promoted direkt ins asserted Zielobjekt `engineering_profile` (`backend/app/api/v1/endpoints/langgraph_v2.py:3248-3308`).

9. **Buyer-Flow `< 90 Sekunden`**  
   Nicht auditierbar aus lokalem Code; keine belastbare End-to-End-Metrik gefunden.

**Gap-Bewertung**  
DoD insgesamt **nicht erreicht**.

**Risiko, wenn so belassen**  
Das System kann operativ brauchbar wirken, ohne die fachlichen Sicherheiten zu liefern, die Blueprint v1.2 als Mindeststandard setzt.

## 4. Critical Non-Compliance Findings

1. **Kein formaler `Observed -> Normalized -> Asserted` Enforcement-Pfad.** Direkte Promotion ins asserted Zielobjekt ist produktiv verdrahtet.
2. **Governance-Enumerationen sind nicht blueprint-identisch.** Das ist kein kosmetisches Naming-Thema, sondern Contract-Drift.
3. **`AnswerContract` ist kein v1.2-Result-Contract.** Mehrere Pflichtfelder fehlen vollständig.
4. **`rfq_draft` wird auch im inadmissible-Fall erzeugt.** Das widerspricht der Blueprint-Sperrregel "Kein RFQ".
5. **RAG ist nicht claim-basiert formalisiert.** Es fehlt ein zentraler `EvidenceClaim`-/`claim_type`-Pfad.
6. **Candidate-Cluster-Semantik ist invertiert gegenüber v1.2.** `plausibly_viable` verlangt hier compound-spezifische Governed-Kandidaten statt family/subfamily mit Caveat.

## 5. False Positives / Overstated Gaps

1. **Cycle-Control ist nicht fehlend, sondern nur unvollständig.** `obsolete`, `obsolete_reason`, `superseded_by_cycle`, stale invalidation und revision binding sind real implementiert (`backend/app/langgraph_v2/utils/assertion_cycle.py:42-122`).
2. **HITL ist nicht nur behauptet.** Alle drei Checkpoints existieren als echte Interrupt-/Resume-Pfade (`backend/app/langgraph_v2/nodes/answer_subgraph/subgraph_builder.py:355-390`).
3. **Der Hard-Gate gegen blocking unknowns ist real und getestet.** Das Repo ist hier besser als ein bloßer Happy-Path-Schein (`backend/app/langgraph_v2/utils/rfq_admissibility.py:92-151`, `backend/app/langgraph_v2/tests/test_rfq_admissibility_hard_gate.py:181-210`).
4. **Identity-Gating existiert an zwei Stellen.** Nicht-confirmed Felder werden sowohl vor RAG-Queries als auch vor Contract-Aufbau entfernt (`backend/app/services/rag/nodes/p2_rag_lookup.py:45-81`, `backend/app/langgraph_v2/nodes/answer_subgraph/node_prepare_contract.py:647-665`).
5. **Keycloak-/Tenant-Scoping ist vorhanden.** Es ist nicht Kernlücke dieses Audits; Tenant-Claims werden propagiert und Knowledge/RAG-Pfade scopen tenant-aware (`backend/app/api/v1/endpoints/langgraph_v2.py:937-939`, `backend/app/mcp/knowledge_tool.py:761-808`).

## 6. Priorisierte Patch-Reihenfolge

### Patch 1
**Ziel**  
Normatives State-Schema v1.2 einfrieren: `Observed`, `Normalized`, `Asserted`, `Governance`, `CycleControl` als explizite Modelle/TypedDicts; Promotion nur noch über deterministischen Builder.

**Warum architektonisch jetzt**  
Ohne diese Schichtgrenze bleiben alle Folgepatches semantisch instabil.

**Betroffene Dateien**  
`backend/app/langgraph_v2/state/sealai_state.py`  
`backend/app/langgraph_v2/utils/parameter_patch.py`  
`backend/app/api/v1/endpoints/langgraph_v2.py`  
`backend/app/services/rag/nodes/p1_context.py`

**Abhängigkeiten**  
Keine.

**Risiko bei Nicht-Umsetzung**  
Weiterhin direkter Raw/User->Asserted-Pfad und keine saubere Auditierbarkeit.

### Patch 2
**Ziel**  
Alle v1.2-Governance-Enumerationen zentralisieren und driftfreie Laufzeitvalidierung erzwingen.

**Warum architektonisch jetzt**  
Enums sind Contract-Grenzen fuer Gates, Konflikte, Cluster, Specs und RFQ.

**Betroffene Dateien**  
`backend/app/langgraph_v2/state/sealai_state.py`  
`backend/app/langgraph_v2/utils/candidate_semantics.py`  
`backend/app/langgraph_v2/utils/rfq_admissibility.py`  
`backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py`

**Abhängigkeiten**  
Patch 1.

**Risiko bei Nicht-Umsetzung**  
Persistente Drift zwischen Blueprint, Tests, API und UI.

### Patch 3
**Ziel**  
Risk-driven completeness engine auf 7 Kategorien plus Depth-Levels umstellen; Trigger- und Fragepriorisierung daraus ableiten.

**Warum architektonisch jetzt**  
Completeness ist vor RFQ/Governance der zentrale Zulaessigkeitsvorlauf.

**Betroffene Dateien**  
`backend/app/langgraph_v2/nodes/nodes_supervisor.py`  
`backend/app/langgraph_v2/io.py`  
`backend/app/langgraph_v2/state/sealai_state.py`

**Abhängigkeiten**  
Patch 1-2.

**Risiko bei Nicht-Umsetzung**  
Feldlogik bleibt dominierend; kritische Unknowns werden nicht blueprint-konform priorisiert.

### Patch 4
**Ziel**  
Result Contract, SealingRequirementSpec und RFQDraft auf vollständige v1.2-Pflichtfelder und Semantik heben; inadmissible RFQ-Artefakte unterbinden.

**Warum architektonisch jetzt**  
Das ist der outward-facing Governance-Kern.

**Betroffene Dateien**  
`backend/app/langgraph_v2/state/sealai_state.py`  
`backend/app/langgraph_v2/nodes/answer_subgraph/node_prepare_contract.py`  
`backend/app/langgraph_v2/nodes/answer_subgraph/node_finalize.py`

**Abhängigkeiten**  
Patch 1-3.

**Risiko bei Nicht-Umsetzung**  
Extern sichtbare Artefakte tragen weiter nicht die normativ geforderte Fachverbindlichkeit.

### Patch 5
**Ziel**  
Conflict Resolver auf blueprint-konforme Typen/Severities/Evidenzhierarchie umstellen und Eskalationspfade sauber in Governance Unknowns überführen.

**Warum architektonisch jetzt**  
Konflikte bestimmen Release- und RFQ-Zulässigkeit.

**Betroffene Dateien**  
`backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py`  
`backend/app/langgraph_v2/state/sealai_state.py`  
`backend/app/services/knowledge/factcard_store.py`

**Abhängigkeiten**  
Patch 2 und 4.

**Risiko bei Nicht-Umsetzung**  
Konfliktentscheidungen bleiben inkonsistent und schwer belastbar.

### Patch 6
**Ziel**  
Claim-Governance fuer RAG formalisieren: `EvidenceClaim`, `claim_type`, source-rank-Grenzen, heuristische Kennzeichnung und deterministic-over-heuristic enforcement.

**Warum architektonisch jetzt**  
Das Blueprint erklärt diese Trennung explizit zum Sicherheitsnetz der Intelligence-Schicht.

**Betroffene Dateien**  
`backend/app/services/rag/nodes/p2_rag_lookup.py`  
`backend/app/langgraph_v2/nodes/answer_subgraph/node_prepare_contract.py`  
`backend/app/langgraph_v2/nodes/answer_subgraph/node_verify_claims.py`  
`backend/app/services/knowledge/factcard_store.py`

**Abhängigkeiten**  
Patch 2, 4 und 5.

**Risiko bei Nicht-Umsetzung**  
Heuristische und evidenzbasierte Pfade bleiben fachlich unzureichend getrennt.

## 7. Empfohlener nächster Schritt

**Als nächstes genau einen Patch beginnen: Patch 1, also das v1.2-State-Schema formal einfrieren und den direkten User/Patch->`engineering_profile`-Promotionspfad entfernen.**
