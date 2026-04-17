# SeaLAI SSoT — Supplement v2.0 (Chapters 37–43)

**Status:** Binding supplement to `sealai_ssot_architecture_plan.md` v1.0 and `sealai_ssot_supplement_v1.md`.
**Scope:** Introduces strategic positioning, moat definition, MVP scope boundary, terminology mapping, manufacturer capability model, and business-logic constraints derived from the strategic positioning analysis (see `sealai_strategische_positionierung.md`).
**Reader:** Written for consumption by Codex CLI and Claude Code during audit and patch phases, and for strategic review by the founder. Rules are imperative, testable, and cross-referenced.
**Precedence:** Equal to base SSoT and supplement v1. Where this supplement adds a new constraint, the constraint is binding. Where it conflicts with supplement v1 on the same topic, supplement v2 wins because it is newer and reflects decisions made after strategic analysis.

---

## 37 — Positioning and technical moat

### 37.1 Scope

This chapter defines the binding strategic positioning of SeaLAI. It is a design constraint, not marketing copy. Every feature decision, API contract, data model choice, and UI behavior MUST be evaluated against the three moat layers defined here. A feature that violates any layer is rejected regardless of short-term benefit.

### 37.2 The three moat layers

SeaLAI's competitive defensibility rests on three layers. No single layer is sufficient; the combination is.

**Layer 1 — Structural neutrality.** SeaLAI is neutral by construction, not by claim. This means:

- No manufacturer equity ownership in SeaLAI
- No exclusive sponsorship agreements that influence matching
- No hidden ranking boosts in matching algorithms
- Transparent visual separation of any paid visibility from matching results
- Founder's conflict-of-interest with respect to any employer-manufacturer is surfaced in public documentation (see §38.6)

**Layer 2 — Technical translation.** SeaLAI translates between:

- Proprietary product terminologies (Simmerring, Turcon Variseal, V-Ring, etc.) and generic engineering concepts
- User-language problem descriptions and structured engineering parameters
- Manufacturer capability descriptions (marketing text, datasheets) and normalized capability claims

This layer is the primary technical moat. It is implemented through the Terminology Mapping Registry (§40) and the Manufacturer Capability Model (§41).

**Layer 3 — Request qualification.** SeaLAI converts unstructured user problems into manufacturer-ready inquiry packages. This delivers value to manufacturers independently of matching outcomes by reducing their applications-engineering effort on unqualified requests. The economic justification for manufacturer monetization rests on this layer.

### 37.3 Moat invariants (testable)

For each layer, the following invariants MUST hold and MUST be verifiable by code review or automated tests:

**Layer 1 invariants:**
- No field on any Manufacturer entity influences matching rank except those derived from technical fit calculation
- No configuration flag can boost a manufacturer's matching rank globally
- Sponsored listings render in a UI zone structurally separated from matching results; the separation is defined in §43
- Any paid visibility is marked in the API response with an explicit `sponsored: true` flag at every surface where it appears

**Layer 2 invariants:**
- Every product-name input from a user is resolved through the Terminology Mapping Registry before matching
- Unknown product names produce explicit "not recognized" feedback, not silent fallthrough
- Every manufacturer capability is represented as a structured ManufacturerCapabilityClaim, not as free text on the profile
- Matching operates on normalized engineering concepts only; no regex-on-marketing-text matching is permitted

**Layer 3 invariants:**
- Every Case produced by SeaLAI that reaches a manufacturer is a structured, parameterized inquiry package, not a forwarded user message
- The inquiry package carries explicit open-points and assumptions
- A manufacturer receiving an inquiry from SeaLAI can process it without returning to the user for basic parameter clarification in at least 80% of cases (measured KPI)

### 37.4 Design-constraint application

For every feature proposal, the team MUST answer in writing:

1. Which moat layer does this feature strengthen or weaken?
2. If it weakens any layer, why is the weakening acceptable?
3. What is the testable invariant this feature adds?

Feature proposals that cannot answer these three questions are rejected.

### 37.5 Cross-references

- §38 defines explicit anti-patterns that would violate these moat layers
- §39 fixes MVP scope consistent with these layers
- §40 and §41 implement Layer 2
- §43 implements monetization constraints derived from Layer 1

---

## 38 — Anti-patterns

### 38.1 Scope

This chapter enumerates forbidden patterns. Some are technical, some are procedural, some are relational. A violation is a blocking issue regardless of perceived short-term benefit.

### 38.2 Forbidden matching patterns

**Pay-for-ranking.** No amount of manufacturer payment may influence the ranking within matching results. This applies to:

- Base listing fee
- Performance-per-lead fees
- Featured listing fees
- Any future monetization variant

Featured listings (if implemented) appear in a separate UI zone, not interleaved with the matching result. The separation is visual and structural, not merely label-based.

**Artificial manufacturer supply.** SeaLAI MUST NOT list manufacturers without their explicit consent. Scraping public data to simulate supply is forbidden regardless of coverage benefit.

**Hidden manufacturer priority.** No manufacturer — including the founder's current employer — may receive matching boosts through:

- Configuration flags
- Dataset tuning
- Algorithm exceptions
- UI visibility preferences outside the designated sponsored zone

The founder's employer relationship is disclosed publicly (§38.6).

### 38.3 Forbidden content patterns

**Manufacturer-specific advertising to users.** SeaLAI MUST NOT display advertising for sealing manufacturers to users. This applies regardless of whether the advertiser is a listed manufacturer. The only permitted monetization touchpoints are the structural Featured Listing zone (§43) and the manufacturer's own profile page.

**Fake neutrality language.** SeaLAI MUST NOT use terms like "independent ranking," "unbiased recommendation," or "objectively best match" in user-facing text unless the specific algorithmic basis is documented and auditable. Overclaiming neutrality is itself a neutrality violation.

**Hidden sponsorship integration.** Sponsored content MUST be visually distinguishable from organic content at every surface where it appears: UI, API response, exported PDF, exported JSON, email notifications.

### 38.4 Forbidden engineering patterns

