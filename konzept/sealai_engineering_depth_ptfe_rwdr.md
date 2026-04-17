# SeaLAI Engineering Depth Guide — PTFE-RWDR

**Version:** 1.0
**Datum:** 2026-04-17
**Status:** Binding engineering reference for MVP depth target
**Precedence:** Equal to base SSoT and supplements v1/v2 for all PTFE-RWDR engineering decisions
**Companion to:** `sealai_ssot_supplement_v2.md` §39 (MVP scope) and §42 (engineering depth reference)

---

## Preamble — what this document is and is not

This document is a technical reference. It fixes:

- the PTFE-compound taxonomy SeaLAI uses
- the mandatory and optional schema fields for PTFE-RWDR cases
- the failure-mode vocabulary (controlled list, not free text)
- the physics-based checks SeaLAI computes
- the risk-score inputs and thresholds
- the shaft-side engineering requirements

It is not:

- a textbook on sealing technology
- an exhaustive manufacturer product catalog
- a chemistry reference for PTFE compounding

Everything in this document is written so that a developer implementing against the SSoT can build the right data model, write the right rule checks, and configure the right matching logic — without needing independent sealing-domain expertise.

Domain facts in this document that are not self-evident carry a source reference in square brackets. Sources include industry standards (DIN, ISO, API), manufacturer published datasheets, peer-reviewed sealing-engineering literature, and (where noted) founder expertise. A full reference list appears at the end.

---

## 1. Scope

### 1.1 Coverage

This document covers radial shaft seals made wholly or predominantly from PTFE (polytetrafluoroethylene) or PTFE compounds as the primary sealing lip material. It includes:

- Virgin PTFE lip seals
- Filled PTFE lip seals (glass, carbon, bronze, MoS2, graphite, PEEK, mixed fillers)
- Spring-energized PTFE lip designs
- Non-spring-loaded PTFE lip designs
- O-ring energized PTFE rotary designs (dual-lip geometries)

### 1.2 Out of scope

This document does not cover:

- Elastomer radial shaft seals (NBR, FKM, FFKM, etc.) — covered in a future `sealai_engineering_depth_elastomer_rwdr.md`
- Mechanical (face) seals — separate future guide
- Static seals (O-rings, gaskets, flange seals) — separate future guide
- Hydraulic piston and rod seals — separate future guide
- PTFE use in non-rotary applications (packings, gaskets) — out of scope entirely

### 1.3 Relationship to base SSoT engineering paths

This document provides depth for:

```
engineering_path = rwdr
sealing_material_family ∈ ptfe_* values (per supplement v2 §39.3)
```

For all other combinations, the Case is a "shallow" case per supplement v2 §39.4 and this document does not apply in full.

---

## 2. PTFE as a sealing material — base properties

### 2.1 Why PTFE is used as a sealing lip material

PTFE has a specific combination of properties that makes it useful where elastomers fail:

- Extremely wide temperature range: approximately -200°C to +260°C continuous, short-term excursions higher [ISO 527, PTFE material datasheets; Dupont Teflon technical literature]
- Very low coefficient of friction against steel (approximately 0.04-0.10 dynamic, depending on compound and surface finish) [tribological literature, Trelleborg Turcon technical documents]
- Chemical inertness against nearly all media except molten alkali metals and elemental fluorine [standard PTFE resistance tables]
- Low surface energy (non-stick)
- Dry-run tolerance (limited, compound-dependent)

### 2.2 Why PTFE is problematic as a sealing lip material

These same properties create engineering constraints that the SeaLAI model must represent:

- **Cold flow (creep).** PTFE deforms permanently under sustained load, even at room temperature. This is the single most important failure driver in PTFE-RWDR. Compound selection and lip geometry must account for creep. [DIN EN ISO 899, PTFE creep data from manufacturers]
- **Low elasticity / poor rebound.** Unlike elastomers, PTFE does not return to shape after deformation. This limits misalignment tolerance and makes spring energization often necessary.
- **Poor abrasion resistance in virgin state.** Virgin PTFE wears rapidly; hence filler compounds.
- **Crystallization transitions.** PTFE undergoes volume change at ~19°C and ~30°C (crystalline structure transitions), which can affect seal-to-shaft interference fit in applications cycling through these temperatures. [ASTM D4894, PTFE crystallography literature]
- **Narrow pressure window.** Without appropriate geometry (rib-backed, spring-energized), PTFE-RWDR tolerate much lower pressure than elastomer equivalents.

