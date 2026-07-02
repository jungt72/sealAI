import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { ChatResponse } from "../contracts";
import { Answer } from "./Answer";

afterEach(cleanup);

const base: ChatResponse = {
  answer: "Grundsätzlich vertragen sich diese Materialien.",
  model: "fake",
  grounded: true,
  intent: null,
  citations: [],
};

describe("Answer — base rendering (unchanged behaviour)", () => {
  it("renders the candidate badge and the markdown answer", () => {
    render(<Answer res={base} />);
    expect(screen.getByTestId("answer")).toBeInTheDocument();
    expect(screen.getByTestId("candidate-label")).toBeInTheDocument();
    expect(screen.queryByTestId("vorlaeufig-label")).not.toBeInTheDocument();
  });

  it("shows the vorläufig badge only when NOT grounded", () => {
    render(<Answer res={{ ...base, grounded: false }} />);
    expect(screen.getByTestId("vorlaeufig-label")).toBeInTheDocument();
  });
});

describe("Answer — P4 Gegencheck note (disqualify-only, E4-1)", () => {
  it("renders the disqualified verdict visibly (outside the collapsed meta), with reason + source", () => {
    render(
      <Answer
        res={{
          ...base,
          gegencheck: {
            disqualified: true,
            reason: "FKM hydrolysiert in Heißdampf oberhalb 150 °C.",
            source: "Verträglichkeitsmatrix · MX-FKM-DAMPF (reviewed)",
          },
        }}
      />,
    );
    const note = screen.getByTestId("gegencheck-disqualified");
    expect(note).toBeInTheDocument();
    expect(note).toHaveTextContent("FKM hydrolysiert in Heißdampf oberhalb 150 °C.");
    expect(note).toHaveTextContent("MX-FKM-DAMPF");
    // NOT nested inside the collapsed <details> answer-meta
    expect(note.closest("details")).toBeNull();
  });

  it("renders the bedingt verdict with the condition text, not the reason field", () => {
    render(
      <Answer
        res={{
          ...base,
          gegencheck: {
            disqualified: false,
            basis: "matrix_conditional",
            condition: "Nur bei Wellendrehzahl < 10 m/s einsetzen.",
            source: "Verträglichkeitsmatrix · MX-VMQ-DYNAMISCH (reviewed)",
          },
        }}
      />,
    );
    const note = screen.getByTestId("gegencheck-conditional");
    expect(note).toHaveTextContent("Nur bei Wellendrehzahl < 10 m/s einsetzen.");
  });

  it.each(["matrix_compatible", "no_matrix_data", "no_medium"] as const)(
    "renders NOTHING for basis=%s — absence of an incompatibility is never an affirmative claim",
    (basis) => {
      render(
        <Answer res={{ ...base, gegencheck: { disqualified: false, basis } }} />,
      );
      expect(screen.queryByTestId("gegencheck-disqualified")).not.toBeInTheDocument();
      expect(screen.queryByTestId("gegencheck-conditional")).not.toBeInTheDocument();
      expect(screen.queryByText(/Gegencheck/)).not.toBeInTheDocument();
    },
  );

  it("renders nothing when gegencheck is absent/null (no Gegencheck situation)", () => {
    render(<Answer res={{ ...base, gegencheck: null }} />);
    expect(screen.queryByText(/Gegencheck/)).not.toBeInTheDocument();
  });
});

describe("Answer — P4 Verification badge (L3 trust status)", () => {
  it("shows the confidently-verified badge", () => {
    render(
      <Answer
        res={{
          ...base,
          verified: true,
          verification: { action: "pass", parse_ok: true, hedged: false, ran: true },
        }}
      />,
    );
    expect(screen.getByTestId("verification-verified")).toHaveTextContent("geprüft");
  });

  it("prioritises the hedged badge over the verified flag", () => {
    render(
      <Answer
        res={{
          ...base,
          verified: false,
          verification: { action: "blocked_hedge", parse_ok: true, hedged: true, ran: true },
        }}
      />,
    );
    expect(screen.getByTestId("verification-hedged")).toBeInTheDocument();
    expect(screen.queryByTestId("verification-verified")).not.toBeInTheDocument();
  });

  it("shows the unverified disclosure when L3 never ran", () => {
    render(
      <Answer
        res={{
          ...base,
          verified: false,
          verification: { action: null, parse_ok: null, hedged: false, ran: false },
        }}
      />,
    );
    expect(screen.getByTestId("verification-unverified")).toHaveTextContent("nicht geprüft");
  });

  it("shows the unverified disclosure on a parse failure even though L3 ran", () => {
    render(
      <Answer
        res={{
          ...base,
          verified: false,
          verification: { action: "pass", parse_ok: false, hedged: false, ran: true },
        }}
      />,
    );
    expect(screen.getByTestId("verification-unverified")).toBeInTheDocument();
  });

  it("renders no verification badge at all when the field is absent", () => {
    render(<Answer res={base} />);
    expect(screen.queryByTestId("verification-verified")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verification-hedged")).not.toBeInTheDocument();
    expect(screen.queryByTestId("verification-unverified")).not.toBeInTheDocument();
  });
});
