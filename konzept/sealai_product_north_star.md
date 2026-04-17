# SeaLAI — Product North Star

**Version:** 1.0
**Datum:** 2026-04-17
**Status:** Binding product compass — supersedes or overrides any narrower interpretation in the Authority documents
**Audience:** Founder, implementation agents, future team members, potential investors
**Purpose:** Capture the non-negotiable product truths that define what SeaLAI is and what it must never become. Written in founder's own words wherever possible.

---

## 0. How to read this document

This is the shortest authority document in the SeaLAI set. It does not contain schemas, code rules, or technical specifications. It contains the **product truths** that justify every technical decision.

Read this document first, before any other authority. When the technical documents leave a decision ambiguous, consult this one. When a technical decision seems to optimize correctly but feels wrong, check against this one.

The quotations in italics are the founder's own words from the 2026-04-17 strategy session. They are more authoritative than my paraphrases, because they come from 15+ years of domain experience in a niche market.

---

## 1. What SeaLAI is for

SeaLAI exists to solve two structural problems that the sealing technology industry has not solved after 80 years of operation:

### 1.1 The user's blindfold

Industrial users — design engineers, maintenance engineers, purchasers — face a recurring situation:

> *"Der Anwender hat oft ein Dichtungsproblem und weiß nicht wie er es am besten lösen kann, welches Material für welches Medium, welchen Dichtungstypen, wie sollte die Vorspannung der Dichtlippe sein, was mach ich bei Schokolade zb. warum ist die Qualität der Welle wichtig usw."*

The user doesn't know what they don't know. The industry's response has historically been to offer complex selector tools from specific manufacturers, which lead to the manufacturer's own products, or to require the user to contact manufacturers directly and endure clarification loops.

### 1.2 The manufacturer's blindflight

Mid-size specialized manufacturers — the segment with the best technical solutions for niche problems — face their own structural disadvantage:

> *"Als Hersteller in der Nische ist man immer im Blindflug unterwegs. Die Kunden finden einen zufällig im Internet oder stolpert über Empfehlungen bzw. die Marke ist bekannt weil sie bereits 50 Jahre am Markt ist."*

Customer acquisition for specialists is passive and coincidental. Marketing budget determines visibility more than technical excellence does. This is structurally bad for the users (they don't find the best technical solutions) and for the manufacturers (they can't compete on technical merit).

### 1.3 SeaLAI's purpose

SeaLAI connects these two problems by being a **neutral technical translation and qualification layer** between user and manufacturer. It does not sell seals. It does not manufacture seals. It helps the user understand their problem and identifies the manufacturers technically best suited to solve it.

---

## 2. The two core principles of user interaction

### 2.1 Dignity — the user never feels stupid

> *"Der User hat nicht das Problem das er wie doof dasteht."*

The user arrives with a problem, not with a specification. They may have a photo of a broken seal, a scribbled article number, or just "I need a replacement for my pump." SeaLAI never responds with implicit or explicit judgment about what the user should have known.

Concrete implications:
- No "mandatory field" gates at the start of an interaction
- No jargon without explanation
- No silent rejection ("please provide more information") — always explain what is needed and why
- Active teaching as a side effect of inquiry: when a parameter matters, SeaLAI explains why
- Errors in user statements are gently corrected with explanation, not flagged as mistakes

### 2.2 Respect for the user's time — asynchronous by design

> *"Er kann jederzeit wann er Zeit hat sich beraten lassen."*

SeaLAI does not require the user to be available for a live conversation with a sales engineer. It does not push the user through a timed flow. It waits patiently while the user goes to measure a shaft, takes a photo, or consults a colleague.

Concrete implications:
- Case state persists indefinitely
- Users return at any time to continue a case
- No "session timeout" that loses context
- Notifications when information arrives, but no urgent nudging
- The consultation happens on the user's schedule

---

## 3. The consultative interaction — what SeaLAI actively does

### 3.1 Understand, then advise

> *"Der Kunde möchte verstanden und geführt werden. Es muss ein präzises Bild herausgearbeitet werden damit man die konkrete Lösung anbieten kann."*

This is the sentence that defines SeaLAI's interaction model. It is not a form-filler. It is not a catalog search. It is a structured consultation that builds a precise picture of the user's situation before proposing solutions.