### 2.3 Implications for SeaLAI case model

The properties above translate into mandatory schema fields:

- Operating temperature range (min, nominal, max) — critical for creep calculation
- Operating pressure (max, dynamic peaks) — critical for extrusion/gap calculation
- Shaft surface speed — critical for friction heat calculation
- Dry-run requirement (yes/no/intermittent) — affects compound selection
- Start-stop frequency — affects transient thermal behavior
- Misalignment and runout — affects lip contact stability

These fields are already in the base SSoT schema (§14, §16) but their **interpretation and mandatory status** for PTFE-RWDR cases is defined in sections 4-5 of this document.

---

## 3. PTFE compound taxonomy

### 3.1 Why compound matters

Virgin PTFE is rarely used as a dynamic sealing lip in production applications. Fillers are added to address:

- Abrasion resistance (bronze, carbon, glass)
- Creep resistance (glass, carbon fiber, mineral fillers)
- Thermal conductivity (bronze, graphite)
- Dry-run tolerance (graphite, MoS2)
- Chemical-specific compatibility adjustments

Each filler modifies PTFE properties differently and has different compatibility trade-offs. SeaLAI must represent this at the compound level, not just "PTFE."

### 3.2 Compound family enum (mandatory field)

The MVP supports the following compound families as first-class values on `rwdr.sealing_material_family`:

**ptfe_virgin**
- Unfilled PTFE
- Used for food-grade applications, pharmaceutical, some chemical services
- Poor abrasion resistance, significant creep
- Temperature range: -200°C to +260°C
- Typical max surface speed: 3-5 m/s in dry, up to 10 m/s in lubricated
- FDA 21 CFR 177.1550 compliance possible

**ptfe_glass_filled**
- Typical filler percentages: 5%, 15%, 25%, 40% by weight
- Most common compound for general industrial PTFE-RWDR
- Significantly reduced creep, increased wear resistance, slightly higher friction
- Temperature range: similar to virgin, slightly better creep performance at elevated temperatures
- Typical max surface speed: 10-15 m/s lubricated
- Abrasive to counterface if shaft hardness too low (requires ≥55 HRC typically)

**ptfe_carbon_filled**
- Filler: graphite carbon or carbon fiber, typically 15-25%
- Reduced creep, good wear resistance, lower friction than glass-filled
- Better thermal conductivity
- Temperature range: up to 260°C
- Typical max surface speed: 15-20 m/s lubricated
- Electrically conductive (relevant for some applications)

**ptfe_bronze_filled**
- Filler: bronze powder, typically 40-60%
- High thermal conductivity
- Good wear resistance, moderate creep resistance
- Higher friction than carbon-filled
- Temperature range: up to 280°C in some compounds
- NOT suitable for strong acids (bronze attack) or for applications requiring electrical isolation
- Typical max surface speed: 10-15 m/s

**ptfe_mos2_filled**
- Filler: molybdenum disulfide, typically 5-15%, often combined with other fillers
- Improved dry-run tolerance
- Reduced friction in low-lubrication conditions
- MoS2 degrades above approximately 350°C in air, limits use in high-temperature dry applications
- Often combined: "PTFE + 15% glass + 5% MoS2"

**ptfe_graphite_filled**
- Filler: synthetic graphite, typically 15%
- Good dry-run tolerance
- Low friction
- Reduced creep
- Electrically conductive
- Not suitable for strong oxidizers

**ptfe_peek_filled**
- Filler: PEEK (polyether ether ketone), typically 10-20%
- High-performance compound
- Very low creep
- High temperature stability
- Higher cost
- Used in aerospace, high-pressure hydraulics

**ptfe_mixed_filled**
- Any compound with two or more fillers (e.g., glass + MoS2, carbon + graphite)
- Used when properties of multiple fillers are needed
- Requires explicit compound specification in case to avoid over-generalization

### 3.3 Compound selection decision factors (reference for matching)

When SeaLAI suggests compound families for a given application, the decision rests on:

