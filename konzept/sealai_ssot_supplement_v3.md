# SeaLAI SSoT — Supplement v3.0 (Chapters 44–53)

**Status:** Binding supplement to `sealai_ssot_architecture_plan.md` v1.0, `sealai_ssot_supplement_v1.md`, and `sealai_ssot_supplement_v2.md`.
**Scope:** Implements the Product North Star principles as concrete schema extensions, service contracts, and design constraints. Introduces Fast Responder architecture, Problem-First Matching, Application Pattern Library, Small-Quantity Capability Model, Proactive Boundary Conditions Advisory, Cascading Calculation Engine, Medium Intelligence, Educational Output Contract, Multimodal Input Processing, and Knowledge-to-Case Bridge.
**Reader:** Written for Codex CLI and Claude Code during implementation. Rules are imperative and testable.
**Precedence:** Equal to base SSoT and supplements v1/v2. Where v3 adds a constraint, the constraint is binding. Where v3 conflicts with an earlier supplement on the same topic, v3 supersedes because it implements the Product North Star (which is at top of authority per CLAUDE.md §2).

---

## 44 — Fast Responder Architecture

### 44.1 Scope

This chapter defines a lightweight response path that runs **before** the main graph pipeline for non-case-creating interactions. It prevents the full graph from being invoked for greetings, meta-questions, and blocked content — both for performance and for preserving User Dignity (Product North Star §2.1).

### 44.2 Two-layer model

SeaLAI's runtime is organized into two layers:

**Layer 1 — Fast Responder.** Handles `GREETING`, `META_QUESTION`, `BLOCKED` classifications. No case is created. No persistence. No graph invocation. Direct LLM response with a bounded prompt. Latency target: 500ms–1s.

**Layer 2 — Full Graph Pipeline.** Handles `KNOWLEDGE_QUERY` and `DOMAIN_INQUIRY`. Invokes the full agent graph with three-mode gate, service layer, and persistence where applicable. Latency target: 10–30s for complex flows; shorter for partial state updates.

```
User input
     │
     ▼
Pre-Gate Classifier (supplement v2 §39, Decision #5)
     │
     ├─── GREETING      ──┐
     ├─── META_QUESTION  ─┤
     ├─── BLOCKED        ─┼──►  Fast Responder (Layer 1)
     │                    │         │
     │                    │         └─►  conversational_answer (no case)
     │
     ├─── KNOWLEDGE_QUERY ─┐
     │                     │
     └─── DOMAIN_INQUIRY  ─┴──►  Full Graph Pipeline (Layer 2)
                                    │
                                    ├─► Three-mode gate
                                    ├─► Case creation (if DOMAIN_INQUIRY)
                                    ├─► Knowledge service (if KNOWLEDGE_QUERY)
                                    └─► Output class derivation
```

### 44.3 Fast Responder service

```
backend/app/services/fast_responder_service.py
```

Interface:

```python
def respond(
    user_input: str,
    classification: PreGateClassification,  # GREETING | META_QUESTION | BLOCKED
    session_context: Optional[SessionContext],
) -> FastResponse
```

Where `FastResponse` contains:

- `output_class: str = "conversational_answer"`
- `content: str` (the reply text)
- `source_classification: PreGateClassification`
- `registration_prompt: Optional[RegistrationPrompt]` (shown for META_QUESTION if user might benefit from signing up)
- `no_case_created: bool = True` (explicit marker for consumers)

The service MUST:

- Call the LLM with a bounded prompt per classification type
- Return in under 2 seconds for 95% of calls (SLO)
- NOT write to Postgres
- NOT trigger the LangGraph agent
- NOT create any Case, CaseStateSnapshot, MutationEvent, or InquiryExtract

### 44.4 Classification boundary — hard restriction

Fast Responder MUST handle only the three listed classifications. **Adding any other classification is forbidden** without an explicit amendment to this supplement.

If the Pre-Gate Classifier returns an ambiguous or unsupported classification, the default is escalation to the Full Graph Pipeline (fail-safe towards the governed path).

### 44.5 Per-classification prompt design

Each classification has a narrowly scoped prompt template stored in `backend/app/prompts/fast_responder/`:

**GREETING prompt (gist, not verbatim):**
> *"The user has sent a greeting or short acknowledgment. Respond briefly and warmly. Offer to help. Do not ask for technical details. Example user inputs: 'Hallo', 'Moin', 'Guten Tag', 'Hi there', 'Danke'."*

Response characteristics:
- 1-3 sentences
- Friendly, not cold, not effusive
- Ends with a gentle offer ("Was kann ich für dich tun?" / "How can I help?")
- Localized to user's detected language

**META_QUESTION prompt (gist):**
> *"The user is asking about SeaLAI itself — what it does, what it can help with, how it works. Respond concisely with a plain-language summary. Do not claim capabilities that SeaLAI does not have. Reference these product truths: SeaLAI is a neutral technical translation platform for sealing technology. It helps users understand their sealing problems and connects them with manufacturers whose capabilities technically match. It does not sell seals itself."*

Response characteristics:
- 2-4 sentences
- Honest about scope (PTFE-RWDR as current MVP focus)
- Offers to demonstrate with a specific question if user wants

**BLOCKED prompt (gist):**
> *"The user input matched content-safety or scope rules for blocking. Politely decline in 1-2 sentences. Do not lecture. Offer an alternative path if possible (e.g., 'I can help with sealing technology questions — would you like to ask about that?')."*

Response characteristics:
- Brief
- No moralizing
- Redirect offered where appropriate

### 44.6 No persistence without registration

Fast Responder interactions are stateless from SeaLAI's persistence perspective:

- No Case object is created
- No tenant_id is required (session can be anonymous)
- Message history is kept only in the session's transient memory (Redis or frontend state)
- If the conversation evolves from GREETING → DOMAIN_INQUIRY, the user is invited to register, and the full graph pipeline begins a fresh case

This preserves Decision #6's tenant ownership model (user owns case, but anonymous sessions don't create cases).

### 44.7 Metrics and observability

The Fast Responder emits metrics:

- `fast_responder.invocations_total` (counter, per classification)
- `fast_responder.latency_seconds` (histogram)
- `fast_responder.escalated_to_graph_total` (counter, when classifier is uncertain)

If the fast responder's share of total traffic drops below 20%, it indicates either a classifier problem (misclassifying greetings as inquiries) or usage-pattern shift (fewer smalltalk starts). This should trigger analysis.

### 44.8 Testability

Fast Responder is testable without LangGraph imports (supplement v1 §33.8). Tests cover:

- Each of the three classifications with 5+ example inputs
- Language detection (German vs. English at minimum)
- Graceful handling of ambiguous inputs (escalation path)
- Latency budget compliance

---

## 45 — Problem-First Matching Architecture

### 45.1 Scope

This chapter fixes the direction of the matching algorithm: **from user problem to manufacturer capability**, not the reverse. It amends supplement v2 §41.7 to make the directionality explicit and enforceable.

### 45.2 The two possible directions — and why one is wrong

**Capability-First Matching (rejected):**
- Start with a manufacturer's declared capabilities
- Find problems the manufacturer can solve
- Present matching manufacturers to the user

This is what manufacturer-captive selector tools do. It optimizes for manufacturer fit and against neutrality. It allows the manufacturer's capability claims to implicitly filter the user's problem space.

