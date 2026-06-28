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
  /** A Domain Pack that is announced but not yet built — its tab renders grayed and is not
   * selectable (no schema/kernel yet). RWDR is the only enabled pack today. */
  disabled?: boolean;
}

/** The calc-registry inputs a kernel field may feed (knowledge/calc_seed.json). A kernelKey outside
 * this set is a schema error (asserted in situations.test.ts). */
export const KERNEL_INPUTS = ["d1_mm", "rpm", "p_bar", "v_m_s"] as const;

const o = (value: string, label: string): FieldOption => ({ value, label });

/**
 * UNIVERSAL CORE — the operating conditions that are the SAME field across every Domain Pack
 * (Medium, Druck, Betriebs-/Spitzentemperatur). Rendered ABOVE the type tabs and shared by every
 * situation: on a (later) type switch these values stay put, while the type-specific fields swap
 * with the tab. A field belongs here ONLY if it is the identical field for all types (same key,
 * unit, meaning); anything whose structure/unit/meaning changes per type (geometry, speed/motion)
 * lives in the Domain Pack. `druck` keeps its kernel binding (→ p_bar); `druck_max` is a context
 * fact (no kernel guess — fail-closed). The trust-spine boundary still holds field-by-field.
 */
export const UNIVERSAL_CORE: FieldDef[] = [
  {
    // Phase-1 Medium-Wiring: the SPECIFIC medium is FREE-TEXT — it shows whatever the chat extracted
    // (Hydrauliköl, Heißwasser, Salzsäure …), vocab-independent, and the user can edit it. Hydrates the
    // backend case-state fact feld="medium".
    key: "medium", label: "Medium", unit: "", type: "text", required: false, role: "context",
    help: "Das konkrete Medium, z. B. Hydrauliköl, Heißwasser, Salzsäure.",
  },
  {
    // The coarse bucket — auto-filled from the specific medium (feld="medium_kategorie"); lossy by design.
    key: "medium_kategorie", label: "Kategorie", unit: "", type: "enum", required: false, role: "context",
    options: [
      o("oel", "Öl"), o("fett", "Fett"), o("wasser", "Wasser"), o("emulsion", "Emulsion"),
      o("kraftstoff", "Kraftstoff"), o("kuehlmittel", "Kühlmittel"), o("luft", "Luft"), o("sonstiges", "Sonstiges"),
    ],
  },
  { key: "druck", label: "Druck (normal)", unit: "bar", type: "number", required: false, role: "kernel", kernelKey: "p_bar" },
  { key: "druck_max", label: "Druck (max)", unit: "bar", type: "number", required: false, role: "context", help: "Spitzendruck" },
  { key: "betriebstemperatur", label: "Betriebstemperatur", unit: "°C", type: "number", required: false, role: "context" },
  { key: "spitzentemperatur", label: "Spitzentemperatur", unit: "°C", type: "number", required: false, role: "context" },
];

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
        // Druck (normal/max) lives in the Universal Core above the tabs; here only the RWDR-specific direction.
        {
          key: "druckrichtung", label: "Druckrichtung", unit: "", type: "enum", required: false, role: "context",
          options: [o("oelseite", "Ölseite"), o("luftseite", "Luftseite"), o("wechselnd", "wechselnd")],
        },
      ],
    },
    {
      id: "D",
      title: "Medium-Zusätze",
      fields: [
        // Medium + Betriebs-/Spitzentemperatur live in the Universal Core above the tabs.
        { key: "additive", label: "Additive", unit: "", type: "text", required: false, role: "context" },
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

/** Announced-but-unbuilt Domain Packs — their tabs render grayed (not selectable) so the type
 * surface is honest about what's coming without offering an empty, broken pack. Phase B fills the
 * groups + the type-aware kernel; until then they carry no fields and can never become `active`. */
/** HYDRAULIK — second Domain Pack, first functional cut. All fields are role:"context": they
 * settle as case-state facts and inform L1's *vorläufige* guidance, but NONE binds to the
 * deterministic Rechenkern — the type-aware Hydraulik kernel is Phase B, and feeding the
 * RWDR-calibrated kernel here would risk a wrong number (fail-closed). Pressure/medium/temperature
 * still come from the Universal Core. Geometry/labels are a sound first pass, not yet owner-final. */
export const HYDRAULIK_SITUATION: SituationDef = {
  id: "hydraulik",
  label: "Hydraulik",
  groups: [
    {
      id: "A",
      title: "Bauart",
      fields: [
        {
          key: "dichtungsart", label: "Dichtungsart", unit: "", type: "enum", required: false, role: "context",
          options: [o("stangendichtung", "Stangendichtung"), o("kolbendichtung", "Kolbendichtung"), o("abstreifer", "Abstreifer"), o("fuehrungsring", "Fuehrungsring"), o("stuetzring", "Stuetzring")],
        },
        {
          key: "einbauart", label: "Einbauart", unit: "", type: "enum", required: false, role: "context",
          options: [o("nut_geschlossen", "geschlossene Nut"), o("nut_geteilt", "geteilte Nut"), o("eingestochen", "eingestochen")],
        },
      ],
    },
    {
      id: "B",
      title: "Geometrie",
      fields: [
        { key: "durchmesser", label: "Durchmesser (Stange/Kolben)", unit: "mm", type: "number", required: false, role: "context", help: "Stangen- bzw. Kolbendurchmesser" },
        { key: "nutbreite", label: "Nutbreite", unit: "mm", type: "number", required: false, role: "context" },
        { key: "nuttiefe", label: "Nuttiefe / Radialhoehe", unit: "mm", type: "number", required: false, role: "context" },
        { key: "spaltmass", label: "Dichtspalt", unit: "mm", type: "number", required: false, role: "context", help: "radialer Spalt" },
      ],
    },
    {
      id: "C",
      title: "Bewegung",
      fields: [
        {
          key: "bewegungsart", label: "Bewegungsart", unit: "", type: "enum", required: false, role: "context",
          options: [o("translatorisch", "translatorisch"), o("rotierend", "rotierend"), o("schwenkend", "schwenkend"), o("statisch", "statisch")],
        },
        { key: "geschwindigkeit", label: "Geschwindigkeit", unit: "m/s", type: "number", required: false, role: "kernel", kernelKey: "v_m_s", help: "Hub- bzw. Gleitgeschwindigkeit (feeds PV-Wert)" },
        { key: "hublaenge", label: "Hublaenge", unit: "mm", type: "number", required: false, role: "context" },
        { key: "frequenz", label: "Frequenz", unit: "1/min", type: "number", required: false, role: "context", help: "Doppelhuebe pro Minute" },
      ],
    },
    {
      id: "D",
      title: "Werkstoff & Gegenlaufflaeche",
      fields: [
        {
          key: "werkstoffvorgabe", label: "Werkstoffvorgabe", unit: "", type: "enum", required: false, role: "context",
          options: [o("PU", "PU"), o("NBR", "NBR"), o("HNBR", "HNBR"), o("FKM", "FKM"), o("PTFE", "PTFE"), o("POM", "POM"), o("PA", "PA"), o("offen", "offen")],
        },
        { key: "haerte", label: "Haerte", unit: "Shore", type: "number", required: false, role: "context", help: "Shore A / D" },
        { key: "rauheit", label: "Gegenlauf-Rauheit", unit: "µm", type: "number", required: false, role: "context", help: "Ra oder Rz" },
        {
          key: "oberflaeche", label: "Gegenlauf-Oberflaeche", unit: "", type: "enum", required: false, role: "context",
          options: [o("hartverchromt", "hartverchromt"), o("nitriert", "nitriert"), o("geschliffen", "geschliffen"), o("beschichtet", "beschichtet"), o("sonstiges", "Sonstiges")],
        },
      ],
    },
    {
      id: "E",
      title: "Anforderung & Umgebung",
      fields: [
        {
          key: "leckageanforderung", label: "Leckageanforderung", unit: "", type: "enum", required: false, role: "context",
          options: [o("technisch_trocken", "technisch trocken"), o("leichter_film", "leichter Schmierfilm"), o("tropfend_ok", "Tropfleckage tolerierbar")],
        },
        {
          key: "verschmutzung", label: "Verschmutzung", unit: "", type: "enum", required: false, role: "context",
          options: [o("sauber", "sauber"), o("leicht", "leicht"), o("stark", "stark")],
        },
        { key: "ausseneinsatz", label: "Ausseneinsatz / UV", unit: "", type: "boolean", required: false, role: "context" },
      ],
    },
  ],
};
export const STATISCH_SITUATION: SituationDef = {
  id: "statisch",
  label: "Statisch",
  groups: [],
  disabled: true,
};

/** All situations (type tabs), in display order. RWDR is the only enabled pack today. */
export const SITUATIONS: SituationDef[] = [RWDR_SITUATION, HYDRAULIK_SITUATION, STATISCH_SITUATION];

/** Flatten a situation's fields (renderer + submit helpers). */
export const situationFields = (s: SituationDef): FieldDef[] => s.groups.flatMap((g) => g.fields);

/** The Universal Core fields (shared across types, rendered above the tabs). */
export const coreFields = (): FieldDef[] => UNIVERSAL_CORE;

/** Every field the form manages for a situation: the Universal Core PLUS the active pack's fields.
 * The single source for buildItems / hydration / the empty-field DELETE reconcile, so the Core
 * obeys every R2 invariant exactly like the type-specific fields. */
export const formFields = (s: SituationDef): FieldDef[] => [...UNIVERSAL_CORE, ...situationFields(s)];

/** The kernel-critical fields (role:"kernel") — DERIVED, the single source for the stage compact
 * card. A future kernel-field change (a schema entry) auto-updates the card; never a hardcoded
 * parallel list. The compact card == this set is the Phase-3 invariant. */
export const kernelFields = (s: SituationDef): FieldDef[] =>
  situationFields(s).filter((f) => f.role === "kernel");