**LLM-derived engineering authority.** An LLM MUST NOT be the authoritative source of:

- Chemical compatibility judgments
- Pressure, temperature, or speed limits for specific materials
- Norm applicability decisions
- Risk score values
- Readiness states

These come from the Terminology Registry (§40), the Capability Model (§41), the Compatibility Engine (base SSoT §22), the Risk Engine (base SSoT §21), or deterministic rule services. The LLM normalizes, extracts, and renders.

**Marketing-text matching.** Matching MUST NOT use free-text similarity search on manufacturer marketing descriptions. All matching operates on structured ManufacturerCapabilityClaim objects (§41).

**Silent terminology fallthrough.** An unrecognized product name MUST produce an explicit "not recognized" response. Silent mapping to a default category is forbidden because it hides moat-layer-2 failures.

### 38.5 Forbidden business patterns

**Founder-employer matching bonus.** The founder's current employer, when listed as a manufacturer, receives exactly the same matching treatment as any other manufacturer. No field, no flag, no configuration may deviate from this.

**Tying monetization to specific product categories.** SeaLAI MUST NOT offer manufacturers premium placement "for medium X" or "in industry Y." Monetization is at the account level (Basic, Performance, Featured — see §43), not at the category level. Category-level pay-for-play reintroduces platzhirsch economics.

**Exit to a captive acquirer without neutrality warranties.** If SeaLAI is ever acquired by a sealing manufacturer or by an entity with vertical integration into sealing manufacturing, the acquisition MUST carry a written neutrality-preservation warranty with termination rights for users and manufacturers if violated. This constraint is a note for future decision-making, not enforceable in code.

### 38.6 Conflict-of-interest policy (binding)

The founder is employed full-time by a PTFE-RWDR manufacturer while building SeaLAI. This creates an unavoidable conflict of interest that SeaLAI handles as follows:

**Public disclosure.** The founder's employer affiliation is disclosed on SeaLAI's "About" page, on the manufacturer profile of that employer (if listed), and in the founder's public communications about SeaLAI. The disclosure is plain language, not hidden in terms of service.

**Operational separation.** The employer-manufacturer receives no operational privileges within SeaLAI:

- Same onboarding process as any other manufacturer
- Same fee schedule (no founder discount)
- Same capability-claim validation process
- Same matching algorithm (no boosts, no demotions)

**Data firewall.** No employer data enters SeaLAI's code or datasets:

- No proprietary customer lists
- No internal calculation spreadsheets
- No employer-confidential CAD models or compound recipes
- Generic domain knowledge (norms, public datasheets, public physics) is permitted

**Written employer agreement.** Before the first external pilot manufacturer is onboarded, the founder MUST hold a written agreement with the employer that specifies:

- SeaLAI is developed in the founder's own time
- No employer IP is used
- The employer claims no stake in SeaLAI
- The employer-manufacturer relationship with SeaLAI is at arm's length
- No non-compete restriction prevents the SeaLAI business model

A template for this agreement is provided in Annex A of this supplement.

**Review trigger.** If the founder ceases employment with the current employer, or if the employer's ownership changes, the conflict-of-interest policy is reviewed within 30 days.

### 38.7 Enforcement mechanisms

Most anti-patterns are enforced by combination of:

- Code review (human)
- Lint rules and CI checks (automated)
- Periodic neutrality audit (semi-automated, quarterly)

The neutrality audit verifies:

- No field on Manufacturer records other than technical-fit-derived values influences ranking
- Top-N matching results for a representative set of 20 queries match expected technical outcomes
- All sponsored listings are correctly flagged in all surfaces
- No upward import violations in the service layer

A failed neutrality audit blocks any new release.

---

## 39 — MVP scope boundary

### 39.1 Scope

This chapter fixes the MVP product scope. It supersedes base SSoT §8 product-strategy guidance and `SEALAI_KONZEPT_FINAL.md` §8.3 where they conflict.

### 39.2 MVP pillar

**The MVP is PTFE-based radial shaft seals (PTFE-RWDR).** The MVP is narrow in depth and wide in structure:

- Narrow in depth: only PTFE-based RWDR receives full engineering fidelity in Phase 1
- Wide in structure: the data model, terminology registry, capability model, and UI accept all RWDR variants as first-class objects, with explicit depth indicators

### 39.3 sealing_material_family enum

A new mandatory field is introduced on the `rwdr` engineering path:

```
rwdr.sealing_material_family ∈ {
    "ptfe_virgin",
    "ptfe_glass_filled",
    "ptfe_carbon_filled",
    "ptfe_bronze_filled",
    "ptfe_mos2_filled",
    "ptfe_graphite_filled",
    "ptfe_peek_filled",
    "ptfe_mixed_filled",
    "elastomer_nbr",
    "elastomer_hnbr",
    "elastomer_fkm",
    "elastomer_ffkm",
    "elastomer_epdm",
    "elastomer_silicone",
    "elastomer_acm",
    "elastomer_other",
    "unknown"
}
```

All PTFE values are collectively "PTFE-family" and are the MVP depth target. All elastomer values are "elastomer-family" and receive structural support but flat depth in Phase 1.

The detailed taxonomy and per-compound properties are defined in the separate document `sealai_engineering_depth_ptfe_rwdr.md` and referenced by §42 below.

### 39.4 Depth level indicator

Every Case carries an implicit `depth_level` derived from `engineering_path` and `sealing_material_family`:

```
depth_level ∈ {"deep", "shallow"}

rwdr + ptfe_*           → deep
rwdr + elastomer_* | unknown → shallow
ms_pump | static | hyd_pneu | labyrinth → shallow
rwdr + unknown material  → shallow with clarification request
```

A "deep" case receives:
- Full PTFE-RWDR failure-mode taxonomy
- Full PTFE-RWDR risk-score engine
- Full PTFE-RWDR parameter schema
- Full manufacturer-matching against PTFE-capable manufacturers

