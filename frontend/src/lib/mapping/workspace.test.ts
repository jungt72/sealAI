import assert from "node:assert/strict";
import test from "node:test";

import { mapWorkspaceView } from "./workspace.ts";

function legacyProjection() {
  return {
    communication_context: {
      conversation_phase: "clarification",
      turn_goal: "clarify_primary_open_point",
      primary_question: "Koennen Sie den Betriebsdruck noch einordnen?",
      supporting_reason: "Dann kann ich die technische Einengung sauber weiterfuehren.",
      response_mode: "single_question",
      confirmed_facts_summary: ["Medium: Steam"],
      open_points_summary: ["Betriebsdruck"],
    },
    case_summary: {
      thread_id: "case-123",
      turn_count: 4,
      max_turns: 12,
    },
    completeness: {
      coverage_score: 0.65,
      coverage_gaps: ["surface_finish"],
      completeness_depth: "prequalification",
      missing_critical_parameters: ["speed_rpm"],
      analysis_complete: false,
      recommendation_ready: false,
    },
    governance_status: {
      release_status: "manufacturer_validation_required",
      scope_of_validity: ["temperature <= 180C"],
      assumptions_active: ["surface finish assumed"],
      unknowns_release_blocking: ["speed_rpm"],
      unknowns_manufacturer_validation: ["compound approval"],
      gate_failures: [],
      governance_notes: ["Validation required"],
      required_disclaimers: ["Manufacturer validation required."],
      verification_passed: true,
    },
    specificity: {
      material_specificity_required: "compound_required",
      completeness_depth: "prequalification",
      elevation_possible: true,
      elevation_target: "compound_required",
      elevation_hints: [
        {
          label: "Define compound",
          field_key: "compound",
          reason: "Improves technical narrowing.",
          priority: 1,
          action_type: "specify_material",
        },
      ],
    },
    candidate_clusters: {
      plausibly_viable: [{ kind: "material", value: "FKM", specificity: "family_only" }],
      manufacturer_validation_required: [{ kind: "material", value: "HNBR", specificity: "compound_required" }],
      inadmissible_or_excluded: [{ kind: "material", value: "NBR", excluded_by_gate: "chemistry" }],
      total_candidates: 3,
    },
    conflicts: {
      total: 1,
      open: 1,
      resolved: 0,
      by_severity: { HARD: 1 },
      items: [
        {
          conflict_type: "PARAMETER_CONFLICT",
          severity: "HARD",
          summary: "Pressure exceeds fit window.",
          resolution_status: "OPEN",
        },
      ],
    },
    claims_summary: {
      total: 2,
      by_type: { deterministic_fact: 1, evidence_based_assertion: 1 },
      by_origin: { deterministic: 1, evidence: 1 },
      items: [
        { value: "FKM OK", claim_type: "evidence_based_assertion", claim_origin: "evidence" },
        { value: "NBR excluded", claim_type: "deterministic_fact", claim_origin: "deterministic" },
      ],
    },
    manufacturer_questions: {
      mandatory: ["Compound approval?"],
      open_questions: [],
      total_open: 1,
    },
    partner_matching: {
      matching_ready: true,
      not_ready_reasons: [],
      material_fit_items: [
        {
          material: "FKM",
          cluster: "viable",
          specificity: "family_only",
          requires_validation: false,
          fit_basis: "evidence",
          grounded_facts: [],
        },
      ],
      open_manufacturer_questions: ["Compound approval?"],
      selected_partner_id: null,
      data_source: "candidate_derived",
    },
    rfq_status: {
      release_status: "manufacturer_validation_required",
      rfq_confirmed: false,
      blockers: ["speed_rpm"],
      open_points: ["compound approval"],
      has_pdf: false,
      has_html_report: true,
      handover_ready: false,
      handover_initiated: false,
    },
    rfq_package: {
      has_draft: true,
      rfq_id: "rfq-1",
      rfq_basis_status: "provisional",
      operating_context_redacted: {
        medium: "Steam",
        pressure_bar: 12,
      },
      manufacturer_questions_mandatory: ["Compound approval?"],
      conflicts_visible_count: 1,
      buyer_assumptions_acknowledged: ["surface finish assumed"],
    },
    technical_derivations: [
      {
        calc_type: "rwdr",
        status: "ok",
        v_surface_m_s: 3.93,
        pv_value_mpa_m_s: 0.39,
        dn_value: 75000,
        notes: ["Dn-Wert liegt im ueblichen Richtbereich."],
      },
    ],
    cycle_info: {
      current_assertion_cycle_id: 2,
      state_revision: 5,
      asserted_profile_revision: 3,
      derived_artifacts_stale: false,
      stale_reason: null,
    },
  };
}

test("mapWorkspaceView normalizes legacy workspace sections", () => {
  const workspace = mapWorkspaceView("case-123", legacyProjection());

  assert.equal(workspace.caseId, "case-123");
  assert.equal(workspace.governance.releaseStatus, "manufacturer_validation_required");
  assert.equal(workspace.governance.releaseClass, "C");
  assert.equal(workspace.completeness.coveragePercent, 65);
  assert.equal(workspace.matching.items.length, 1);
  assert.equal(workspace.rfq.documentUrl, "/api/bff/rfq/case-123/document");
  assert.equal(workspace.communication?.conversationPhase, "clarification");
  assert.equal(workspace.communication?.primaryQuestion, "Koennen Sie den Betriebsdruck noch einordnen?");
  assert.equal(workspace.technicalDerivations?.[0]?.calcType, "rwdr");
  assert.equal(workspace.technicalDerivations?.[0]?.vSurfaceMPerS, 3.93);
});
