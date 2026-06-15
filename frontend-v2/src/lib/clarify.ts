import type { Clarification } from "../contracts";

/** German label for a physical dimension — used in the honest "wrong kind of quantity" message. */
export const DIM_LABEL: Record<string, string> = {
  length: "Längen",
  frequency: "Drehzahl",
  angle: "Winkel",
  pressure: "Druck",
};

/** The honest unit-recovery wording (single source for the Berechnungen panel AND the parameter-form
 * confirmation). Scale mismatch (cm on a mm field) → "bitte in mm angeben"; a DIMENSION mismatch
 * (grad on a length field) → name it the wrong kind of quantity. Pure presentation — the binder owns
 * the decision; this only renders it. */
export function clarifyMessage(c: Clarification): string {
  if (c.reason === "no_value") {
    return `${c.feld}: kein Wert erkannt — bitte Zahl + Einheit in ${c.suggested_unit} angeben.`;
  }
  if (c.reason === "unit_known_other") {
    const dimensionMismatch =
      Boolean(c.known_dimension) &&
      Boolean(c.expected_dimension) &&
      c.known_dimension !== c.expected_dimension;
    if (dimensionMismatch) {
      const got = DIM_LABEL[c.known_dimension] ?? c.known_dimension;
      const want = DIM_LABEL[c.expected_dimension] ?? c.expected_dimension;
      return `${c.feld}: »${c.raw_unit}« ist eine ${got}-Angabe — hier wird eine ${want}-Angabe in ${c.suggested_unit} erwartet.`;
    }
    return `${c.feld}: »${c.raw_unit}« wird hier nicht unterstützt — bitte in ${c.suggested_unit} angeben.`;
  }
  if (c.reason === "unit_missing") {
    return `${c.feld}: Einheit fehlt — meintest du ${c.raw_value} ${c.suggested_unit}?`;
  }
  return `${c.feld}: Einheit »${c.raw_unit}« unklar — meintest du ${c.suggested_unit}?`;
}
