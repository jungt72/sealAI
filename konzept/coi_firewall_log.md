# SeaLAI -- COI Firewall Log

**Version:** 1.0
**Datum:** 2026-04-18
**Status:** Binding declaration of data firewall compliance
**Next review:** 2026-07-18 (quarterly) OR on any trigger event below
**Signatory:** Thorsten Jung, Founder

---

## 1. Purpose

This log documents SeaLAI's data firewall between the founder's employer and the SeaLAI corpus. It exists because `konzept/sealai_ssot_supplement_v2.md` §38.6 makes the COI firewall binding, and `konzept/founder_decisions_phase_1a.md` Decision #3 records the firewall as non-negotiable on legal and strategic grounds. The declaration creates an auditable repository artifact before external pilot onboarding and before any manufacturer trust claim depends on SeaLAI's neutrality.

## 2. Scope -- covered SeaLAI artifacts

This log covers the following artifact categories within the SeaLAI repository and associated data stores:

- Knowledge base JSON files (e.g., `SEALAI_KB_PTFE_factcards_gates_v1_3.json`, `SEALAI_KB_PTFE_compound_matrix_v1_3.json` and successors)
- YAML rules under `backend/app/services/langgraph/rules/` (to be migrated and removed per Founder Decision #2)
- LLM prompts under the prompt library
- Qdrant vector store documents
- Golden cases (once introduced per Supplement v3 §46 extension path)
- Test fixtures
- Terminology Registry seed data
- Medium Registry seed data
- Application Pattern Library seed data

## 3. Founder declaration (four-point assurance)

The founder hereby declares, based on personal review of the SeaLAI corpus as of the date above:

### 3.1 No employer-proprietary direct data

No employer-proprietary data -- specifically: compound recipes, internal test results, customer lists, non-public datasheets, internal calculation tables -- has been entered into any SeaLAI dataset listed in section 2.

### 3.2 PTFE KB-JSONs sourced from public material

The PTFE-RWDR knowledge base JSON files contain only values and classifications from public sources (DIN/ISO/API standards, publicly available manufacturer datasheets, professional literature) and the founder's general engineering domain knowledge. They do NOT contain employer-proprietary knowledge.

### 3.3 Golden cases and test fixtures are generic or constructed

Existing golden cases and test fixtures are based on generic, constructed, or public examples. They are NOT based on actual customer inquiries received at the employer.

### 3.4 Qdrant documents from non-employer sources

Qdrant vector store documents do not originate from internal employer sources.

## 4. Review trigger events

This declaration must be formally revisited and re-signed when any of the following occur:

- Quarterly calendar trigger (every three months from the date above)
- Substantive new manufacturer-specific content is added to the corpus
- Change of founder's employer or substantial change in employer's ownership
- Before onboarding the first external pilot manufacturer
- Any legal inquiry, lawsuit, or threatened litigation touching trade-secret, unfair-competition, or COI claims
- Any employee feedback, audit finding, or external reviewer claim alleging possible firewall violation

## 5. Legal and strategic context

### 5.1 Legal framework (Germany)

The founder acknowledges that this firewall is binding under:

- §17 UWG -- Verrat von Geschäftsgeheimnissen
- §§ 823, 826 BGB -- damages for breach of duty

Informal employer support for the SeaLAI project does NOT override these statutory obligations.

### 5.2 Strategic role in Moat Layer 1

Moat Layer 1 (Structural neutrality, Supplement v2 §37) depends on verifiable absence of employer-specific content in SeaLAI. A future discovery of employer-origin material would immediately falsify the neutrality claim and damage SeaLAI's market position in an industry where trust is critical.

## 6. Enforcement mechanisms

Going forward, when new content is added to the SeaLAI corpus:

- The source of each addition must be identifiable
- Public-domain or general-domain sources are acceptable
- Employer-sourced material is not permitted (unless explicitly released by the employer in writing)
- This log is updated if any edge cases arise

## 7. Annex A employer agreement dependency

This firewall log is one of two prerequisites for external pilot onboarding. The other is a signed version of the Annex A employer agreement template from Supplement v2. Both must exist in committed form before the first external manufacturer is contacted.

## 8. Signature

Declared and signed by: Thorsten Jung
Date: 2026-04-18
Location: [repository commit metadata serves as digital signature]
