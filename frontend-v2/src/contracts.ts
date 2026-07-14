// TS shapes mirroring the /api/v2 JSON (M6c). The V2 client's OWN contracts — it never imports V1's
// @/lib/contracts. These are display shapes only; all truth is computed server-side.
export interface Citation {
  text: string;
  sources: string[]; // owner-verified PRIMARY sources (Parker / ISO 3601-2) — never the internal card_id
}
// M8 kernel channel: a deterministically computed value (the kern owns numbers; the browser never
// computes). `parent_fields` are the case-state inputs it depends on; populated on the /compute read
// surface, empty on the chat in-band path. provenance is always "kernel_computed".
export interface KernelValue {
  calc_id: string;
  name: string;
  value: number;
  unit: string;
  formula: string;
  parent_fields: string[];
  input_origins: string[];
  provenance: string;
}
export interface NotComputed {
  calc_id: string;
  reason: string; // honest "nicht berechenbar" — never a number
}
// A fail-closed unit-recovery hint from the binder (kernel channel). The binder NEVER auto-binds;
// `one_click` is the BACKEND-owned "appending the canonical unit is safe" decision — the panel MUST
// honor it (no confirm button when one_click=false, or the no-silent-rescale guard is bypassed).
export interface Clarification {
  feld: string;
  input_name: string;
  raw_value: string; // the number as typed ("5000"); the full value when no number (no_value)
  raw_unit: string; // the trailing token as typed ("u/mon"); "" when missing
  reason: "no_value" | "unit_missing" | "unit_known_other" | "unit_unrecognized";
  suggested_unit: string; // the field's expected canonical unit (e.g. "U/min")
  known_dimension: string; // the TYPED unit's dimension (unit_known_other): length|frequency|angle
  expected_dimension: string; // the FIELD's dimension; differs from known ⇒ wrong kind of quantity
  one_click: boolean; // true ⇒ append suggested_unit to raw_value is a SAFE recovery
}
export interface ComputeResponse {
  computed: KernelValue[];
  not_computed: NotComputed[];
  notes: string[];
  clarifications?: Clarification[]; // additive; absent on older payloads → treated as []
}
// Phase 2b — the parameter-form batch submit + its deterministic confirmation. `wert` in
// `uebernommen` is the POST-BIND value (kernel) or the settled value (context), never the raw
// submitted string; a clarify-triggering field is a `rueckfragen` entry, never claimed as taken.
export interface ParamItem {
  feld: string;
  wert: string;
  label: string;
}
export interface ConfirmationTaken {
  feld: string;
  label: string;
  wert: string;
}
export interface ConfirmationRueckfrage {
  feld: string;
  label: string;
  clarification: Clarification;
}
export interface ConfirmationResponse {
  uebernommen: ConfirmationTaken[];
  rueckfragen: ConfirmationRueckfrage[];
  computed: KernelValue[];
  not_computed: NotComputed[];
  notes: string[];
  clarifications: Clarification[];
  next_question?: NextQuestionPayload | null;
}
// Medium Intelligence (Phase 2): helper-LLM-researched medium properties + sealing challenges for the
// MEDIUM panel. ALWAYS vorläufig (LLM knowledge, never reviewed) — the panel renders the badge.
export interface MediumIntelligence {
  medium: string;
  kategorie: string;
  eigenschaften: string[];
  herausforderungen: string[];
  werkstoff_tendenz: string[];
  unsicher: boolean;
  vorlaeufig: boolean;
}
// Kandidaten-Spezifikation (Produktspec v3.1) — a deterministic, STRUCTURALLY CAPPED candidate space
// (Bauform/Werkstoff/DIN). NEVER a release: final_design_code is always null (G3), freigegeben always
// false (G1), a free-text medium → candidate-set only (G2). Render-only; always "vorläufig".
export interface SpecAxis {
  name: string;
  value: string | null;
  status: string;
  begruendung: string[];
}
export interface SpecMaterial {
  kind: string;
  primary: string[];
  alternatives: string[];
  escalation: string[];
  excluded: string[];
  reason_codes: string[];
  next_question: string[];
  validation_required: boolean;
}
export interface KandidatenSpec {
  response_level: string;
  envelope_band: string | null;
  kritikalitaet: string;
  axes: SpecAxis[];
  material: SpecMaterial;
  material_candidate_set: string[];
  din_candidate_label: string | null;
  final_design_code: string | null; // always null (G3)
  defer_gruende: string[];
  open_verifications: string[];
  offene_punkte: string[];
  failure_mode_checklist: string[];
  freigegeben: boolean; // always false (G1)
  geltungsrahmen: string;
  quellen: string[];
}
// Modus F (Hersteller-Partner pool, Dim. 6) — owner business model: payment gates pool MEMBERSHIP,
// the SELECTION ranks BY CAPABILITY (neutral, §3.9; never pay-to-rank). A paid listing → transparently
// labelled "Partner · Anzeige". lead_email is internal and is NEVER part of this payload.
export interface HerstellerOption {
  id: string;
  firmenname: string;
  beschreibung?: string;
  website?: string;
  standort?: string;
  werkstoffe?: string[];
  zertifikate?: string[];
}
export interface Alternativen {
  grounded_data: boolean;
  partner?: boolean; // true → transparent paid partner pool ("Partner · Anzeige")
  hersteller?: HerstellerOption[]; // capability-ordered, neutral (never pay-to-rank)
  ordered_by?: string;
  neutralitaet?: string;
  hinweis?: string; // shown when grounded_data is false
}
// The lead-gen action (POST /api/v2/anfrage): a structured RFQ briefing routed to the chosen partner.
// The briefing preview is returned so the user transparently sees what was sent; lead_email never is.
export interface AnfrageResponse {
  status: string;
  lead_id: number;
  partner: { hersteller: string; firmenname: string };
  briefing: { title: string; body: string; provenance: string[] };
  case_id: string;
  case_revision: number;
  read_only: true;
  hinweis: string;
}
// Platform-owner surface (/api/v2/admin/*, role-gated). The FULL editable partner record — incl.
// lead_email (the routing target the owner manages); never exposed on the user-facing pool.
export interface AdminPartner {
  hersteller: string;
  firmenname: string;
  aktiv: boolean;
  lead_email: string;
  website: string;
  beschreibung: string;
  standort: string;
  kontakt_oeffentlich: string;
  partner_seit: string;
  plan: string; // billing metadata — never a ranking input
  werkstoffe: string[];
  bauformen: string[];
  groessen: string;
  zertifikate: string[];
}
export interface AdminLead {
  id: number;
  partner_id: string;
  firmenname: string;
  lead_email: string;
  tenant_id: string;
  session_id: string;
  briefing_title: string;
  briefing_body: string;
  created_at: string;
  status: string;
}
// Manufacturer SELF-SERVICE (/api/v2/partner/me). The GET returns the full AdminPartner record; the
// PUT body is only the manufacturer-editable subset (aktiv/plan/partner_seit stay owner-controlled).
export type SelfPartnerUpdate = Pick<
  AdminPartner,
  | "firmenname"
  | "lead_email"
  | "website"
  | "beschreibung"
  | "standort"
  | "kontakt_oeffentlich"
  | "werkstoffe"
  | "bauformen"
  | "groessen"
  | "zertifikate"
