# Keycloak Onboarding and Authentication Audit

**System:** sealingAI production realm `sealAI`  
**Date:** 2026-07-13  
**Scope:** Live Keycloak 26.7.0, realm settings, authentication and registration
flows, OIDC clients, tenant claims, dashboard authorization boundaries, and the
visible browser onboarding experience.

## Executive summary

> **Remediation update, 2026-07-13:** The owner explicitly approved a temporary
> test exception because the enrolled authenticator is unavailable. The live
> realm is currently reconciled with `KEYCLOAK_SECURITY_PROFILE=test`: the
> owner's OTP credential and pending OTP action are removed, ordinary login is
> unblocked, and the nested conditional OTP subflow is disabled. This is not a
> production release posture. The versioned `production` profile restores the
> standard password-then-OTP flow and requires fresh OTP enrollment for the
> privileged owner, requires email verification and password recovery, and
> fails reconciliation when realm SMTP is absent.
>
> KCA-01 is remediated in code by deriving a stable private workspace from the
> verified issuer and subject when no explicit tenant claim exists, and by
> enforcing `owner_subject` for conversations, curated memory, and durable case
> records. The browser cannot provide or override either boundary. Legacy rows
> without an owner remain inaccessible to ordinary authenticated users.

OTP is **not** the barrier for ordinary sealingAI users. Production currently has
nine realm users, one enrolled OTP credential, and no pending
`CONFIGURE_TOTP` required action. The only OTP user is also the only privileged
realm administrator. The active browser flow requests OTP only when a user has
already configured an OTP credential.

Removing OTP from the owner account would therefore not improve free-user
onboarding. It would weaken the most privileged account while leaving the real
onboarding defects untouched.

The actual release blocker is the mismatch between open self-registration and
the product's authorization model. Self-registration is enabled in production,
but three enabled accounts have no `tenant_id`. V2 rejects tokens without that
claim. Assigning every free user the existing shared `sealai` tenant would not
be a safe shortcut: several conversation, memory, and case reads are scoped to
the tenant rather than to the individual subject. A public free tier first needs
an isolated personal-workspace identity model.

The recommended product posture is:

1. Keep strong MFA for privileged and governance accounts in production; use
   the documented test exception only while access recovery is being tested.
2. Give free users a low-friction personal workspace without mandatory OTP.
3. Offer passkeys and enterprise/social identity as easier alternatives to a
   password, rather than weakening password protection.
4. Require an account only when a user wants persistence, files, memory, cases,
   or governed collaboration. A rate-limited anonymous knowledge entry point is
   the lowest-friction path for a user who only wants public sealing knowledge.

## Verified production state

| Control | Live state | Assessment |
|---|---|---|
| Keycloak | 26.7.0, digest-pinned image, healthy | Good |
| Hostname / proxy | strict public hostname, TLS at nginx, internal Keycloak ports only | Good |
| OIDC | Authorization Code + PKCE S256; implicit and direct grants disabled | Good |
| Access token | 5 minutes | Good |
| SSO session | 1 hour idle, 12 hours maximum | Appropriate baseline |
| Refresh tokens | rotation enabled, maximum reuse 0 | Good |
| Password storage | Argon2, 5 iterations | Current Keycloak default and good |
| Brute force | enabled, 6 failures, temporary backoff up to 15 minutes | Good, monitor denial-of-service risk |
| Self-registration | enabled | Safe only with the remediated private-workspace backend |
| Email verification | disabled in test; required in production profile | SMTP remains a production gate |
| SMTP | no realm SMTP configuration | Password recovery and verification are not operational |
| OTP default action | disabled | Correct for ordinary users |
| OTP enrollment | removed under explicit test exception | Must be re-enrolled before production |
| Pending OTP action | 0 users | No forced OTP onboarding for ordinary users |
| Identity providers | none | Avoidable sign-up friction |
| Passkeys | policy objects exist, but no enabled product flow or enrolled recovery path | Incomplete |
| Recovery codes | no active required-action/provider path | Incomplete for privileged recovery |
| Internationalization | German default, German/English enabled by reconciler | Remediated |
| Registration form | email-as-username; names progressive | Remediated |
| Tenant claim | optional for personal users | Missing claim derives a private workspace from verified issuer + subject |

## Findings

### KCA-01 — Open registration is incompatible with the tenant boundary

**Severity:** Critical before public onboarding  
**Evidence:**

