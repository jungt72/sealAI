# Engineering Knowledge Answer Standard

Status: accepted architecture baseline, 2026-07-11

## Purpose

sealingAI answers sealing engineers, maintenance specialists, buyers and technical quality roles.
A knowledge answer is therefore not a glossary response. It must expose the engineering model needed
to understand, compare or pre-qualify a sealing subject without pretending to issue a release.

The LLM does not decide answer depth. `core/knowledge_answer.py` selects a deterministic answer
profile, reviewed claims carry explicit answer facets, retrieval fills those facets, and L1 renders
the result. Missing evidence remains visible to curation and must not be replaced with invented
numbers or normative claims.

## Universal Rules

Every technical knowledge answer follows these rules:

1. Start with the engineering core statement, not a product pitch or beginner preamble.
2. Explain mechanisms and causal chains, not only advantages and disadvantages.
3. Bind every number to a grade/product or seal design, test or operating condition, and source.
4. Treat datasheet typical values as comparison data, never as specification or application limits.
5. Do not combine independent maxima for pressure, temperature, speed or PV into one operating point.
6. Separate material-family tendencies from compound/product-specific performance.
7. Separate chemical compatibility from mechanical, tribological and geometrical suitability.
8. State which inputs change the decision and which validation closes the remaining uncertainty.
9. For comparisons, use identical axes and conditions; never declare a universal winner.
10. A pure knowledge answer may be detailed. A concrete application remains subject to the normal
    clarification, calculation, compatibility and manufacturer-validation gates.

## Material Overview

Required output:

1. **Classification and structure**: polymer/material class, relevant molecular or microstructural
   feature, and why it matters in a seal.
2. **Engineering behavior**: thermal, mechanical, tribological and chemical behavior, including
   recovery, creep/compression set, wear, friction and permeation where relevant.
3. **Reference parameters**: only source-conditioned values with grade, test basis and limitations.
4. **Variants and trade-offs**: subfamilies, cure systems, fillers or compounds and the property
   gained and lost by each change.
5. **Media behavior**: compatibility mechanisms, concentration/temperature dependence and relevant
   exceptions; no family-wide release.
6. **Seal forms and applications**: which designs use the material and how the material is energized.
7. **Limits and failure mechanisms**: trigger, physical/chemical mechanism, damage pattern and result.
8. **Selection and validation**: required application inputs, concrete grade/compound evidence,
   applicable test basis and manufacturer/system qualification.

## Material Comparison

Compare both materials on the same axes:

- grade/compound and test basis;
- temperature behavior and recovery;
- media compatibility at stated concentration and temperature;
- friction, wear, creep/compression set and extrusion resistance;
- gas permeation or rapid-gas-decompression behavior where relevant;
- dynamic/static suitability and counterface requirements;
- available seal forms, compliance and cleanliness constraints;
- dominant failure modes;
- scenario-specific fit, exclusions and missing decision data.

The answer should use an aligned table for comparable data, followed by scenario logic. A table cell
is left open when the evidence does not share a comparable basis.

## Medium Overview Or Comparison

Required output:

1. **Identity**: exact chemical species or commercial product, base fluid, concentration, water
   content, pH when relevant, additives and contaminants.
2. **Seal-relevant properties**: phase, viscosity, density, vapor pressure/phase-change behavior,
   lubricity, volatility and solids/crystallization.
3. **Operating conditions**: temperature, pressure, exposure time, cycles, flow, cleaning and media
   changes.
4. **Material interactions**: swelling, extraction/shrinkage, hardening/softening, hydrolysis,
   oxidation, permeation, explosive decompression and stress cracking where relevant.
5. **System consequences**: friction and film formation, heat, leakage, wear, seal-form and support-
   system implications.
6. **Evidence and qualification**: SDS/TDS or analysis data, compound-specific compatibility,
   immersion screening and an application-representative system test.

ISO 1817 immersion results are evidence for liquid effects on rubber properties; they are not a
complete seal-system release because groove, preload, friction, pressure, permeation and dynamic heat
are not represented by immersion alone.

## Seal-Type Overview

Required output:

1. **Function and sealing mechanism**: leakage path, contact/gap mechanism, forces and lubricating
   film.