| Driver | Preferred compound families |
|---|---|
| High speed + good lubrication | ptfe_carbon_filled, ptfe_peek_filled |
| High speed + poor lubrication | ptfe_graphite_filled, ptfe_mos2_filled, ptfe_carbon_filled |
| Abrasive medium (particles) | ptfe_glass_filled, ptfe_bronze_filled |
| Aggressive acids | ptfe_virgin, ptfe_carbon_filled, ptfe_glass_filled (not bronze) |
| High pressure | ptfe_peek_filled, ptfe_glass_filled (higher percentages) |
| High temperature (> 200°C) | ptfe_peek_filled, ptfe_carbon_filled, ptfe_bronze_filled |
| Food / pharma / FDA | ptfe_virgin (FDA-grade), specific ptfe_glass_filled variants with FDA filler certification |
| Dry run tolerance | ptfe_graphite_filled, ptfe_mos2_filled, ptfe_bronze_filled |

This table is not a matching algorithm but a reference feeding into the matching algorithm's technical-fit-score calculation (supplement v2 §41.9).

### 3.4 Compound-specific schema fields

For a PTFE-RWDR case, the following fields are relevant beyond base SSoT §15.2:

```
rwdr.ptfe_compound.family            : enum (per §3.2)
rwdr.ptfe_compound.filler_percent    : decimal, NULL if not specified
rwdr.ptfe_compound.specific_grade    : text, manufacturer's internal code if known
rwdr.ptfe_compound.fda_compliant     : bool NULLABLE
rwdr.ptfe_compound.ex_atex_certified : bool NULLABLE
rwdr.ptfe_compound.special_certifications : text[]
```

---

## 4. Lip geometry parameters

### 4.1 The sealing lip

For PTFE-RWDR, the sealing lip is the critical interface. Its geometry determines:

- Radial contact force on the shaft
- Contact width and therefore PV loading
- Pumping behavior (intentional / unintentional)
- Pressure tolerance
- Dry-run survivability

### 4.2 Lip geometry schema fields

```
rwdr.lip.type                    : enum {single_lip, double_lip, triple_lip}
rwdr.lip.angle_primary_deg       : decimal, degrees (typical range 15-45°)
rwdr.lip.angle_back_deg          : decimal, degrees (air-side angle)
rwdr.lip.contact_width_mm        : decimal (typical 0.1-0.5mm for PTFE)
rwdr.lip.preload_source          : enum {virgin_material, garter_spring, cantilever, conical_washer}
rwdr.lip.radial_force_n_per_mm   : decimal, N/mm circumference
rwdr.lip.is_energized            : bool (spring-energized or otherwise pre-loaded)
rwdr.lip.energizer_type          : enum NULLABLE {coil_spring, o_ring, cantilever_spring, V_spring}
rwdr.lip.energizer_material      : text NULLABLE (e.g., stainless_steel_302, Hastelloy)
```

The **primary lip angle** is the angle between the lip surface and the shaft on the oil/medium side. Typical PTFE lip angles are shallower than elastomer lip angles because PTFE cannot support steep angles without rapid wear. Typical values: 15° for high-speed, up to 35° for high-pressure or low-speed applications.

The **back angle** (air side) affects back-pumping (oil drawn back into the chamber). For PTFE, the back angle is often engineered to create controlled back-pumping to compensate for the lower elastic conformity of PTFE compared to elastomers.

### 4.3 Lip contact width

The contact width (also called contact band or footprint) is the axial width of the lip-to-shaft interface. For PTFE-RWDR, typical values are 0.1-0.5 mm. This is narrower than elastomer contact widths because:

- PTFE is stiffer and conforms less
- Narrower contact reduces friction power dissipation (PV loading)
- Narrower contact is more sensitive to surface finish quality

### 4.4 Radial force

The radial force (normal to shaft axis, per unit circumference) is the contact force. For a shaft of diameter D, the total radial force is:

```
F_radial_total = π · D · f_radial_per_mm
```

Typical values for PTFE lip seals: 0.3-2.0 N/mm, compound and design dependent.

For spring-energized designs, the spring provides a large fraction of this force and keeps it stable as the lip material creeps.

---

## 5. Shaft-side engineering requirements

### 5.1 Why shaft surface matters

The shaft-side requirements for PTFE-RWDR are stricter than for elastomer RWDR. PTFE is less forgiving of surface imperfections because:

- Lower elastic conformity means small asperities are not smoothed out
- Lead patterns on the shaft cause directional pumping (intentional with elastomers, destructive with PTFE)
- Surface roughness above threshold causes rapid lip wear
- Shaft hardness below threshold causes shaft wear instead of lip wear

### 5.2 Schema fields for shaft side

