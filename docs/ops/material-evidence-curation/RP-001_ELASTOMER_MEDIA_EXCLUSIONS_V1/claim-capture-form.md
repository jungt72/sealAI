# RP-001 atomic claim capture form

Copy this file once for each claim. Keep every field explicit. Do not use an
empty value, `null`, "same as above", or an inferred default. A partly completed
form is `NOT_IMPORTABLE`.

This worksheet is not evidence authority. Only the existing repositories can
derive canonical references, validate snapshots, and append authenticated
human lifecycle events.

## 1. Record control

| Field | Human entry | Requirement |
|---|---|---|
| Package ID | `RP-001_ELASTOMER_MEDIA_EXCLUSIONS_V1` | Fixed. |
| Worksheet ID |  | Locally unique, non-authoritative work identifier. |
| Worksheet state | `DRAFT` | `DRAFT`, `CREATOR_COMPLETE`, `RETURNED_BY_REVIEWER`, `REVIEW_READY`, `APPROVAL_READY`, or `REJECTED`. These are worksheet states, not MAT-EVID lifecycle states. |
| Tenant ID |  | Must come from the authenticated operator context; never from a request override. |
| Domain pack ID |  | Owner-supplied exact `domain_pack_id`; do not invent. |
| Created timestamp |  | UTC ISO-8601. |
| Last edited timestamp |  | UTC ISO-8601. |

Do not record a token, session ID, password, or credential in this form.

## 2. Candidate selection

| Field | Human entry | Requirement |
|---|---|---|
| Material gap subject ID |  | Exact `material:*` ID from `candidate-register.json`. |
| Service/media gap subject ID |  | Exact `service:*` ID from `candidate-register.json`. |
| Why this pair is being researched |  | Research rationale only; it must not assert compatibility or incompatibility. |
| Pairing selected by creator | `NO` | Change to `YES` only by the verified-human creator after deliberate selection. |
| Legacy matrix used | `NO` | Must remain `NO`. |
| LLM classification used | `NO` | Must remain `NO`. |

The two gap labels are triage inputs only. They are not canonical material,
media, service, or compatibility facts.

## 3. Proposed rule boundary

Complete this section only after source acquisition. It is still a proposal,
not a `MaterialRuleV1`.

| Field | Human entry | Requirement |
|---|---|---|
| Proposed rule reference |  | Reserved `MR-<UPPERCASE-ASCII-ID>` supplied under the later import authorization. |
| Proposed verdict |  | Exactly `unvertraeglich` or opaque `bedingt`; never `vertraeglich`. |
| Material identity |  | Exactly one human-confirmed material/compound identity; a family must not be represented as a released compound. |
| Canonical media ID |  | Exactly one current reviewed `med_<64 lowercase hex>` entry. Free text is not accepted. |
| Condition reference |  | Exactly one explicit, non-empty condition reference. No wildcard or ambiguous zero/null semantics. |
| Complete proposed statement |  | Must later equal one primary claim byte-for-byte after NFC normalization. Maximum 512 Unicode characters and 1024 UTF-8 bytes. |
| Positive statement present | `NO` | Must remain `NO`. |

## 4. Claim purpose and type

| Field | Human entry | Requirement |
|---|---|---|
| Claim purpose |  | One of `RULE_PRIMARY`, `RULE_SUPPORTING`, or `MEDIA_IDENTITY`. |
| Claim type |  | Closed MAT-EVID-01C value listed below. |
| Claim text |  | One atomic proposition; maximum 512 Unicode characters and 1024 UTF-8 bytes for approval. |
| Uncertainty/open point |  | Explicitly state remaining uncertainty. This text is workflow context and is not imported as a claim. |

Allowed mappings:

| Purpose | Allowed claim type |
|---|---|
| `RULE_PRIMARY` with proposed `unvertraeglich` | `incompatibility` |
| `RULE_PRIMARY` with proposed `bedingt` | `conditional_compatibility` |
| `RULE_SUPPORTING` | `temperature_limit`, `application_limit`, or `regulatory_constraint` |
| `MEDIA_IDENTITY` | `other_technical` only; this belongs to a separately reviewed MED-NORM identity track and is not a supporting MATERIAL-RULES claim. |

No temperature value, limit, coefficient, regulation, or application fact may
be entered unless the cited source states it and the human scope review accepts
it.

## 5. Exact claim scope

MAT-EVID stores arrays, but RP-001 rule claims must be atomic.

| Field | Human entry | Requirement |
|---|---|---|
| `scope.materials[0]` |  | Exactly one value for a rule claim. For a `MEDIA_IDENTITY` claim this field is forbidden by `RP001-OD-01`; do not invent a placeholder. |
| `scope.media[0]` |  | Exactly one canonical `med_*` ID for a rule claim. A future v2 MED-NORM identity claim instead uses exactly one scalar `media_ref`. |
| `scope.conditions[0]` |  | Exactly one value. For a MED-NORM identity claim, exactly the catalog entry's `med-norm-identity-sha256:<hash>` assertion reference. |
| Additional materials/media/conditions | `NONE` | Must remain `NONE`; split the proposition into another claim if needed. |

All values must be NFC, non-empty, unique, and UTF-8-byte sorted in imported
arrays. Punctuation or conjunctions never prove a resolved multi-medium scope.

## 6. Source records