A "shallow" case receives:
- Structural case handling (routing, basic fields, provenance)
- Simplified risk-score engine (basic PV, surface-speed, obvious-blocker checks only)
- Manufacturer matching based on declared capability claims without deep validation
- Explicit user-facing message: "SeaLAI currently provides deepest engineering coverage for PTFE-based radial shaft seals. Your inquiry is in a related but less deeply modeled area. You will receive a qualified manufacturer pre-selection, but risk scoring and compatibility judgments are less granular than for PTFE-RWDR cases."

This message is a user-facing string defined in §39.7 and MUST be rendered verbatim or with explicit content-team approval.

### 39.5 Phase 2 expansion path

The architecture is deliberately built to support Variant 3 (all RWDR) as a future phase. The transition from Phase 1 (PTFE-RWDR deep) to Phase 2 (all RWDR deep) requires:

1. Extending `sealai_engineering_depth_ptfe_rwdr.md` with a parallel `sealai_engineering_depth_elastomer_rwdr.md`
2. Adding elastomer-specific failure modes to the failure-mode taxonomy
3. Adding elastomer-compound compatibility data to the compatibility engine
4. Flipping the `depth_level` derivation for elastomer cases from "shallow" to "deep"

No schema migration, no data model rebuild, no architectural change is required. This is the payoff of choosing Variant 2-with-Variant-3-extensibility over pure Variant 1.

### 39.6 Phase 3+ expansion

After all RWDR reaches depth parity, the next expansion targets remain consistent with base SSoT §7.2 engineering paths:

- `ms_pump` (mechanical seals for centrifugal pumps) — large market, separate engineering depth guide required
- `static` (O-rings, gaskets, flange seals) — adjacent and partly covered by PTFE-RWDR Phase 1 infrastructure
- `hyd_pneu` (hydraulic and pneumatic seals) — distinct depth profile
- `labyrinth` — niche, likely Phase 4+
- `rca_failure_analysis` and `retrofit` as request types cross over all paths

Each phase expansion produces its own engineering depth guide and updates the MVP scope boundary in this chapter.

### 39.7 User-facing scope messaging (verbatim)

The following strings are the canonical depth-limitation messages. They are stored in the prompt library and MUST be rendered verbatim in user-facing text:

**For a shallow case:**

> *"SeaLAI currently provides its deepest engineering coverage for PTFE-based radial shaft seals. Your inquiry is in a related but less deeply modeled area ({path_label}). You will receive a qualified pre-selection of manufacturers and a structured inquiry package, but risk scoring and compatibility judgments are less granular than for PTFE-RWDR cases. Manufacturers receiving your inquiry will complete the technical review."*

**For an out-of-scope case:**

> *"Your inquiry falls outside SeaLAI's currently modeled scope. SeaLAI focuses on industrial dynamic seals — specifically radial shaft seals, mechanical pump seals, static seals, and hydraulic/pneumatic seals. Your inquiry appears to relate to {detected_scope}. We can forward a basic inquiry to manufacturers registered as adjacent-capable, but cannot provide engineering-grade pre-selection at this time."*

### 39.8 Golden case requirements

The golden-case test suite (base SSoT §29.2) is extended for MVP:

- At least 5 PTFE-RWDR golden cases covering: virgin PTFE water application, glass-filled PTFE hydrocarbon application, bronze-filled PTFE high-pressure application, dry-run tolerant PTFE compound case, chemical-resistance edge case
- At least 2 elastomer-RWDR cases (shallow depth) covering: standard NBR gearbox case, FKM high-temperature case — to validate that shallow cases produce usable output
- At least 1 out-of-scope case for testing the §39.7 out-of-scope message

Golden cases MUST be generic-by-construction. No golden case may contain proprietary customer data from any manufacturer's existing customer base, including the founder's employer.

---

## 40 — Terminology mapping registry

### 40.1 Scope

This chapter defines the Terminology Mapping Registry, which is the technical implementation of moat layer 2. It is a structured datastore that maps proprietary product names, series names, and legacy nomenclature to generic engineering concepts.

### 40.2 Conceptual model

The registry has three core entity types:

**GenericConcept.** A technology-neutral, standards-anchored concept. Examples: "radial shaft seal per DIN 3760 / ISO 6194," "spring-energized PTFE lip seal," "O-ring per ISO 3601." A generic concept is described in:

- Standards references (DIN, ISO, API, EN)
- Structured technical parameters (what defines it functionally)
- Plain-language description

**ProductTerm.** A specific, often proprietary name used by one or more manufacturers. Examples: "Simmerring" (Freudenberg), "Turcon Variseal" (Trelleborg), "Premium Sine Seal" (Freudenberg), "V-Ring" (generic across multiple manufacturers).

**Mapping.** A link between a ProductTerm and a GenericConcept, with metadata:

- Source type (standards-documented, manufacturer-datasheet, public-reference, community-contributed)
- Source reference (URL, document ID, standard number)
- Confidence level
- Validity window (some terms evolve over time)
- Reviewer status (pending, reviewed, published, deprecated)

### 40.3 Registry schema

```
GenericConcept
  concept_id: UUID
  canonical_name: TEXT (e.g., "spring_energized_ptfe_lip_seal")
  display_name: TEXT (e.g., "Spring-energized PTFE lip seal")
  standards_refs: TEXT[]
  engineering_path: ENUM (rwdr, ms_pump, static, ...)
  sealing_material_family: ENUM (ptfe_*, elastomer_*, unknown)
  description: TEXT
  structural_parameters: JSONB
  created_at: TIMESTAMPTZ
  updated_at: TIMESTAMPTZ

ProductTerm
  term_id: UUID
  term_text: TEXT
  term_language: TEXT (ISO 639-1)
  term_type: ENUM (brand_name, series_name, generic_term, abbreviation, colloquial)
  originating_manufacturer_id: UUID NULLABLE (null for generic terms)
  is_trademark: BOOLEAN
  created_at: TIMESTAMPTZ

Mapping
  mapping_id: UUID
  term_id: UUID REFERENCES ProductTerm
  concept_id: UUID REFERENCES GenericConcept
  source_type: ENUM (standards, manufacturer_datasheet, manufacturer_website,
                     community_contribution, expert_judgment)
  source_reference: TEXT
  confidence: SMALLINT (1-5)
  validity_from: DATE NULLABLE
  validity_to: DATE NULLABLE
  reviewer_status: ENUM (pending, reviewed, published, deprecated)
  reviewer_id: UUID NULLABLE
  review_notes: TEXT
  created_at: TIMESTAMPTZ
```

