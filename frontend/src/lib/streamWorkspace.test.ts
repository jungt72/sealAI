import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildStreamWorkspaceView } from "./streamWorkspace.ts";

const RFQ_READINESS_CONTRACT_FIXTURE = new URL(
  "../../../contracts/rfq_readiness_projection_v1.fixture.json",
  import.meta.url,
);

function rfqReadinessContractFixture(): Record<string, unknown> {
  return JSON.parse(
    readFileSync(RFQ_READINESS_CONTRACT_FIXTURE, "utf8"),
  ) as Record<string, unknown>;
}

test("buildStreamWorkspaceView normalizes state_update ui payloads", () => {
  const rfqReadinessProjection = rfqReadinessContractFixture();
  const view = buildStreamWorkspaceView({
    type: "state_update",
    caseId: "case-123",
    reply: "Antwort",
    responseClass: "governed_state_update",
    turnContext: {
      conversationPhase: "clarification",
      turnGoal: "clarify_primary_open_point",
      primaryQuestion: "Welcher Druck liegt an?",
      supportingReason: "Der Druck bestimmt die mechanische Belastung.",
      responseMode: "single_question",
      confirmedFactsSummary: ["Medium: Dampf"],
      openPointsSummary: ["Betriebsdruck"],
    },
    structuredState: { output_status: "governed_non_binding_result" },
    rfq_readiness_projection: rfqReadinessProjection,
    ui: {
      parameter: {
        parameters: [{ field_name: "medium", value: "steam", unit: null, confidence: "confirmed" }],
        parameter_count: 1,
        needs_confirmation: true,
      },
      assumption: {
        items: [{ kind: "open_point", text: "pressure missing" }],
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
        status: "ready",
        selected_manufacturer: "Acme",
        manufacturer_count: 1,
        manufacturers: ["Acme"],
        notes: ["technical fit available"],
      },
      rfq: {
        status: "pending",
        rfq_ready: false,
        rfq_admissible: false,
        selected_manufacturer: "Acme",
        recipient_count: 1,
        qualified_material_count: 1,
        requirement_class: "PTFE10",
        dispatch_ready: false,
        dispatch_status: "pending",
        notes: ["awaiting review"],
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
        summary: "Allgemeiner Medium-Kontext.",
        properties: ["wasserbasiert"],
        challenges: ["Korrosionsrisiko an Metallkomponenten beachten"],
        followup_points: ["Salzkonzentration"],
        confidence: "medium",
        source_type: "llm_general_knowledge",
        not_for_release_decisions: true,
        disclaimer: "Allgemeiner Medium-Kontext, nicht als Freigabe.",
      },
    },
  });

  assert.equal(view.caseId, "case-123");
  assert.equal(view.reply, "Antwort");
  assert.equal(view.ui.parameter.parameter_count, 1);
  assert.deepEqual(view.ui.assumption.open_points, ["pressure missing"]);
  const firstComputeItem = view.ui.compute.items?.[0];
  assert.ok(firstComputeItem);
  assert.equal(firstComputeItem.calc_type, "rwdr");
  assert.equal(firstComputeItem.v_surface_m_s, 3.93);
  assert.equal(view.ui.matching.selected_manufacturer, "Acme");
  assert.deepEqual(view.ui.rfq.notes, ["awaiting review"]);
  assert.equal(view.ui.medium_classification.canonical_label, "Salzwasser");
  assert.equal(view.ui.medium_classification.family, "waessrig_salzhaltig");
  assert.equal(view.ui.medium_context.medium_label, "Salzwasser");
  assert.equal(view.turnContext?.conversationPhase, "clarification");
  assert.deepEqual(view.turnContext?.confirmedFactsSummary, ["Medium: Dampf"]);
  assert.equal(view.rfqReadinessProjection?.preview_action_name, "create_rfq_preview");
  assert.equal(view.rfqReadinessProjection?.dispatch_allowed, false);
  assert.equal(view.rfqReadinessProjection?.external_contact_allowed, false);
  assert.equal(view.rfqReadinessProjection?.final_approval_claim_allowed, false);
  assert.deepEqual(view.rfqReadinessProjection?.known_missing_fields, ["Medium"]);
  assert.equal(view.rfqReadinessProjection?.pending_question?.target_field, "medium");
  assert.equal(
    view.rfqReadinessProjection?.pending_question?.question_text,
    "Welches Medium soll abgedichtet werden?",
  );
  assert.equal(view.rfqReadinessProjection?.preview_endpoint, "/api/v1/rfq/preview");
  assert.equal(view.rfqReadinessProjection?.projection_version, "rfq_readiness_projection_v1");
});

test("buildStreamWorkspaceView fills missing ui sections conservatively", () => {
  const view = buildStreamWorkspaceView({
    type: "state_update",
    caseId: "case-456",
    ui: {},
  });

  assert.equal(view.reply, null);
  assert.equal(view.ui.parameter.parameter_count, 0);
  assert.deepEqual(view.ui.assumption.open_points, []);
  assert.deepEqual(view.ui.compute.items, []);
  assert.equal(view.ui.recommendation.scope_status, "pending");
  assert.equal(view.ui.matching.status, "pending");
  assert.equal(view.ui.rfq.dispatch_status, "pending");
  assert.equal(view.ui.medium_classification.status, "unavailable");
  assert.equal(view.ui.medium_context.status, "unavailable");
  assert.equal(view.rfqReadinessProjection, null);
});
