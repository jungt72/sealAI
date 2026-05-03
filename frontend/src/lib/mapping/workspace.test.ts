import assert from "node:assert/strict";
import test from "node:test";

import { mapWorkspaceView } from "./workspace.ts";

function legacyProjection() {
  return {
    request_type: "retrofit",
    engineering_path: "rwdr",
    cockpit_view: {
      request_type: "retrofit",
      engineering_path: "rwdr",
      routing_metadata: {
        phase: "clarification",
        last_node: "facade_hydration",
        routing: {},
      },
      sections: [
        {
          section_id: "application_function",
          title: "1. Anlage & Funktion",
          completion: { mandatory_present: 2, mandatory_total: 3, percent: 67 },
          properties: [
            {
              key: "medium",
              label: "Medium / Fluid",
              value: "Steam",
              origin: "user_override",
              confidence: "confirmed",
              source_type: "user_stated",
              validation_status: "user_stated",
              is_confirmed: true,
              is_mandatory: true,
            },
          ],
        },
      ],
      checks: [
        {
          calc_id: "rwdr_circumferential_speed",
          label: "Umlaufgeschwindigkeit",
          formula_version: "rwdr_calc_v1",
          required_inputs: ["shaft_diameter_mm", "speed_rpm"],
          missing_inputs: [],
          valid_paths: ["rwdr"],
          output_key: "v_surface_m_s",
          unit: "m/s",
          status: "ok",
          value: 3.93,
          fallback_behavior: "insufficient_data_when_required_inputs_missing",
          guardrails: ["diameter and speed must be present and non-negative"],
          notes: ["Dn-Wert liegt im ueblichen Richtbereich."],
        },
      ],
      missing_mandatory_keys: ["speed_rpm"],
      blockers: ["compound approval"],
      readiness: {
        status: "preliminary",
        is_rfq_ready: false,
        release_status: "manufacturer_validation_required",
        coverage_score: 0.65,
      },
    },
    deep_dive_tabs: [
      {
        tab_id: "material",
        label: "Werkstoff",
        status: "available",
        detected: ["PTFE"],
        relevance: "Werkstoff muss gegen Medium und Temperatur gespiegelt werden.",
        opportunities: ["Materialrichtung eingrenzen"],
        risks: ["Herstellerfreigabe erforderlich"],
        derived_direction: "PTFE als Richtung",
        missing: ["surface_finish"],
        next_action: "Oberflaeche klaeren",
        return_to_analysis: "Zurueck zur Analyse",
        cards: [{ title: "Werkstoffbasis", body: "PTFE Richtung", items: ["PTFE"] }],
      },
    ],
    communication_context: {
      conversation_phase: "clarification",
      turn_goal: "clarify_primary_open_point",
      primary_question: "Können Sie den Betriebsdruck noch einordnen?",
      supporting_reason: "Dann kann ich die technische Einengung sauber weiterfuehren.",
      response_mode: "single_question",
      confirmed_facts_summary: ["Medium: Steam"],
      open_points_summary: ["Betriebsdruck"],
    },
    parameters: {
      medium: "Steam",
      pressure_bar: 12,
      temperature_c: 180,
      shaft_diameter_mm: 50,
      speed_rpm: 6000,
      installation: "rotierende Wellenabdichtung",
      motion_type: "rotary",
    },
    medium_context: {
      medium_label: "Steam",
      status: "available",
      scope: "case",
      summary: "Steam context",
      properties: ["hot"],
      challenges: ["burn"],
      followup_points: ["pressure source"],
      confidence: "medium",
      source_type: "rag_verified",
      validation_status: "documented",
      not_for_release_decisions: true,
      disclaimer: "No release decision.",
    },
    seal_application_profile: {
      seal_family: "rotary",
      seal_type: "radial_shaft_seal",
      seal_type_confidence: 0.82,
      confidence_band: "high",
      matched_alias: "RWDR",
      ambiguous: false,
      candidate_types: [],
      application_domain: "shaft_sealing",
      motion_type: "rotary",
      standard_refs: [],
      type_specific_missing_hints: ["surface_finish"],
      notes: [],
      source: "seal_type_normalizer",
    },
    decision_understanding: {
      case_summary: "Steam RWDR case with open surface finish.",
      understood_now: ["Medium: Steam"],
      technical_meaning: ["Temperature drives material review."],
      plausible_directions: ["RWDR inquiry basis"],
      not_yet_decidable: ["surface_finish"],
      key_risks: ["temperature"],
      confidence_notes: ["source-backed but incomplete"],
      next_best_question: "Which surface finish is documented?",
      manufacturer_review_needs: ["compound approval"],
      needs_analysis: {
        primary_need: "retrofit",
        secondary_needs: ["technical_clarification"],
        urgency: "normal",
        user_side: "buyer",
        context_side: "maintenance",
        confidence: 0.7,
        notes: [],
      },
      current_state_analysis: {
        known_fields: ["medium"],
        missing_fields: ["surface_finish"],
        uncertain_fields: [],
        conflicting_fields: [],
        evidence_backed_fields: ["medium"],
        seal_type_status: "candidate",
        readiness_hint: "prequalification",
        confidence: 0.6,
      },
      next_best_questions: [
        {
          question: "Which surface finish is documented?",
          reason: "Surface finish drives seal lip review.",
          focus_key: "surface_finish",
          priority: 1,
          expected_answer_type: "text",
          applies_to_case_type: "retrofit",
          applies_to_seal_type: "radial_shaft_seal",
          source: "next_best_question_service",
          max_questions_policy: "ask_1_to_3_targeted_questions",
        },
      ],
      completeness_score: {
        score: 0.65,
        missing_critical_count: 1,
        known_critical_count: 4,
        uncertainty_count: 1,
        conflict_count: 0,
        notes: [],
      },
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
    evidence_summary: {
      evidence_present: true,
      evidence_count: 1,
      trusted_sources_present: true,
      evidence_supported_topics: ["medium"],
      source_backed_findings: ["medium"],
      deterministic_findings: ["pressure_bar"],
      assumption_based_findings: ["installation"],
      unresolved_open_points: ["missing_source_for_compliance"],
      evidence_gaps: ["missing_source_for_compliance"],
    },
    manufacturer_questions: {
      mandatory: ["Compound approval?"],
      open_questions: [],
      total_open: 1,
    },
    partner_matching: {
      matching_ready: true,
      shortlist_ready: true,
      inquiry_ready: false,
      not_ready_reasons: [],
      blocking_reasons: ["manufacturer_validation_required"],
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
      manufacturer_fit_matrix: {
        status: "fit_computed",
        disclosure: "Partnernetzwerk-Disclosure. Herstellerprüfung bleibt erforderlich.",
        eligible_partner_count: 2,
        no_suitable_partner_reason: null,
        rows: [
          {
            manufacturer_id: "partner-a",
            fit_score: 93.5,
            verification_level: "documented",
            fit_reasons: ["seal_type:rwdr"],
            gaps: [],
            missing_requirements: [],
            source_claim_ids: ["claim-a"],
          },
        ],
      },
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
        temperature_headroom_c: 140,
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
  assert.equal(workspace.requestType, "retrofit");
  assert.equal(workspace.engineeringPath, "rwdr");
  assert.equal(workspace.decisionUnderstanding?.caseSummary, "Steam RWDR case with open surface finish.");
  assert.deepEqual(workspace.decisionUnderstanding?.understoodNow, ["Medium: Steam"]);
  assert.equal(workspace.decisionUnderstanding?.nextBestQuestions[0]?.reason, "Surface finish drives seal lip review.");
  assert.equal(workspace.sealApplicationProfile?.sealType, "radial_shaft_seal");
  assert.equal(workspace.mediumContext.validationStatus, "documented");
  assert.equal(workspace.cockpit?.requestType, "retrofit");
  assert.equal(workspace.cockpit?.path, "rwdr");
  assert.equal(workspace.cockpit?.sections.application_function.properties[0]?.origin, "user_override");
  assert.equal(workspace.cockpit?.sections.application_function.properties[0]?.sourceType, "user_stated");
  assert.equal(workspace.cockpit?.sections.application_function.properties[0]?.validationStatus, "user_stated");
  assert.equal(workspace.cockpit?.checks[0]?.calcId, "rwdr_circumferential_speed");
  assert.equal(workspace.cockpit?.checks[0]?.outputKey, "v_surface_m_s");
  assert.deepEqual(workspace.cockpit?.readiness.missingMandatoryKeys, ["speed_rpm"]);
  assert.equal(workspace.governance.releaseStatus, "manufacturer_validation_required");
  assert.equal(workspace.governance.releaseClass, "C");
  assert.equal(workspace.completeness.coveragePercent, 65);
  assert.equal(workspace.matching.items.length, 1);
  assert.equal(workspace.matching.shortlistReady, true);
  assert.equal(workspace.matching.inquiryReady, false);
  assert.deepEqual(workspace.matching.blockingReasons, ["manufacturer_validation_required"]);
  assert.equal(workspace.matching.manufacturerFitMatrix?.status, "fit_computed");
  assert.equal(workspace.matching.manufacturerFitMatrix?.rows[0]?.manufacturerId, "partner-a");
  assert.equal(workspace.matching.manufacturerFitMatrix?.rows[0]?.fitScore, 93.5);
  assert.equal(workspace.matching.manufacturerFitMatrix?.rows[0]?.verificationLevel, "documented");
  assert.equal(workspace.rfq.documentUrl, "/api/bff/rfq/case-123/document");
  assert.equal(workspace.communication?.conversationPhase, "clarification");
  assert.equal(workspace.communication?.primaryQuestion, "Können Sie den Betriebsdruck noch einordnen?");
  assert.equal(workspace.parameters?.shaft_diameter_mm, 50);
  assert.equal(workspace.parameters?.speed_rpm, 6000);
  assert.equal(workspace.technicalDerivations?.[0]?.calcType, "rwdr");
  assert.equal(workspace.technicalDerivations?.[0]?.vSurfaceMPerS, 3.93);
  assert.equal(workspace.technicalDerivations?.[0]?.temperatureHeadroomC, 140);
  assert.equal(workspace.deepDiveTabs[0]?.tabId, "material");
  assert.equal(workspace.deepDiveTabs[0]?.cards[0]?.title, "Werkstoffbasis");
  assert.equal(workspace.deepDiveTabs[0]?.nextAction, "Oberflaeche klaeren");
  assert.equal(workspace.evidence.evidencePresent, true);
  assert.deepEqual(workspace.evidence.sourceBackedFindings, ["medium"]);
  assert.deepEqual(workspace.evidence.evidenceGaps, ["missing_source_for_compliance"]);
});
