import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import StreamWorkspaceCards from "@/components/dashboard/workspace/StreamWorkspaceCards";

const workspaceStoreState = {
  streamWorkspace: {
    caseId: "case-123",
    reply: "Antwort",
    responseClass: "structured_clarification",
    assertions: null,
    structuredState: { case_status: "clarification_needed" },
    turnContext: {
      conversationPhase: "clarification",
      turnGoal: "clarify_primary_open_point",
      primaryQuestion: "Welcher Betriebsdruck liegt an?",
      supportingReason: "Der Druck bestimmt die mechanische Belastung der Dichtung.",
      responseMode: "single_question",
      confirmedFactsSummary: ["Medium: Dampf", "Temperatur: 180 C"],
      openPointsSummary: ["Betriebsdruck", "Bewegungsart"],
    },
    ui: {
      parameter: {
        parameters: [],
        parameter_count: 2,
        needs_confirmation: false,
      },
      assumption: {
        items: [],
        open_points: ["pressure missing"],
        has_open_points: true,
      },
      recommendation: {
        scope_status: "partial",
        rfq_admissible: false,
        requirement_class: "PTFE10",
        requirement_summary: "PTFE profile",
        validity_notes: ["manufacturer validation required"],
        open_points: ["pressure missing"],
      },
      compute: {
        items: [
          {
            calc_type: "rwdr",
            status: "ok",
            v_surface_m_s: 3.93,
            pv_value_mpa_m_s: 0.39,
            dn_value: 75000,
            notes: ["Dn-Wert liegt im ueblichen Richtbereich."],
          },
        ],
      },
      matching: {
        status: "pending",
        selected_manufacturer: null,
        manufacturer_count: 0,
        manufacturers: [],
        notes: [],
      },
      rfq: {
        status: "pending",
        rfq_ready: false,
        rfq_admissible: false,
        selected_manufacturer: null,
        recipient_count: 0,
        qualified_material_count: 0,
        requirement_class: null,
        dispatch_ready: false,
        dispatch_status: "pending",
        notes: [],
      },
      medium_classification: {
        canonical_label: "Salzwasser",
        family: "waessrig_salzhaltig",
        confidence: "high",
        status: "recognized",
        normalization_source: "deterministic_alias_map",
        mapping_confidence: "confirmed",
        matched_alias: "salzwasser",
        source_registry_key: "salzwasser",
        followup_question: null,
        primary_raw_text: "salzwasser",
        raw_mentions: ["salzwasser"],
      },
      medium_context: {
        medium_label: "Salzwasser",
        status: "available",
        scope: "orientierend",
        summary: "Allgemeiner Medium-Kontext fuer salzhaltige wasserbasierte Anwendungen.",
        properties: ["wasserbasiert", "salzhaltig"],
        challenges: ["Korrosionsrisiko an Metallkomponenten beachten"],
        followup_points: ["Salzkonzentration", "Temperatur"],
        confidence: "medium",
        source_type: "llm_general_knowledge",
        not_for_release_decisions: true,
        disclaimer: "Allgemeiner Medium-Kontext, nicht als Freigabe.",
      },
    },
  },
};

vi.mock("@/lib/store/workspaceStore", () => ({
  useWorkspaceStore: (selector: (state: typeof workspaceStoreState) => unknown) =>
    selector(workspaceStoreState),
}));

describe("StreamWorkspaceCards", () => {
  it("renders live workspace state without right-side prompting", () => {
    render(<StreamWorkspaceCards />);

    expect(screen.getByText("Gezielte Klaerung")).toBeInTheDocument();
    expect(screen.getByText("Live Technischer Stand")).toBeInTheDocument();
    expect(screen.getByText("Medium: Dampf")).toBeInTheDocument();
    expect(screen.getByText("Arbeitsstatus: clarification needed")).toBeInTheDocument();
    expect(screen.getByText("Technische Ableitungen")).toBeInTheDocument();
    expect(screen.getByText("3.93 m/s")).toBeInTheDocument();
    expect(screen.getByText("Medium-Status")).toBeInTheDocument();
    expect(screen.getByText("Medium-Kontext")).toBeInTheDocument();
    expect(screen.queryByText("Naechste Punkte")).not.toBeInTheDocument();
    expect(screen.queryByText("Welcher Betriebsdruck liegt an?")).not.toBeInTheDocument();
    expect(screen.queryByText("Salzkonzentration")).not.toBeInTheDocument();
  });
});