>;
// The manufacturer's own leads — no lead_email / tenant / session (the user's internal ids stay hidden).
export interface SelfLead {
  id: number;
  firmenname: string;
  briefing_title: string;
  briefing_body: string;
  created_at: string;
  status: string;
}
// Wissens-Beitrag: a user shares their worked-out situation + outcome to improve sealingAI. Anonymous by
// default; lands as an untrusted DRAFT in the owner review queue, never auto-feeds a recommendation.
export interface ContributePayload {
  anonym: boolean;
  situation: string;
  recommendation: string;
  outcome: string;
  case_state: { feld: string; wert: string }[];
}
export interface AdminContribution {
  id: number;
  anonym: boolean;
  tenant_ref: string;
  subject_ref: string;
  situation: string;
  case_state: { feld: string; wert: string }[];
  recommendation: string;
  outcome: string;
  created_at: string;
  status: string;
  review_note: string;
}
// Modus E (Gegencheck): a DISQUALIFY-ONLY verdict (owner doctrine E4-1) — `disqualified`/`basis` are
// always present when the object exists at all; `reason`/`source` only accompany a disqualification,
// `condition`/`source` only accompany `basis === "matrix_conditional"`. NEVER render a badge/claim for
// any other `basis` value — the absence of a documented incompatibility is not itself a suitability
// claim (see backend core/gegencheck.py).
export interface Gegencheck {
  disqualified: boolean;
  basis?: "matrix_compatible" | "matrix_conditional" | "no_matrix_data" | "no_medium";
  reason?: string; // grounded matrix cell text, verbatim — only when disqualified
  condition?: string; // grounded matrix cell text, verbatim — only when basis === "matrix_conditional"
  source?: string;
}
// L3 trust status (P1.5) — lets the client distinguish a confidently-verified answer from a hedge or
// a silently-unverified one. See backend api/serializers.py::_verification() for the exact semantics.
export interface Verification {
  action: "pass" | "flag" | "corrected" | "blocked_hedge" | null;
  parse_ok: boolean | null;
  hedged: boolean;
  ran: boolean;
}
export interface NextQuestionPayload {
  case_id: string;
  topic_id: string;
  state_revision: number;
  pack_id: string;
  pack_version: string;
  policy_version: string;
  question_id: string;
  primary_need_id: string;
  related_need_ids: string[];
  question_text: string;
  question_type: string;
  answer_schema: Record<string, unknown>;
  allowed_unknown: boolean;
  allowed_unobtainable: boolean;
  criticality: string;
  rule_refs: string[];
  dependency_refs: string[];
  pending_question_id: string;
}
export interface InterviewRefreshResponse {
  case_id: string;
  next_question: NextQuestionPayload | null;
}
export interface ChatResponse {
  answer: string;
  model: string;
  grounded: boolean; // false → the answer is "vorläufig" (no reviewed grounding)
  intent: string | null;
  citations: Citation[];
  computed?: KernelValue[]; // M8: in-band kern result (additive; panel can update without a 2nd call)
  not_computed?: NotComputed[];
  medium_intelligence?: MediumIntelligence | null; // Phase 2: the MEDIUM panel data (vorläufig)
  kandidaten_spec?: KandidatenSpec | null; // Produktspec v3.1: the PRODUKT-KANDIDAT panel (vorläufig)
  alternativen?: Alternativen | null; // Modus F: the HERSTELLER-AUSWAHL panel data
  gegencheck?: Gegencheck | null; // Modus E: disqualify-only verdict, or null (no Gegencheck situation)
  verified?: boolean; // P1.5: the conservative, honest L3 trust signal
  verification?: Verification; // P1.5: the raw signals behind `verified` (for a precise badge)
  risk_flags?: string[]; // Legal-by-Design Phase D: matched regulated/safety-critical terms, or []
  run?: {
    run_id: string;
    status: string;
    case_id: string;
    case_revision_started: number;
    case_revision_current: number;
    risk_level: string;
    route_name?: string | null;
    execution_class?: string | null;
    model_tier?: string | null;
    verification_mode?: string | null;
    policy_version?: string | null;
    needs_human_review?: boolean;
  } | null;
  // Phase 2B routing → render contract: route-aware chat-UI display flags. All OPTIONAL/nullable so
  // older cached responses and the non-streaming /chat fallback never break. The backend defaults
  // every flag to True whenever no route was classified, so `undefined` MUST be treated as `true`
  // (show) — a section only hides when the flag is explicitly `false`. show_evidence is ANDed with
  // the existing non-empty-citations check; it can only hide Belege, never invent citations.
  route_name?: string | null; // the classified RouteName, or null when route optimization did not run
  show_technical_preassessment?: boolean; // gate the "Technische Vorbewertung" meta block
  show_evidence?: boolean; // gate the "Belege" (citations) section
  show_calculations?: boolean; // gate calculation-derived sections (no matching block in Answer yet)
  show_rfq_sections?: boolean; // gate RFQ-specific sections (no matching block in Answer yet)
  // Backend-owned adaptive-interview question. Absent when the controller is disabled, the case is
  // outside the active RWDR scope, or no question directive is available.
  next_question?: NextQuestionPayload;
}
export interface RememberedFact {
  feld: string;
  wert: string;
  provenance: string; // "distilled-from-conversation" = remembered, unverified
}
export interface Turn {
  role: string;
  text: string;
}
export interface ConversationMemory {
  case_id?: string;
  case_revision?: number;
  case_state: RememberedFact[];
  history: Turn[];
}
// "Fälle"-Sidebar — one entry in the tenant's case list (GET /api/v2/conversations). `title`/
// `created_at`/`updated_at` are null for a case that predates this feature or hasn't had a turn yet.
export interface CaseSummary {
  case_id: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
}
export interface Briefing {
  kind: string;
  title: string;
  body: string;
  provenance: string[];
  case_id?: string;
  case_revision?: number;
  message_index?: number;
  read_only?: boolean;
  risk_flags?: string[]; // Legal-by-Design Phase D/E: drives the same badge in-app and in the PDF export
}

