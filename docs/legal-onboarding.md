# Legal Onboarding: The Legal Gate

## Mechanics

A B2B business-identity + legal-acceptance record required before productive use (chat/briefing/
compute/anfrage). Backend: `db/models.py::V2LegalAcceptance` (one row per tenant — companyName,
businessEmail, role, vatId, three boolean confirmations, three accepted doctrine versions,
timestamp, a salted IP hash, user agent). `api/routes/legal.py`:

- `GET /api/v2/legal/doctrine` — public, current `TERMS_VERSION`/`PRIVACY_VERSION`/`DPA_VERSION`.
- `POST /api/v2/legal/acceptance` — submits the record; rejects a freemail `business_email` domain
  (422), rejects a stale doctrine version (409 — the client must re-fetch `/doctrine` first).
- `GET /api/v2/legal/acceptance-status` — lets the frontend check gate status without re-submitting.

`api/deps.py::require_legal_acceptance` — a fail-closed dependency (mirrors `require_admin`'s
shape) wired onto `/chat`, `/chat/stream`, `/briefing`, `/compute`, `/anfrage`. 403
`legal_acceptance_required` unless a CURRENT (version-matching) row exists for the caller's tenant.
Frontend: `frontend-v2/src/components/LegalGate.tsx` blocks `Shell` (the whole product UI) until
accepted, with links to the three legal pages.

## Freemail blocking

`core/legal_doctrine.py::is_business_email()` checks the domain against `FREEMAIL_DOMAINS` (gmail,
gmx.de, web.de, outlook, ...). Validated server-side at acceptance-submission time — NOT at the
Keycloak registration layer (auth stays untouched; this is a business-rule check on a form field,
not an identity-provider change).

## Why both gates default OFF

`SEALAI_V2_LEGAL_GATE_ENABLED` (backend) and `VITE_LEGAL_GATE_ENABLED` (frontend) both default
`False`. **The shipped legal pages (`/nutzungsbedingungen`, `/datenschutz`, `/auftragsverarbeitung`)
are attorney-review drafts, not final legal text.** Turning the gate on before a review pass would
mean lawfully-uncertain text starts blocking paying customers from the product. Both flags are fully
wired, tested, and deploy-ready — flipping them on is a deliberate, separate, owner-authorized step
once the pages are reviewed.

## Open items before activation (owner-only)

- Attorney review of the three legal pages.
- Fill in the `[Platzhalter: ...]` placeholders: company name/legal form/address (Nutzungsbedingungen
  §1, Auftragsverarbeitung §1), Gerichtsstand (Nutzungsbedingungen §8), Datenschutz-Kontakt +
  Verantwortlicher (Datenschutz §1/§8), Hosting-Anbieter/Serverstandort (Datenschutz §5,
  Auftragsverarbeitung §6).
- `/impressum` — still a dead footer link. Deliberately NOT built this session: it requires real
  company registration facts (Handelsregister, USt-ID, Geschäftsführer) this agent has no access to
  and must not invent.
- A real cookie-consent banner UI before `NEXT_PUBLIC_GOOGLE_CONSENT_DEFAULT` is ever set to
  `granted` in production (currently defaults to `denied` — see `Datenschutz` §6's own open-item
  note).
- The gate currently covers chat/briefing/compute/anfrage. `conversations.py` (case list/read,
  edit/forget fact) is deliberately NOT gated — it's pure case-state management with no LLM call and
  no third-party transmission, so it doesn't carry the same legal exposure; revisit if that changes.

## Tests

`backend/sealai_v2/tests/test_legal_doctrine.py`, `test_legal_acceptance_store.py`,
`test_api_legal.py`, `test_legal_gate.py` (37 tests — freemail rejection, stale-version rejection,
tenant isolation, gate on/off across all five wired routes). Frontend:
`frontend-v2/src/api/legal.test.ts`, `components/LegalGate.test.tsx` (10 tests).
