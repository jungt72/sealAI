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

  it("renders the backend-owned next question and unknown handling", () => {
    render(
      <Answer
        res={{
          ...base,
          next_question: {
            case_id: "case-1",
            topic_id: "rwdr.default",
            state_revision: 2,
            pack_id: "rwdr.v1",
            pack_version: "1.0.1",
            policy_version: "adaptive-interview.lexicographic.1.0.0",
            question_id: "rwdr.q.medium_primary",
            primary_need_id: "rwdr.medium.primary",
            related_need_ids: [],
            question_text: "Welches konkrete Medium liegt an der Dichtkante an?",
            question_type: "structured_text",
            answer_schema: { type: "object" },
            allowed_unknown: true,
            allowed_unobtainable: true,
            criticality: "decision_critical",
            rule_refs: ["AI-T4-REQUIRED-001"],
            dependency_refs: [],
            pending_question_id: "ipq-1",
          },
        }}
      />,
    );
    const prompt = screen.getByTestId("next-question");
    expect(prompt).toHaveTextContent("Welches konkrete Medium liegt an der Dichtkante an?");
    expect(prompt).toHaveTextContent("nicht ermittelbar");
  });

  it("does not invent a next question when the controller payload is absent", () => {
    render(<Answer res={base} />);
    expect(screen.queryByTestId("next-question")).toBeNull();
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

  it("does not render a positive statement from the canonical compatible audit result", () => {
    render(
      <Answer
        res={{
          ...base,
          answer: "Die Angaben werden geprüft.",
          material_constraints: {
            material_state: "known",
            medium_state: "known",
            medium_cardinality: "single",
            relation_state: "not_applicable",
            evaluation_state: "evaluated",
            verdict: "vertraeglich",
            decisive_ref: "MX-NBR-MINERALOEL",
            disqualified: false,
            requires_resolution: false,
            positive_statement_allowed: false,
            conditions: [],
            blockers: [],
            matches: [
              {
                rule_ref: "MX-NBR-MINERALOEL",
                verdict: "vertraeglich",
                statement: "Keine dokumentierte Unverträglichkeit.",
                source_ref: "matrix-cell:MX-NBR-MINERALOEL",
                evidence_binding_state: "unbound",
              },
            ],
          },
        }}
      />,
    );
    const note = screen.getByTestId("material-constraint-neutral");
    expect(note).toHaveTextContent(
      "Keine dokumentierte Unverträglichkeit gefunden; daraus folgt keine Eignungs- oder Freigabeaussage.",
    );
    expect(note).toHaveTextContent("matrix-cell:MX-NBR-MINERALOEL");
    expect(screen.queryByText(/kompatibel|geeignet|freigegeben/i)).not.toBeInTheDocument();
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

describe("Answer — Legal-by-Design Phase D risk-flags note", () => {
  it("renders nothing when risk_flags is absent or empty", () => {
    render(<Answer res={base} />);
    expect(screen.queryByTestId("risk-flags-note")).not.toBeInTheDocument();
    render(<Answer res={{ ...base, risk_flags: [] }} />);
    expect(screen.queryByTestId("risk-flags-note")).not.toBeInTheDocument();
  });

  it("renders the warning visibly (outside the collapsed meta) with the matched terms", () => {
    render(<Answer res={{ ...base, risk_flags: ["ATEX", "Sauerstoff"] }} />);
    const note = screen.getByTestId("risk-flags-note");
    expect(note).toBeInTheDocument();
    expect(note).toHaveTextContent("ATEX, Sauerstoff");
    expect(note).toHaveTextContent("keine Empfehlung");
    expect(note.closest("details")).toBeNull();
  });

  it("renders before the Gegencheck note when both are present", () => {
    render(
      <Answer
        res={{
          ...base,
          risk_flags: ["ATEX"],
          gegencheck: { disqualified: true, reason: "x", source: "y" },
        }}
      />,
    );
    const risk = screen.getByTestId("risk-flags-note");
    const gegencheck = screen.getByTestId("gegencheck-disqualified");
    expect(risk.compareDocumentPosition(gegencheck) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

// A citation so the Belege section has content to (conditionally) render — its own empty-citations
// guard is independent of the route-aware show_evidence flag.
const withCite: ChatResponse = {
  ...base,
  citations: [{ text: "FKM ist beständig gegen Mineralöl.", sources: ["Parker O-Ring Handbook"] }],
};

describe("Answer — Phase 2B route-aware display flags (Technische Vorbewertung)", () => {
  it("shows the Technische Vorbewertung block when the flag is absent (backward compat)", () => {
    render(<Answer res={base} />);
    expect(screen.getByTestId("technical-preassessment")).toBeInTheDocument();
    expect(screen.getByText("Technische Vorbewertung")).toBeInTheDocument();
  });

  it("shows it when the flag is explicitly true (e.g. an engineering route)", () => {
    render(<Answer res={{ ...base, show_technical_preassessment: true }} />);
    expect(screen.getByTestId("technical-preassessment")).toBeInTheDocument();
  });

  it("hides it ONLY when the flag is explicitly false (e.g. smalltalk/off-topic)", () => {
    render(<Answer res={{ ...base, route_name: "smalltalk_navigation", show_technical_preassessment: false }} />);
    expect(screen.queryByTestId("technical-preassessment")).not.toBeInTheDocument();
    expect(screen.queryByText("Technische Vorbewertung")).not.toBeInTheDocument();
    // The badges live inside that block, so they disappear with it.
    expect(screen.queryByTestId("candidate-label")).not.toBeInTheDocument();
  });
});

describe("Answer — Phase 2B route-aware display flags (Belege / citations)", () => {
  it("shows Belege when show_evidence is absent and citations exist (backward compat)", () => {
    render(<Answer res={withCite} />);
    expect(screen.getByText(/Belege/)).toBeInTheDocument();
  });

  it("shows Belege when show_evidence is explicitly true and citations exist", () => {
    render(<Answer res={{ ...withCite, show_evidence: true }} />);
    expect(screen.getByText(/Belege/)).toBeInTheDocument();
  });

  it("hides Belege when show_evidence is explicitly false, even though citations exist", () => {
    render(<Answer res={{ ...withCite, route_name: "smalltalk_navigation", show_evidence: false }} />);
    expect(screen.queryByText(/Belege/)).not.toBeInTheDocument();
  });

  it("still hides Belege when there are no citations (empty guard is independent of the flag)", () => {
    render(<Answer res={{ ...base, show_evidence: true }} />);
    expect(screen.queryByText(/Belege/)).not.toBeInTheDocument();
  });
});