### 40.4 Registry operations (service interface)

The terminology service in `backend/app/services/terminology_service.py` exposes:

- `resolve_user_term(text: str, language: str = "de") -> list[ConceptMatch]`
- `get_concept(concept_id: UUID) -> GenericConcept`
- `list_mappings_for_concept(concept_id: UUID) -> list[Mapping]`
- `propose_mapping(term_text: str, concept_id: UUID, source_ref: str, actor_id: str) -> Mapping` (creates pending mapping)
- `publish_mapping(mapping_id: UUID, reviewer_id: UUID) -> Mapping` (reviewer-only)

### 40.5 Resolution behavior

When a user writes free-text describing a seal, the resolution pipeline:

1. Tokenizes the text
2. Runs exact-match against ProductTerm table (case-insensitive, with common normalization: whitespace, hyphens, trademark symbols)
3. Runs fuzzy match (edit distance ≤ 2 for terms of length ≥ 6) against ProductTerm table
4. For each matched term, retrieves all published mappings
5. Returns ranked ConceptMatch list with confidence and source

If zero matches are found, the service returns an empty list. The downstream graph node MUST interpret empty as "terminology not recognized" and ask the user a disambiguation question; it MUST NOT silently assume a default concept.

### 40.6 Versioning and change management

Mappings are versioned via the `validity_from` / `validity_to` fields. When a manufacturer renames a product line or a concept definition evolves, new mappings are created with updated validity, old ones are deprecated but retained.

The registry MUST NOT be rewritten or migrated in place. Historical resolution must remain reproducible for audit purposes.

### 40.7 Seed data requirements

The MVP launch requires seed data for PTFE-RWDR covering at minimum:

- All PTFE-based RWDR product lines from the top 8 sealing manufacturers listed in the strategic analysis
- Key generic terms (Simmerring, RWDR, oil seal, lip seal, shaft seal, radial shaft seal)
- Standards-anchored concepts (DIN 3760 types A, AS, B, BS, C; ISO 6194 variants)
- Common colloquial terms in German and English

Initial seed data is provided in Annex B of this supplement. It is a starting point, not exhaustive. The registry grows through:

- Manual curation by founder in Phase 1
- Manufacturer self-registration in Phase 2 (manufacturers declare their own product terms during onboarding)
- Community contributions in Phase 3 (with review queue)

### 40.8 Moat invariant (testable)

The registry is a core moat asset. Its integrity is verified by:

- Round-trip test: for each published mapping, resolve the term text and assert the primary match is the expected concept
- Coverage test: for a curated list of the top 100 PTFE-RWDR product names observed in the market, at least 95% MUST resolve to a published mapping within MVP launch
- Conflict detection: a single term mapping to multiple concepts with conflicting engineering paths triggers a reviewer alert

---

## 41 — Manufacturer capability model

### 41.1 Scope

This chapter defines how manufacturer technical capabilities are structured, stored, and used for matching. It is the second technical pillar of moat layer 2. It also amends base SSoT chapter 15 (manufacturer matching) by fixing the data model.

### 41.2 Two-entity model

Manufacturer data is split into two entities with different lifecycle characteristics:

**ManufacturerProfile — relatively stable master data.** Company name, legal entity, address, contacts, industry certifications (ISO 9001, IATF 16949, AS9100), general business information. Changes rarely.

**ManufacturerCapabilityClaim — time-bounded capability declarations.** Each claim represents a specific technical capability ("we can produce PTFE-RWDR for shaft diameter 10-250mm, temperature up to 220°C, with glass-filled compounds for medium class hydrocarbons"). Claims have source types and validity windows.

This separation is taken from the recommendation in `AUDIT_REPORT.md` gap M5 and is now binding.

### 41.3 Profile schema

```
ManufacturerProfile
  manufacturer_id: UUID
  legal_name: TEXT
  display_name: TEXT
  country: TEXT (ISO 3166-1 alpha-2)
  address: JSONB
  website_url: TEXT
  contact_email: TEXT
  contact_phone: TEXT
  industry_certifications: TEXT[]
  size_category: ENUM (micro, small, medium, large, enterprise)
  founded_year: SMALLINT NULLABLE
  languages_supported: TEXT[]
  account_status: ENUM (pending_verification, active, suspended, withdrawn)
  subscription_tier: ENUM (basic, performance, featured, none)
  onboarded_at: TIMESTAMPTZ
  conflict_of_interest_flags: TEXT[]   -- e.g., ["founder_employer"]
```