**Problem-First Matching (required):**
- Start with the user's structured problem (engineering_path, operating envelope, application pattern, constraints)
- Derive the set of required capabilities
- Find manufacturers whose capability claims cover the required set
- Rank by technical fit score (supplement v2 §41.9)

### 45.3 Algorithm structure (binding)

The matching service MUST follow this structure:

```
def match_manufacturers(case: Case) -> list[ManufacturerMatch]:
    # Step 1: Extract problem signature from case
    problem = extract_problem_signature(case)
    #   engineering_path, sealing_material_family, operating_envelope,
    #   application_pattern_id (if matched), quantity, urgency, norm requirements

    # Step 2: Derive required capabilities
    required_capabilities = derive_required_capabilities(problem)
    #   list of CapabilityRequirement objects with (type, payload, strictness)

    # Step 3: Filter manufacturers by required capabilities
    candidates = filter_by_required_capabilities(required_capabilities)
    #   hard requirements filter as AND

    # Step 4: Score candidates on technical fit
    scored = [score_technical_fit(m, problem) for m in candidates]
    #   per supplement v2 §41.9

    # Step 5: Apply verification multiplier (narrow range)
    final_scores = [apply_verification(s) for s in scored]

    # Step 6: Return sorted list
    return sorted(final_scores, key=lambda m: m.total_score, reverse=True)
```

### 45.4 What MUST NOT happen

- Manufacturer capability claims MUST NOT filter the problem space before the problem is formulated
- Matching MUST NOT start with a manufacturer and derive fitting problems
- Marketing text of a manufacturer MUST NOT be in the matching signature (supplement v2 §37.2, §38.4)
- Sponsored listings MUST NOT receive matching-rank bonuses (supplement v2 §37.3)

### 45.5 Edge case — no manufacturer matches

When problem-first matching returns zero candidates, this is NOT a failure mode to hide. It is information:

- The user sees: "No registered manufacturer currently declares capability for your specific requirements. Your problem may require (a) relaxing one of your constraints, (b) waiting for a manufacturer to register, or (c) dispatching to manufacturers with adjacent capabilities for individual evaluation."
- The user can opt to dispatch the inquiry anyway to the top-K manufacturers with most adjacent capabilities — with explicit flagging that they do not fully cover the requirements

This preserves User Dignity (North Star §2.1 — never make the user feel stupid for having a niche problem) and is honest about platform limitations.

### 45.6 Integration with Application Patterns (§46)

If an Application Pattern is matched in the case, the required capabilities are derived largely from the pattern's pre-defined requirements. This accelerates matching and adds consistency.

### 45.7 Output shape

`ManufacturerMatch` contains:

```python
@dataclass
class ManufacturerMatch:
    manufacturer_id: UUID
    total_score: float                # 0-100 after verification multiplier
    technical_fit_score: float        # before multiplier
    verification_multiplier: float    # 0.9-1.1
    capability_coverage: CapabilityCoverage  # which required caps are met/unmet
    accepts_quantity_range: bool      # per user's quantity requirement
    estimated_lead_time_days: Optional[int]
    sponsored: bool = False           # always False in matching list
```

The `sponsored` field is present to make the separation from Featured listings (supplement v2 §43.4) explicit at the type level.

---

## 46 — Application Pattern Library

### 46.1 Scope

This chapter introduces the Application Pattern Library — a structured catalog of common sealing applications. Each pattern encodes the context of a typical problem, the parameters that are usually derivable from the context, the questions that still need to be asked, and the typical compound/type candidates.

Patterns are first-class data, not prose. They accelerate the consultation (North Star §3.1), reduce the number of questions asked of the user, and improve matching consistency.

### 46.2 Entity model

```python
ApplicationPattern
  pattern_id: UUID
  canonical_name: str                    # e.g., "chocolate_processing_melter"
  display_name: dict[str, str]           # localized, e.g. {"de": "Schokoladenverarbeitung — Wärmemantel-Anwendung"}
  triggering_contexts: list[str]         # keywords or phrases that suggest this pattern
  engineering_path: EngineeringPath       # e.g., rwdr
  typical_sealing_material_families: list[SealingMaterialFamily]
  auto_populated_fields: dict[str, FieldAutoValue]
     # fields the pattern pre-fills with typical-value-with-confidence
  required_clarification_fields: list[str]
     # fields the user MUST still provide; pattern cannot assume
  typical_operating_envelope: OperatingEnvelopeTemplate
  relevant_norm_modules: list[str]        # e.g., ["eu_food_contact", "fda_food_contact"]
  candidate_compound_families: list[str]  # ranked shortlist
  typical_failure_modes: list[str]        # relevant from supplement v2 §39 taxonomy
  quantity_profile: QuantityProfile       # typical batch size for this pattern
  educational_note: dict[str, str]        # localized, used by §51 Educational Contract
  provenance: Provenance                  # where the pattern data came from
  version: str
  created_at: TIMESTAMPTZ
  updated_at: TIMESTAMPTZ
```

### 46.3 MVP seed patterns

The MVP Pattern Library includes at minimum the following 14 patterns. All are relevant to the PTFE-RWDR MVP scope or to adjacent use cases that MVP users may realistically encounter.

**Pattern 1 — chemical_process_pump_aggressive_medium.** Chemie-Prozesspumpe mit aggressiven Medien (Säuren, Basen, Lösungsmittel). Anforderungen: chemische Beständigkeit, oft höhere Temperatur, oft Dry-Run-Risiko bei Leerlauf. Typische Compounds: ptfe_virgin, ptfe_carbon_filled, ptfe_graphite_filled (keine Bronze-Filler bei Säuren). Relevante Normen: ATEX, ggf. REACH.

**Pattern 2 — hydraulic_gearbox_standard.** Hydraulik-Getriebe mit mineralölbasiertem Hydrauliköl (HLP46, HLP68). Anforderungen: hohe Drücke zeitweise, mittlere Drehzahl, Temperatur 60-100°C, gute Schmierung vorhanden. Typische Compounds: ptfe_glass_filled, ptfe_bronze_filled. Typical failure modes: lip_wear_uniform, extrusion_failure.

**Pattern 3 — food_processing_chocolate_melter.** Schokoladenverarbeitung, Mantel-Anwendung. Anforderungen: Food-Grade-Compliance (EU 10/2011, FDA 21 CFR 177.1550), Temperaturen 40-80°C in Produktion (heiß-flüssig), CIP/SIP-Reinigung mit chemisch aggressiven Reinigern, klebende Rückstände auf Wellenlauf, Viskosität medium-hoch. Typische Compounds: ptfe_virgin (food-grade), bestimmte zertifizierte Füllstoff-Compounds. Typical failure modes: dust_induced_wear (Kakao-Abrieb), creep_induced_contact_loss (Stillstand, erstarrt).

**Pattern 4 — food_processing_dairy.** Milchverarbeitung (Pasteur, Käserei, Joghurt). Anforderungen: Food-Grade, CIP/SIP, hohe Hygiene-Anforderungen, Temperatur-Zyklen zwischen Reinigung (85°C Heißlauge) und Produktion (4-40°C). Typische Compounds: ptfe_virgin food-grade, bestimmte Elastomer-Alternativen (EPDM, FKM-FDA). Typical failure modes: chemical_attack (Lauge-bedingt), thermal_cycling.

