import assert from "node:assert/strict";
import test from "node:test";

import { buildStreamWorkspaceView } from "./streamWorkspace.ts";
import { streamWorkspaceToWorkspaceView } from "./streamWorkspaceAdapter.ts";

test("streamWorkspaceToWorkspaceView exposes extracted chat parameters as cockpit workspace data", () => {
  const streamWorkspace = buildStreamWorkspaceView({
    type: "state_update",
    caseId: "case-chat-extraction",
    responseClass: "structured_clarification",
    turnContext: {
      conversationPhase: "clarification",
      turnGoal: "clarify_primary_open_point",
      responseMode: "single_question",
      primaryQuestion: "Welche Drehzahl liegt an?",
      supportingReason: "Drehzahl wird für die Umfangsgeschwindigkeit benötigt.",
      confirmedFactsSummary: ["Medium: Dampf CIP"],
      openPointsSummary: ["Drehzahl"],
    },
    structuredState: {
      view: {
        parameter: {
          parameters: [
            { field_name: "medium", value: "Dampf CIP", unit: null, confidence: "inferred" },
            { field_name: "temperature_c", value: 120, unit: "°C", confidence: "inferred" },
            { field_name: "ambiguous_pressure_bar", value: 5, unit: "bar", confidence: "requires_confirmation" },
            { field_name: "shaft_diameter_mm", value: 30, unit: "mm", confidence: "inferred" },
            { field_name: "material", value: "PTFE", unit: null, confidence: "inferred" },
            { field_name: "sealing_type", value: "O-Ring", unit: null, confidence: "inferred" },
          ],
          parameter_count: 6,
          needs_confirmation: true,
        },
        assumption: {
          items: [{ kind: "open_point", text: "Druckrolle klären" }],
          open_points: ["Druckrolle klären"],
          has_open_points: true,
        },
        recommendation: {
          scope_status: "clarification",
          rfq_admissible: false,
          validity_notes: ["Herstellerfreigabe erforderlich"],
          open_points: ["Drehzahl"],
        },
        compute: { items: [] },
        matching: { status: "pending", manufacturer_count: 0, manufacturers: [], notes: [] },
        rfq: { status: "pending", rfq_ready: false, rfq_admissible: false, notes: [] },
        medium_classification: {
          canonical_label: "Dampf",
          family: "dampffoermig",
          confidence: "medium",
          status: "recognized",
          primary_raw_text: "Dampf CIP",
          raw_mentions: ["Dampf CIP"],
        },
        medium_context: {
          medium_label: "Dampf",
          status: "available",
          scope: "orientierend",
          challenges: ["Temperatur- und CIP-Belastung prüfen"],
          followup_points: ["Dampfart"],
          not_for_release_decisions: true,
        },
        v92: {
          seal_system: {
            status: "candidate",
            seal_family: "static",
            seal_type: "O-Ring",
            missing_fields: ["speed_rpm"],
            validity_boundaries: ["Keine finale Freigabe"],
          },
          engineering: { status: "pending", route: "static", blockers: ["speed_rpm"] },
          calculations: { status: "pending", result_count: 0 },
        },
      },
    },
    ui: {},
  });

  const workspace = streamWorkspaceToWorkspaceView(streamWorkspace);

  assert.ok(workspace);
  assert.equal(workspace.caseId, "case-chat-extraction");
  assert.equal(workspace.parameters?.medium, "Dampf CIP");
  assert.equal(workspace.parameters?.temperature_c, 120);
  assert.equal(workspace.parameters?.pressure_bar, 5);
  assert.equal(workspace.parameters?.material, "PTFE");
  assert.equal(workspace.parameters?.sealing_material_family, "PTFE");
  assert.equal(workspace.mediumClassification.canonicalLabel, "Dampf");
  assert.equal(workspace.communication?.primaryQuestion, "Welche Drehzahl liegt an?");
  assert.equal(workspace.completeness.missingCriticalParameters.includes("Druckrolle klären"), true);
});