Repeat this block for every source supporting the claim. A URL alone is
insufficient.

| MAT-EVID field | Human entry | Requirement |
|---|---|---|
| `document_id` |  | Stable document identity, maximum 256 characters / 512 UTF-8 bytes. |
| `document_revision` |  | Exact revision, maximum 128 / 256. |
| `publication_edition` |  | Exact edition/issue, maximum 128 / 256. |
| `content_sha256` |  | SHA-256 of the exact acquired source bytes, lowercase hex. |
| Derived `source_ref` | `PENDING_DERIVATION` | Must be computed by `derive_source_ref`; never hand-authored. |
| `document_title` |  | Exact title, maximum 512 / 1024. |
| `publisher` |  | Exact publisher, maximum 256 / 512. |
| `document_type` |  | One closed type from the list below. |
| `locator.state` |  | `exact` or `unavailable`. |
| `locator.value` or `locator.reason` |  | Exact section/page/table or a specific unavailability reason; maximum 512 / 1024. |
| `rights_state` |  | `permitted`, `licensed`, `public_domain`, `unknown`, or `restricted`. |
| `rights_basis` |  | Verifiable basis, maximum 512 / 1024. |
| `excerpt.state` |  | Prefer `omitted`; use `included` only when rights permit. |
| `excerpt.text` |  | If included: maximum 280 characters / 1024 bytes. Never a full standard or long passage. |
| `excerpt.rights_basis` |  | Required when an excerpt is included. |
| Independent access path |  | Reviewer-accessible location outside this repository; do not place licensed content here. |

Closed document types:

- `manufacturer_datasheet`
- `peer_reviewed_publication`
- `standard_metadata`
- `regulatory_document`
- `technical_report`
- `internal_expert_attestation`

## 7. Claim/source binding

| Field | Human entry | Requirement |
|---|---|---|
| Source references |  | Every and only the derived `source_ref` values that support this claim, unique and sorted. |
| Required source types |  | Non-empty MAT-EVID-01C set chosen by the human review policy; unique and sorted by enum value. Do not invent a default policy. |
| Derived `claim_ref` | `PENDING_DERIVATION` | Must be computed from exact NFC claim text and scope by `derive_claim_ref`. |
| Proposed `rule_ref -> claim_ref` binding | `PENDING_DERIVATION` | May be created only after the exact ruleset snapshot exists. |
| Unreferenced source present | `NO` | Must remain `NO`; every source must support at least one claim. |
| Unbound claim present | `NO` | Must remain `NO`; every claim must bind to a rule in MAT-EVID-01A.v1. |

## 8. Conflict and supersession review

| Field | Human entry | Requirement |
|---|---|---|
| Search performed across current sources | `NO` | Reviewer changes to `YES` after independent search. |
| Potential conflicting claim references |  | Record candidate work IDs before canonical refs exist. |
| Potential superseded claim references |  | Record candidate work IDs before canonical refs exist. |
| MAT-EVID `claim_relations` | `PENDING_REVIEW` | Approval requires the final array to be empty. A conflict requires a corrected evidence snapshot, not a waiver. |

## 9. MED-NORM identity check

| Field | Human entry | Requirement |
|---|---|---|
| Existing reviewed catalog entry found | `NO` | If `NO`, the RP-001 rule claim remains blocked. |
| Evidence scope for identity claim | `MEDIA_IDENTITY_V2_REQUIRED` | `RP001-OD-01` requires a typed v2 `media_identity` scope with no materials and exactly one `media_ref`; import remains blocked until v2 exists end to end. |
| Canonical name |  | Human-curated; never inferred from the service-gap label. |
| Identity kind |  | `chemical_substance`, `defined_mixture`, `fluid_class`, `trade_name`, `process_medium`, or `additive_system`. |
| Exact aliases |  | Complete, unique, NFC and UTF-8-byte sorted; canonical name excluded. |
| Derived media ID | `PENDING_DERIVATION` | Compute with `derive_media_id`. |
| Reviewed identity claim refs |  | Must be approved `other_technical` claims scoped exactly to the media ID and identity assertion. |
| Review snapshot ID/hash |  | Exact current approved MAT-EVID-01C snapshot and content hash. |
| Catalog entry SHA-256 | `PENDING_DERIVATION` | Repository-derived after successful catalog validation. |

## 10. Human separation and handoff

Record stable authenticated subjects only in the append-only repository event.
Do not copy token or session claims into this worksheet.

| Role | Subject recorded by repository | Required verified roles | Completion |
|---|---|---|---|
| Creator |  | `verified_human`, `material_evidence:create` | `PENDING` |
| Reviewer |  | `verified_human`, `material_evidence:review` | `PENDING` |
| Owner-approver |  | `verified_human`, `material_evidence:approve` | `PENDING` |

The three subjects must be pairwise different. A service principal, model,
agent, shared account, or unverified header cannot fill any role.

## 11. Creator declaration

- [ ] I accessed every listed source.
- [ ] I did not use an existing matrix cell or LLM output as a claim source.
- [ ] I entered no positive compatibility statement.
- [ ] The claim is atomic and its uncertainty is explicit.
- [ ] Rights information is complete to the best of my documented knowledge.
- [ ] I have not reviewed or approved my own work.

Creator action: submit the immutable candidate inputs for technical validation;
do not mark the claim reviewed or approved in this file.