```
shaft.diameter_mm                     : decimal
shaft.diameter_tolerance              : enum {h6, h7, h8, h9, h10, other}  -- ISO
shaft.material                        : text (e.g., "steel_1.4301", "steel_ck45", "stainless_17-4PH")
shaft.hardness_hrc                    : decimal (Rockwell C)
shaft.surface_finish_ra_um            : decimal (Ra in micrometers)
shaft.surface_finish_rz_um            : decimal NULLABLE
shaft.surface_finish_rpk_um           : decimal NULLABLE (reduced peak height)
shaft.surface_finish_rvk_um           : decimal NULLABLE (reduced valley depth)
shaft.machining_method                : enum {plunge_ground, traverse_ground, hard_turned, polished, other}
shaft.lead_angle_deg                  : decimal NULLABLE (0 = no lead; positive = one direction, negative = other)
shaft.runout_tir_mm                   : decimal (total indicator reading)
shaft.eccentricity_static_mm          : decimal
shaft.misalignment_static_deg         : decimal NULLABLE
shaft.coating                         : text NULLABLE (e.g., "hard_chrome", "nitride", "DLC")
shaft.coating_thickness_um            : decimal NULLABLE
```

### 5.3 Acceptable ranges for PTFE-RWDR

For a standard PTFE-RWDR application:

| Parameter | Acceptable range | Notes |
|---|---|---|
| Shaft hardness | ≥ 45 HRC, preferred ≥ 55 HRC | Below 45 HRC: rapid shaft wear, counterface erosion. |
| Surface finish Ra | 0.2–0.4 µm preferred | Below 0.1 µm: hydrodynamic lift, potential leakage. Above 0.8 µm: lip wear. |
| Surface finish Rz | ≤ 2.5 µm | |
| Machining | plunge ground or polished preferred | Hard-turned generally not acceptable for PTFE. See §5.4. |
| Lead angle | 0° ideal, absolute value ≤ 0.05° tolerable | Non-zero lead causes active pumping — typically in the wrong direction, leading to leakage. |
| Runout (TIR) | ≤ 0.1 mm typical, compound-specific | Exceeds: lip loses contact momentarily, allowing medium bypass. |
| Misalignment | ≤ 0.5° for spring-energized, ≤ 0.2° for non-spring | Ranges above this require specific compensating designs. |

These values are starting-point rules for the SeaLAI risk engine. Real cases often have manufacturer-specific variations.

### 5.4 Lead angle — specific warning

Lead on a PTFE-RWDR shaft is the single most common cause of apparently-inexplicable early seal failure. Any rotational machining process (grinding with a feed component, single-point turning) leaves a microscopic spiral groove on the shaft surface. PTFE lips, being stiff and conforming less, follow this spiral and pump medium along the spiral direction.

Preferred manufacturing methods: **plunge grinding** (no axial feed during grinding) or **polishing**. Hard turning leaves too much lead for PTFE. Traverse grinding must be performed with very tight feed rate controls and verified with lead measurement (MGA method or similar).

The SeaLAI risk engine treats any `machining_method = hard_turned` as a critical risk for PTFE-RWDR (§8 below).

### 5.5 Coating considerations

Shaft coatings change the equation:

- **Hard chrome** — acceptable for PTFE-RWDR, but finish after chroming must be verified; as-chromed surfaces are often too rough
- **Nitride coatings** — good compatibility
- **DLC (diamond-like carbon)** — excellent wear resistance, sometimes too smooth (hydrodynamic lift)
- **Soft platings (zinc, cadmium)** — not acceptable for PTFE-RWDR (will be worn through)

---

## 6. Operating condition envelope

### 6.1 Temperature

Mandatory fields:

```
operating.temperature.min_c          : decimal
operating.temperature.nom_c          : decimal
operating.temperature.max_c          : decimal
operating.temperature.peak_c         : decimal NULLABLE (short-term excursion)
operating.temperature.peak_duration  : decimal NULLABLE (seconds per occurrence)
```

Risk thresholds for PTFE-RWDR (examples, not exhaustive):

- Continuous above 200°C: requires compound review (virgin PTFE ok to 260°C continuous, but creep accelerates significantly)
- Continuous above 230°C: risk_score.thermal = medium/high
- Peak excursions above 280°C: risk_score.thermal = high
- Below -50°C: risk_score.thermal_low = medium; PTFE becomes brittle, different compound consideration

### 6.2 Pressure

