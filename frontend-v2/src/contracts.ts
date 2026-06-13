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
export interface ComputeResponse {
  computed: KernelValue[];
  not_computed: NotComputed[];
  notes: string[];
}
export interface ChatResponse {
  answer: string;
  model: string;
  grounded: boolean; // false → the answer is "vorläufig" (no reviewed grounding)
  intent: string | null;
  citations: Citation[];
  computed?: KernelValue[]; // M8: in-band kern result (additive; panel can update without a 2nd call)
  not_computed?: NotComputed[];
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