The `conflict_of_interest_flags` array surfaces known COI relationships (currently only the founder's employer) for internal audit and for public disclosure on the profile.

### 41.4 Capability claim schema

```
ManufacturerCapabilityClaim
  claim_id: UUID
  manufacturer_id: UUID REFERENCES ManufacturerProfile
  capability_type: ENUM (
    product_family,       -- "we produce X family of seals"
    operating_envelope,   -- "our products handle Y conditions"
    material_expertise,   -- "we have compound Z capability"
    geometry_range,       -- "we produce dimensions D1 to D2"
    norm_capability,      -- "we manufacture to standard S"
    medium_experience,    -- "we have experience with medium M"
    lot_size_capability,  -- "we handle lot sizes L1 to L2"
    certification         -- "our products carry certification C"
  )
  payload: JSONB          -- structure depends on capability_type
  source_type: ENUM (
    self_declared,        -- manufacturer said so during onboarding
    datasheet_extracted,  -- extracted from a public datasheet
    third_party_verified, -- verified by SeaLAI through norm documents or testing
    customer_reference    -- multiple user reports confirm capability
  )
  source_reference: TEXT
  confidence: SMALLINT (1-5)
  validity_from: DATE
  validity_to: DATE NULLABLE   -- null = open-ended until withdrawn
  verified_at: TIMESTAMPTZ NULLABLE
  verified_by: UUID NULLABLE
  status: ENUM (draft, active, expired, withdrawn)
```

### 41.5 Payload structure by capability type

Each `capability_type` has a specific payload schema. The MVP schemas are:

**product_family:**
```json
{
  "engineering_path": "rwdr",
  "sealing_material_family": "ptfe_glass_filled",
  "generic_concept_ids": ["uuid-1", "uuid-2"]
}
```

**operating_envelope:**
```json
{
  "engineering_path": "rwdr",
  "temperature_min_c": -40,
  "temperature_max_c": 220,
  "pressure_max_bar": 10,
  "shaft_speed_max_ms": 25,
  "shaft_diameter_min_mm": 10,
  "shaft_diameter_max_mm": 250,
  "dry_run_capable": true
}
```

**material_expertise:**
```json
{
  "compound_family": "ptfe_glass_filled",
  "filler_percentages": [15, 20, 25],
  "compound_internal_code": "PTFE-GF25",
  "certifications": ["FDA 21 CFR 177.1550"]
}
```

**medium_experience:**
```json
{
  "medium_class": "hydrocarbons",
  "specific_media": ["hydraulic_oil_hlp46", "diesel", "kerosene"],
  "service_years": 15
}
```

Full schemas for all capability types are documented in `backend/app/domain/capability_claims.py`.

### 41.6 Claim lifecycle

A claim moves through states:

1. **draft** — created during onboarding, not yet active
2. **active** — published and used in matching, within validity window
3. **expired** — validity_to reached without renewal
4. **withdrawn** — manufacturer or SeaLAI removed the claim

State transitions:
- `draft → active`: on manufacturer confirmation during onboarding, or on reviewer approval for higher-risk claim types
- `active → expired`: automatic, when `now() > validity_to`
- `active → withdrawn`: manual, by manufacturer self-service or SeaLAI neutrality audit

### 41.7 Matching operates on claims, not on profiles

Base SSoT §15 specified that matching considers "manufacturer capabilities." This is now sharpened: **Matching MUST operate on ManufacturerCapabilityClaim objects filtered to `status = active`, never on ManufacturerProfile text fields or marketing descriptions.** This is a moat-layer-2 invariant and is enforced by:

- `matching_service.get_candidates(case: Case) -> list[ManufacturerMatch]` signature only accepts structured case data and returns manufacturer IDs ranked by structured claim match
- No marketing text, no free-text description, no profile keyword is in the matching signature

### 41.8 Self-declared claims versus verified claims

MVP reality: most claims will start as `self_declared` because manufacturers have the data and SeaLAI does not. This is acceptable if:

- The `source_type` is visible to users in matching results
- Claims inconsistent with user-reported outcomes can be flagged (post-MVP)
- Third-party verification is a premium tier option, not a gating requirement

In matching results, a manufacturer's ranking is slightly modulated by claim verification levels, but not dominated. The algorithm is documented in §41.9.

### 41.9 Ranking algorithm (summary)

For a given Case, candidate manufacturers are scored as:

```
total_score = technical_fit_score * verification_multiplier
  where technical_fit_score ∈ [0, 100]
  and verification_multiplier ∈ [0.9, 1.1] (narrow range)
```

`technical_fit_score` is derived from structured claim-to-case matching:

- 40 points for engineering-path and material-family match
- 25 points for operating-envelope containment (temp, pressure, speed, diameter)
- 15 points for medium-class experience match
- 10 points for norm/certification match
- 10 points for geometry-range coverage

`verification_multiplier` averages verified claims higher but never doubles them:
- All claims self_declared → 0.95
- Mixed, some third_party_verified → 1.00
- Majority third_party_verified → 1.05
- Customer_reference-supported → 1.10

Sponsored listings do NOT receive any multiplier bonus. Featured placement appears in a separate UI zone per §43.

### 41.10 Onboarding process

Manufacturer onboarding (Phase 1 manual, later self-service) produces:

1. ManufacturerProfile with basic master data
2. Initial set of self_declared ManufacturerCapabilityClaim entries covering the manufacturer's stated scope
3. A review gate before publication (SeaLAI staff checks for obvious issues)
4. Public listing after review approval

The onboarding UX is out of scope for this supplement but referenced in the `frontend` audit.

---

## 42 — Engineering depth reference

### 42.1 Scope

This chapter is short because it delegates. The full engineering depth definition for PTFE-RWDR is maintained as a separate document:

**`sealai_engineering_depth_ptfe_rwdr.md`**

That document is binding at the same precedence level as this supplement for all PTFE-RWDR engineering decisions (schema fields, risk-score inputs, failure-mode taxonomy, check calculations).

### 42.2 Relationship between documents

- **Base SSoT**: strategic and architectural rules (what SeaLAI does, how it is partitioned)
- **Supplement v1**: technical implementation pillars (LangGraph role, consistency, schema layering, persistence)
- **Supplement v2 (this document)**: positioning, moat, MVP scope, terminology, capability
- **Engineering depth guide (PTFE-RWDR)**: fact-dense engineering reference for the MVP depth target

Each Phase-2+ engineering path will produce its own engineering depth guide, named and versioned parallel (e.g., `sealai_engineering_depth_elastomer_rwdr.md`, `sealai_engineering_depth_ms_pump.md`).

### 42.3 Update cadence

The engineering depth guides evolve based on:

- Real user cases encountered in production (after MVP launch)
- Manufacturer feedback on their specific capability requirements
- Standards updates (DIN, ISO, API revisions)
- Failure analysis data from the RCA path (when implemented)

The guides are not static. Quarterly review is required.

---

## 43 — Business logic constraints

### 43.1 Scope

This chapter translates the business-model decisions from the strategic positioning analysis into binding technical constraints. It complements base SSoT chapter 19 (commercial context) with monetization-specific rules.

### 43.2 Subscription tiers

Three tiers are defined. A manufacturer has exactly one active tier at a time.

**Basic (Listing) — MVP launch price 299 EUR/month, open to revision**
- Manufacturer profile visible
- Listed in matching results ranked purely by technical_fit_score
- Standard onboarding support
- Basic analytics (inquiries received, inquiry-to-quote conversion — self-reported)

**Performance — MVP launch price 299 EUR/month base + 75 EUR per accepted inquiry, open to revision**
- Everything in Basic
- Pay-per-qualified-inquiry on top of base
- "Accepted inquiry" is defined as an inquiry the manufacturer marks as "accepted for quotation" in the SeaLAI dashboard within 7 days of receipt
- No payment is triggered if the inquiry is declined, ignored, or marked as unqualified

**Featured — MVP launch price 799 EUR/month, introduced no earlier than Phase 3 (50+ manufacturers)**
- Everything in Performance
- Visibility in the Featured zone (see §43.4)
- Enhanced profile content (images, videos, case studies — subject to content review)
- Priority support

### 43.3 Pricing evolution

The prices listed in §43.2 are MVP-launch anchors, not immutable. Pricing review occurs:

- After 10 active manufacturers
- After 50 active manufacturers
- Annually thereafter

Pricing changes for existing manufacturers require 60 days notice and do not apply retroactively within an active billing cycle.

### 43.4 Sponsored placement UI separation

Featured listings are visible only in a structurally separated UI zone. The separation rules:

**In search or browse views**: The matching result list shows only technical-fit-ranked manufacturers (all tiers). A separate zone, visually distinct and explicitly labeled "Featured manufacturers related to your search," appears below or adjacent to the matching result — never interleaved.

**In case output (cockpit)**: If Featured listings are shown in a case's manufacturer-shortlist view, they appear as a separate collapsible panel titled "Additional available manufacturers." Technical pre-selection (moat layer 3) never includes Featured-boost.

**In exported artifacts (PDF, JSON)**: Featured listings, if included, appear in an explicitly labeled section separate from the technical pre-selection. The JSON schema reflects this with distinct keys (`technical_preselection[]` vs `featured_related_manufacturers[]`).

**In API responses**: `sponsored: true` flag appears on every sponsored manufacturer entry at every API surface.

### 43.5 Transparent labeling

Every user-facing surface that shows a Featured manufacturer labels the entry with a visible, accessible, localized indicator (e.g., "Featured" badge in the UI, "Featured listing" text in exports, `sponsored: true` in API).

Hiding or minimizing the label to reduce user attention is a moat-layer-1 violation and blocks release.

### 43.6 Engineering-time-savings KPI

SeaLAI tracks and exposes (to manufacturers, in their dashboards) an Engineering-Time-Savings KPI for each inquiry they receive:

```
engineering_time_savings_score: int  ∈ [0, 100]
```

The score reflects how completely the inquiry arrives qualified. Factors:

- Completeness of core intake fields (base SSoT §14): +40 points for all mandatory fields
- Completeness of failure-driver fields (base SSoT §15): +30 points
- Completeness of geometry fields (base SSoT §16): +20 points
- Explicit open-points list: +10 points

The score justifies manufacturer monetization: A manufacturer's internal cost-per-inquiry is reduced in proportion to the savings score.

This KPI is exposed in the manufacturer dashboard and becomes, in Phase 2, the basis for pay-per-accepted-inquiry pricing.

### 43.7 Revenue accounting constraints

Revenue is recognized when:

- Basic/Featured subscription: pro-rated daily across the billing period (straight-line recognition)
- Performance: on manufacturer acceptance of an inquiry

Refund rules:
- Subscription: prorated on cancellation within the current billing cycle, no minimum commitment
- Performance: no refund on already-accepted inquiries

### 43.8 Conflict-of-interest compliance in monetization

The founder's employer, if listed, is subject to the same tier structure and pricing as any other manufacturer. No founder discount, no waived fees, no grandfathered tier. Violating this triggers §38.6.

### 43.9 Monetization transparency

SeaLAI publishes, on a public page:

- Current tier structure
- Current pricing
- Revenue distribution summary (aggregated, no individual manufacturer data)
- Any material changes to pricing or tiers

This is a neutrality-reinforcing mechanism: users can verify there are no hidden manufacturer relationships.

---

## Cross-reference index (v2)

| Base SSoT chapter | Amended or extended by |
|-------------------|------------------------|
| §7 (Case model) | §39 (sealing_material_family) |
| §8 (LLM responsibilities) | §37.2 (moat layer 2 boundary) |
| §12 (Canonical data model) | §40, §41 schemas |
| §15 (Manufacturer matching) | §41 in full |
| §19 (Commercial context) | §43 |
| §22 (Compatibility engine) | §40 (terminology feeds in), §41 (capability filters) |
| §24 (Output classes) | §43.4 (sponsored separation) |

| Supplement v1 chapter | Related in v2 |
|-----------------------|---------------|
| §33 (LangGraph orchestration) | §37 (moat layer 2 enforcement at graph boundary) |
| §35 (Four-layer schema) | §40, §41 add domain models in layer 1 |
| §36 (Persistence model) | §40, §41 tables persist following §36 rules |

## Final binding rule

Supplement v2 sits at the same precedence level as base SSoT and supplement v1. Where v2 adds a constraint, the constraint is binding. Where v2 conflicts with v1 on the same topic, v2 supersedes because it is newer and reflects strategic decisions made after market analysis.

The MVP is PTFE-RWDR. The moat is neutrality + technical translation + request qualification. Anti-patterns are forbidden. Terminology and capability are structured. Monetization respects neutrality. These are not suggestions.

---

# Annex A — Template for employer written agreement (German)

**Dieser Text ist eine Vorlage, keine rechtliche Beratung.** Er deckt die aus Architektur- und Gründungssicht relevanten Punkte ab. Vor Unterzeichnung sollte er durch eine Anwältin / einen Anwalt für Arbeits- und Gesellschaftsrecht geprüft werden. Eine Erstprüfung kostet typisch 200–500 EUR und ist eine sehr gute Investition.

---

## Vereinbarung zum Nebenprojekt „SeaLAI" zwischen [Arbeitgeber-Name] und Thorsten Jung

**Präambel**

Herr Thorsten Jung (nachfolgend „Arbeitnehmer") ist bei [Arbeitgeber-Name] (nachfolgend „Arbeitgeber") in Vollzeit angestellt. Außerhalb seiner Arbeitszeit entwickelt der Arbeitnehmer das Projekt „SeaLAI" (nachfolgend „Projekt"), eine digitale Plattform zur neutralen technischen Vorqualifizierung von Dichtungstechnik-Anfragen. Beide Parteien wünschen eine klare, schriftliche Abgrenzung zwischen Anstellungsverhältnis und Projekt.

