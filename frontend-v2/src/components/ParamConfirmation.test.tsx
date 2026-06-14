import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ConfirmationResponse } from "../contracts";
import { ParamConfirmation } from "./ParamConfirmation";

afterEach(cleanup);

const base: ConfirmationResponse = {
  uebernommen: [],
  rueckfragen: [],
  computed: [],
  not_computed: [],
  notes: [],
  clarifications: [],
};

describe("ParamConfirmation (deterministic — echoes settled values + kern, no LLM)", () => {
  it("renders übernommen (POST-BIND values) + the kern result", () => {
    render(
      <ParamConfirmation
        conf={{
          ...base,
          uebernommen: [
            { feld: "druck", label: "Druck p", wert: "0,5 bar" },
            { feld: "medium", label: "Medium", wert: "Öl" },
          ],
          computed: [
            {
              calc_id: "pv_wert",
              name: "pv_bar_m_s",
              value: 3.927,
              unit: "bar·m/s",
              formula: "",
              parent_fields: [],
              input_origins: [],
              provenance: "kernel_computed",
            },
          ],
        }}
      />,
    );
    const taken = screen.getByTestId("confirmation-uebernommen");
    expect(taken).toHaveTextContent("Druck p:");
    expect(taken).toHaveTextContent("0,5 bar"); // the post-bind value, never a raw "0.5 bar"
    expect(screen.getByTestId("confirmation-kern")).toHaveTextContent("3,93 bar·m/s");
  });

  it("a clarify-pending field is a Rückfrage, NOT übernommen (the value was not taken)", () => {
    render(
      <ParamConfirmation
        conf={{
          ...base,
          rueckfragen: [
            {
              feld: "druck",
              label: "Druck p",
              clarification: {
                feld: "druck",
                input_name: "p_bar",
                raw_value: "500",
                raw_unit: "mbar",
                reason: "unit_known_other",
                suggested_unit: "bar",
                known_dimension: "pressure",
                expected_dimension: "pressure",
                one_click: false,
              },
            },
          ],
        }}
      />,
    );
    expect(screen.getByTestId("confirmation-rueckfragen")).toHaveTextContent(/bitte in bar angeben/i);
    expect(screen.queryByTestId("confirmation-uebernommen")).toBeNull(); // nothing claimed taken
    expect(screen.getByTestId("param-confirmation")).toHaveTextContent("Rückfragen");
  });
});