- Production has `registration_allowed=true`; the versioned realm export has
  `registrationAllowed=false` in `keycloak/realm-export.json:30`.
- Three enabled production users have no non-empty `tenant_id` attribute.
- `backend/sealai_v2/security/auth.py:91-97` rejects tokens without a tenant.
- `backend/sealai_v2/api/routes/conversations.py:38-76` lists and reads
  conversations using only `(tenant_id, case_id)`.
- `backend/sealai_v2/db/conversation_memory.py:292-308` returns all sessions in
  a tenant.
- `backend/sealai_v2/api/routes/memory_v2.py:123-161` reads memory tenant-wide.
- `backend/sealai_v2/api/routes/case_records.py:95-115` retrieves a case bundle
  by tenant and case ID without checking `owner_subject`.

**Impact:** A self-registered user currently authenticates but cannot use V2.
If all free users were simply assigned `tenant_id=sealai`, tenant-wide endpoints
could expose or mutate another user's conversations, memory, or cases.

**Required fix:** Introduce a personal workspace boundary before reopening
public registration. A verified Keycloak subject must map server-side to a
unique personal workspace/tenant membership. Organization tenants must use an
explicit membership table and roles. Repository queries must enforce the
effective workspace plus subject/role policy; public clients must never choose
their own tenant.

**Immediate containment:** Do not market the current registration flow as a
working free onboarding path until KCA-01 is resolved. Do not assign all free
users to the shared `sealai` tenant as a shortcut.

**Remediation:** Implemented. A missing tenant claim now derives a stable
private workspace from the cryptographically verified issuer and subject.
Conversation sessions, curated memory items, and durable cases additionally
carry and enforce the verified owner subject. Same-tenant cross-user reads and
mutations return the same 404 as an unknown record.

### KCA-02 — Privileged MFA is enrolled once, not continuously role-enforced

**Severity:** High  
**Evidence:**

- `ops/keycloak_ensure_roles.sh:157-162` correctly keeps TOTP from becoming a
  global default action.
- `ops/keycloak_ensure_roles.sh:197-207` assigns TOTP during owner recovery and
  then grants privileged roles.
- The live browser flow uses `Condition - User Configured` followed by required
  OTP. This prompts OTP only while the credential exists.
- The reset-credentials flow contains `Reset - Conditional OTP`, so a recovery
  path can remove OTP after email verification once SMTP is configured.

**Impact:** The current owner is protected now, but deleting/resetting the OTP
credential can leave a privileged account able to authenticate with a password
until reconciliation assigns the action again. The policy claim "MFA is
required for privileged users" is stronger than its continuous enforcement.

**Required fix:** Bind a custom, versioned browser flow that requires a second
factor when the verified user has the `admin` or governance role. Prefer a
phishing-resistant passkey/WebAuthn credential; retain TOTP and recovery codes
as controlled fallback methods. Password/OTP reset for privileged accounts must
not silently downgrade the required assurance level.

**Remediation:** Implemented as two explicit desired-state profiles. Both use
Keycloak's supported browser-flow order, so an OTP authenticator never runs
before username/password has established the user. The production profile
enables the credential-conditioned OTP subflow and requires the privileged
owner to enroll whenever no OTP credential exists. The temporary test profile
disables that subflow for every user and removes the owner's inaccessible OTP
credential. Reconciliation revokes owner sessions after a profile change.
Passkeys and recovery codes remain a production hardening item.

### KCA-03 — Account recovery is enabled but cannot send mail

**Severity:** High for public launch  
**Evidence:** The realm has `reset_password_allowed=true`, but the live
`realm_smtp_config` contains no entries. Email verification is disabled.

**Impact:** A user can be offered a recovery path that cannot complete. Public
registration also accepts an email address without proving ownership.

**Required fix:** Configure and test SMTP, generic anti-enumeration messages,
delivery monitoring, bounced-mail handling, and short-lived action tokens.
Enable email verification for password accounts before granting persistence.
Social/OIDC accounts may rely on a trusted provider's verified email only when
the provider and claim policy are explicitly trusted.

**Remediation:** Contained, not operationally complete. Test mode disables
verification and password reset so the UI cannot advertise a broken mail path.
Production reconciliation fails closed when SMTP is absent. SMTP credentials,
delivery monitoring, and end-to-end mail tests remain required before launch.

### KCA-04 — The free-user registration UX is longer and less coherent than necessary