**§ 1 — Trennung der Tätigkeiten**

(1) Das Projekt wird vom Arbeitnehmer ausschließlich in seiner Freizeit betrieben. Arbeitszeiten beim Arbeitgeber werden nicht für das Projekt verwendet.

(2) Der Arbeitnehmer nutzt keine Betriebsmittel des Arbeitgebers für das Projekt. Dies umfasst — ohne abschließende Aufzählung — Arbeitgeber-Rechner, Arbeitgeber-Software-Lizenzen, Arbeitgeber-Räumlichkeiten, Arbeitgeber-Kommunikationsmittel.

(3) Im Projekt wird kein geistiges Eigentum des Arbeitgebers verwendet. Hierzu zählen insbesondere: eigene Rezepturen und Compound-Zusammensetzungen, interne Kalkulationsgrundlagen, Kundendaten, CAD-Modelle, interne Qualitätsdokumente, nicht-öffentliche Applikations-Referenzen.

(4) Im Projekt werden allgemein zugängliche Fach- und Domänenkenntnisse verwendet (Normen, öffentlich verfügbare Datenblätter, allgemeine Physik und Werkstofflehre). Diese gelten nicht als Betriebsgeheimnis.

**§ 2 — Eigentum am Projekt**

(1) Das Projekt einschließlich aller zugehörigen Rechte (Quellcode, Marken, Domains, Kundenbeziehungen, Verträge mit Dritten) steht im ausschließlichen Eigentum des Arbeitnehmers.

