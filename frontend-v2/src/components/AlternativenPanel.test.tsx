import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Alternativen } from "../contracts";
import { AlternativenPanel } from "./AlternativenPanel";

afterEach(cleanup);

describe("AlternativenPanel", () => {
  it("renders the capable manufacturers (neutral) when grounded", () => {
    const data: Alternativen = {
      grounded_data: true,
      hersteller: ["Hersteller A", "Hersteller B"],
      ordered_by: "capability",
      neutralitaet: "nach Fähigkeit, nie nach Bezahlung",
    };
    render(<AlternativenPanel data={data} />);
    expect(screen.getByTestId("alternativen-panel")).toBeInTheDocument();
    expect(screen.getByText("Hersteller A")).toBeInTheDocument();
    expect(screen.getByText("Hersteller B")).toBeInTheDocument();
    expect(screen.getByText("neutral")).toBeInTheDocument();
    expect(screen.getByText(/nach Fähigkeit/)).toBeInTheDocument();
  });

  it("shows the honest no-data hinweis when the Hersteller seed is empty", () => {
    const data: Alternativen = {
      grounded_data: false,
      hinweis: "Aktuell liegen keine geerdeten Hersteller-Fähigkeitsdaten vor.",
    };
    render(<AlternativenPanel data={data} />);
    expect(
      screen.getByText(/keine geerdeten Hersteller-Fähigkeitsdaten/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});
