import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ActiveQuestionCard,
  CaseFactsCard,
  CaseStatusCard,
  CockpitProjectionCards,
  ConflictsCard,
  EvidenceStandardsCard,
  KnowledgeNotesCard,
  MissingFieldsCard,
  RiskMatrixCard,
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

  // --- AC3: full case-situation projection (current_facts, missing_fields,
  // readiness/review, risk_matrix, evidence/standards) ---------------------
  it("renders detected facts with values, units and provenance", () => {
    render(
      <CaseFactsCard
        projection={{
          current_facts: [
            { field_name: "temperature_c", value: 90, unit: "°C", source: "asserted_state" },
            { field_name: "speed_rpm", value: 1450, unit: "rpm", source: "normalized_state" },
            { field_name: "ignored", value: null },
          ],
        }}
      />,
    );
    expect(screen.getByText("Erkannte Angaben")).toBeInTheDocument();
    expect(screen.getByText("90 °C")).toBeInTheDocument();
    expect(screen.getByText("1450 rpm")).toBeInTheDocument();
    expect(screen.getByText("bestätigt")).toBeInTheDocument();
    expect(screen.getByText("normalisiert")).toBeInTheDocument();
  });

  it("does not render a facts card when no fact has a value", () => {
    const { container } = render(<CaseFactsCard projection={{ current_facts: [{ field_name: "x", value: null }] }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders open and blocking missing fields with the right badge", () => {
    render(
      <MissingFieldsCard
        projection={{
          missing_fields: [{ key: "counterface_surface", label: "counterface_surface", status: "missing" }],
          blocking_missing_fields: [{ key: "medium", label: "medium", status: "missing" }],
        }}
      />,
    );
    expect(screen.getByText("Offene Angaben")).toBeInTheDocument();
    expect(screen.getByText("Medium")).toBeInTheDocument();
    expect(screen.getByText("Gegenfläche")).toBeInTheDocument();
    expect(screen.getByText("blockierend")).toBeInTheDocument();
    expect(screen.getByText("offen")).toBeInTheDocument();
  });

  it("renders readiness, review status, next action and the no-release marker", () => {
    render(
      <CaseStatusCard
        projection={{
          readiness_band: "rfq_ready_for_expert_review",
          review_status: { status: "pending", human_review_required: true, blocking_findings: ["a"] },
          recommendation_card: { next_action: "collect_missing_inputs", no_final_technical_release: true },
        }}
      />,
    );
    expect(screen.getByText("Status & Einordnung")).toBeInTheDocument();
    expect(screen.getByText("Anfragebasis für Prüfung")).toBeInTheDocument();
    expect(screen.getByText(/Prüfung erforderlich/)).toBeInTheDocument();
    expect(screen.getByText(/1 Blocker/)).toBeInTheDocument();
    expect(screen.getByText(/Nächster Schritt/)).toBeInTheDocument();
    expect(screen.getByText("Keine finale Freigabe")).toBeInTheDocument();
  });

  it("does not render a status card for a not_ready, not_started, no-recommendation projection", () => {
    const { container } = render(
      <CaseStatusCard projection={{ readiness_band: "not_ready", review_status: { status: "not_started" } }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders risk-matrix findings with a severity badge", () => {
    render(
      <RiskMatrixCard
        projection={{
          risk_matrix: [{ title: "Trockenlauf-Risiko", summary: "Schmierung unklar", severity: "blocking", kind: "contradiction" }],
        }}
      />,
    );
    expect(screen.getByText("Risiken & Befunde")).toBeInTheDocument();
    expect(screen.getByText("Trockenlauf-Risiko")).toBeInTheDocument();
    expect(screen.getByText("Schmierung unklar")).toBeInTheDocument();
    expect(screen.getByText("blockierend")).toBeInTheDocument();
  });

  it("renders evidence and standards summaries when populated", () => {
    render(
      <EvidenceStandardsCard
        projection={{
          evidence_summary: { status: "evidence_found", node_count: 3, unresolved_gaps: ["Datenblatt"], claim_boundary: "screening" },
          standards_summary: { status: "evaluated", applicable_count: 2, blocking_gaps: [] },
        }}
      />,
    );
    expect(screen.getByText("Evidenz & Normen")).toBeInTheDocument();
    expect(screen.getByText(/3 Belege/)).toBeInTheDocument();
    expect(screen.getByText(/2 anwendbar/)).toBeInTheDocument();
    expect(screen.getByText(/Datenblatt/)).toBeInTheDocument();
  });

  it("does not render the evidence/standards card while both are pending/empty", () => {
    const { container } = render(
      <EvidenceStandardsCard
        projection={{ evidence_summary: { status: "pending", node_count: 0 }, standards_summary: { status: "pending", applicable_count: 0 } }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders every AC3 section together from a full projection", () => {
    render(
      <CockpitProjectionCards
        projection={{
          active_question: { field: "medium", question: "Welches Medium?" },
          current_facts: [{ field_name: "temperature_c", value: 90, unit: "°C", source: "asserted_state" }],
          missing_fields: [{ key: "medium", label: "medium", status: "missing" }],
          readiness_band: "screening_possible",
          conflicts: [{ field_name: "temperature_operating_c", description: "90 vs 190 °C", severity: "warning" }],
          risk_matrix: [{ title: "Trockenlauf-Risiko", severity: "watch" }],
          evidence_summary: { status: "evidence_found", node_count: 1 },
        }}
      />,
    );
    expect(screen.getByText("Aktive Frage")).toBeInTheDocument();
    expect(screen.getByText("Erkannte Angaben")).toBeInTheDocument();
    expect(screen.getByText("Offene Angaben")).toBeInTheDocument();
    expect(screen.getByText("Status & Einordnung")).toBeInTheDocument();
    expect(screen.getByText("Widersprüche")).toBeInTheDocument();
    expect(screen.getByText("Risiken & Befunde")).toBeInTheDocument();
    expect(screen.getByText("Evidenz & Normen")).toBeInTheDocument();
  });
});