(2) Der Arbeitgeber erhebt keinerlei Ansprüche auf Anteile am Projekt, auf dessen Umsätze oder auf dessen Exit-Erlöse.

(3) Sollte sich im Arbeitsverhältnis eine Situation ergeben, in der der Arbeitgeber einen Ansatzpunkt für einen Anspruch sieht, ist dies schriftlich anzuzeigen und zwischen den Parteien zu klären, bevor einseitige Maßnahmen ergriffen werden.

**§ 3 — Wettbewerbsverhältnis**

(1) Der Arbeitgeber ist selbst Hersteller von PTFE-Radialwellendichtringen und damit eine potenzielle Partnerorganisation des Projekts.

(2) Die Parteien sehen im Projekt kein unzulässiges Wettbewerbsverhältnis, solange:

  a) das Projekt eine neutrale technische Vermittlungsplattform ist und nicht selbst Dichtungen herstellt oder vertreibt,

  b) der Arbeitgeber innerhalb des Projekts kein anderes oder schlechteres Matching-Ergebnis erhält als andere gelistete Hersteller,

  c) keine Kundendaten des Arbeitgebers in das Projekt fließen.

(3) Der Arbeitgeber kann sich als Hersteller im Projekt listen lassen. In diesem Fall gilt er aus Sicht des Projekts wie jeder andere Hersteller. Die Listing-Gebühren richten sich nach den öffentlichen Tarifen des Projekts, ohne Sonderkonditionen.

**§ 4 — Gegenseitige Offenheit**

(1) Der Arbeitnehmer informiert den Arbeitgeber zeitnah, wenn das Projekt die reine Entwicklungs-/Testphase verlässt und in den produktiven Betrieb geht.

(2) Der Arbeitgeber informiert den Arbeitnehmer zeitnah, wenn sich am Anstellungsverhältnis oder an der Eigentümerstruktur des Arbeitgebers Änderungen ergeben, die diese Vereinbarung berühren könnten.

(3) Bei wesentlichen Änderungen wird diese Vereinbarung auf Antrag einer der Parteien neu besprochen.

**§ 5 — Beendigung des Anstellungsverhältnisses**

(1) Die Beendigung des Anstellungsverhältnisses — durch Kündigung einer der Parteien, Aufhebungsvertrag, Rente oder andere Gründe — berührt diese Vereinbarung nicht. Das Projekt bleibt im Eigentum des Arbeitnehmers.

(2) Ein etwaiges nachvertragliches Wettbewerbsverbot aus dem Anstellungsvertrag ist so auszulegen, dass es den Fortbetrieb des Projekts als neutrale Plattform im Sinne dieser Vereinbarung nicht erfasst.

**§ 6 — Vertraulichkeit**

(1) Inhalt und Existenz dieser Vereinbarung sind gegenüber Dritten vertraulich zu behandeln, mit Ausnahme von:

  a) rechtlichen Beratern beider Parteien,

  b) ggf. Investoren des Projekts, sofern diese eine Vertraulichkeitserklärung unterzeichnet haben,

  c) Behörden, soweit gesetzlich erforderlich.

(2) Die öffentliche Offenlegung des Arbeitnehmer-Arbeitgeber-Verhältnisses auf der SeaLAI-Plattform selbst (im Rahmen der Conflict-of-Interest-Transparenzpflicht gemäß §38.6 des SeaLAI-SSoT) ist ausdrücklich zulässig.

**§ 7 — Schlussbestimmungen**

(1) Änderungen dieser Vereinbarung bedürfen der Schriftform.