```
operating.pressure.min_bar           : decimal
operating.pressure.nom_bar           : decimal
operating.pressure.max_bar           : decimal
operating.pressure.peak_bar          : decimal NULLABLE
operating.pressure.cycling_rate_hz   : decimal NULLABLE
operating.pressure.differential_sign : enum {medium_side_high, air_side_high, both}
```

PTFE-RWDR pressure tolerance depends strongly on design:

- Standard spring-energized PTFE lip seal: up to 2-5 bar
- Rib-backed PTFE lip seal: up to 10-20 bar
- Specialized high-pressure designs: up to 50+ bar
- Pressure pulses (hydraulic slap) are more destructive than steady pressure

### 6.3 Shaft speed

```
operating.shaft_speed.rpm_nom        : decimal
operating.shaft_speed.rpm_max        : decimal
operating.shaft_speed.start_stop_per_hour : decimal NULLABLE
operating.shaft_speed.direction      : enum {unidirectional_cw, unidirectional_ccw, bidirectional}
operating.shaft_speed.duty_cycle     : enum {continuous, intermittent_heavy, intermittent_light, rare}
```

Surface speed is derived:

```
v = π · D · n / 60    [m/s]  where D in meters, n in rpm
```

PTFE surface speed limits depend on compound and lubrication:

- Virgin PTFE, lubricated: up to 5 m/s
- Glass-filled PTFE, lubricated: up to 15 m/s
- Carbon-filled PTFE, lubricated: up to 20 m/s
- Any compound, dry: reduce by ~50-70%

### 6.4 Medium properties

The medium is covered in base SSoT §12.2 and §22 (compatibility engine). PTFE-RWDR-specific medium concerns:

- **Corrosive media**: PTFE itself is compatible with nearly everything, but the filler may not be. Bronze fillers fail in acids. Carbon fillers are robust. Glass fillers can fail in hydrofluoric acid specifically.
- **Particle-laden media**: PTFE's low hardness means abrasive particles embed in the lip. Bronze-filled handles this slightly better; glass-filled is at high risk.
- **Lubricity**: Poor-lubricity media (water, alcohols, many chemicals) reduce allowable surface speed
- **Vapor pressure**: Low-vapor-pressure media can cause local flashing at the lip (similar to mechanical seal flashing risk), more relevant for mechanical seals but important for some PTFE-RWDR chemical applications

### 6.5 Dry-run requirements

```
operating.dry_run.permitted           : bool
operating.dry_run.duration_max_s      : decimal NULLABLE
operating.dry_run.frequency_per_hour  : decimal NULLABLE
```

If `permitted = true`, the compound selection is constrained to graphite-filled, MoS2-filled, or specific bronze-filled families. Virgin PTFE and glass-filled PTFE are not dry-run tolerant in most applications.

---

## 7. Failure mode taxonomy (PTFE-RWDR specific)

### 7.1 Purpose

This taxonomy is a controlled vocabulary. RCA cases (base SSoT §17) classify `rca.damage_pattern.primary` against this list, not free text. Matching and risk scoring consume the taxonomy as structured input.

### 7.2 The taxonomy

**lip_wear_uniform** — circumferentially uniform wear of the lip contact area. Causes: normal service life end, abrasive medium, high surface speed, compound inadequate for PV. Typical signature: consistent wear band around the lip.

**lip_wear_localized** — wear concentrated in one sector. Causes: shaft misalignment, runout beyond tolerance, non-circular shaft, eccentric installation. Signature: asymmetric wear band.

**lead_induced_pumping_leakage** — leakage caused by shaft lead. Seal appears geometrically intact. Liquid migration in specific direction along shaft. Signature: dry lip, wet shaft downstream on one side.

**spiral_failure** — seal lip develops a spiral tear. Specific to PTFE and PTFE-like materials; does not occur in elastomers. Causes: shaft surface too rough, lead present, lip shortened by creep. Signature: visible spiral pattern in the lip material.

**extrusion_failure** — lip material extruded into the clearance gap on the downstream pressure side. Causes: pressure above compound limit, compound too soft, clearance gap too large. Signature: nibbled or rolled lip edge on pressure side.

**creep_induced_contact_loss** — lip-to-shaft contact lost due to sustained PTFE creep under radial force. Typical in non-spring-energized designs after long service. Signature: geometrically deformed lip, still intact but no longer in contact.

**edge_rollover** — the lip edge has rolled back or folded during installation or service. Causes: installation over shaft step without proper tooling, excessive shaft interference, chamfer missing. Signature: visibly folded lip material.

