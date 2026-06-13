import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ComputeResponse } from "../contracts";
import { BerechnungenPanel } from "./BerechnungenPanel";

afterEach(cleanup);

const V: ComputeResponse = {
  computed: [
    {
      calc_id: "umfangsgeschwindigkeit",
      name: "v_m_s",
      value: 16.7552,
      unit: "m/s",
      formula: "v = π·d1·n/60000",
      parent_fields: ["wellendurchmesser", "drehzahl"],
      input_origins: [
        "vom Nutzer im Formular eingegeben (wellendurchmesser: »40 mm«, user-form)",
        "vom Nutzer im Formular eingegeben (drehzahl: »8000 U/min«, user-form)",
      ],
      provenance: "kernel_computed",
    },
  ],
  not_computed: [],
  notes: [],
};

const OPEN: ComputeResponse = {
  computed: [],
  not_computed: [
    { calc_id: "umfangsgeschwindigkeit", reason: "nicht berechenbar: Eingaben fehlen (rpm)" },
  ],
  notes: ["drehzahl: Wert »8000« nicht eindeutig bindbar — nicht gebunden"],
};

describe("BerechnungenPanel (the kernel channel — backend values only)", () => {
  it("renders the deterministic kern value, unit, formula and honest provenance", () => {
    render(<BerechnungenPanel compute={V} />);
    const panel = screen.getByTestId("berechnungen-panel");
    expect(panel).toBeInTheDocument();
    const row = screen.getByTestId("kernel-value");
    expect(row).toHaveTextContent("Umfangsgeschwindigkeit");
    expect(row).toHaveTextContent("16,76 m/s"); // German comma; the kern's value, display-rounded
    expect(row).toHaveTextContent("v = π·d1·n/60000");
    // provenance is honest: computed from the named input felder (orientation ≠ Freigabe)
    expect(row).toHaveTextContent(/deterministisch berechnet/i);
    expect(row).toHaveTextContent("wellendurchmesser");
    expect(panel).toHaveTextContent(/Orientierung, keine Freigabe/i);
  });

  it("renders a 'nicht berechenbar' open point with NO number (fail-closed, honest)", () => {
    render(<BerechnungenPanel compute={OPEN} />);
    const open = screen.getByTestId("kernel-not-computed");
    expect(open).toHaveTextContent("Umfangsgeschwindigkeit");
    expect(open).toHaveTextContent(/nicht berechenbar/i);
    expect(screen.getByTestId("kernel-note")).toHaveTextContent("nicht eindeutig bindbar");
  });

  it("TRUST: never shows a computed number when the kern reported none (no client compute)", () => {
    const { container } = render(<BerechnungenPanel compute={OPEN} />);
    // even though the inputs are present elsewhere, the panel shows NO velocity value/unit
    expect(container.textContent ?? "").not.toMatch(/m\/s/);
    expect(container.textContent ?? "").not.toMatch(/\d+[.,]\d+\s*m/);
  });

  it("renders nothing when there is no kern output at all (clean stage)", () => {
    const { container } = render(<BerechnungenPanel compute={null} />);
    expect(container.firstChild).toBeNull();
    cleanup();
    const empty: ComputeResponse = { computed: [], not_computed: [], notes: [] };
    const { container: c2 } = render(<BerechnungenPanel compute={empty} />);
    expect(c2.firstChild).toBeNull();
  });
});