The structure of this consultation is:
1. **Receive initial context** in whatever form the user provides (photo, article number, free text, datasheet fragment)
2. **Extract maximum information** from what was provided
3. **Ask targeted questions** to fill gaps — but only questions that matter for the decision
4. **Build a precise problem picture** — application context, operating envelope, installation context, failure history, constraints
5. **Check the assumed solution** — is the current seal actually the optimal one, or would a different material / geometry / compound be better?
6. **Propose matched manufacturers** with structured reasoning

### 3.2 Proactive validation, not passive replication

When a user asks for a replacement of an existing seal, SeaLAI does not simply identify the existing seal and forward the order. It validates whether the existing solution was optimal.

The founder's own example:
> *"Vielleicht ist ja PTFE-Glas sinnvoller"*

If a user has been running virgin PTFE in an abrasive slurry for years and accepts short replacement intervals as normal, SeaLAI should recognize that glass-filled PTFE would likely extend service life. The user may or may not accept the suggestion — but the option must be surfaced.

This is a fundamental differentiator from catalog-based replacement tools that assume the incumbent solution is correct.

### 3.3 Teach while qualifying

SeaLAI is consultative, not extractive. Every question about shaft surface finish becomes an opportunity to explain why it matters. Every explanation of compound selection teaches the user something they can use in future decisions.

This builds:
- **User loyalty** (the platform is useful beyond the immediate transaction)
- **Manufacturer trust** (SeaLAI arrives at a specification the manufacturer can accept because the user understands the reasoning)
- **Industry improvement** (users gradually develop better intuition, which compounds over time)

### 3.4 What SeaLAI takes off the manufacturer's plate

> *"Diese ganzen Informationsfragen, Bedarfsanalyse, Verstehen der Dichtungsproblematik, den Pain und die Berechnungen soll SeaLAI alles dem Hersteller abnehmen."*

The manufacturer's applications engineer today spends 30-50% of their time on clarification loops with under-qualified inquiries. SeaLAI takes that work.

