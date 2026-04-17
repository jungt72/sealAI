SeaLAI — Single Source of Truth (SSoT) Architecture Plan
Version: 1.0
Status: Binding architectural SSoT for Codex CLI–driven rebuild
Date: 2026-04-16
Owner: Thorsten Jung / SeaLAI
---
1. Purpose of this document
This document is the single architectural source of truth for rebuilding SeaLAI with Codex CLI.
It is not a marketing concept, not a generic product brief, and not a loose target vision. It is the binding implementation specification that defines:
what SeaLAI is supposed to do,
how the system is partitioned,
where the source of truth lives,
what the LLM may and may not do,
what the deterministic rule engine must decide,
how engineering data must be represented,
how readiness, risk, and provenance are enforced,
and in which implementation sequence Codex CLI must build it.
This document supersedes fragmented architecture intent spread across prior concept drafts. The earlier blueprints remain useful background, especially for the four-layer engineering model, provenance, routing, norm modules, calculations, and cockpit contract, but this file is the one implementation reference Codex CLI should follow.   
---
2. Precedence rules
2.1 Architectural precedence
For all architecture and product-behavior decisions, precedence is:
This SSoT document
Repository-level operational constraints (`AGENTS.md`) only where they govern coding workflow, repo hygiene, or patch discipline
Existing code
Older concept documents
2.2 Conflict handling
If current code conflicts with this document:
current code is treated as legacy implementation,
this document defines the target,
Codex CLI must explicitly report the delta and implement toward this document.
2.3 No silent reinterpretation
Codex CLI must not “improvise architecture” when something is unspecified. It must either:
follow this document,
or flag a precise gap for approval.
---
3. Codex CLI operating protocol for this repo
This SSoT is written specifically for Codex CLI execution. OpenAI’s current official Codex guidance supports a workflow where large changes start with a planning pass, then proceed into coding once the plan is grounded; OpenAI also recommends well-scoped tasks, keeping persistent repo context in `AGENTS.md`, using the latest supported Codex model family, and structuring prompts clearly and specifically with instructions first and explicit output formats. The current Codex CLI help and Codex guidance also document approval modes (`Suggest`, `Auto Edit`, `Full Auto`) and emphasize repo-local execution, while the latest help docs note that model availability depends on CLI version/config and that Codex currently uses the GPT‑5.1‑Codex family depending on configuration. 
3.1 Required Codex execution style
Codex CLI must work in this sequence:
Read-only audit / ask-first phase for any large architectural change
Delta report against this SSoT
Patch plan in small, named patches
Implementation patch by patch
Validation after each patch
3.2 Prompting rules for Codex CLI in this repo
All Codex prompts for substantial work must include:
a precise task summary,
explicit scope boundaries,
exact target files or likely target areas,
required output format,
constraints,
validation commands,
and the instruction to use this SSoT as binding architecture.
3.3 Codex mode usage
Use Suggest / Ask mode for audits, repo mapping, gap analysis, architecture verification, and patch planning.
Use Auto Edit only for contained patches with clear acceptance criteria.
Use Full Auto only for tightly scoped implementation loops where the task, file scope, and validation commands are already stable. OpenAI’s official CLI guidance describes these approval modes and their intended use. 
3.4 Codex prompt construction rules
Codex prompts in this repo must follow these OpenAI-aligned principles:
instructions first,
context clearly separated,
specific desired outputs,
explicit tool/validation expectations,
small well-scoped tasks where possible,
and persistent repo context maintained in `AGENTS.md`. 
3.5 Repo-local execution assumptions
Codex CLI should assume:
project root is `/home/thorsten/sealai`,
commands must be run from repo root where possible,
changes are patch-based and auditable,
no silent architectural drift is acceptable,
and any broad change must first be decomposed.
---
4. Product definition
SeaLAI is a technical clarification, qualification, and preselection system for sealing problems and sealing demand.
It is not:
a mere chat UI,
a generic RAG bot,
a simple product finder,
a norm lookup tool,
or an autonomous final approval engine.
SeaLAI must behave like a digital senior sealing engineer who:
first understands the problem,
then identifies the correct engineering path,
then gathers path-specific data,
then calculates deterministically,
then marks risk and uncertainty explicitly,
and only then generates a bounded technical preselection or manufacturer-ready inquiry basis.
This problem-first and path-first flow is already present across the prior senior-level blueprints and norm-integrated concept.  
---
5. Architectural goals
SeaLAI must be able to:
understand the user’s real request type,
determine the correct engineering path,
collect and store engineering data with provenance,
apply deterministic rules and calculations,
activate norm modules only when applicable,
separate tentative hints from confirmed engineering truth,
support RCA, retrofit, validation, and spare-part scenarios,
expose a backend-driven cockpit view,
maintain auditability and regression safety,
and generate bounded outputs based on explicit output classes.
---
6. Non-goals
SeaLAI must not:
claim final product suitability on its own,
allow the LLM to invent engineering facts,
silently convert web hints into confirmed values,
let the frontend compute authoritative readiness,
treat norms as decorative labels,
or keep stale downstream results alive after critical upstream changes.
---
7. Two-dimensional case model
SeaLAI classifies every case across two orthogonal dimensions.
7.1 Request type
Allowed values:
`new_design`
`retrofit`
`rca_failure_analysis`
`validation_check`
`spare_part_identification`
`quick_engineering_check`
7.2 Engineering path
Allowed values:
`ms_pump`
`rwdr`
`static`
`labyrinth`
`hyd_pneu`
`unclear_rotary`
7.3 Why this matters
A case is not defined only by its sealing family. It is also defined by the user’s real need:
a new design,
a retrofit under geometric constraints,
an RCA problem,
a validation under changed operating conditions,
a spare-part identification task,
or a narrow single-check request.
This dual structure is essential to model real industrial entry situations rather than only “greenfield design”. It directly extends the earlier SeaLAI target model, which already established path-based routing, phased data collection, and backend-first cockpit projection.  
---
8. Mandatory architectural principles
8.1 LLM responsibilities
The LLM may only:
normalize user language,
extract structured candidate values,
propose likely request types or paths,
prioritize missing questions,
summarize system state,
and render bounded outputs.
8.2 LLM forbidden actions
The LLM may not:
set final engineering path,
set final norm applicability,
mark values confirmed,
compute authoritative readiness,
invent calculations,
issue unbounded material or product claims,
declare RFQ readiness,
or bypass blocked fields.
8.3 Deterministic rule engine responsibilities
The rule engine must exclusively own:
request-type finalization,
path routing,
norm gating,
mandatory field logic,
check execution eligibility,
risk scoring,
readiness states,
stale-state invalidation,
and output-class eligibility.
8.4 Backend source of truth
Backend owns:
case state,
provenance,
calculated values,
risk scores,
readiness,
artifacts,
revisions,
and the canonical projection model.
Frontend renders backend truth only.
---
9. Phase model
SeaLAI progresses through deterministic phases.
Phase 0 — Scope and intent gate
Determine:
request type candidate(s),
candidate path(s),
in-scope / out-of-scope status,
missing discriminators.
Phase 1 — Deterministic path selection
Set final path using rule-based routing.
Phase 2 — Core intake
Collect universal minimum data required for any serious technical path.
Phase 3 — Failure drivers
Collect path-specific technical risk drivers.
Phase 4 — Geometry / fit
Collect geometry, tolerances, surfaces, cavity/chamber/groove information, vibration, fit-critical machine data.
Phase 5 — RFQ / liability / commercial readiness
Evaluate readiness for bounded preselection, inquiry admissibility, and RFQ readiness.
This phase stack follows the senior-engineering logic already defined in the prior blueprints: understand the function first, then choose the path, then activate norm- and path-specific logic. 
---
10. Phase transition rules
10.1 Phase 0 → 1
Allowed if:
request type is recognized, or at most two plausible request types remain,
and at least two of the following are known:
`motion.type`
`application.equipment_type`
`sealing_location`
`pressure_presence`
Else: return `structured_clarification`.
10.2 Phase 1 → 2
Allowed if:
`routing.path` is set,
or `routing.path = unclear_rotary` with explicit `missing_discriminators[]`.
10.3 Phase 2 → 3
Allowed if:
at least 80% of path-independent core mandatory fields are present,
and these are present:
medium name,
motion type,
equipment type,
pressure presence/status,
reference geometry.
Exception: `quick_engineering_check` may proceed if the requested check’s exact inputs are complete.
10.4 Phase 3 → 4
Allowed if:
at least 70% of path-specific failure-driver mandatory fields are present,
and no `critical_unknown` blocks geometry/fit evaluation.
10.5 Phase 4 → 5
Allowed if:
fit-critical geometry fields are present,
active checks can run or are explicitly marked insufficient-input,
and no hidden assumptions exist in fit-critical values.
10.6 Inquiry admissibility
`readiness.inquiry_admissible = true` if:
case is export-structured,
technical prequalification is sufficient,
open points are explicitly included,
no forbidden claims are required.
10.7 RFQ readiness
`readiness.rfq_ready = true` only if:
all path-critical mandatory fields are complete,
critical medium / failure / geometry values are at least `documented`, `registry`, or `confirmed`,
compliance context is assigned where relevant,
and no critical blockers remain.
---
11. State regression / downgrade rules
This is mandatory.
Any change to an upstream field must invalidate dependent downstream artifacts.
11.1 Mutation events
Supported mutation events include:
`field_updated`
`property_confirmed`
`document_attached`
`medium_context_refreshed`
`registry_lookup_applied`
11.2 Dependency invalidation
Every field must have dependency links.
Example:
changing `medium.input.name` invalidates:
`medium.context`
`medium.registry`
chemical compatibility results
corrosion-related scores
lubricity-related scores
flashing-related scores
technical preselection
inquiry admissibility
RFQ readiness
potentially the routing path
11.3 Required backend behavior after mutation
Synchronously:
increment case revision,
mark dependent artifacts `stale`,
recompute `highest_valid_phase`,
downgrade readiness if needed,
record `recompute_required[]`.
Asynchronously:
refresh medium intelligence,
rerun compatibility lookups,
rerun calculations,
rerun scores,
rerun RCA if affected,
invalidate exports and PDFs.
11.4 Frontend behavior
Frontend may only display:
stale flags,
downgraded phases,
recompute in progress,
blocked export states.
Frontend may not determine phase, readiness, or validity.
---
12. Canonical data model
12.1 Root case contract
```json
{
  "case_id": "string",
  "schema_version": "string",
  "ruleset_version": "string",
  "calc_library_version": "string",
  "risk_engine_version": "string",
  "norm_module_versions": {},
  "case_revision": 1,
  "request_type": "enum",
  "routing": {},
  "core_intake": {},
  "failure_drivers": {},
  "geometry_fit": {},
  "rfq_liability": {},
  "rca": {},
  "commercial": {},
  "medium": {
    "input": {},
    "context": {},
    "registry": {},
    "inferred_properties": {},
    "confirmed_properties": {}
  },
  "checks": {},
  "risk_scores": {},
  "readiness": {},
  "norm_context": {},
  "artifacts": {},
  "audit": {}
}
```
12.2 Engineering property contract
```json
{
  "key": "string",
  "label": "string",
  "value": "any",
  "unit": "string|null",
  "origin": "user_stated|documented|web_hint|calculated|confirmed|missing",
  "confidence": 0.0,
  "is_confirmed": false,
  "is_mandatory": false,
  "mandatory_for_paths": [],
  "used_in_checks": [],
  "source_refs": [],
  "updated_at": "timestamp"
}
```
12.3 Provenance requirements
Every critical field must carry origin and source traceability.
Critical origins include:
`user_stated`
`documented`
`web_hint`
`calculated`
`confirmed`
`missing`
For medium and chemistry specifically, the architecture must preserve the separation between:
`medium_input`
`medium_context`
`medium_registry`
`inferred_properties`
`confirmed_properties`
This provenance model is a core design pillar of the production-grade blueprint and is required to prevent hallucinated engineering truth. 
---
13. EngineeringCockpitView (backend projection contract)
The frontend consumes a backend-generated projection.
```json
{
  "path": "ms_pump|rwdr|static|labyrinth|hyd_pneu|unclear_rotary",
  "request_type": "new_design|retrofit|rca_failure_analysis|validation_check|spare_part_identification|quick_engineering_check",
  "sections": [
    {
      "section_id": "core_intake|failure_drivers|geometry_fit|rfq_liability|rca|commercial",
      "title": "string",
      "completion": {
        "mandatory_present": 0,
        "mandatory_total": 0,
        "percent": 0
      },
      "properties": []
    }
  ],
  "medium_context": {},
  "checks": {},
  "risk_scores": {},
  "readiness": {},
  "missing_mandatory_keys": [],
  "blockers": []
}
```
This backend-first cockpit contract is already aligned with the prior blueprint and must remain the sole authority for frontend rendering. 
---
14. Core intake schema
Mandatory core fields:
`medium.input.name`
`medium.input.composition`
`medium.state`
`operating.temperature.min_c`
`operating.temperature.nom_c`
`operating.temperature.max_c`
`operating.pressure.min_bar`
`operating.pressure.nom_bar`
`operating.pressure.max_bar`
`motion.type`
`motion.rotary.rpm_nom` or `motion.linear.v_mm_s`
`geometry.reference_diameter_mm`
`application.equipment_type`
`application.installation.orientation`
`application.pressure_direction`
---
15. Failure-driver schema by path
15.1 `ms_pump`
Mandatory failure-driver candidates:
viscosity at operating temperature
density / specific gravity
vapor pressure at Tmax
pH / chemistry class
solids percentage
particle size
particle hardness / abrasiveness
lubricity rating
dry-run allowance
start/stop frequency
pressure cycling
vibration level
emissions class
support-system context
15.2 `rwdr`
Mandatory failure-driver candidates:
lubricity rating
pressure differential
contamination level
shaft runout
shaft-to-bore misalignment
shaft finish
shaft hardness
shaft directionality / lead
15.3 `static`
Mandatory failure-driver candidates:
allowable leakage
emissions class
chemistry class
flange/nut type
seat width
emissions proof context
15.4 `hyd_pneu`
Mandatory failure-driver candidates:
pressure spikes
stroke
frequency
cleanliness class
side load
clearance gap
15.5 `labyrinth`
Mandatory failure-driver candidates:
clearance
pressure ratio
medium state
stage count
drain/vent strategy
---
16. Geometry / fit schema
Representative geometry/fit fields:
`shaft.material`
`shaft.surface.ra_um`
`shaft.surface.hardness_hrc`
`shaft.surface.directionality_deg`
`shaft.eccentricity_static_mm`
`shaft.runout.dynamic_mm_tir`
`shaft.misalignment.stbm_mm_tir`
`shaft.axial_endplay_mm`
`geometry.bore.diameter_mm`
`geometry.bore.ra_um`
`machine.vibration.mm_s_rms`
chamber / cavity / flange / groove specifics by path
The previous full blueprint already identifies runout, lead, hardness, roughness, chamber geometry, and fit-critical dimensions as mandatory engineering reality, not optional detail. 
---
17. RCA schema
For `rca_failure_analysis`, required evidence dimensions include:
`rca.symptom_class`
`rca.failure_timing`
`rca.damage_pattern.primary`
`rca.damage_pattern.secondary`
`rca.leakage_pattern`
`rca.operating_phase_of_failure`
`rca.runtime_to_failure_hours`
`rca.changed_operating_conditions`
`rca.maintenance_history`
`rca.installation_history`
`rca.inspection_assets[]`
Outputs:
`rca.likely_failure_mode_clusters[]`
`rca.required_evidence[]`
`rca.recommended_inspection_steps[]`
`rca.probable_root_causes[]`
`rca_outcome`
---
18. Retrofit schema
For `retrofit`, required fields include:
`retrofit.geometry_locked`
`retrofit.allowed_changes[]`
`retrofit.old_part_known`
`retrofit.old_part_dimensions`
`retrofit.cavity_standard_known`
`retrofit.available_radial_space_mm`
`retrofit.available_axial_space_mm`
`retrofit.photo_assets[]`
`retrofit.drawing_assets[]`
Outputs:
`retrofit.standard_candidate_possible`
`retrofit.custom_solution_required`
`retrofit.measurement_gap[]`
---
19. Commercial / supply context schema
Required fields:
`commercial.production_mode` (`prototype|small_batch|serial`)
`commercial.lot_size`
`commercial.lead_time_days`
`commercial.standardization_goal`
`commercial.second_source_required`
`commercial.price_vs_reliability_focus`
`commercial.lifecycle_strategy`
This block exists because the optimal sealing solution changes materially between one-off retrofit work and large-scale serial production.
---
20. Formula library
Every calculation must be registered with:
`calc_id`
`formula_version`
`required_inputs[]`
`valid_paths[]`
`output_key`
`fallback_behavior`
`guardrails[]`
20.1 Required baseline calculations
Circumferential speed
```text
v = π * d * n / 60
```
PV factor
```text
PV = P_f * v
```
Where `P_f` is effective contact/facing pressure, not blindly the process pressure.
Flashing margin
```text
flashing_margin_bar = p_local_abs_bar - p_vap_bar_at_T
```
Pressure-to-vapor ratio
```text
pvap_ratio = p_sealed_abs_bar / p_vap_bar_at_T
```
Friction / heat indicator
```text
H = P_f * V * A_f * f
```
Linear speed
```text
v_linear = stroke_mm * freq_hz * 2 / 1000
```
Extrusion indicator
```text
extrusion_index = pressure_max / clearance_gap
```
The production-grade blueprint already defined the need for explicit engineering checks such as circumferential speed, PV, vapor margin, leakage-related indicators, and risk-linked calculations. 
---
21. Risk-score engine
21.1 Required score types
`flashing_risk`
`lubrication_concern`
`corrosion_concern`
`fit_risk`
`wear_risk`
`emission_risk`
`supply_risk`
`retrofit_risk`
`rca_severity`
21.2 Score scale
`0` = none
`1` = low
`2` = medium
`3` = high
`4` = critical
`9` = unknown_due_to_missing_data
21.3 Score object
```json
{
  "score": 3,
  "label": "high",
  "reason_codes": ["low_pvap_ratio", "solids_present", "geometry_missing"],
  "inputs_used": [],
  "missing_inputs": []
}
```
21.4 Minimum deterministic rules
Flashing risk
missing required inputs → 9
`flashing_margin_bar <= 0` → 4
`pvap_ratio < 1.5` → 4
`pvap_ratio < 2.0` → 3
`pvap_ratio < 3.0` → 2
otherwise lower
Lubrication concern
aqueous / poor lubricity + high speed → high to critical
lubricity unknown for contacting paths → 9
Corrosion concern
aggressive chemistry + unknown material or incompatible material → high/critical
insufficient concentration → at most provisional
Fit risk
critical fit inputs missing → 9
runout / lead / chamber envelope violations → high/critical
Retrofit risk
geometry locked + no reliable dimensions → 9
standard cavity known + full dimensions present → low/medium
---
22. Chemical compatibility engine
22.1 Architectural decision
This module is registry-first.
Primary source priority:
internal compatibility registry
structured OEM/manufacturer tables
SDS / TDS mappings
web hints
LLM context (assistive only)
22.2 Registry-traceability requirement
If `source_type = registry`, then the result must include:
`registry_entry_id`
`registry_version`
`entry_hash`
`source_refs[]`
22.3 Output categories
`compatible`
`conditionally_compatible`
`not_recommended`
`insufficient_data`
22.4 Mandatory dimensions
medium key
concentration range
temperature range
static rating
dynamic rating
limitations
source type
traceable source reference
No corrosion or compatibility score may rely solely on LLM text.
---
23. Norm modules
Norms must be implemented as modules with:
applicability gate,
required fields,
deterministic checks,
escalation rules,
bounded outputs.
Mandatory norm modules
`norm_api_682`
`norm_en_12756`
`norm_din_3760_iso_6194`
`norm_iso_3601`
`norm_vdi_2290`
`norm_atex`
Example applicability pattern
A norm module may only activate if:
path is compatible,
scope is in range,
and minimum required fields are present.
The norm-integrated SeaLAI concept already established this modular norm-gating pattern and the need to keep norm-neutral data collection separate from norm application. 
---
24. Output classes and enforcement
Output classes
Allowed output classes:
`conversational_answer`
`structured_clarification`
`governed_state_update`
`technical_preselection`
`rca_hypothesis`
`candidate_shortlist`
`inquiry_ready`
Enforcement rule
Every generated answer must be validated server-side before reaching the frontend.
Validation must check:
whether the response matches the allowed class,
whether forbidden claims are present,
whether finality markers violate readiness state.
Failure handling
If validation fails:
reject or downgrade output,
produce a safe fallback,
log the violation,
mark `output_validation_failed = true`.
---
25. RCA → redesign / retrofit handover
RCA must never become a dead-end.
RCA outcome contract
```json
{
  "rca_outcome": {
    "root_cause_confidence": "low|medium|high",
    "cause_cluster": "design|operation|installation|maintenance|material|unknown",
    "redesign_candidate": true,
    "retrofit_candidate": false,
    "operational_fix_candidate": true,
    "inspection_required": true
  }
}
```
Handover rules
operational / maintenance problem → remain in RCA
design problem with geometry constraints → hand over to `retrofit`
design problem without geometry constraints → hand over to `new_design`
Handover payload
```json
{
  "handover": {
    "from_request_type": "rca_failure_analysis",
    "to_request_type": "retrofit",
    "reason": "design_incompatibility_under_fixed_geometry",
    "transferred_fields": [],
    "blocked_fields": [],
    "rca_reference_id": "rca-2026-00017"
  }
}
```
---
26. blocked_fields contract
If a field is blocked due to RCA or retrofit constraints:
frontend must render it read-only,
frontend must show the reason,
frontend must show origin,
changes must only be possible through an explicit override workflow.
This prevents endless loops and silent context loss.
---
27. Versioning and migration strategy
27.1 Version fields
Each case must store:
`schema_version`
`ruleset_version`
`calc_library_version`
`risk_engine_version`
`norm_module_versions`
`case_revision`
27.2 Compatibility rules
additive fields must be nullable or defaulted,
new mandatory rules may not silently invalidate old cases,
old cases requiring new data must be marked `needs_revalidation = true`,
server must generate cockpit projections version-aware.
27.3 No silent reinterpretation
Old cases must not be silently re-evaluated under incompatible rules without an explicit revalidation state.
---
28. API surface (minimum)
Required endpoints:
`POST /cases`
`GET /cases/{id}`
`PATCH /cases/{id}`
`GET /cases/{id}/engineering-cockpit`
`POST /cases/{id}/properties/confirm`
`POST /cases/{id}/routing/recompute`
`POST /cases/{id}/checks/recompute`
`POST /cases/{id}/medium-context/refresh`
`POST /cases/{id}/medium-registry/lookup`
`POST /cases/{id}/rca/recompute`
`GET /cases/{id}/rfq/export`
`GET /cases/{id}/rfq/pdf`
`GET /cases/{id}/rfq/json`
The previous blueprint already specified a minimal, backend-first API shape around `EngineeringCockpitView`, property confirmation, metrics recompute, and RFQ export; this document makes that the required baseline. 
---
29. Validation strategy
29.1 CI gates
Every patch must pass:
typecheck
build
lint
schema validation
required targeted tests
29.2 Golden cases
At minimum, maintain golden cases for:
`ms_pump` water/saltwater case
corrosive chemistry case
dirty medium / solids case
classic `rwdr` gearbox case
pressure-overrun `rwdr` case
`static` emissions / flange case
`hyd_pneu` rod seal case
RCA early leakage case
RCA startup leakage case
retrofit cavity-locked case
29.3 Property-based tests
Use property-based tests for:
routing
mandatory-field logic
phase transitions
readiness
stale-state regression
risk score thresholds
---
30. Codex CLI implementation sequence
Ready now
Patch 1 — request type + routing layer
Patch 2 — canonical schema + cockpit projection
Patch 3 — formula library + checks registry
Must be finalized before Patch 4+
output-class enforcement
phase gates
state-regression contract
chemical compatibility architecture
versioning + revalidation
RCA handover
blocked-fields behavior
Later sequence
Patch 4 — risk-score engine
Patch 5 — RCA path
Patch 6 — chemical compatibility engine
Patch 7 — transient operating model
Patch 8 — retrofit module
Patch 9 — commercial/supply context
Patch 10 — norm modules
Patch 11 — RFQ/export hardening
Patch 12 — golden-case suite
This sequence preserves the strong architectural base while reducing rework risk and matches the repo’s preferred pattern of audit first, then minimal-diff patching.
---
31. Final build rule for Codex CLI
Codex CLI must treat this document as binding architecture.
For any substantial task, Codex must:
audit current implementation against this SSoT,
produce a delta report,
propose a named patch plan,
implement one patch at a time,
validate each patch,
and never improvise architectural behavior outside this contract.
---
32. Final statement
SeaLAI is only production-ready when it not only asks the right engineering questions, but also controls:
what it is allowed to conclude,
when prior conclusions become invalid,
how uncertainty is represented,