**Severity:** Medium  
**Evidence:** Browser inspection showed an English registration page requiring
username, password, password confirmation, email, first name, and last name.
The realm has `reg_email_as_username=false`, internationalization disabled, and
no default locale. The active B2B flow uses the combined username/password
authenticator, so the custom split username/password templates in
`keycloak/themes/sealai-b2b/login/` are not the forms users actually see.

**Impact:** Users coming from a German "kostenlos starten" CTA encounter a
generic English identity form, must invent a redundant username, and provide
profile data before receiving value.

**Required fix:** Use email as username, set German as the default locale with
German/English selectable, and collect only the minimum account data during
registration. First and last name should be progressive profile fields unless
there is a documented business or legal need at account creation. Align the
bound flow with the templates, or delete the inactive custom templates and
theme the active form deliberately.

**Remediation:** Implemented by desired-state reconciliation: email is the
username, German is the default with German/English enabled, and first/last name
are no longer registration requirements.

### KCA-05 — No low-friction password alternative is available

**Severity:** Medium  
**Evidence:** The realm has no configured identity providers and no active
passkey login/registration journey.

**Impact:** Every free user must create and remember a new password even when a
trusted enterprise or platform identity is available.

**Required fix:** Offer passkeys using Keycloak 26.7's conditional mediation,
plus carefully configured Microsoft and Google OIDC as optional sign-in paths.
Do not auto-join an organization based only on an email domain. Organization
membership remains an explicit, server-side authorization decision.

### KCA-06 — Password policy is close, but not optimized for password-only users

**Severity:** Medium  
**Evidence:** The policy is `length(14)`, maximum 128, not username/email, and
history 5. Passwords are stored with Argon2. No password denylist is configured.

**Impact:** Reducing the length to make onboarding easier would weaken the only
factor for free password users. At the same time, password history adds little
value when periodic password changes are not required, while common/breached
password blocking is absent.

**Required fix:** For password-only accounts, use at least 15 characters,
allow all character classes without composition rules, add a maintained common
password denylist, and avoid periodic forced rotation. Reduce friction by
offering passkeys/identity providers, not by shortening the password.

**Remediation:** Partially implemented. The desired policy now requires 15
characters, permits up to 128, blocks username/email reuse, and keeps history
five. A maintained breached/common-password source remains a production gate.

### KCA-07 — Realm configuration has production drift

**Severity:** Medium  
**Evidence:** The versioned export says registration and brute-force protection
are disabled, while production has registration and brute-force protection
enabled. `ops/keycloak_ensure_roles.sh` reconciles only part of the realm and
does not assert registration, locale, email verification, SMTP readiness, or
the active browser/registration flow as one coherent product profile.

**Impact:** A restore, recovery, or later reconciliation can silently change
onboarding and security behavior. Reviewers cannot infer production state from
the repository.

**Required fix:** Replace the stale full export as an authority with an
idempotent desired-state reconciliation and a redacted read-back test. The test
must fail on drift in registration, flows, required actions, token/session
policy, client redirects/origins, locale, SMTP presence, roles, and protocol
mappers. Exports remain rollback artifacts, not the primary configuration API.

**Remediation:** Implemented. The idempotent reconciler asserts the selected
security profile, realm policy, registration shape, roles, clients,
ordered password/OTP flow, privileged enrollment state, and redacted live
readback. Bootstrap exports were aligned but remain recovery artifacts rather
than the production authority.

### KCA-08 — Privileged recovery lacks a second usable factor

**Severity:** Medium  
**Evidence:** The privileged owner has TOTP, but the realm has no active recovery
codes path and no registered passkey path.

**Impact:** Loss of the authenticator creates an avoidable administrator
lockout and encourages unsafe emergency bypasses.

**Required fix:** Enroll at least two independently stored privileged factors:
prefer two passkeys (for example, platform plus hardware key), with sealed
recovery codes and the existing one-shot bootstrap-admin runbook as the final
break-glass path. Test recovery without weakening the normal flow.

### KCA-09 — The Keycloak admin console shares the public application ingress

**Severity:** Low now, defense-in-depth  
**Evidence:** `nginx/default.conf:215-229` exposes `/admin/` on
`sealingai.com`; `docs/keycloak-upgrade.md` already records this boundary.

**Required fix:** Move the admin console to a separately controlled admin
hostname or VPN/identity-aware ingress when operationally available. Keep realm
admin roles owner-specific and phishing-resistant MFA mandatory.