**thermal_degradation** — compound thermally degraded. Discoloration (brown to black), loss of material integrity, sometimes charring. Causes: local temperature exceeded compound limit, often from dry running or seal overload.

**chemical_attack_filler** — filler material attacked chemically (e.g., bronze filler in acid service, glass filler in HF). PTFE matrix remains intact but compound fails mechanically. Signature: pitted or etched appearance of the lip material.

**dust_induced_wear** — accelerated wear from particulate contamination. Typical in gearboxes with internal wear debris or external dust ingress. Signature: heavy wear, often with particles embedded in lip material.

**hang_up** — seal stuck axially or radially, not following shaft motion. Causes: corrosion between seal OD and housing, gummy medium residue, excessive interference. Signature: seal OD shows surface damage, lip shows either no wear or catastrophic wear.

**installation_damage** — damage occurred during installation, not service. Causes: wrong tool, skipped chamfer, foreign object, seal over sharp edge. Signature: cut, gouge, or deformed lip localized to installation path.

**spring_failure** — garter spring broken, corroded, or popped out. PTFE lip intact but no longer energized. Causes: corrosion (material mismatch), fatigue, vibration. Signature: spring absent or discontinuous; lip may still look normal.

**counterface_wear** — shaft material worn below acceptable surface finish. Seal may be intact but now runs on a damaged surface that will fail the next seal. Causes: shaft hardness too low for compound. Signature: visible groove or roughened band on shaft.

**blistering** — gas-filled blisters in the lip material. Uncommon in PTFE compared to elastomers but possible with compounds containing absorbent fillers in high-gas-pressure applications.

**unknown** — Failure mode cannot be determined from available evidence. Triggers SeaLAI's RCA path to request more investigation (additional photos, further disassembly).

### 7.3 Schema encoding

```
rca.damage_pattern.primary   : enum (one of the above)
rca.damage_pattern.secondary : enum[] (optional, multiple allowed)
rca.damage_confidence        : enum {low, medium, high}
rca.evidence_assets[]        : photos, measurements, text descriptions per base SSoT §17
```

### 7.4 Risk drivers linked to failure modes

Each failure mode has typical root causes, and each root cause maps to a risk dimension:

| Failure mode | Typical root cause → risk dimension |
|---|---|
| lip_wear_uniform | over-PV operation → risk.wear |
| lip_wear_localized | misalignment/runout → risk.fit |
| lead_induced_pumping_leakage | shaft machining method → risk.installation |
| spiral_failure | shaft surface quality → risk.fit, risk.installation |
| extrusion_failure | pressure too high for compound → risk.pressure |
| creep_induced_contact_loss | design inadequate (needs spring) → risk.design |
| chemical_attack_filler | compound incompatible with medium → risk.compatibility |
| dust_induced_wear | missing/inadequate pre-seal → risk.contamination |
| hang_up | corrosion, inadequate material pair → risk.compatibility |

The risk engine (base SSoT §21) receives this mapping as configuration.

---

## 8. Risk score inputs and thresholds (PTFE-RWDR)

### 8.1 Scope

This section defines PTFE-RWDR-specific risk dimensions and thresholds. The risk engine framework is in base SSoT §21; this section provides the compound-and-path-specific values.

### 8.2 Risk dimensions for PTFE-RWDR

**risk.thermal** — operating temperature vs. compound limits
- Inputs: `operating.temperature.max_c`, `operating.temperature.peak_c`, `rwdr.ptfe_compound.family`
- Threshold: compound-specific (see §3.2)

**risk.pressure** — pressure vs. design capability
- Inputs: `operating.pressure.max_bar`, `rwdr.lip.is_energized`, seal-design category
- Threshold: 5 bar for standard spring-energized, higher for specialized designs
- Critical if pressure exceeds compound extrusion limit for given lip contact width

**risk.surface_speed** — shaft surface speed vs. compound/lubrication limits
- Inputs: shaft.diameter_mm, operating.shaft_speed.rpm_nom, lubrication state, compound
- Threshold: calculated per compound tables in §3.3

**risk.lead_pumping** — lead angle causing pumping leakage
- Inputs: shaft.lead_angle_deg, shaft.machining_method
- Critical if machining_method = hard_turned; high if lead_angle_deg > 0.05°

**risk.surface_quality** — shaft surface finish adequacy for PTFE
- Inputs: shaft.surface_finish_ra_um, shaft.surface_finish_rz_um, shaft.hardness_hrc
- Critical if Ra < 0.1 or Ra > 0.8; high if hardness < 45 HRC