**Pattern 5 — pharmaceutical_mixing.** Pharmazeutische Misch-Anwendung. Anforderungen: USP Class VI Certification, FDA, EU GMP compliance, extreme Reinheit, low-extractables, sterilisierbar. Typische Compounds: ptfe_virgin USP-grade, bestimmte FFKM-Alternativen. Pattern erwähnt explizit, dass PTFE-RWDR hier eine von mehreren legitimen Optionen ist, nicht immer die primäre Wahl.

**Pattern 6 — water_treatment_pump.** Wasseraufbereitung (Trinkwasser, Brauchwasser, Abwasser nicht-aggressiv). Anforderungen: KTW- oder NSF-Zertifizierung, mittlere Drücke, Temperatur-Range breit (5-40°C), oft kontinuierlicher Betrieb. Typische Compounds: ptfe_glass_filled KTW, ptfe_virgin mit bestimmten Zertifizierungen.

**Pattern 7 — automotive_gearbox_axle.** Automotive-Getriebe oder -Achse. Nicht MVP-Kern, aber häufiger Anfrage-Typ. Anforderungen: IATF 16949 häufig gefordert, Temperatur-Zyklen, oft Standard-Geometrien, hohe Stückzahlen bei Erstausrüstung aber kleine Stückzahlen bei Ersatzteil. Typische Compounds: ptfe_glass_filled, bestimmte HNBR/FKM als Alternativen.

**Pattern 8 — rotating_drum_mixer.** Rotierender Misch- oder Trommeltrockner mit partikelhaltigem Medium. Anforderungen: Abrieb-Resistenz, oft Staubseite-Schutz, Partikel auf der Luftseite können ins Lager wandern. Typische Compounds: ptfe_glass_filled höhere Füllgrade, ptfe_bronze_filled. Typical failure modes: dust_induced_wear, lip_wear_localized.

**Pattern 9 — compressor_sealing.** Kompressor-Wellendichtung (Luft, Gas, Kältemittel). Anforderungen: Druckbelastung, Temperatur oft erhöht durch Kompression, Gas-Dichtigkeit. Typische Compounds: ptfe_carbon_filled, ptfe_peek_filled bei hohen Drücken. Pattern erwähnt auch, dass Double-Lip- oder Tandem-Lösungen häufig notwendig sind.

**Pattern 10 — cryogenic_or_low_temperature.** Tieftemperatur-Anwendung (unter -40°C). Anforderungen: Kälte-Flexibilität des Materials, PTFE wird bei sehr niedrigen Temperaturen spröder. Typische Compounds: ptfe_virgin mit Vorsicht, PTFE mit weichen Füllstoffen, bestimmte Elastomer-Alternativen (Silikon bei einigen Anwendungen). Warnung: PTFE ist oft nicht die optimale Wahl unter -50°C.

**Pattern 11 — high_speed_spindle.** Hochdrehzahl-Spindel (Werkzeugmaschine, Zentrifuge). Anforderungen: hohe Oberflächen-Geschwindigkeiten (>15 m/s), gute Schmierung, präzise Welle. Typische Compounds: ptfe_carbon_filled, ptfe_peek_filled, ptfe_graphite_filled. Shaft-Anforderungen besonders kritisch (Ra < 0.2, präzise Plungergeschliffen).

**Pattern 12 — pump_dry_run_risk.** Standard-Pumpe mit Trockenlauf-Risiko (z. B. Dosierpumpe, die zeitweise leer läuft; Tauchpumpe mit Niveauschutz-Ausfall). Anforderungen: Dry-Run-Kompatibilität als primäre Anforderung. Typische Compounds: ptfe_graphite_filled, ptfe_mos2_filled, bestimmte bronze-filled mit Vorsicht. Pattern priorisiert Compound-Auswahl anders als Standard-Pumpen-Patterns.

**Pattern 13 — rebuild_replacement_individual.** Einzelersatz für gelaufene Dichtung, 1 Stück benötigt, oft mit Foto und/oder Artikelnummer einer bestehenden Dichtung anderen Herstellers. Dieses Pattern ist ein **Meta-Pattern** und kombiniert sich mit einem der anderen Patterns (z. B. "rebuild_replacement_individual + hydraulic_gearbox_standard" = Einzelersatz in einem Getriebe). Aktiviert Decision #1 Small-Quantity-Filtering (supplement v3 §47).

**Pattern 14 — generic_industrial_unclear.** Fallback-Pattern, wenn User-Kontext keinem spezifischen Anwendungsbereich zuzuordnen ist. Pattern sammelt nur die minimalen Pflichtfelder (Wellendurchmesser, Medium, Temperatur, Drehzahl), keine Auto-Population. Dient als "Safety Net" und signalisiert: *"Dein Fall ist nicht einem typischen Muster zuzuordnen — ich stelle dir einige Basis-Fragen und wir arbeiten uns gemeinsam durch."*

### 46.4 Pattern matching in intake