## Recommended target journeys

### 1. Anonymous knowledge visitor

- Can ask a bounded, rate-limited public knowledge question without an account.
- Cannot upload files, create durable memory, save a case, see private sources,
  or invoke organization/manufacturer workflows.
- Is asked to create an account only when persistence or governed work begins.

### 2. Free personal workspace

- Email-as-username, passkey or trusted OIDC preferred.
- Password fallback uses the password policy in KCA-06.
- No mandatory OTP at first sign-in.
- Verified subject maps to a unique personal workspace.
- Optional passkey enrollment is offered after the first successful value
  moment, not as a blocking registration step.

### 3. Organization / manufacturer workspace

- Explicit invitation or independently validated membership.
- Role and organization membership are separate from email-domain ownership.
- Step-up MFA for sensitive actions such as invitations, exports, capability
  changes, approvals, and factor changes.

### 4. Admin and governance

- Separate privileged identity; do not use it as the normal UX test account.
- Passkey/WebAuthn required by role on every new privileged authentication.
- TOTP/recovery codes only as controlled fallback.
- Short session, event logging, no email-only downgrade of MFA.

## Implementation order

1. **Contain drift:** Mark current self-registration as non-production until the
   personal workspace path exists. Preserve admin TOTP.
2. **Fix authorization ownership:** Add workspace memberships and subject-aware
   repository policies; migrate existing users and prove cross-user denial.
3. **Automate onboarding:** Create a personal workspace and `user_basic`
   membership atomically on verified first login. Do not trust client-provided
   tenant data.
4. **Reconcile Keycloak declaratively:** Version and test the exact realm, flows,
   client scopes, actions, locale, recovery, and role policy.
5. **Reduce friction:** Email-as-username, German locale, minimal registration,
   passkeys, optional Microsoft/Google OIDC, operational SMTP.
6. **Harden privileged authentication:** Role-conditioned phishing-resistant
   MFA, recovery codes, second passkey, and non-downgradable recovery.
7. **Expose anonymous knowledge carefully:** Rate limits, abuse telemetry,
   strict data boundaries, no persistence, and no private source access.

## Mandatory acceptance tests

- A new free user sees no OTP setup and receives a unique personal workspace.
- User A cannot list, read, edit, delete, or infer User B's conversations,
  memory items, cases, snapshots, decisions, or files.
- A verified personal user without an explicit tenant claim receives a stable,
  private server-derived workspace; an unverified token is denied.
- A user cannot select or alter `tenant_id` from the browser.
- An admin with no approved second factor cannot obtain a privileged session.
- Password reset and factor reset do not downgrade privileged MFA.
- Recovery works with a second passkey/recovery code and leaves an audit event.
- Registration and login are coherent in German and English on mobile/desktop.
- SMTP verification and reset links work, expire, and do not enumerate accounts.
- Bot registration controls do not impose a visible challenge on ordinary
  traffic unless risk requires it.
- A read-only drift check matches repository desired state to production.

## Primary guidance used

- Keycloak Server Administration Guide: authentication flows, conditional OTP,
  passkeys, recovery codes, registration, password policies, and brute-force
  detection: https://www.keycloak.org/docs/latest/server_admin/index.html
- Keycloak 26.7.0 release notes: current passkey/WebAuthn policy behavior:
  https://www.keycloak.org/2026/07/keycloak-2670-released
- NIST SP 800-63B-4: authentication assurance, password length, and
  phishing-resistant options: https://pages.nist.gov/800-63-4/sp800-63b.html
- OWASP Authentication and MFA Cheat Sheets: adaptive/step-up authentication,
  common-password blocking, and MFA UX:
  https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
  and https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html
- CISA MFA guidance: prioritize phishing-resistant MFA for administrators and
  sensitive access:
  https://www.cisa.gov/audiences/small-and-medium-businesses/secure-your-business/require-multifactor-authentication

## Decision

**Current decision:** OTP removal is approved only for the temporary test
profile because the owner cannot access the enrolled authenticator. Do not call
this profile production-ready. Before production, switch to
`KEYCLOAK_SECURITY_PROFILE=production`, configure and test SMTP, re-enroll at
least one approved admin factor (preferably two passkeys plus controlled
recovery), and rerun the drift readback. Personal-workspace provisioning and
subject-level authorization are implemented in this remediation branch.