2. **Components and variants**: components, construction axes and the selection consequence of each.
3. **Operating factors**: pressure, temperature, velocity/motion, medium, cycles and their coupling.
4. **Interfaces**: groove/housing, shaft or counterface, surface texture, hardness, runout,
   eccentricity, lubrication and installation.
5. **Materials and media**: functional material pairing, not a single-family compatibility claim.
6. **Applications and boundaries**: appropriate contexts and the boundary to alternative designs.
7. **Failure analysis**: observed pattern, mechanism, provoking condition and corrective direction.
8. **Standards and validation**: standard scope, inspection/installation/qualification and required
   selection data.

### O-Ring Additions

Always cover squeeze, installed stretch/compression, gland fill, extrusion gap, tolerance stack,
thermal/media-induced volume change, compound and hardness, static/dynamic mode, surface finish,
installation and the ISO 3601 split between dimensions, housings, quality and back-up rings.

### RWDR Additions

Always cover lip energization and lubrication, circumferential speed, differential pressure,
lip temperature, medium/additives, shaft finish/hardness/lead, runout and eccentricity, dust exclusion,
installation and the distinction between elastomeric ISO 6194 and thermoplastic ISO 16589 designs.

### Mechanical-Seal Additions

Always cover primary faces and secondary seals, lubricating-film/leakage principle, balance,
single/dual arrangement, rotating/stationary and pusher/bellows construction, face pairing, process
phase/viscosity/vapor pressure/solids, seal chamber conditions, support system and the scoped use of
ISO 21049/API 682 classifications.

## Evidence Coverage

The planner measures required facets against reviewed grounding facts:

- `complete`: at least 75% of required facets covered;
- `partial`: at least 35%;
- `sparse`: less than 35%.

Coverage is an observability and rendering constraint, not permission to fabricate missing content.
The current core release includes reviewed profiles for PTFE, O-Rings, RWDR, mechanical seals and
the general method for media evaluation. Additional materials/media use the same contract and remain
explicitly incomplete until reviewed claims cover their missing facets.

## Primary Source Baseline

- [ISO 3601-1:2012, O-ring dimensions and designation](https://www.iso.org/standard/58043.html)
- [ISO 3601-2:2025, O-ring housing dimensions](https://www.iso.org/standard/85921.html)
- [Parker O-Ring Handbook ORD 5700](https://www.parker.com/content/dam/Parker-com/Literature/O-Ring-Division-Literature/ORD-5700.pdf)
- [ISO 6194-1:2007, elastomeric rotary shaft lip seals](https://www.iso.org/standard/34678.html)
- [SKF Industrial Shaft Seals](https://www.skf.com/binaries/pub12/Images/0901d1968099986c-Industrial-Shaft-Seals-catalogue_tcm_12-524179.pdf)
- [Trelleborg Rotary Seals, April 2026](https://www.trelleborg.com/seals/-/media/tss-media-repository/tss_website/pdf-and-other-literature/catalogs/rotary_gb_en.pdf)
- [ISO 16589-4:2011, thermoplastic rotary shaft lip seals](https://www.iso.org/standard/53937.html)
- [EagleBurgmann mechanical-seal fundamentals](https://www.eagleburgmann.com/en/products/mechanical-seal/)
- [ISO 21049:2004, pump shaft sealing systems](https://www.iso.org/standard/35625.html)
- [API 682 Fourth Edition overview](https://www.api.org/~/media/files/publications/whats%20new/682%20e4%20pa.pdf)
- [ISO 1817:2024, effect of liquids on rubber](https://www.iso.org/standard/86602.html)
- [Parker PTFE data-sheet interpretation](https://discover.parker.com/PTFE-Seal-Material-Material-Data-Sheets-Part1)
- [Parker PTFE Seals Design Guide](https://www.parker.com/content/dam/parker/na/united-states/industries/off-road/pdfs-offroad/PTFE%20Seal%20Design%20Guide.pdf)
- [Trelleborg Turcon Variseal material guide](https://www.trelleborg.com/seals/-/media/tss-media-repository/tss_website/pdf-and-other-literature/catalogs/variseal_en.pdf)