Specifically, SeaLAI does:
- Requirements analysis (what does the user actually need?)
- Problem understanding (what is the real pain?)
- Engineering calculations (PV loading, compound feasibility, speed limits, thermal margin)
- Case documentation (structured artifact, complete enough that the manufacturer doesn't need to re-interview)

SeaLAI does NOT do:
- Final engineering review (the manufacturer signs off on the specific solution for their product)
- Binding quote (the manufacturer issues the quote with their pricing, lead time, terms)
- Manufacturing
- Customer relationship from quote acceptance onward

This division is the economic basis for manufacturer payment. Manufacturers pay SeaLAI because SeaLAI saves them the applications-engineering time they otherwise waste on unqualified inquiries.

---

## 4. Heterogeneous and multimodal input

### 4.1 What users actually submit

> *"Die Kunden haben meistens Fotos ihrer defekten Dichtung, schicken uns Artikelbeschreibungen bzw. Bezeichnung ihrer aktuellen Dichtung von anderen Herstellern, wollen beraten werden was möglich ist."*

Real users arrive with:
- Photos of broken seals (sometimes dismantled, sometimes in-situ)
- Article numbers from other manufacturers ("NOK PG32 28x45x7", "Simmerring BAUSL 30x52x7")
- Datasheet fragments (screenshot, PDF page, photo of a printed page)
- Free-text descriptions ("brauche Ersatz für die Dichtung in der Pumpe")
- Dimensional sketches (hand-drawn or CAD-derived)
- Installation context photos (housing, shaft, surrounding assembly)

SeaLAI must accept all of this. Not as second-class inputs to be normalized by the user, but as first-class inputs that SeaLAI structures.

### 4.2 The translation layer in practice

For each input type, SeaLAI has a specific extraction approach:

**Photo of a seal:** Identify type (single-lip, double-lip, cassette), estimate compound family from color and wear pattern, extract damage mode if visible, estimate dimensions if reference is present.

**Article number:** Decode manufacturer-specific nomenclature into generic engineering concepts. "NOK PG32" → (manufacturer: NOK, series: PG32, typical compound: NBR with specific additives, typical shaft range). "Simmerring BAUSL" → (manufacturer: Freudenberg / trademark, type: standard elastomeric RWDR with dust lip). This is the Terminology Registry in action (supplement v2 §40).

**Datasheet fragment:** Extract available parameters (dimensions, material, temperature range, pressure rating). Flag extracted values with provenance source = "documented."

**Free-text description:** Interpret with LLM support, but as a proposal, not as truth. Validate with the user: "You mentioned 'Pumpe für Getriebeöl' — can you confirm the medium is gear oil at approximately 60-80°C?"

**Installation context:** Visual cues about shaft, housing, mounting method inform fit and installation risk.

### 4.3 What SeaLAI should never do with heterogeneous input

- **Never silently assume.** If the input is ambiguous, ask.
- **Never present extracted information as confirmed.** Provenance is explicit.
- **Never punish the user for submitting too little.** Teach what is needed and why.
- **Never ignore a photo because it's "not in the right format."** Fallback to asking for specific information instead.

---

## 5. Small quantities are first-class

### 5.1 The small-quantity reality

> *"Der User benötigt ja meistens nur 4-10 Stück oder auch nur einen Ring. Standard Ringe sind meistens nicht für die individuelle Problemstellung auf Dauer dicht."*

This is a structural mismatch the industry has not resolved. Users often need a small number of seals for specific problems. Standard catalog parts don't fit. Custom manufacturing is possible but has economics that many manufacturers avoid.

SeaLAI's role here:

### 5.2 First-class small-quantity support

**Manufacturer Capability Claims (supplement v2 §41) must include:**
- `lot_size_capability` — minimum, typical, maximum production batch sizes
- `small_quantity_acceptance` — explicit boolean + pricing indicator (staffelpreise, rush-surcharges)
- `rapid_manufacturing` — availability of 24-72h production against surcharge

**Matching logic:**
- When a user indicates a small quantity need, SeaLAI filters to manufacturers that explicitly accept it
- Small-quantity-willing manufacturers are surfaced even if they are less "big name" than the user might expect
- This is a Moat Layer 2 feature (technical translation includes matching the commercial reality, not just the technical fit)

**User expectation management:**
- When a user asks for 1-10 pieces, SeaLAI explains the economic reality: piece prices scale non-linearly with batch size, tooling amortization dominates cost for single pieces
- Range indication ("Einzelstücke für PTFE-Sonderanwendung liegen typischerweise im Bereich 80-250 EUR pro Stück") helps the user prepare for realistic offers
- The user is not shocked by manufacturer quotes

### 5.3 Small quantities as a differentiator for SeaLAI itself

Most large-scale B2B marketplaces optimize for volume. SeaLAI optimizes for the full range, including single pieces. This is a strategic USP:

- For users: the only neutral platform that reliably serves small-quantity needs
- For specialized mid-size manufacturers: direct access to users with small but technically meaningful needs — exactly their sweet spot

---

## 6. The price question

### 6.1 The user's question is real

> *"Wo bekomme ich den her und warum ist der so teuer?"*

The price question is legitimate. Users are confused by the gap between catalog standard seals (10-30 EUR) and custom single pieces (80-250 EUR or more). This confusion leads to suspicion of manufacturers ("why do they charge so much?") and to bad decisions (ordering the catalog part, having it fail, reordering).

### 6.2 SeaLAI's position on pricing — evolutionary

**Phase 1 (MVP):** SeaLAI does NOT compare prices. It provides **price context**:

- **Range indication by product class**: "Custom PTFE-RWDR for chemical applications: typically 80-250 EUR per piece in small quantities; 15-40 EUR in larger batches"
- **Cost-driver education**: Why does a custom seal cost what it does? Tooling, small batch, documentation, quality inspection, rapid delivery surcharges
- **Fair expectations before inquiry**: The user knows what to expect when manufacturer quotes arrive

**Phase 2+ (if market adoption is strong):** A Check24-style price comparison model may be added as a separate, opt-in feature — but only if the neutrality and manufacturer relationship has proven robust.

### 6.3 Why we start with price context, not price comparison

> *"Eine Preisvergleichmaschine ist aktuell vielleicht nicht sinnvoll, ein Check24 Modell könnte aber nachgelagert angedacht werden wenn SeaLAI am Markt gut angenommen wird."*

Price comparison creates immediate pressure on manufacturer margins and incentivizes race-to-the-bottom dynamics. In a niche market where technical excellence should be the competitive axis, race-to-the-bottom destroys the exact manufacturers SeaLAI wants to support.

Price context without comparison:
- Educates the user
- Sets realistic expectations
- Does not put manufacturers into direct price competition
- Keeps technical fit as the dominant matching axis
- Preserves the Moat Layer 1 (structural neutrality)

---

## 7. The non-negotiables — what SeaLAI must never become

Several failure modes would destroy SeaLAI's value proposition. These are absolute constraints.

### 7.1 SeaLAI must never become a catalog

A catalog displays products. SeaLAI understands problems. The moment SeaLAI's primary surface becomes "browse seals by category," the product has degraded.

### 7.2 SeaLAI must never become a marketing funnel

Every major sealing manufacturer has a marketing funnel. SeaLAI's value is to NOT be one. Sponsored listings, if ever introduced, are structurally separated and visually labeled. Organic matching is never influenced by commercial relationships.

### 7.3 SeaLAI must never become a price aggregator

See §6. Price aggregation collapses technical excellence into price competition and destroys the economic basis for the specialist manufacturers SeaLAI serves.

### 7.4 SeaLAI must never make users feel stupid

See §2.1. The day a user closes a session feeling stupid is a product failure, regardless of whether they got a technically correct answer.

### 7.5 SeaLAI must never pretend to know what it doesn't

Hallucinated engineering advice is worse than no advice. SeaLAI honestly says "I don't know" or "this is an assumption to verify" whenever its confidence is limited. Provenance tracking (base SSoT §9) is the technical enforcement of this principle.

### 7.6 SeaLAI must never bypass the manufacturer's final authority

SeaLAI qualifies inquiries and matches manufacturers. The manufacturer makes the final engineering decision on their product. SeaLAI never issues a binding engineering statement or a binding commercial commitment on behalf of a manufacturer.

---

## 8. Industry problems SeaLAI explicitly solves

This section is the concrete list of problems that, when a user or manufacturer looks at SeaLAI, they should recognize. If any of these problems remain unsolved, SeaLAI has failed at its purpose.

### 8.1 For the user

- "I don't know what material works for my medium." → SeaLAI's compatibility service answers this in structured form.
- "I don't know what seal type I need." → SeaLAI's consultation builds a precise picture before proposing.
- "I don't know what the right lip preload / contact width is." → SeaLAI calculates and explains.
- "I don't know why shaft quality matters." → SeaLAI educates while qualifying.
- "I have a photo of my broken seal, can you help?" → SeaLAI analyzes and asks targeted follow-ups.
- "I have an article number from another manufacturer." → SeaLAI decodes and finds equivalents.
- "I only need 4 pieces, can anyone help me?" → SeaLAI matches manufacturers who accept small quantities.
- "What will this realistically cost?" → SeaLAI provides range context.
- "Where do I buy this?" → SeaLAI surfaces matched manufacturers.
- "Will this solution actually last?" → SeaLAI evaluates and surfaces risk dimensions.

### 8.2 For the manufacturer

- "I get too many unqualified inquiries." → SeaLAI filters before forwarding.
- "I spend too much engineering time on clarification." → SeaLAI does the clarification.
- "I am invisible to users who aren't already my customers." → SeaLAI gives visibility on technical merit.
- "I don't know if the quote I made is for the optimal solution." → SeaLAI's structured case provides the context.
- "Price competition erodes my margin." → SeaLAI does not pit manufacturers on price.
- "I can make small quantities but nobody asks me." → SeaLAI surfaces small-quantity capability to relevant users.

---

## 9. The business model implication

> *"Also quasi ein Industrie Stock das auf die Dichtungstechnik zugeschnitten ist und mit AI optimiert ist."*

Users use SeaLAI for free. Manufacturers pay for findability with qualified leads. No advertising on the user side (see §7.2). Pricing tiers per supplement v2 §43.

The founder's mental model — "Industrie-Stock zugeschnitten auf Dichtungstechnik" — is the correct frame. SeaLAI is to sealing technology what specialized B2B platforms are to other industries, with AI enabling depth of domain modeling that generic platforms cannot match.

---

## 10. What changes if we lose sight of this document

This document exists because architectural decisions tend to drift toward technical perfection at the expense of product purpose. Several failure modes are predictable:

- **The schema is beautiful, but the user still fills 20 fields.** → Product purpose violated (dignity principle).
- **The matching is technically correct, but users abandon because it feels like a form.** → Product purpose violated (consultative principle).
- **The engineering depth is excellent, but manufacturers don't sign up because the qualified-lead promise isn't kept.** → Product purpose violated (manufacturer value).
- **The platform grows, but technical specialists get pushed aside by bigger brands.** → Product purpose violated (structural neutrality).

When any of these appear, this document is the diagnostic tool. Read the founder's quoted sentences. Ask: is this still what we promised?

If yes, proceed. If no, stop and correct.

---

## 11. Attribution

The core quotations in this document are verbatim statements from Thorsten Jung, founder of SeaLAI, during the strategy session on 2026-04-17. Paraphrases are my structuring; the product truths they carry are his.

This document is living. As SeaLAI encounters real users and real manufacturers, new formulations of these truths will emerge. They belong here.

---

**Document end.**