**risk.creep_longevity** — expected seal life reduced by creep
- Inputs: compound family, temperature, radial force, expected service duration
- Medium if service duration > 5 years without spring energization; compound-dependent

**risk.chemical_compatibility** — medium attack on compound including filler
- Inputs: medium.registry lookup with compound as query
- Uses base SSoT §22 compatibility engine with PTFE-compound-specific rules

**risk.dry_run** — dry-run conditions vs. compound tolerance
- Inputs: operating.dry_run.permitted, operating.dry_run.duration_max_s, compound
- High if dry-run permitted but compound is virgin or glass-filled

**risk.misalignment** — runout and misalignment vs. design tolerance
- Inputs: shaft.runout_tir_mm, shaft.misalignment_static_deg, lip type
- Medium if runout > 0.1 mm; high if > 0.2 mm

**risk.installation** — installation-related failure risk
- Inputs: shaft lead-in chamfer present, tooling available, shaft step/keyway to traverse
- Medium if not disclosed; high if explicit hazards

### 8.3 Threshold tables (examples, not exhaustive)

For `risk.thermal`:

```
If compound = ptfe_virgin:
  temp_max_c ≤ 200 → score 1 (low)
  200 < temp_max_c ≤ 230 → score 2 (medium)
  230 < temp_max_c ≤ 260 → score 3 (high)
  temp_max_c > 260 → score 4 (critical)

If compound = ptfe_glass_filled:
  temp_max_c ≤ 220 → score 1
  220 < temp_max_c ≤ 250 → score 2
  250 < temp_max_c ≤ 270 → score 3
  temp_max_c > 270 → score 4

If compound = ptfe_peek_filled:
  temp_max_c ≤ 250 → score 1
  ...
```

Full tables are implemented in `backend/app/services/risk_engine/ptfe_rwdr_thresholds.py` and are versioned along with the risk engine.

### 8.4 Uncertainty propagation

When a required input is missing, the score defaults to `9` (unknown_due_to_missing_data) per base SSoT §21.2. The missing input is added to the case's `recompute_required[]` and a user-facing clarification is triggered.

---

## 9. Checks and calculations (PTFE-RWDR)

### 9.1 Check registry entries

PTFE-RWDR adds these entries to the formula library (base SSoT §20):

**circumferential_speed**
```
Inputs:  shaft.diameter_mm, operating.shaft_speed.rpm_nom
Formula: v = π · D / 1000 · n / 60   [m/s]
Output:  derived.surface_speed_ms
Used in: risk.surface_speed
Fallback: N/A, required input
```

**compound_pv_loading**
```
Inputs:  rwdr.lip.radial_force_n_per_mm, derived.surface_speed_ms, rwdr.lip.contact_width_mm
Formula: contact_pressure = radial_force / contact_width  [N/mm²]
         PV = contact_pressure · v  [N/(mm²·m/s) or MW/m²]
Output:  derived.pv_loading
Used in: risk.wear, risk.creep_longevity
Fallback: Use compound defaults if lip_force/contact_width missing, flag assumption
```

**creep_gap_estimate_simplified**
```
Inputs:  rwdr.lip.radial_force_n_per_mm, operating.temperature.nom_c, compound family, expected_duration_years
Formula: compound-specific empirical creep factor × duration × temperature factor
Output:  derived.estimated_creep_gap_um
Used in: risk.creep_longevity
Fallback: Mark as "insufficient_input" if compound family missing; use generic PTFE curve otherwise
```

This is a simplified estimator, not a FEM calculation. Intended for order-of-magnitude risk assessment, not detailed design.

**thermal_load_indicator**
```
Inputs:  derived.pv_loading, lubricant conductivity factor (default 1.0 if not specified)
Formula: heat_flux ≈ PV · friction_coefficient · π · D
Output:  derived.heat_flux_w_per_mm
Used in: risk.thermal
Fallback: Use default friction coefficient of 0.08 if compound unknown, flag assumption
```

**extrusion_gap_check**
```
Inputs:  operating.pressure.max_bar, clearance (seal OD to housing), compound hardness
Formula: empirical extrusion limit table lookup
Output:  derived.extrusion_safety_margin
Used in: risk.pressure
Fallback: Flag as insufficient_input if clearance unknown
```

### 9.2 What SeaLAI does NOT calculate at MVP

