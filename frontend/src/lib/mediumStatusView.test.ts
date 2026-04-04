import { describe, expect, it } from "vitest";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import type { StreamWorkspaceView } from "@/lib/streamWorkspace";
import {
  buildMediumStatusViewFromStream,
  buildMediumStatusViewFromWorkspace,
} from "@/lib/mediumStatusView";

describe("mediumStatusView", () => {
  it("builds the same recognized status from stream and canonical workspace data", () => {
    const streamView = buildMediumStatusViewFromStream({
      caseId: "case-123",
      reply: null,
      responseClass: "structured_clarification",
      assertions: null,
      structuredState: null,
      turnContext: null,
      ui: {
        parameter: { parameters: [], parameter_count: 0, needs_confirmation: false },
        assumption: { items: [], open_points: [], has_open_points: false },
        recommendation: {
          scope_status: "pending",
          rfq_admissible: false,
          requirement_class: null,
          requirement_summary: null,
          validity_notes: [],
          open_points: [],
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
          summary: null,
          properties: [],
          challenges: [],
          followup_points: [],
          confidence: null,
          source_type: null,
          not_for_release_decisions: true,
          disclaimer: null,
        },
      },
    } as StreamWorkspaceView);

    const workspaceView = buildMediumStatusViewFromWorkspace({
      mediumClassification: {
        canonicalLabel: "Salzwasser",
        family: "waessrig_salzhaltig",
        confidence: "high",
        status: "recognized",
        normalizationSource: "deterministic_alias_map",
        mappingConfidence: "confirmed",
        matchedAlias: "salzwasser",
        sourceRegistryKey: "salzwasser",
        followupQuestion: null,
      },
      mediumCapture: {
        rawMentions: ["salzwasser"],
        primaryRawText: "salzwasser",
        sourceTurnRef: "turn:1",
        sourceTurnIndex: 1,
      },
    } as WorkspaceView);

    expect(streamView).toMatchObject({
      status: "recognized",
      statusLabel: "erkannt",
      label: "Salzwasser",
      family: "wässrig, salzhaltig",
      confidence: "hoch",
    });
    expect(workspaceView).toMatchObject(streamView);
  });

  it("falls back to the raw mention when the medium is mentioned but unclassified", () => {
    const workspaceView = buildMediumStatusViewFromWorkspace({
      mediumClassification: {
        canonicalLabel: null,
        family: "unknown",
        confidence: "low",
        status: "mentioned_unclassified",
        normalizationSource: null,
        mappingConfidence: null,
        matchedAlias: null,
        sourceRegistryKey: null,
        followupQuestion: "Können Sie den Stoff oder die Zusammensetzung näher einordnen?",
      },
      mediumCapture: {
        rawMentions: ["XY-Compound 4711"],
        primaryRawText: "XY-Compound 4711",
        sourceTurnRef: "turn:2",
        sourceTurnIndex: 2,
      },
    } as WorkspaceView);

    expect(workspaceView.status).toBe("mentioned_unclassified");
    expect(workspaceView.label).toBe("XY-Compound 4711");
    expect(workspaceView.nextStepHint).toBe(
      "Können Sie den Stoff oder die Zusammensetzung näher einordnen?",
    );
  });
});
