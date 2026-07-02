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
  hinweis: string;
}
// Owner/admin surface (/api/v2/admin/*, role-gated). The FULL editable partner record — incl.
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
  case_state: RememberedFact[];
  history: Turn[];
}
export interface Briefing {
  kind: string;
  title: string;
  body: string;
  provenance: string[];
}
