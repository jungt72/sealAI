import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { KandidatenSpec } from "../contracts";
import { KandidatenSpecPanel } from "./KandidatenSpecPanel";

afterEach(cleanup);

const base: KandidatenSpec = {
  response_level: "L1_candidate_space",
  envelope_band: "green_base",
  kritikalitaet: "normal",
  axes: [
    { name: "material", value: "NBR/HNBR", status: "ok", begruendung: [] },
    { name: "shaft", value: null, status: "open_verification", begruendung: [] },
  ],
  material: {
    kind: "candidate_set",
    primary: ["NBR"],
    alternatives: ["HNBR"],
    escalation: [],
    excluded: ["EPDM"],
    reason_codes: ["RWDR-G-SPEED"],
    next_question: [],
    validation_required: false,
  },
  material_candidate_set: ["NBR", "HNBR"],
  din_candidate_label: "DIN-3760-orientierter Kandidatenraum",
  final_design_code: null,
  defer_gruende: [],
  open_verifications: ["Wellenhärte 45–55 HRC bestätigen"],
  offene_punkte: [],
  failure_mode_checklist: [],
  freigegeben: false,
  geltungsrahmen: "Kandidaten-Spezifikation (Screening), keine technische Freigabe.",
  quellen: [],
};

describe("KandidatenSpecPanel", () => {
  it("renders the candidate set + DIN label with the mandatory vorläufig badge", () => {
    render(<KandidatenSpecPanel data={base} />);
    expect(screen.getByTestId("kandidaten-spec-panel")).toBeInTheDocument();
    expect(screen.getByText("vorläufig")).toBeInTheDocument();
    expect(screen.getByText(/DIN-3760-orientierter Kandidatenraum/)).toBeInTheDocument();
    expect(screen.getByText("NBR")).toBeInTheDocument();
    expect(screen.getByText("HNBR")).toBeInTheDocument();
  });

  it("renders the backend Geltungsrahmen verbatim + the open verifications (never a release)", () => {
    render(<KandidatenSpecPanel data={base} />);
    expect(screen.getByText(/keine technische Freigabe/)).toBeInTheDocument();
    expect(screen.getByText(/Wellenhärte 45–55 HRC bestätigen/)).toBeInTheDocument();
  });
});
