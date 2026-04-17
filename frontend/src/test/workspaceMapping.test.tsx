import { describe, expect, it } from "vitest";

import { mapWorkspaceView } from "@/lib/mapping/workspace";

describe("mapWorkspaceView", () => {
  it("uses canonical RFQ readiness and pdf availability", () => {
    const workspace = mapWorkspaceView("case-123", {
      request_type: "validation_check",
      engineering_path: "rwdr",
      cockpit_view: {
        request_type: "validation_check",
        engineering_path: "rwdr",
        routing_metadata: {
          phase: "clarification",
          last_node: "facade_hydration",
          routing: {},
        },
        sections: [
          {
            section_id: "core_intake",
            title: "A. Grunddaten",
            completion: { mandatory_present: 3, mandatory_total: 4, percent: 75 },
            properties: [
              {
                key: "medium",
                label: "Medium / Fluid",
                value: "Salzwasser",
                origin: "fast_brain_extracted",
                confidence: "confirmed",
                is_confirmed: true,
                is_mandatory: true,
              },
            ],
          },
        ],
        checks: [
          {
            calc_id: "rwdr_circumferential_speed",
            label: "RWDR circumferential speed",
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
        missing_mandatory_keys: ["geometry_context"],
        blockers: [],
        readiness: {
          status: "preliminary",
          is_rfq_ready: false,
          release_status: "manufacturer_validation_required",
          coverage_score: 0.65,
        },
      },
      communication_context: {
        conversation_phase: "clarification",
        turn_goal: "clarify_primary_open_point",
        primary_question: "Koennen Sie den Betriebsdruck noch einordnen?",
        supporting_reason: "Dann kann ich die technische Einengung sauber weiterfuehren.",
        response_mode: "single_question",
        confirmed_facts_summary: ["Medium: Dampf"],
        open_points_summary: ["Betriebsdruck"],
      },
      medium_capture: {
        raw_mentions: ["salzwasser"],
        primary_raw_text: "salzwasser",
        source_turn_ref: "turn:1",
        source_turn_index: 1,
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
      case_summary: {
        thread_id: "case-123",
        turn_count: 4,
        max_turns: 12,
      },
      completeness: {
        coverage_score: 0.65,
        coverage_gaps: [],
        completeness_depth: "prequalification",
        missing_critical_parameters: [],
        analysis_complete: false,
        recommendation_ready: false,
      },
      governance_status: {
        release_status: "manufacturer_validation_required",
        scope_of_validity: [],
        assumptions_active: [],
        unknowns_release_blocking: [],
        unknowns_manufacturer_validation: [],
        gate_failures: [],
        governance_notes: [],
        required_disclaimers: [],
        verification_passed: true,
      },
      specificity: {
        material_specificity_required: "compound_required",
        completeness_depth: "prequalification",
        elevation_possible: false,
        elevation_hints: [],
        elevation_target: null,
      },
      candidate_clusters: {
        plausibly_viable: [],
        manufacturer_validation_required: [],
        inadmissible_or_excluded: [],
        total_candidates: 0,
      },
      conflicts: {
        total: 0,
        open: 0,
        resolved: 0,
        by_severity: {},
        items: [],
      },
      claims_summary: {
        total: 0,
        by_type: {},
        by_origin: {},
        items: [],
      },
      manufacturer_questions: {
        mandatory: [],
        open_questions: [],
        total_open: 0,
      },
      partner_matching: {
        matching_ready: false,
        not_ready_reasons: [],
        material_fit_items: [],
        open_manufacturer_questions: [],
        selected_partner_id: null,
        data_source: "candidate_derived",
      },
      rfq_status: {
        release_status: "manufacturer_validation_required",
        rfq_confirmed: false,
        rfq_ready: true,
        blockers: [],
        open_points: [],
        has_pdf: true,
        has_html_report: false,
        handover_ready: false,
        handover_initiated: false,
      },
      rfq_package: {
        has_draft: true,
        rfq_id: "rfq-1",
        rfq_basis_status: "rfq_ready",
        operating_context_redacted: {},
        manufacturer_questions_mandatory: [],
        conflicts_visible_count: 0,
        buyer_assumptions_acknowledged: [],
      },
      cycle_info: {
        current_assertion_cycle_id: 2,
        state_revision: 5,
        asserted_profile_revision: 3,
        derived_artifacts_stale: false,
        stale_reason: null,
      },
    });

    expect(workspace.rfq.status).toBe("ready");
    expect(workspace.requestType).toBe("validation_check");
    expect(workspace.engineeringPath).toBe("rwdr");
    expect(workspace.cockpit?.requestType).toBe("validation_check");
    expect(workspace.cockpit?.path).toBe("rwdr");
    expect(workspace.cockpit?.sections.core_intake.properties[0]?.origin).toBe("fast_brain_extracted");
    expect(workspace.cockpit?.checks[0]?.calcId).toBe("rwdr_circumferential_speed");
    expect(workspace.cockpit?.checks[0]?.outputKey).toBe("v_surface_m_s");
    expect(workspace.cockpit?.readiness.missingMandatoryKeys).toEqual(["geometry_context"]);
    expect(workspace.rfq.documentUrl).toBe("/api/bff/rfq/case-123/document");
    expect(workspace.communication?.conversationPhase).toBe("clarification");
    expect(workspace.communication?.primaryQuestion).toBe(
      "Koennen Sie den Betriebsdruck noch einordnen?",
    );
    expect(workspace.mediumCapture.primaryRawText).toBe("salzwasser");
    expect(workspace.mediumClassification.canonicalLabel).toBe("Salzwasser");
    expect(workspace.mediumClassification.family).toBe("waessrig_salzhaltig");
    expect(workspace.mediumContext.mediumLabel).toBe("Salzwasser");
    expect(workspace.mediumContext.scope).toBe("orientierend");
    expect(workspace.mediumContext.notForReleaseDecisions).toBe(true);
    expect(workspace.technicalDerivations?.[0]?.calcType).toBe("rwdr");
    expect(workspace.technicalDerivations?.[0]?.dnValue).toBe(75000);
  });
});
