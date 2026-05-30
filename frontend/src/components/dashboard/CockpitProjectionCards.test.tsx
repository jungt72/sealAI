import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ActiveQuestionCard,
  CockpitProjectionCards,
  ConflictsCard,
  KnowledgeNotesCard,
  VisualCandidatesCard,
} from "@/components/dashboard/SealCockpit";

describe("CockpitPatch projection cards (Patch 4)", () => {
  it("renders nothing when the projection is empty/null", () => {
    const { container } = render(<CockpitProjectionCards projection={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for an empty object projection", () => {
    const { container } = render(<CockpitProjectionCards projection={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the active question from the projection", () => {
    render(
      <ActiveQuestionCard
        projection={{
          active_question: { field: "shaft_surface_condition", question: "Siehst du eine Rille?" },
        }}
      />,
    );
    expect(screen.getByText("Aktive Frage")).toBeInTheDocument();
    expect(screen.getByText("Siehst du eine Rille?")).toBeInTheDocument();
  });

  it("does not render an active-question card without a question", () => {
    const { container } = render(<ActiveQuestionCard projection={{ active_question: {} }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders conflicts with severity badge", () => {
    render(
      <ConflictsCard
        projection={{
          conflicts: [
            { field_name: "temperature_operating_c", description: "90 vs 190 °C", severity: "warning" },
          ],
        }}
      />,
    );
    expect(screen.getByText("Widersprüche")).toBeInTheDocument();
    expect(screen.getByText("90 vs 190 °C")).toBeInTheDocument();
    expect(screen.getByText("prüfen")).toBeInTheDocument();
  });

  it("renders knowledge notes with a non-release marker", () => {
    render(
      <KnowledgeNotesCard
        projection={{ knowledge_notes: [{ label: "FKM als Werkstoffrichtung prüfen", source: "Datenblatt" }] }}
      />,
    );
    expect(screen.getByText("Wissensnotizen")).toBeInTheDocument();
    expect(screen.getByText("FKM als Werkstoffrichtung prüfen")).toBeInTheDocument();
    expect(screen.getByText(/keine Freigabe/)).toBeInTheDocument();
  });

  it("renders no visual-candidates card while empty (Patch 6 fills it)", () => {
    const { container } = render(
      <VisualCandidatesCard projection={{ visual_candidates: [], sketch_candidates: [] }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders visual candidates as confirmation candidates when present", () => {
    render(
      <VisualCandidatesCard
        projection={{ visual_candidates: [{ value: "RWDR-artige Bauform", confidence: "low" }] }}
      />,
    );
    expect(screen.getByText("Bild-/Skizzen-Kandidaten")).toBeInTheDocument();
    expect(screen.getByText("RWDR-artige Bauform")).toBeInTheDocument();
    expect(screen.getByText("bestätigen")).toBeInTheDocument();
  });
});