The following are NOT in MVP scope:

- FEM simulations of lip deformation
- Transient thermal simulations
- Detailed friction/wear life predictions
- Spring fatigue calculations

These are candidates for Phase 3+ via integration with FreeCAD/CalculiX (already present in the stack but not wired).

---

## 10. Bridge to elastomer RWDR (Phase 2 preparation)

### 10.1 What stays identical

When Phase 2 adds elastomer-RWDR depth, the following structures are reused unchanged:

- `engineering_path = rwdr` (same value)
- Shaft-side schema (§5.2) is identical
- Operating envelope (§6) is identical
- Many failure modes are shared (lip_wear_uniform, lip_wear_localized, extrusion_failure, installation_damage, counterface_wear, blistering)
- Risk dimension framework is identical
- Check registry patterns are identical

### 10.2 What changes

For elastomer-RWDR, the following require their own depth:

- Material family enum (already prepared in §39.3 of supplement v2)
- Compound properties table (elastomer chemistry differs from PTFE fillers)
- Lip geometry conventions (elastomer lip angles are different from PTFE)
- Lead-angle tolerance (elastomer tolerates more lead, some designs use it intentionally)
- Pressure tolerance (elastomer can go much higher with rib support)
- Additional failure modes: compression set, aging, swelling, EPDM ozone cracking, etc.
- Thermal behavior (glass transition, dynamic rebound loss, etc.)

### 10.3 Migration path

When the elastomer-RWDR engineering depth guide is written:

1. Copy this document structure, replace PTFE-specific content
2. Extend the compound taxonomy
3. Add elastomer-specific failure modes to the taxonomy
4. Update risk thresholds per elastomer family
5. Flip `depth_level` for elastomer cases from "shallow" to "deep" in supplement v2 §39.4

No schema migration is needed. The data model already accommodates all RWDR variants; only the depth content expands.

---

## 11. References

### 11.1 Standards

- **DIN 3760** — Radial shaft seal rings: dimensions and nomenclature (Types A, AS, B, BS, C). The European baseline for RWDR geometry.
- **ISO 6194-1** — Rotary shaft lip-type seals: nominal dimensions and tolerances. International equivalent of DIN 3760.
- **ISO 6194-2** — Rotary shaft lip-type seals: vocabulary.
- **ISO 6194-3** — Rotary shaft lip-type seals: storage, handling and installation.
- **ISO 527** — Plastics: determination of tensile properties. Relevant for PTFE material characterization.
- **ASTM D4894** — Standard specification for PTFE granular molding and ram extrusion materials.
- **DIN EN ISO 899** — Plastics: determination of creep behavior. Relevant for PTFE creep prediction.
- **API 682** — Shaft sealing systems for centrifugal and rotary pumps. Not directly applicable to RWDR but shares medium-definition and flush-plan vocabulary.

### 11.2 Manufacturer technical literature (public)

- Trelleborg Sealing Solutions: Turcon Variseal technical documents, Rotary Seal Selector documentation
- Freudenberg Sealing Technologies: PTFE material datasheets (Y002 food-grade PTFE; PTFE POP Seal literature), Simmerring technical handbooks
- SKF Industrial Seals: PTFE radial shaft seal product pages and application guides
- Parker Hannifin: O-Ring Handbook (ORD 5700), PTFE rotary seal technical pages
- John Crane: Type 8628VL and other high-performance seal technical documents (where public)

### 11.3 Industry associations

- ESA (European Sealing Association): public technical materials on sealing fundamentals
- FSA (Fluid Sealing Association, US): sealing handbook and standards references

### 11.4 Domain expertise

Sections of this document reflect founder expertise accumulated through work in PTFE-RWDR manufacturing. Where this expertise is the primary source of a specific threshold or design rule, and where no public reference substantiates it identically, the threshold is marked as "founder domain expertise, to be validated against production cases in MVP phase."

Specifically, many of the threshold values in §5.3 (acceptable ranges), §6.3 (compound speed limits), §7.1 (failure mode descriptions), and §8.3 (risk thresholds) fall in this category. They are engineering-reasonable starting points, not published absolute values. They will be refined as real cases validate them.

---

**Document end.**

This guide is reviewed quarterly. Next scheduled review: 2026-07-17.

Changes to this document follow the SSoT precedence rules: technical-fact corrections are non-breaking and update `validity_from` where applicable. Schema changes require corresponding supplement v2 updates to the scope boundary.