During intake, the Pre-Gate Classifier (Decision #5, §44) routes DOMAIN_INQUIRY cases to the pattern matcher:

1. Analyze user input for pattern-triggering contexts
2. Propose 1-3 candidate patterns with confidence
3. Present to user for confirmation or refinement
4. Adopt chosen pattern; auto-populate fields with typical values (user sees them as **proposed** with provenance `pattern_derived`, user can override)

Pattern matching is **explicit**, not silent. The user is told which pattern was selected and can switch. This preserves North Star §4.3 (never silently assume).

### 46.5 Extensibility

New patterns are added by:

1. Creating a new pattern record (UUID, canonical name, content)
2. Adding pattern to the seed data
3. Regression test that existing patterns still match their canonical triggering contexts

No code change is required to add a pattern. This is designed for growth — as SeaLAI encounters real cases, new patterns emerge from golden-case analysis (Decision #6).

### 46.6 Cross-reference

Patterns integrate with:

- §45 Problem-First Matching (pattern derives required capabilities)
- §47 Small-Quantity (quantity_profile on pattern feeds quantity filtering)
- §49 Cascading Calculations (pattern provides typical values for inputs not yet supplied)
- §50 Medium Intelligence (pattern names typical media for each application)
- §51 Educational Output (pattern's educational_note is a teaching entry)

---

## 47 — Small-Quantity Capability Model Extension

### 47.1 Scope

This chapter extends the ManufacturerCapabilityClaim schema (supplement v2 §41) to represent small-quantity acceptance as first-class. It also introduces the `quantity_requested` field as a mandatory user-facing intake field.

### 47.2 Why this is first-class

From the Product North Star §5:

> Users often need a small number of seals for specific problems. Standard catalog parts don't fit. Custom manufacturing is possible but has economics that many manufacturers avoid. SeaLAI's role is to make this transparent.

Current ManufacturerCapabilityClaim has a `lot_size_capability` capability type (supplement v2 §41.5), but its payload is minimal. This chapter specifies the payload precisely.

### 47.3 Extended lot_size_capability payload

```json
{
  "minimum_order_pieces": 1,
  "typical_minimum_pieces": 4,
  "maximum_order_pieces": 100000,
  "preferred_batch_size_range": [100, 10000],
  "accepts_single_pieces": true,
  "tooling_cost_range_eur": [500, 5000],
  "tooling_amortization_strategy": "per_order" | "shared_across_orders" | "customer_paid",
  "price_structure_example": {
    "quantity_1": "base_price + tooling_cost_full",
    "quantity_4": "base_price_with_small_discount + tooling_amortized",
    "quantity_10": "typical_small_batch_price",
    "quantity_100": "standard_series_price"
  },
  "rapid_manufacturing_available": true,
  "rapid_manufacturing_surcharge_percent": 50,
  "rapid_manufacturing_leadtime_hours": 72,
  "standard_leadtime_weeks": 4,
  "notes": "Staffelpreise gelten ab 1 Stück, Werkzeugkosten werden bei Erstauftrag berechnet."
}
```

### 47.4 Intake field `quantity_requested`

Every DOMAIN_INQUIRY case captures a `quantity_requested` field:

```python
QuantityRequested:
  pieces: int | Range[int]           # e.g., 1, or (5, 10)
  urgency: UrgencyLevel              # standard, elevated, rush
  context: QuantityContext           # single_replacement, small_series_new, prototype, production_series
  flexibility: bool                  # willing to order slightly more for better price
```

The field is captured during intake (possibly pattern-derived from Pattern 13 `rebuild_replacement_individual`).

### 47.5 Matching filter — hard for small quantity

If `quantity_requested.pieces <= 10`, the matching service filters:

- Manufacturers WHERE `lot_size_capability.accepts_single_pieces = true` AND `lot_size_capability.minimum_order_pieces <= quantity_requested.pieces`

This is a HARD filter — manufacturers that don't accept the quantity are not shown. Rationale: It's not useful to show a manufacturer who will reject the inquiry at first contact. Better to be transparent upfront.

### 47.6 Matching signal — soft for larger quantity

For `quantity_requested.pieces > 10`, the match is a soft signal:

- Manufacturers WHERE `lot_size_capability.preferred_batch_size_range` overlaps with `quantity_requested.pieces` receive a small positive score modifier
- No hard filter

### 47.7 User expectation management

Before the inquiry is dispatched, SeaLAI shows the user an expected-price-range estimate based on:

- Pattern's typical price range (from §46)
- Quantity factor
- Urgency surcharge
- Compound selection premium

Format (example, localized):

> *"Typische Preis-Erwartung für deinen Fall (PTFE-Glas, Chemie-Prozesspumpe, 4 Stück, Standard-Lieferzeit): 180–350 EUR pro Stück plus einmalige Werkzeugkosten 800–1500 EUR. Einzelne Hersteller können hiervon abweichen."*

This is **price context**, not price comparison (North Star §6.2). It prepares the user for realistic offers.

---

## 48 — Proactive Boundary Conditions Advisory

### 48.1 Scope

This chapter defines how SeaLAI proactively surfaces alternatives, warnings, and contextual advisories — without waiting for the user to ask. Implements North Star §3.2 (proactive validation) and §3.3 (teach while qualifying).

### 48.2 The "vielleicht ist PTFE-Glas sinnvoller" principle

Founder statement:

> *"Vielleicht ist ja PTFE-Glas sinnvoller"*

SeaLAI does not simply replicate what the user describes. If the user has a short-lived virgin PTFE seal in an abrasive slurry and asks for the same as replacement, SeaLAI surfaces: *"You might get longer service life with glass-filled PTFE in this application. Would you like me to explain why?"*

This is consultation, not order-taking.

### 48.3 Advisory policy — medium-conservative

Per Founder instruction (decision during v3 drafting):

- SeaLAI provides advisories ONLY when the minimum parameter set for evaluation is available
- Advisories include an explicit disclaimer: "Not all circumstances could be assessed."
- Advisories are emitted automatically as soon as data triggers them — the user does not need to ask

### 48.4 Advisory Note schema

Introduced as a new structured output element:

```python
@dataclass
class AdvisoryNote:
    advisory_id: str                  # unique within case
    category: AdvisoryCategory        # see below
    severity: AdvisorySeverity        # info, caution, warning
    triggering_parameters: list[str]  # which case parameters triggered this
    title: str                        # localized short
    body: str                         # localized explanation
    recommendation: str               # localized actionable suggestion
    alternative_options: list[AdvisoryAlternative]
    rationale_references: list[Reference]  # norms, engineering guide sections, registry entries
    disclaimer: str                   # localized disclaimer template
    dismissable: bool = False         # whether user can dismiss permanently
    created_at: TIMESTAMPTZ
```

### 48.5 Advisory categories

Initial categories (extensible):

**MATERIAL_SUBOPTIMAL.** Current or proposed material is inferior to an alternative for the specific application. Example: virgin PTFE in abrasive slurry → glass-filled preferable.

**LIFESPAN_EXPECTATION_MISMATCH.** Expected service life appears unrealistic given parameters. Example: user wants 5-year service with Compound X in condition Y, but typical life is 1-2 years.

**SHAFT_REQUIREMENTS_CONCERN.** Shaft specifications may be inadequate for the proposed seal. Example: Ra > 0.6 for PTFE seal → premature wear likely.

**NORM_COMPLIANCE_ALERT.** User's application may trigger norm requirements they haven't indicated. Example: user mentions food contact; FDA 21 CFR 177.1550 applies.

**DRY_RUN_RISK.** Application may have dry-run conditions the user hasn't noted; compound may not tolerate.

**MEDIUM_INCOMPATIBILITY_HINT.** Medium + compound combination has known risks beyond chemical compatibility (e.g., swelling, extraction, color changes).

**INSTALLATION_CONCERN.** Installation context (shaft step, missing chamfer, mounting method) risks installation damage.

**QUANTITY_ECONOMIC_CONSIDERATION.** Quantity is in a range where ordering slightly more / less shifts manufacturer availability significantly.

### 48.6 When advisories are generated

The advisory engine runs after each of the following:

- User completes a pattern selection (§46)
- User provides a new parameter value
- A cascading calculation (§49) produces a new derived value
- Medium Intelligence (§50) identifies a medium

The engine is deterministic: rules map parameter combinations to advisories. Rules are implemented as Python functions in `backend/app/services/advisory_engine.py`, not in YAML (per Founder Decision to consolidate away from YAML rules).

### 48.7 Advisory rendering in output

Advisories appear in the case output (cockpit projection) as a dedicated section. They are NOT part of the output class itself — they co-exist with whatever output class the case produces (`governed_state_update`, `technical_preselection`, etc.).

User-facing UI renders advisories as cards or panels with clear visual distinction from parameters and results.

### 48.8 Disclaimer template

Every advisory carries a disclaimer:

> *"Diese Hinweise basieren auf den bisher erfassten Parametern. Nicht alle Umstände deines konkreten Falls konnten berücksichtigt werden. Der finale Hersteller prüft deine Anfrage fachlich und schlägt ggf. Ergänzungen oder Alternativen vor."*

English equivalent provided. The disclaimer is rendered verbatim; localization is stored in the prompt library.

### 48.9 Advisory vs. blocker — boundary

Advisories are ADVISORY. They do NOT block the case from reaching inquiry_ready. The user is informed and proceeds as they wish.

Norm-module violations, in contrast, DO block (supplement v3 §46.7 and supplement v2 §39-related norm-gate logic). The difference: norm violations are hard compliance failures; advisories are judgment-improving hints.

---

## 49 — Cascading Calculation Engine

### 49.1 Scope

This chapter specifies the Cascading Calculation Engine — the service that automatically executes PTFE-RWDR engineering calculations as soon as their required inputs become available, including recursively triggering follow-on calculations that become possible with new derived values.

Implements Founder's direct statement:

> *"Es sollen die Berechnungen direkt ausgeführt werden sobald die benötigten Informationen vorliegen. Es sollen bei den Berechnungen auch Folgeberechnungen automatisch stattfinden die eventl. mit dem Berechnungsergebnis aus der Erst-Berechnungsebene zusätzlich möglich sind. Das ist für einen Ingenieur auch aufwendig, wenn er die Berechnungen aus den Formelbüchern per Hand machen muss."*

### 49.2 Why this is a core USP

For a sealing engineer, running cascading calculations manually with reference books is hours of work. SeaLAI doing this automatically — synchronously, while the user is entering data — is a concrete, measurable time-saving. This is the Product North Star §3.4 principle in code: SeaLAI takes off the manufacturer's plate what the manufacturer would otherwise have to do.

### 49.3 Architecture — synchronous by design

**Decision (MVP): Synchronous execution in the same request.**

When a case's parameters change (user input, pattern selection, medium intelligence result, another calculation's output), the calculation engine:

1. Identifies which calculations have all their required inputs satisfied
2. Executes them in dependency order
3. Writes results to the case state
4. Identifies calculations newly satisfiable by these results
5. Repeats until fixpoint (no more calculations become satisfiable)
6. Returns the updated case state in the same request

Typical PTFE-RWDR cascade: 5-7 calculations, executes in 10-50 milliseconds. Synchronous is the right tradeoff for this volume.

**Why not asynchronous outbox:** Asynchronous processing is designed for real side-effects (external API calls, notifications, expensive re-computations). Microsecond formula evaluations don't need it, and it would introduce user-visible latency where the user expects immediate feedback.

Async processing remains appropriate for: risk-score recomputes after norm-gate verification requiring external certificate lookups; golden-case anonymization pipeline; manufacturer notification dispatch. These remain outbox-based.

### 49.4 Calculation dependency graph

Each calculation declares:

```python
@dataclass
class CalculationDefinition:
    calc_id: str                          # e.g., "circumferential_speed"
    version: str                          # semantic version
    required_inputs: list[FieldPath]      # e.g., ["shaft.diameter_mm", "operating.shaft_speed.rpm_nom"]
    optional_inputs: list[FieldPath]      # improves precision if present
    outputs: list[FieldPath]              # e.g., ["derived.surface_speed_ms"]
    applicable_when: Callable[[Case], bool]  # gating predicate (e.g., only for rwdr)
    formula: Callable[..., CalcResult]
    fallback_behavior: FallbackSpec       # what to do on missing input
    provenance: Provenance                # source reference
```

### 49.5 MVP PTFE-RWDR calculation cascade

The minimal set of calculations for MVP, all defined in `backend/app/services/formula_library/ptfe_rwdr/`:

**circumferential_speed** (calc_id = "ptfe_rwdr.circumferential_speed")
- Inputs: shaft.diameter_mm, operating.shaft_speed.rpm_nom
- Output: derived.surface_speed_ms
- Formula: v = π · D / 1000 · n / 60
- Used by: risk.surface_speed, contact_pressure (below)

**contact_pressure** (calc_id = "ptfe_rwdr.contact_pressure")
- Inputs: rwdr.lip.radial_force_n_per_mm, rwdr.lip.contact_width_mm
- Output: derived.contact_pressure_n_per_mm2
- Formula: p = F / w
- Used by: pv_loading

**pv_loading** (calc_id = "ptfe_rwdr.pv_loading")
- Inputs: derived.contact_pressure_n_per_mm2, derived.surface_speed_ms
- Output: derived.pv_loading
- Formula: PV = p · v
- Used by: thermal_load_indicator, creep_gap_estimate_simplified, risk.wear

**thermal_load_indicator** (calc_id = "ptfe_rwdr.thermal_load_indicator")
- Inputs: derived.pv_loading, compound friction coefficient (from registry), shaft.diameter_mm
- Optional: lubricant thermal conductivity factor
- Output: derived.heat_flux_w_per_mm
- Formula: heat_flux ≈ PV · friction_coefficient · π · D
- Used by: risk.thermal

**extrusion_gap_check** (calc_id = "ptfe_rwdr.extrusion_gap_check")
- Inputs: operating.pressure.max_bar, extrusion gap (shaft clearance), compound family
- Output: derived.extrusion_safety_margin
- Used by: risk.pressure

**creep_gap_estimate_simplified** (calc_id = "ptfe_rwdr.creep_gap_estimate_simplified")
- Inputs: rwdr.lip.radial_force_n_per_mm, operating.temperature.nom_c, compound family, expected_service_duration_years
- Output: derived.estimated_creep_gap_um
- Used by: risk.creep_longevity

**compound_temperature_headroom** (calc_id = "ptfe_rwdr.compound_temperature_headroom")
- Inputs: operating.temperature.max_c, compound family
- Output: derived.temperature_headroom_c
- Used by: risk.thermal

### 49.6 Execution algorithm

```python
def execute_cascade(case: Case) -> tuple[Case, list[CalcExecutionRecord]]:
    """Run cascading calculations to fixpoint. Returns updated case and log."""
    executed = []
    changed = True
    guard = 0
    while changed and guard < MAX_CASCADE_ITERATIONS:
        changed = False
        for calc_def in registered_calculations:
            if already_executed_with_current_inputs(calc_def, case):
                continue
            if not calc_def.applicable_when(case):
                continue
            if not has_all_required_inputs(calc_def, case):
                continue
            result = execute_calculation(calc_def, case)
            case = apply_result_to_case(case, result)
            executed.append(
                CalcExecutionRecord(
                    calc_id=calc_def.calc_id,
                    version=calc_def.version,
                    inputs_used=...,
                    outputs_produced=...,
                    provenance="calculated",
                )
            )
            changed = True
        guard += 1
    if guard >= MAX_CASCADE_ITERATIONS:
        raise CascadeLoopError("calculation cascade did not converge — likely circular dependency")
    return case, executed
```

`MAX_CASCADE_ITERATIONS` = 20 (generous; typical cascades are 3-5 iterations).

### 49.7 Provenance

Every derived value carries `provenance = "calculated"` with:

- The `calc_id` and `version` that produced it
- The input values used (captured at execution time for audit)
- Timestamp

If the user later changes an input, the calc is marked stale (per supplement v1 §34 stale-invalidation semantics) and re-executed.

### 49.8 Integration with Risk Engine

The Risk Engine (supplement v3 §47 advisory categories and Engineering Depth Guide §8) consumes calculation outputs. When a calculation updates, the relevant risk dimension is re-scored synchronously in the same cascade.

### 49.9 Testability

Tests cover:

- Each calculation with known inputs and expected outputs (unit)
- Cascade order stability (given same inputs, same execution order)
- Fixpoint convergence (no infinite loops)
- Missing-input fallback (calc returns `insufficient_input` with flagged missing fields)
- Stale recomputation on input change

### 49.10 Extensibility

Adding a new calculation (e.g., for elastomer-RWDR in Phase 2) requires:

1. Writing the CalculationDefinition
2. Registering it in the calculation registry
3. Declaring its engineering_path applicability
4. Providing unit tests

No schema change is required. This is the Selective Rewrite strategy in action.

---

## 50 — Medium Intelligence Service

### 50.1 Scope

This chapter specifies the Medium Intelligence Service — the component that, when a user enters a medium name (e.g., "Schokolade", "Hydrauliköl HLP46", "Natronlauge 10%"), extracts and presents structured information about the medium and its implications for seal material selection.

Implements Founder's direct statement:

> *"Wenn der User das Medium eingegeben hat soll das LLM sämtliche relevanten Informationen die es zu dem Medium hat aus seinem Wissen ausgeben und in einer separaten Kachel anzeigen. Wie zb Viskosität, oder aggressiv etc. alles was für das Material und Dichtung wichtig ist. Es soll auch eine kleine Abhandlung in einer Kachel angezeigt werden damit der User sich ein Bild von seinem Medium machen kann um zu verstehen warum das Material so ausgewählt wird."*

### 50.2 The three-tier provenance model

This service is explicitly LLM-augmented. To preserve North Star §7.5 (never pretend to know what we don't), all Medium Intelligence output carries provenance at three tiers:

**Tier 1 — Registry-grounded facts.** Data from a curated medium registry (chemical database, standard material tables). Shown with high confidence, no special disclaimer.

**Tier 2 — LLM plausibility synthesis.** LLM-generated information based on its general knowledge. Clearly labeled *"Plausibilitäts-Schätzung, bitte im konkreten Fall prüfen"* (or English equivalent).

**Tier 3 — User-provided.** The user told SeaLAI the medium name or its properties. Treated as given, but SeaLAI may still cross-check registry.

Visual distinction in UI is required. Registry facts render without a "plausibility" badge; LLM synthesis renders with one.

### 50.3 Medium Registry schema

Separate from but coexisting with Terminology Registry (supplement v2 §40):

```python
MediumEntry
  medium_id: UUID
  canonical_name: str                  # e.g., "sulfuric_acid_50pct"
  display_name: dict[str, str]
  aliases: list[str]                   # colloquial names, trade names, abbreviations
  chemical_class: MediumClass          # acid, base, hydrocarbon, food_grade, aqueous, ...
  aggressiveness: AggressivenessScore  # 1-10 scale
  ph_range: Optional[tuple[float, float]]
  viscosity_range_mPas: Optional[tuple[float, float]]
  viscosity_temperature_sensitivity: Optional[str]  # low/medium/high
  typical_temperature_range_c: Optional[tuple[float, float]]
  boiling_point_c: Optional[float]
  vapor_pressure_at_temp: Optional[dict]  # temp→vapor pressure
  flash_point_c: Optional[float]
  food_grade_applicable: bool
  pharmaceutical_grade_applicable: bool
  compound_compatibility_notes: dict   # compound_family → (rating, notes)
  typical_challenges: list[str]        # e.g., ["abrasive_particles", "oxidizing", "viscous_at_low_temp"]
  typical_applications: list[UUID]     # ApplicationPattern ids
  references: list[Reference]
  provenance: Provenance               # "registry" for curated entries
  version: str
  updated_at: TIMESTAMPTZ
```

MVP registry seeds with approximately 50 entries covering:
- Common hydraulic/gear oils (HLP46, HLP68, ATF, SAE grades)
- Common acids (sulfuric, hydrochloric, nitric at various concentrations, organic acids)
- Common bases (sodium hydroxide, potassium hydroxide)
- Food media (milk, chocolate, various oils, sugar solutions)
- Aqueous media (drinking water, sea water, process water, condensate)
- Solvents (acetone, ethanol, isopropanol, toluene, xylene)
- Pharmaceutical media (WFI, various APIs)
- Refrigerants (common R-series)
- Cleaning chemicals (CIP/SIP alkaline and acidic)

### 50.4 Medium Intelligence Service interface

```python
def get_medium_intelligence(
    medium_query: str,              # user's free-text medium name
    temperature_c: Optional[float], # helps LLM context
    application_context: Optional[str]  # e.g., pattern name
) -> MediumIntelligenceResult
```

Where `MediumIntelligenceResult` contains:

```python
@dataclass
class MediumIntelligenceResult:
    matched_registry_entry: Optional[MediumEntry]
    llm_synthesized_properties: dict[str, PropertyWithProvenance]
    medium_summary: str              # "kleine Abhandlung" localized
    material_selection_rationale: str  # why certain materials are suited
    compound_recommendations: list[CompoundRecommendation]
    risk_notes: list[AdvisoryNote]   # feed into Advisory Engine §48
    confidence_level: ConfidenceLevel
    references: list[Reference]
    provenance_tier: ProvenanceTier
```

### 50.5 Processing flow

1. **Normalize user input.** Remove trailing descriptors, strip obvious typos (using a lenient matcher).

2. **Attempt Registry match.** Fuzzy match against canonical names and aliases. If matched with high confidence → return tier-1 data.

3. **If no registry match.** Delegate to LLM with a bounded prompt:
   *"The user entered medium: '{medium_query}' in application context: '{context}'. Provide structured information about this medium relevant to seal material selection. If you are not confident about a property, say so explicitly. Do not guess numerical values without stating uncertainty."*

4. **Parse LLM response into structured fields.** Each field tagged with provenance `llm_synthesis` and confidence.

5. **Run cross-checks.** E.g., if LLM says "low aggressiveness" but name contains "acid", flag inconsistency.

6. **Generate medium summary** (the "kleine Abhandlung"). LLM-assisted, 3-5 sentences, describes: what the medium is, why it matters for sealing, typical challenges.

7. **Generate material selection rationale.** LLM explains why certain PTFE compounds (or elastomers if applicable) are suited, with specific reasoning tied to the medium's properties. Links to Compound Taxonomy (Engineering Depth Guide §3).

8. **Identify advisory-triggering conditions.** Pass relevant flags to Advisory Engine (§48) — e.g., "food_grade_applicable → food-norm-module trigger", "aggressiveness > 7 → material selection advisory".

### 50.6 UI rendering — the "separate Kachel"

The Medium Intelligence output renders as a dedicated UI card (Kachel) visible to the user during intake. Sections:

**Section 1 — Identifikation.** Matched name, chemical class, confidence level. If registry-matched, green checkmark. If LLM-synthesized, yellow badge.

**Section 2 — Eigenschaften.** Structured table of properties (viscosity, pH, temperature range, aggressiveness, etc.) with per-property provenance tags.

**Section 3 — Abhandlung.** The "kleine Abhandlung" prose — readable, 3-5 sentences, explaining the medium's characteristics for seal selection.

**Section 4 — Warum dieses Material?** The material selection rationale. This is where the user gets the understanding of why a PTFE-Glass (say) vs. virgin PTFE is proposed. This is North Star §3.3 (teach while qualifying) in direct action.

**Section 5 — Hinweise.** Any risk notes or advisories — linked to Advisory Engine.

### 50.7 Integration with Knowledge Service

If a user reads the Medium Intelligence card and wants to go deeper ("Warum genau diese Aggressivität?", "Was ist WFI genau?"), the query is routed to the Knowledge Service (Decision #8 / §53). This preserves the "teach while qualifying" thread without blowing up the Medium Intelligence surface.

### 50.8 Caching

Medium Intelligence results are cached per (medium_query, temperature, application_context) tuple. Cache expiry: 7 days for LLM-synthesized, indefinite for registry-matched (invalidated only on registry updates).

### 50.9 Curation feedback

When users correct Medium Intelligence output (e.g., flag as wrong), this goes to a review queue. Human curator (initially the founder, later a domain specialist) evaluates and, if appropriate, updates the registry. Over time, LLM-synthesis fraction decreases as registry grows.

---

## 51 — Educational Output Contract

### 51.1 Scope

This chapter defines how SeaLAI embeds educational content in its interactions — the "teach while qualifying" principle (North Star §3.3) as a concrete output contract.

### 51.2 Design philosophy

Every field that SeaLAI asks the user or presents to the user is an opportunity to teach. But educational content must not overwhelm. The rule: **educational content is available on demand, or auto-shown for novices; advanced users see it collapsed.**

### 51.3 Educational Note schema

Fields in the case schema can carry educational metadata:

```python
FieldDefinition:
  field_path: str
  name_localized: dict[str, str]
  description_short: dict[str, str]
  educational_note_localized: dict[str, str]  # 1-3 paragraphs
  educational_examples: list[EducationalExample]
  references: list[Reference]
  importance_tier: ImportanceTier            # always_show, show_if_novice, show_on_demand
```

Pattern entries (supplement v3 §46) carry their own educational_note for pattern-level teaching.

Advisory Notes (supplement v3 §48) inherently teach through their body and recommendation.

### 51.4 User experience proficiency detection

SeaLAI detects (heuristically, from behavior) whether the user is a novice or experienced:

**Novice signals:**
- Asks basic questions ("What is a Simmerring?")
- Provides few parameters spontaneously
- Uses colloquial terms

**Experienced signals:**
- Uses technical terminology correctly
- Provides structured parameters upfront
- References specific norms or products

Proficiency level is stored as session state and influences educational content display:

- Novice: educational notes auto-expanded, more advisories shown
- Intermediate: default collapsed, easy to expand
- Experienced: minimal educational chrome, focus on data

### 51.5 Educational surfaces

Educational content appears in these places:

**Parameter fields.** Each field can show a "what is this?" icon. Hover or tap reveals the educational note. For novices: auto-shown when field is focused.

**Pattern selection.** When user chooses a pattern, the pattern's educational_note explains the application class briefly.

**Medium Intelligence card (§50).** Section 4 "Warum dieses Material?" is inherently educational.

**Advisory Notes (§48).** Every advisory explains *why* the advisory exists.

**Output explanations.** When SeaLAI produces a result (technical_preselection, etc.), a "How did SeaLAI arrive at this?" link opens a breakdown showing the cascade of rules and calculations that led there.

### 51.6 Content sources

Educational content is authored (not LLM-generated for novice-facing surfaces, to preserve accuracy):

- Field-level educational notes: authored in field definition files, reviewed, versioned
- Pattern-level: part of pattern data, reviewed, versioned
- Advisory explanations: part of advisory rules, reviewed
- "How did SeaLAI arrive at this?" breakdowns: deterministic rendering of the rule/calculation trace, no LLM

LLM-generated educational content is reserved for Knowledge Service (§53) where the user explicitly asks a free-form question.

### 51.7 Anti-patterns

Educational content MUST NOT:

- Be condescending or make the user feel stupid (North Star §2.1)
- Assume the user lacks intelligence — assume they lack domain exposure
- Pad the interface — show only what's relevant to the current task
- Replace clear information architecture — if educational content is needed to understand a field, the field label is unclear and should be improved

### 51.8 Evolution

Educational content is refined as golden cases (Decision #6) reveal misunderstandings. A user who misinterpreted a field signals an opportunity to improve the educational note.

---

## 52 — Multimodal Input Processing Contract

### 52.1 Scope

This chapter concretizes North Star §4 — heterogeneous and multimodal input as first-class. It defines contracts for each input type, per-type extraction expectations, and how extracted information flows into the case.

### 52.2 Supported input types

MVP supports:

1. **Photo of seal or installation context.** JPEG, PNG, WebP up to 10MB.
2. **Article number / part designation.** Free text like "NOK PG32 28x45x7", "Simmerring BAUSL 30x52x7".
3. **Datasheet fragment.** Image or PDF page up to 5MB.
4. **Dimensional sketch.** Hand-drawn or CAD-derived image.
5. **Free-text description.** Unstructured German or English.

### 52.3 Intake contract — shared across types

For every input, the processor produces:

```python
@dataclass
class IntakeExtraction:
    input_type: InputType
    raw_input_reference: str          # path or opaque ref
    extracted_parameters: dict[FieldPath, ExtractedValue]
    confidence_per_parameter: dict[FieldPath, ConfidenceScore]
    provenance: Provenance            # "user_photo", "user_article_number", etc.
    extraction_model_version: str
    user_verification_required: bool  # True if low confidence or ambiguity
    clarification_questions: list[ClarificationQuestion]
    notes: str
    timestamp: TIMESTAMPTZ
```

Extracted parameters are **proposals**, not ground truth. The user is always asked to confirm or correct (North Star §4.3).

### 52.4 Photo processing

**Service:** `backend/app/services/photo_analysis_service.py`

**What the service attempts:**

- Seal type classification (single-lip, double-lip, cassette, V-ring, etc.) — from visible geometry
- Compound family estimation (virgin PTFE vs. filled vs. elastomer) — from color and surface appearance
- Damage mode identification (wear pattern, spiral failure, extrusion, creep, etc.) — from visible damage
- Dimension estimation — only if reference scale is present (e.g., coin, ruler)
- Installation context — if housing/shaft visible

**What the service does NOT claim:**

- Exact compound composition
- Exact dimensions without scale reference
- Service history without context
- Definitive damage root cause (that's RCA territory, deferred to Phase 2)

**Output** is a set of `extracted_parameters` with low-to-medium confidence, plus clarification questions like: "I see what appears to be a single-lip PTFE seal with wear on the contact band. Can you confirm the seal diameter?"

### 52.5 Article number decoding

**Service:** `backend/app/services/article_number_decoder_service.py`

**Pattern recognition:**

- Known manufacturer codes (NOK, SKF, Freudenberg, Simrit, Parker, etc.)
- Standard DIN/ISO-derived codes (BAUSL → DIN 3760 Type AS; similar decoders for other common notations)
- Dimensional triples (28x45x7 → ID × OD × W)

**Knowledge source:** Terminology Registry (supplement v2 §40) with manufacturer-specific series mappings.

**Output:**

- Decomposed fields: manufacturer, series, type, dimensions
- Equivalence mapping to generic concept (e.g., "this is a DIN 3760 AS with NBR 70")
- Typical operating envelope for this part

**Handling unknown article numbers:** Graceful fallback. Don't invent. Ask user for clarification: "I don't recognize this article number. Could you tell me the seal type and dimensions, or the manufacturer?"

### 52.6 Datasheet fragment processing

**Service:** `backend/app/services/datasheet_extraction_service.py`

**Approach:** OCR + structured extraction (table recognition, key-value extraction) with LLM assistance for formatting variance.

**Extracted fields:** Whatever structured data is visible — dimensions, material, temperature ranges, pressure ratings, certifications.

**Output** with provenance `documented` per base SSoT §9.

### 52.7 Dimensional sketch processing

MVP support is limited — we accept the input but don't OCR handwritten dimensions reliably. The sketch is stored as evidence, and the user is asked to transcribe key dimensions. Future phase can improve this.

### 52.8 Free-text processing

Handled by the intake LLM (intake_observe node evolution). LLM extracts proposed parameters, marks confidence, asks clarifying questions. Standard behavior per supplement v1 §33 LangGraph role.

### 52.9 Conflict handling across inputs

If the user provides both a photo and an article number that disagree (photo shows cassette, article number decodes as single-lip), SeaLAI:

1. Presents the conflict to the user explicitly
2. Asks which input is authoritative
3. Does not silently pick one

This preserves honesty and User Dignity (user may have sent the wrong photo, the wrong article number, etc. — no blame).

### 52.10 Privacy and data handling

User-uploaded photos may contain identifying information (facility names, logos, serial numbers). Per Decision #3 and #6:

- Photos are retained only on the user's case (not in manufacturer extracts)
- If a case becomes a golden case, photos are stripped (not embedded) and replaced with anonymized descriptions
- EXIF metadata is removed from stored photos

---

## 53 — Bridge from Knowledge to Case

### 53.1 Scope

This chapter concretizes Decision #8 — the seamless transition from a KNOWLEDGE_QUERY interaction into a DOMAIN_INQUIRY (case creation). The bridge preserves context accumulated during knowledge exploration and invites the user to move forward without friction.

### 53.2 The user journey

**Phase A — Knowledge exploration.** User asks general questions ("What's the difference between FKM and PTFE?"). Fast path (§44 → KNOWLEDGE_QUERY → Knowledge Service) responds with curated answers and attribution. No case is created.

**Phase B — Emerging specificity.** User moves toward a concrete problem. Signals include:
- Mentions their own context ("I have a pump with...")
- Asks for a specific recommendation
- Expresses intent to find a manufacturer
- Provides parameters (shaft diameter, medium, etc.)

**Phase C — Invitation to case.** SeaLAI detects the transition and invites:

> *"It sounds like you're describing a specific application. Would you like me to do a structured qualification of your case? I can help you identify matching manufacturers. This would create a case you can return to anytime."*

**Phase D — Case creation.** User accepts. SeaLAI:
- Asks for registration (or uses existing auth)
- Creates a case with `tenant_id` set
- Transfers accumulated context from the knowledge session into the new case:
  - Any parameters the user has already mentioned
  - The user's apparent application pattern (if identifiable)
  - Relevant knowledge entries for future reference

### 53.3 Transition detection

The Pre-Gate Classifier, in KNOWLEDGE_QUERY mode, watches for transition signals on each user turn:

```python
def detect_transition_signal(
    turn_text: str,
    knowledge_session_context: KnowledgeSessionContext
) -> TransitionSignal
```

Signals:

- Possessive references: "my pump", "our application", "meine Anlage"
- Concrete parameters: numbers with units (mm, bar, °C, rpm)
- Outcome-seeking: "what should I use?", "which one is best for me?"
- Match-seeking: "where do I buy", "who makes"

If any signal is present with confidence above threshold, the bridge invitation is issued at the end of SeaLAI's response to the user's current turn.

### 53.4 Context accumulation during knowledge session

Knowledge sessions are anonymous, transient, but SeaLAI accumulates context within the session:

```python
KnowledgeSessionContext:
  session_id: str                  # transient, non-persistent
  turn_history: list[KnowledgeTurn]
  mentioned_parameters: dict[FieldPath, ExtractedValue]
  explored_concepts: list[UUID]    # knowledge base entries viewed
  detected_intent: Optional[str]   # e.g., "learning", "product_comparison", "application_planning"
  transition_offered: bool
  created_at: TIMESTAMPTZ
  last_activity_at: TIMESTAMPTZ
```

On transition to case, this context is transformed into a seed Case with provenance `knowledge_session_seed`.

### 53.5 Registration flow at bridge point

If the user accepts the bridge invitation and is not registered:

1. Light-touch registration prompt: "To save your case and dispatch inquiries to manufacturers, please register." (minimal fields: email, password, company optional, role dropdown)
2. Keycloak signup
3. Case created with new tenant_id
4. Knowledge session context transferred
5. Continuation seamless (user doesn't start over)

If the user declines registration, the knowledge session continues, case is not created, user can still get knowledge answers but not a qualified inquiry dispatch.

### 53.6 Back-transition

A user in a case can also ask knowledge questions (e.g., "While we're here, what's the difference between glass-filled and bronze-filled PTFE?"). The Pre-Gate Classifier detects KNOWLEDGE_QUERY within an active case and routes to Knowledge Service for the answer; the case state is not disturbed.

This bi-directional flow is the practical realization of "teach while qualifying" (North Star §3.3).

### 53.7 Measurement

SeaLAI tracks:

- Knowledge-to-case conversion rate (sessions that transitioned / total knowledge sessions)
- Bridge invitation acceptance rate
- Case completion rate post-bridge-origin vs. direct-intake-origin

These metrics inform knowledge base curation and intake UX over time.

---

## Cross-reference index (v3)

| Base SSoT / earlier supplement chapter | Amended or extended by v3 |
|----------------------------------------|----------------------------|
| Base SSoT §7 (Case model) | §46 Application Pattern, §47 quantity_requested field |
| Base SSoT §10 (Output classes) | §48 AdvisoryNote as cross-cutting output element |
| Base SSoT §14 (Checks registry) | §49 Cascading Calculation Engine (supersedes registry pattern with synchronous execution graph) |
| Base SSoT §22 (Compatibility engine) | §50 Medium Intelligence integrates compatibility |
| Supplement v1 §33 (LangGraph role) | §44 Fast Responder Architecture (pre-graph layer) |
| Supplement v1 §34 (Consistency/Outbox) | §49 Cascading Calculations as synchronous exception to async outbox |
| Supplement v2 §37 (Moat) | §45 Problem-First Matching enforces Layer 2 |
| Supplement v2 §39 (MVP scope) | §46 Patterns fit within MVP scope (PTFE-RWDR-aligned) |
| Supplement v2 §40 (Terminology) | §50 Medium Registry is a parallel registry |
| Supplement v2 §41 (Capability model) | §47 Small-Quantity extension |
| Founder Decision #5 (Pre-Gate) | §44 makes Pre-Gate operational |
| Founder Decision #8 (Knowledge) | §53 Bridge operationalizes bi-directional flow |

## Final binding rule

Supplement v3 implements the Product North Star as concrete technical specifications. It sits at the same precedence level as base SSoT and supplements v1/v2. Where v3 adds a constraint, it is binding. Where v3 conflicts with an earlier supplement on the same topic, v3 supersedes — because it carries the Product North Star into technical reality, and the Product North Star is at the top of authority per CLAUDE.md §2.

Fast Responder handles smalltalk efficiently. Problem-First Matching enforces neutrality. Application Patterns accelerate consultation. Small-Quantity Capability serves real user needs. Proactive Advisory teaches while qualifying. Cascading Calculations take engineering work off the manufacturer's plate. Medium Intelligence makes the user understand their problem. Educational Output respects user dignity. Multimodal Input accepts users as they arrive. Knowledge-to-Case Bridge respects user time.

These are not independent features. They are the operationalization of "verstehen und führen, ohne den User dumm dastehen zu lassen" — understand and guide without making the user look stupid.

---

**Document end.**