// --- sealingAI Memory Architecture V1.0 — Patch 1 (Types & Schemas) ---
// Mirrors backend/sealai_v2/memory/curated.py. This is the CURATED, cross-session, owner-
// confirmable memory tier — distinct from ConversationMemory/RememberedFact above (the existing
// session working-window/case-state, Layer 1-3). No API wiring yet (Patch 3+); these types exist
// so the Right Rail / Memory Inspector UI (Patch 9/10) can be typed against the real shape from
// the start instead of retrofitted later.

export type MemoryScope = "user" | "workspace" | "tenant" | "project" | "case" | "session";

// NOTE: TECHNICAL_NOTE/PREFERENCE/CASE_PARAMETER are inferred from the source prompt's Patch 7/12
// policy text (not an exhaustive bullet-list enum the way Status/Scope are) — see the Patch 1
// report for the explicit owner-confirmation flag on this set.
export type MemoryType = "preference" | "technical_note" | "case_parameter";

export type MemoryStatus =
  | "candidate"
  | "implicit_context"
  | "confirmed"
  | "rejected"
  | "deprecated"
  | "deleted_pending_purge"
  | "purged";

// Statuses a client must NEVER treat as usable context, even if a stale response briefly contains
// one (e.g. a Right Rail re-render racing a "forget" action) — mirrors the backend's
// NEVER_INJECTABLE_STATUSES so both sides agree on what "still live" means.
export const NEVER_INJECTABLE_STATUSES: ReadonlySet<MemoryStatus> = new Set([
  "rejected",
  "deprecated",
  "deleted_pending_purge",
  "purged",
]);

export interface MemorySource {
  kind: string; // e.g. "user_stated" | "llm_inferred" | "owner_manual_entry"
  session_id?: string;
  turn_id?: string;
  note?: string;
}

export interface MemoryItem {
  id: string;
  tenant_id: string;
  scope: MemoryScope;
  scope_id: string;
  type: MemoryType;
  status: MemoryStatus;
  content: string;
  semantic_key: string;
  sources: MemorySource[];
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at?: string | null;
  purge_after?: string | null;
}

export function isMemoryItemInjectable(item: Pick<MemoryItem, "status">): boolean {
  return !NEVER_INJECTABLE_STATUSES.has(item.status);
}

// Legal-by-Design Phase B (Goal 3): the Legal-Gate onboarding submission — field names mirror the
// backend's LegalAcceptanceRequest (api/routes/legal.py) 1:1.
export interface LegalAcceptancePayload {
  company_name: string;
  business_email: string;
  role: string;
  vat_id: string;
  legal_basis_accepted: boolean;
  dpa_accepted: boolean;
  business_user_confirmed: boolean;
  terms_version: string;
  privacy_version: string;
  dpa_version: string;
}

export interface LegalAcceptanceStatus {
  accepted: boolean;
}
