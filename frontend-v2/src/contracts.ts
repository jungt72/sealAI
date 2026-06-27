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
export interface ChatResponse {
  answer: string;
  model: string;
  grounded: boolean; // false → the answer is "vorläufig" (no reviewed grounding)
  intent: string | null;
  citations: Citation[];
  computed?: KernelValue[]; // M8: in-band kern result (additive; panel can update without a 2nd call)
  not_computed?: NotComputed[];
  medium_intelligence?: MediumIntelligence | null; // Phase 2: the MEDIUM panel data (vorläufig)
  alternativen?: Alternativen | null; // Modus F: the HERSTELLER-AUSWAHL panel data
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
