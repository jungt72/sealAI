# Legal-by-Design: Product Doctrine

Single source: [`backend/sealai_v2/core/legal_doctrine.py`](../backend/sealai_v2/core/legal_doctrine.py) (`PRODUCT_PURPOSE_DOCTRINE`).

## What sealingAI is

KI-gestützte **Wissens-, Strukturierungs- und Anfrageintelligenz** für Dichtungstechnik:
information extraction, case structuring, parameter mapping, document/upload evaluation as a
working basis, RFQ preparation, general explanation, marking uncertainties.

## What sealingAI is NOT

No technical approval, no binding design/Auslegung, no material/suitability approval, no
standards-conformity or safety assessment, no manufacturer approval, no inspection report
(Prüfbericht/Gutachten), no binding "geeignet" recommendation. Every output is a draft
(Arbeitsentwurf/Anfrageentwurf) — final decisions sit with the manufacturer / responsible engineer.

## Where this is enforced (not just stated)

| Surface | Mechanism |
|---|---|
| L1 prompt (always) | `core/framing.py`'s `CLAIM_BOUNDARY`/`GELTUNGSRAHMEN` — the pre-existing, always-on per-answer claim boundary |
| L1 prompt (risk-flagged turns, opt-in) | `system_l1.jinja`'s `{% if risk_flags %}` block, gated by `SEALAI_V2_RISK_FLAG_PROMPT_ENABLED` (default OFF) |
| Chat/briefing/anfrage response | `risk_flags` field (always populated, see `docs/ai-safety-guardrails.md`) |
| PDF export | title "Technisches Arbeitsblatt / Anfrageentwurf" + disclaimer + risk badge — `frontend-v2/src/lib/pdf.ts` |
| UI vocabulary | `FORBIDDEN_STATUS_TERMS` map + the terminology lint (backend `test_terminology_lint.py`, frontend `scripts/check-terminology.mjs`) |
| Legal pages | `/nutzungsbedingungen`, `/datenschutz`, `/auftragsverarbeitung` (marketing site) restate the same doctrine in binding legal form |
| Onboarding | Legal Gate — see `docs/legal-onboarding.md` |

## Versioning

`TERMS_VERSION` / `PRIVACY_VERSION` / `DPA_VERSION` in `legal_doctrine.py` are plain date-stamped
strings (not content hashes — the legal page text lives in the Next.js marketing app, outside this
module's reach). Bump on every reviewed text change; the Legal Gate forces re-acceptance on a bump.

## Non-goal

This module does not constitute legal advice and the shipped legal pages are attorney-review
**drafts** (see `docs/legal-onboarding.md`'s open items). This doc describes engineering
enforcement of an already-drafted doctrine, not the doctrine's legal sufficiency.
