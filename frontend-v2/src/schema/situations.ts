/**
 * Domain SCHEMA for the parameter Fast-Path form (Universal Core / Domain Pack).
 *
 * A situation → groups → fields tree. The universal renderer (`ParameterForm`) renders ENTIRELY from
 * this; adding a situation or a field is a schema entry here, never renderer code. RWDR is the first
 * and only situation today; the shape is built so a second Domain Pack is a new `SituationDef`.
 *
 * TRUST-SPINE BOUNDARY (build-spec §4): a field is `role: "kernel"` ONLY if its value feeds the
 * deterministic Rechenkern — and then `key` MUST equal a backend binder key (core/calc/binding.py
 * `_BINDINGS`) and `kernelKey` MUST be the calc-registry input it feeds (knowledge/calc_seed.json).
 * Everything else is `role: "context"`: a plain case-state fact that informs L1's *vorläufige*
 * guidance and never reaches a computation. The form crosses nothing — the binder is the boundary.
 *
 * Verified bindings (2026-06-14): wellendurchmesser→d1_mm ✓, drehzahl→rpm ✓ are live in `_BINDINGS`;
 * druck→p_bar is declared here but BINDS only once the Phase-2 binder unpark lands (until then the
 * pressure field settles as an unbound case-state fact — fail-closed, never a wrong number).
 */

export type FieldType = "number" | "enum" | "boolean" | "text";
export type FieldRole = "kernel" | "context";

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldDef {
  /** case-state feld key. For role="kernel" this MUST be a backend binder `_BINDINGS` key. */
  key: string;
  label: string;
  /** canonical unit appended on submit (number fields); "" for enum/boolean/text. */
  unit: string;
  type: FieldType;
  required: boolean;
  role: FieldRole;
  /** role="kernel" only: the calc-registry input this field feeds (d1_mm | rpm | p_bar). */
  kernelKey?: string;
  /** enum only: the selectable options (label is what gets stored — readable German for L1). */
  options?: FieldOption[];
  /** soft hint (sub-quantity, reference). Not a validator. */
  help?: string;
  /** soft advisory bounds — a value outside warns, never blocks (the kern owns the hard validity). */
  min?: number;
  max?: number;
}

export interface GroupDef {
  id: string;
  title: string;
  fields: FieldDef[];
}

export interface SituationDef {
  id: string;
  label: string;
  groups: GroupDef[];
}

/** The calc-registry inputs a kernel field may feed (knowledge/calc_seed.json). A kernelKey outside
 * this set is a schema error (asserted in situations.test.ts). */
export const KERNEL_INPUTS = ["d1_mm", "rpm", "p_bar"] as const;

const o = (value: string, label: string): FieldOption => ({ value, label });

/** RWDR — the first and only Domain Pack. Required = only d₁ and n (build-spec / owner). Every other
 * field has "Unbekannt" as a first-class state (the renderer omits empty/Unbekannt → param MISSING,
 * never a fake default). */