(2) Sollte eine Bestimmung unwirksam sein oder werden, bleibt die Wirksamkeit der übrigen Bestimmungen unberührt.

(3) Gerichtsstand ist [Sitz des Arbeitgebers]. Es gilt deutsches Recht.

---

Ort, Datum: ____________________

Arbeitgeber (Geschäftsführung): ____________________

Arbeitnehmer (Thorsten Jung): ____________________

---

# Annex B — Terminology mapping seed data (PTFE-RWDR)

This annex provides a starting-point dataset for the Terminology Mapping Registry (§40). It is NOT exhaustive and will grow through manufacturer onboarding and community contributions. Each row is formatted as it would appear in the registry after ingestion.

## B.1 Generic concepts (MVP seed)

| canonical_name | display_name | standards_refs | family |
|---|---|---|---|
| `rwdr_ptfe_lip_spring_loaded` | Spring-energized PTFE lip seal | DIN 3760 (basis), manufacturer variations | `ptfe_*` |
| `rwdr_ptfe_lip_non_spring` | Non-spring PTFE lip seal | DIN 3760 (basis) | `ptfe_*` |
| `rwdr_ptfe_double_lip` | Double-lip PTFE radial shaft seal | DIN 3760 Type BS/ASL | `ptfe_*` |
| `rwdr_ptfe_o_ring_energized` | O-ring energized PTFE rotary seal | proprietary designs | `ptfe_*` |
| `rwdr_elastomer_standard` | Standard elastomer radial shaft seal (Simmerring-type) | DIN 3760 Types A, AS, B, BS, C; ISO 6194-1 | `elastomer_*` |
| `rwdr_elastomer_cassette` | Cassette-type radial shaft seal with integrated metal sleeve | proprietary / automotive standards | `elastomer_*` |
| `rwdr_elastomer_v_ring` | V-ring axial-acting elastomer seal | manufacturer standards | `elastomer_*` |

## B.2 Product term mappings (MVP seed, PTFE-RWDR focused)

| term_text | term_type | manufacturer | concept |
|---|---|---|---|
| Simmerring | brand_name | Freudenberg (trademark) | rwdr_elastomer_standard (most commonly) |
| Simmerring PTFE | brand_name | Freudenberg | rwdr_ptfe_lip_spring_loaded |
| Premium Sine Seal | brand_name | Freudenberg | rwdr_elastomer_standard (sinusoidal lip variant) |
| PTFE POP Seal | brand_name | Freudenberg | rwdr_ptfe_lip_spring_loaded |
| Turcon Variseal | brand_name | Trelleborg (trademark) | rwdr_ptfe_lip_spring_loaded |
| Turcon Roto Variseal | brand_name | Trelleborg | rwdr_ptfe_lip_spring_loaded |
| Variseal M2 | series_name | Trelleborg | rwdr_ptfe_lip_spring_loaded |
| Variseal HF | series_name | Trelleborg | rwdr_ptfe_lip_spring_loaded (static/face variant) |
| SKF PTFE seal | generic_term | SKF | rwdr_ptfe_lip_spring_loaded |
| PTFE Radialwellendichtring | generic_term | - | rwdr_ptfe_lip_* (family) |
| PTFE-RWDR | abbreviation | - | rwdr_ptfe_lip_* (family) |
| Teflon seal | colloquial | - | rwdr_ptfe_lip_* (family; Teflon is DuPont trademark for PTFE) |
| Lip seal PTFE | generic_term | - | rwdr_ptfe_lip_* (family) |
| Wellendichtring | generic_term | - | rwdr_elastomer_standard OR rwdr_ptfe_* depending on material |
| Oil seal | generic_term | - | rwdr_elastomer_standard (most common interpretation) |
| Shaft seal | generic_term | - | rwdr_* (family, requires disambiguation) |
| Radial shaft seal | generic_term | - | rwdr_* (family) |
| Dichtring | colloquial | - | rwdr_* OR static sealing element (requires disambiguation) |
| Cassette seal | series_name | multiple | rwdr_elastomer_cassette |
| RWDR | abbreviation | - | rwdr_* (family) |

## B.3 Disambiguation rules

Several terms are ambiguous and require contextual disambiguation. The Terminology Service applies rules like:

- **"Simmerring"** alone defaults to `rwdr_elastomer_standard` unless qualified by "PTFE" or context makes PTFE clear
- **"Shaft seal"** alone requires disambiguation between rotary (RWDR) and static; default to asking if context is insufficient
- **"Oil seal"** defaults to `rwdr_elastomer_standard` but triggers a language-agnostic clarification if the medium in the case is not oil
- **"Teflon"** is recognized as PTFE (trademark) but SeaLAI's generated text uses "PTFE" for clarity

Disambiguation prompts are part of the prompt library in `backend/app/prompts/terminology_disambiguation.j2`.

## B.4 Source attribution for seed data

The seed data above is compiled from:

- Public manufacturer websites (Freudenberg FST, Trelleborg, SKF, Parker, John Crane product pages)
- Standards documents (DIN 3760, ISO 6194-1)
- Industry glossaries (ESA European Sealing Association public materials where available)
- Founder's domain knowledge from work in PTFE-RWDR manufacturing

Every registry entry carries a `source_reference` pointing to the specific source. Trademarks are acknowledged on the `ProductTerm.is_trademark` field.

## B.5 Known gaps at MVP launch

The MVP seed does NOT cover:

- Japanese manufacturer terminology (NOK, etc.) — Phase 2
- Chinese manufacturer terminology — Phase 2+
- Niche mid-size European manufacturers' proprietary series names — grows through manufacturer onboarding
- Obsolete / legacy product names (DMS SKT series old names, etc.) — grows through community contributions
- Non-sealing cross-concept terms that users might accidentally use — handled as out-of-scope via §39.7

These gaps are acceptable for MVP because the coverage KPI (§40.8) measures against "top 100 PTFE-RWDR product names in the current market," not against historical completeness.

---

**Document end.** Next step: see the companion document `sealai_engineering_depth_ptfe_rwdr.md` for the engineering depth reference.