export const RWDR_SITUATION: SituationDef = {
  id: "rwdr",
  label: "RWDR (Radial-Wellendichtring)",
  groups: [
    {
      id: "A",
      title: "Wellengeometrie",
      fields: [
        { key: "wellendurchmesser", label: "Wellendurchmesser d₁", unit: "mm", type: "number", required: true, role: "kernel", kernelKey: "d1_mm" },
        { key: "gehäusebohrung", label: "Gehäusebohrung D", unit: "mm", type: "number", required: false, role: "context" },
        { key: "einbaubreite", label: "Einbaubreite b", unit: "mm", type: "number", required: false, role: "context" },
      ],
    },
    {
      id: "B",
      title: "Kinematik",
      fields: [
        { key: "drehzahl", label: "Drehzahl n", unit: "U/min", type: "number", required: true, role: "kernel", kernelKey: "rpm" },
        {
          key: "drehrichtung", label: "Drehrichtung", unit: "", type: "enum", required: false, role: "context",
          options: [o("gleichbleibend", "gleichbleibend"), o("reversierend", "reversierend")],
        },
      ],
    },
    {
      id: "C",
      title: "Druck",
      fields: [
        { key: "druck", label: "Druck p", unit: "bar", type: "number", required: false, role: "kernel", kernelKey: "p_bar" },
        {
          key: "druckrichtung", label: "Druckrichtung", unit: "", type: "enum", required: false, role: "context",
          options: [o("oelseite", "Ölseite"), o("luftseite", "Luftseite"), o("wechselnd", "wechselnd")],
        },
      ],
    },
    {
      id: "D",
      title: "Medium & Temperatur",
      fields: [
        {
          key: "medium", label: "Medium", unit: "", type: "enum", required: false, role: "context",
          options: [
            o("oel", "Öl"), o("fett", "Fett"), o("wasser", "Wasser"), o("emulsion", "Emulsion"),
            o("kraftstoff", "Kraftstoff"), o("kuehlmittel", "Kühlmittel"), o("luft", "Luft"), o("sonstiges", "Sonstiges"),
          ],
        },
        { key: "additive", label: "Additive", unit: "", type: "text", required: false, role: "context" },
        { key: "betriebstemperatur", label: "Betriebstemperatur", unit: "°C", type: "number", required: false, role: "context" },
        { key: "spitzentemperatur", label: "Spitzentemperatur", unit: "°C", type: "number", required: false, role: "context" },
      ],
    },
    {
      id: "E",
      title: "Gegenlauffläche",
      fields: [
        {
          key: "wellenwerkstoff", label: "Wellenwerkstoff", unit: "", type: "enum", required: false, role: "context",
          options: [o("stahl", "Stahl"), o("edelstahl", "Edelstahl"), o("grauguss", "Grauguss"), o("beschichtet", "beschichtet"), o("sonstiges", "Sonstiges")],
        },
        { key: "haerte", label: "Härte", unit: "HRC", type: "number", required: false, role: "context" },
        { key: "rauheit", label: "Rauheit", unit: "µm", type: "number", required: false, role: "context", help: "Ra oder Rz" },
        {
          key: "drall", label: "Drall", unit: "", type: "enum", required: false, role: "context",
          options: [o("drallfrei", "drallfrei"), o("drallbehaftet", "drallbehaftet"), o("unbekannt", "unbekannt")],
        },
        { key: "einfuehrfase", label: "Einführfase", unit: "", type: "boolean", required: false, role: "context" },
      ],
    },
    {
      id: "F",
      title: "Dynamik",
      fields: [
        { key: "rundlauf", label: "Rundlauf", unit: "mm", type: "number", required: false, role: "context", help: "TIR" },
        { key: "versatz", label: "Versatz", unit: "mm", type: "number", required: false, role: "context", help: "Welle ↔ Bohrung" },
      ],
    },
    {
      id: "G",
      title: "Umgebung & Schmierung",
      fields: [
        {
          key: "verschmutzung", label: "Verschmutzung", unit: "", type: "enum", required: false, role: "context",
          options: [o("sauber", "sauber"), o("leicht", "leicht"), o("stark", "stark")],
        },
        { key: "spritzwasser", label: "Spritzwasser", unit: "", type: "boolean", required: false, role: "context" },
        { key: "uv_aussen", label: "UV / Außeneinsatz", unit: "", type: "boolean", required: false, role: "context" },
        {
          key: "schmierung", label: "Schmierung", unit: "", type: "enum", required: false, role: "context",
          options: [o("oelbad", "Ölbad"), o("spritzoel", "Spritzöl"), o("fett", "Fett"), o("mangel", "Mangelschmierung")],
        },
      ],
    },
    {
      id: "H",
      title: "Bauform-Vorgaben",
      fields: [
        {
          key: "bauform", label: "Bauform", unit: "", type: "enum", required: false, role: "context",
          options: [o("A", "A"), o("AS", "AS"), o("doppellippe", "Doppellippe")],
        },
        { key: "staublippe", label: "Staublippe", unit: "", type: "boolean", required: false, role: "context" },
        {
          key: "werkstoffvorgabe", label: "Werkstoffvorgabe", unit: "", type: "enum", required: false, role: "context",
          options: [o("NBR", "NBR"), o("HNBR", "HNBR"), o("FKM", "FKM"), o("VMQ", "VMQ"), o("EPDM", "EPDM"), o("PTFE", "PTFE"), o("offen", "offen")],
        },
        {
          key: "federwerkstoff", label: "Federwerkstoff", unit: "", type: "enum", required: false, role: "context",
          options: [o("federstahl", "Federstahl"), o("edelstahl", "Edelstahl")],
        },
      ],
    },
    {
      id: "I",
      title: "Bestand & Historie (Austauschfall)",
      fields: [
        {
          key: "vorgaengerwerkstoff", label: "Vorgängerwerkstoff", unit: "", type: "enum", required: false, role: "context",
          options: [o("NBR", "NBR"), o("HNBR", "HNBR"), o("FKM", "FKM"), o("VMQ", "VMQ"), o("EPDM", "EPDM"), o("PTFE", "PTFE"), o("unbekannt", "unbekannt")],
        },
        { key: "altteilcode", label: "Altteil-Code", unit: "", type: "text", required: false, role: "context" },
        {
          key: "schadensbild", label: "Schadensbild", unit: "", type: "enum", required: false, role: "context",
          options: [o("leckage", "Leckage"), o("verschleiss", "Verschleiß"), o("verhaertung", "Verhärtung"), o("risse", "Risse"), o("unbekannt", "unbekannt")],
        },
      ],
    },
  ],
};

/** All situations (tabs). One today; a second Domain Pack appends here. */
export const SITUATIONS: SituationDef[] = [RWDR_SITUATION];

/** Flatten a situation's fields (renderer + submit helpers). */
export const situationFields = (s: SituationDef): FieldDef[] => s.groups.flatMap((g) => g.fields);
