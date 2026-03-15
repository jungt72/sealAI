import assert from "node:assert/strict";
import test from "node:test";

import { projectCaseStatePanel } from "./caseStateProjection.ts";

test("structured payload with case_state updates the panel model", () => {
  const model = projectCaseStatePanel(
    {
      active_domain: "rwdr_preselection",
      case_meta: {
        case_id: "case-17",
        analysis_cycle_id: "cycle-7",
        state_revision: 7,
      },
      raw_inputs: {
        pressure_bar: { value: 10, unit: "bar", confirmed: true },
        medium: { value: "Wasser", confirmed: true },
      },
      derived_calculations: {
        surface_speed_mps: {
          value: 3.927,
          unit: "m/s",
          formula_id: "surface_speed_from_diameter_and_rpm_v1",
        },
      },
      engineering_signals: {
        governance_conflicts_present: {
          value: 1,
          severity: "high",
          signal_class: "conflict_count",
        },
        material_risk_warning: {
          value: "PTFE requires validation for this case.",
          severity: "medium",
          signal_class: "warning",
        },
        rwdr_pressure_risk_level: {
          value: "high",
          severity: "high",
          signal_class: "risk_level",
        },
      },
      qualification_results: {
        material_governance: {
          status: "manufacturer_validation_required",
          binding_level: "QUALIFIED_PRESELECTION",
          source_type: "sealing_state.governance",
          source_ref: "sealing_state.governance",
          details: {
            assumptions_active: ["temperature_estimated"],
            gate_failures: ["identity_conflict_material"],
            unknowns_release_blocking: ["pressure_bar"],
          },
        },
        rwdr_preselection: {
          status: "engineering_review_required",
          binding_level: "QUALIFIED_PRESELECTION",
          source_type: "rwdr.output",
          source_ref: "rwdr.output",
          details: { type_class: "engineering_review_required", review_flags: ["review_water_with_pressure"] },
        },
      },
      result_contract: {
        analysis_cycle_id: "cycle-7",
        state_revision: 7,
        binding_level: "QUALIFIED_PRESELECTION",
        release_status: "manufacturer_validation_required",
        rfq_admissibility: "provisional",
        specificity_level: "subfamily",
        scope_of_validity: ["specificity_level:subfamily"],
        contract_obsolete: false,
        invalidation_requires_recompute: false,
        evidence_ref_count: 1,
        evidence_refs: ["fc-qualified-1"],
        source_ref: "case_state.result_contract",
        qualified_action: {
          summary: "qualified_action_blocked",
          allowed: false,
          binding_level: "ORIENTATION",
        },
      },
      sealing_requirement_spec: {
        contract_version: "sealing_requirement_spec_v1",
        rendering_status: "rendered",
        release_status: "manufacturer_validation_required",
        rfq_admissibility: "provisional",
        binding_level: "QUALIFIED_PRESELECTION",
        source_ref: "case_state.sealing_requirement_spec",
        render_artifact: {
          artifact_type: "sealing_requirement_spec_markdown",
          artifact_version: "sealing_requirement_spec_render_v1",
          filename: "sealing-requirement-spec-cycle-7.md",
          mime_type: "text/markdown",
          source_ref: "case_state.rendered_sealing_requirement_spec",
        },
      },
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: false,
        missing_review_inputs: ["available_width_mm"],
      },
      evidence_trace: {
        used_evidence_refs: ["fc-qualified-1"],
        used_source_fact_ids: ["sf-17"],
        evidence_ref_count: 1,
      },
      invalidation_state: {
        requires_recompute: false,
        stale_sections: [],
        recompute_reasons: ["temperature_c_changed"],
        recompute_completed: true,
        material_input_revision: 7,
        provider_contract_revision: 7,
      },
      audit_trail: [
        {
          event_type: "qualification_snapshot",
          timestamp: "2026-03-13T00:00:02+00:00",
          source_ref: "case_state.qualification_results",
          details: {
            result_keys: ["rwdr_preselection"],
          },
        },
      ],
    },
    {
      bindingLevel: "QUALIFIED_PRESELECTION",
      hasCaseState: true,
    },
  );

  assert.ok(model);
  assert.equal(model.isStructured, true);
  const checkpointItem = model.caseSummary.find(item => item.key === "checkpoint");
  assert.equal(checkpointItem?.value, "Cycle cycle-7 · Rev 7");
  assert.match(checkpointItem?.detail ?? "", /Qualification Snapshot/);
  const resumeItem = model.caseSummary.find(item => item.key === "resume_readiness");
  assert.equal(resumeItem?.value, "Resumable");
  assert.equal(resumeItem?.severity, "medium");
  assert.match(resumeItem?.detail ?? "", /Case case-17/);
  assert.match(resumeItem?.detail ?? "", /Review available_width_mm/);
  const currentCaseItem = model.caseSummary.find(item => item.key === "current_case_summary");
  assert.equal(currentCaseItem?.value, "manufacturer_validation_required");
  assert.equal(currentCaseItem?.severity, "medium");
  assert.match(currentCaseItem?.detail ?? "", /Binding QUALIFIED_PRESELECTION/);
  assert.match(currentCaseItem?.detail ?? "", /1 review missing/);
  const directionItem = model.technicalDirection.find(item => item.key === "technical_direction_current");
  assert.equal(directionItem?.value, "Engineering Review Required");
  assert.match(directionItem?.detail ?? "", /RWDR type-class direction/);
  const basisItem = model.technicalDirection.find(item => item.key === "technical_direction_basis");
  assert.equal(basisItem?.value, "RWDR");
  assert.match(basisItem?.detail ?? "", /Qualification Engineering Review Required/);
  const bindingItem = model.technicalDirection.find(item => item.key === "technical_direction_binding");
  assert.equal(bindingItem?.value, "QUALIFIED_PRESELECTION");
  assert.match(bindingItem?.detail ?? "", /RFQ provisional/);
  assert.match(bindingItem?.detail ?? "", /Scope Prequalified/);
  const limitsItem = model.technicalDirection.find(item => item.key === "technical_direction_limits");
  assert.equal(limitsItem?.value, "2 open item(s)");
  assert.match(limitsItem?.detail ?? "", /review_water_with_pressure/);
  assert.match(limitsItem?.detail ?? "", /available_width_mm/);
  const scopeItem = model.validityEnvelope.find(item => item.key === "validity_scope");
  assert.equal(scopeItem?.value, "1 marker(s)");
  assert.match(scopeItem?.detail ?? "", /specificity_level:subfamily/);
  const assumptionsItem = model.validityEnvelope.find(item => item.key === "validity_assumptions");
  assert.equal(assumptionsItem?.value, "1 active");
  assert.match(assumptionsItem?.detail ?? "", /temperature_estimated/);
  const constraintsItem = model.validityEnvelope.find(item => item.key === "validity_constraints");
  assert.equal(constraintsItem?.value, "1 gate · 1 blocking");
  assert.match(constraintsItem?.detail ?? "", /identity_conflict_material/);
  assert.match(constraintsItem?.detail ?? "", /pressure_bar/);
  const obsolescenceItem = model.validityEnvelope.find(item => item.key === "validity_obsolescence");
  assert.equal(obsolescenceItem?.value, "Current");
  assert.match(obsolescenceItem?.detail ?? "", /Reasons temperature_c_changed/);
  const failureModeItem = model.failureAnalysis.find(item => item.key === "failure_mode");
  assert.equal(failureModeItem?.value, "Hypothesis active");
  assert.match(failureModeItem?.detail ?? "", /Not a confirmed root cause/);
  const failureSymptomsItem = model.failureAnalysis.find(item => item.key === "failure_symptoms");
  assert.equal(failureSymptomsItem?.value, "2");
  assert.match(failureSymptomsItem?.detail ?? "", /Material Risk Warning: PTFE requires validation for this case\./);
  assert.match(failureSymptomsItem?.detail ?? "", /RWDR Pressure Risk Level: high/);
  const failureHypothesesItem = model.failureAnalysis.find(item => item.key === "failure_hypotheses");
  assert.equal(failureHypothesesItem?.value, "2");
  assert.match(failureHypothesesItem?.detail ?? "", /Leakage hypothesis/);
  assert.match(failureHypothesesItem?.detail ?? "", /Chemical damage hypothesis/);
  const failureConfirmedLimitsItem = model.failureAnalysis.find(item => item.key === "failure_confirmed_limits");
  assert.equal(failureConfirmedLimitsItem?.value, "1 review case(s)");
  assert.match(failureConfirmedLimitsItem?.detail ?? "", /review_water_with_pressure/);
  const failureUnknownsItem = model.failureAnalysis.find(item => item.key === "failure_open_unknowns");
  assert.equal(failureUnknownsItem?.value, "1");
  assert.match(failureUnknownsItem?.detail ?? "", /available_width_mm/);
  const nextInputFocusItem = model.nextBestInputs.find(item => item.key === "next_input_focus");
  assert.equal(nextInputFocusItem?.value, "1 input(s)");
  assert.match(nextInputFocusItem?.detail ?? "", /Available Width Mm/);
  const nextInputSplitItem = model.nextBestInputs.find(item => item.key === "next_input_split");
  assert.equal(nextInputSplitItem?.value, "0 critical · 1 review");
  assert.match(nextInputSplitItem?.detail ?? "", /Review Available Width Mm/);
  const nextStepImpactItem = model.nextBestInputs.find(item => item.key === "next_progress_step");
  assert.equal(nextStepImpactItem?.value, "Resolve review inputs");
  assert.match(nextStepImpactItem?.detail ?? "", /Collect Available Width Mm/);
  assert.match(nextStepImpactItem?.detail ?? "", /RFQ provisional/);
  assert.equal(model.suggestedNextQuestions.length, 1);
  assert.equal(model.suggestedNextQuestions[0]?.value, "Review input");
  assert.match(model.suggestedNextQuestions[0]?.detail ?? "", /available installation width in mm/i);
  const evidenceBasisItem = model.caseSummary.find(item => item.key === "evidence_basis");
  assert.equal(evidenceBasisItem?.value, "1 evidence ref(s)");
  assert.match(evidenceBasisItem?.detail ?? "", /fc-qualified-1/);
  assert.match(evidenceBasisItem?.detail ?? "", /sf-17/);
  const sourceBindingItem = model.caseSummary.find(item => item.key === "source_binding");
  assert.equal(sourceBindingItem?.value, "4 bound source(s)");
  assert.match(sourceBindingItem?.detail ?? "", /Types sealing_state\.governance, rwdr\.output/);
  assert.match(sourceBindingItem?.detail ?? "", /case_state\.result_contract/);
  assert.match(sourceBindingItem?.detail ?? "", /rwdr\.output/);
  assert.match(sourceBindingItem?.detail ?? "", /case_state\.qualification_results/);
  const deltaItem = model.caseSummary.find(item => item.key === "what_if_delta");
  assert.equal(deltaItem?.value, "Recomputed");
  assert.equal(deltaItem?.severity, "medium");
  assert.match(deltaItem?.detail ?? "", /Input rev 7/);
  assert.match(deltaItem?.detail ?? "", /Temperature C Changed/);
  const auditTrailItem = model.caseSummary.find(item => item.key === "audit_trail_summary");
  assert.equal(auditTrailItem?.value, "1 event(s)");
  assert.match(auditTrailItem?.detail ?? "", /Latest Qualification Snapshot/);
  const exportSnapshotItem = model.caseSummary.find(item => item.key === "export_snapshot");
  assert.equal(exportSnapshotItem?.value, "Exportable snapshot");
  assert.match(exportSnapshotItem?.detail ?? "", /sealing-requirement-spec-cycle-7\.md/);
  assert.match(exportSnapshotItem?.detail ?? "", /sealing_requirement_spec_render_v1/);
  assert.match(exportSnapshotItem?.detail ?? "", /Artifact case_state\.rendered_sealing_requirement_spec/);
  const handoverItem = model.caseSummary.find(item => item.key === "commercial_handover");
  assert.equal(handoverItem?.value, "Prequalified");
  assert.equal(handoverItem?.severity, "medium");
  assert.match(handoverItem?.detail ?? "", /Binding QUALIFIED_PRESELECTION/);
  assert.match(handoverItem?.detail ?? "", /Release manufacturer_validation_required/);
  assert.equal(model.knownParameters[0]?.label, "Medium");
  assert.equal(model.derivedValues[0]?.label, "Surface Speed M/S");
  const pressureRiskItem = model.engineeringSignals.find(item => item.key === "rwdr_pressure_risk_level");
  assert.equal(pressureRiskItem?.value, "high");
  const contradictionItem = model.engineeringSignals.find(item => item.key === "contradiction_summary");
  assert.equal(contradictionItem?.value, "1");
  assert.match(contradictionItem?.detail ?? "", /Governance Conflicts Present 1/);
  const boundaryItem = model.engineeringSignals.find(item => item.key === "boundary_summary");
  assert.equal(boundaryItem?.value, "1");
  assert.match(boundaryItem?.detail ?? "", /RWDR Pressure Risk Level: high/);
  const resultContractItem = model.qualificationStatus.find(item => item.key === "result_contract");
  assert.equal(resultContractItem?.label, "Result Contract");
  assert.match(resultContractItem?.detail ?? "", /Cycle cycle-7/);
  const bindingLevelItem = model.qualificationStatus.find(item => item.key === "binding_level");
  assert.equal(bindingLevelItem?.value, "QUALIFIED_PRESELECTION");
  const signalSummaryItem = model.qualificationStatus.find(item => item.key === "engineering_signal_summary");
  assert.match(signalSummaryItem?.value ?? "", /1 contradiction\(s\) · 1 boundary signal\(s\)/);
  const qualificationLevelItem = model.qualificationStatus.find(item => item.key === "qualification_level");
  assert.equal(qualificationLevelItem?.value, "Engineering Review Required");
  const rfqItem = model.qualificationStatus.find(item => item.key === "rfq_admissibility");
  assert.equal(rfqItem?.value, "provisional");
  const qualificationEvidenceItem = model.qualificationStatus.find(item => item.key === "qualification_evidence");
  assert.equal(qualificationEvidenceItem?.value, "1");
  assert.match(qualificationEvidenceItem?.detail ?? "", /fc-qualified-1/);
  assert.match(qualificationEvidenceItem?.detail ?? "", /case_state\.result_contract/);
  const deltaImpactItem = model.qualificationStatus.find(item => item.key === "delta_impact");
  assert.equal(deltaImpactItem?.value, "Qualification refreshed");
  assert.equal(deltaImpactItem?.severity, "medium");
  assert.match(deltaImpactItem?.detail ?? "", /Temperature C Changed/);
  const missingReviewInputs = model.qualificationStatus.find(item => item.key === "missing_review_inputs");
  assert.equal(missingReviewInputs?.value, "1");
  assert.match(missingReviewInputs?.detail ?? "", /available_width_mm/);
  const criticalSummary = model.qualificationStatus.find(item => item.key === "missing_critical_summary");
  assert.equal(criticalSummary?.value, "0");
});

test("frontend projection disables RFQ action when qualified action gate is blocked", () => {
  const model = projectCaseStatePanel(
    {
      active_domain: "material_static_seal_prequalification",
      raw_inputs: {
        medium: { value: "Wasser", confirmed: true },
      },
      derived_calculations: {},
      engineering_signals: {
        rwdr_pressure_risk_level: { value: "high", severity: "high", signal_class: "risk_level" },
        rwdr_tribology_risk_level: { value: "critical", severity: "high", signal_class: "risk_level" },
      },
      qualification_results: {
        material_core: {
          status: "stale_requires_recompute",
          binding_level: "ORIENTATION",
          details: { qualification_status: "neutral_rfq_basis_ready" },
        },
      },
      qualified_action_gate: {
        action: "download_technical_rfq",
        allowed: false,
        rfq_ready: false,
        block_reasons: ["requires_recompute", "stale_material_qualification"],
        summary: "qualified_action_blocked",
      },
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: false,
        missing_review_inputs: [],
      },
      invalidation_state: {
        requires_recompute: true,
        stale_sections: ["qualification_results.material_core", "derived_calculations", "engineering_signals"],
        recompute_reasons: ["temperature_c_changed", "provider_contract_fingerprint_changed"],
        recompute_completed: false,
      },
    },
    {
      bindingLevel: "QUALIFIED_PRESELECTION",
      hasCaseState: true,
    },
  );

  assert.ok(model);
  assert.equal(model.actionGate?.allowed, false);
  assert.deepEqual(model.actionGate?.blockReasons, ["requires_recompute", "stale_material_qualification"]);
  const deltaItem = model.caseSummary.find(item => item.key === "what_if_delta");
  assert.equal(deltaItem?.value, "Impact Detected");
  assert.equal(deltaItem?.severity, "high");
  assert.match(deltaItem?.detail ?? "", /Affected Qualification Results \/ Material Core/);
  const handoverItem = model.caseSummary.find(item => item.key === "commercial_handover");
  assert.equal(handoverItem?.value, "Prequalified");
  assert.equal(handoverItem?.severity, "medium");
  assert.match(handoverItem?.detail ?? "", /Gate blocked/);
  const actionGateItem = model.qualificationStatus.find(item => item.key === "qualified_action_gate");
  assert.equal(actionGateItem?.value, "Blocked");
  const deltaImpactItem = model.qualificationStatus.find(item => item.key === "delta_impact");
  assert.equal(deltaImpactItem?.value, "Qualification affected");
  assert.equal(deltaImpactItem?.severity, "high");
  assert.match(deltaImpactItem?.detail ?? "", /Recompute required before relying on stale sections/);
  const nextInputFocusItem = model.nextBestInputs.find(item => item.key === "next_input_focus");
  assert.equal(nextInputFocusItem?.value, "No immediate input gap");
  assert.match(nextInputFocusItem?.detail ?? "", /stale sections should be recomputed/i);
  const nextStepImpactItem = model.nextBestInputs.find(item => item.key === "next_progress_step");
  assert.equal(nextStepImpactItem?.value, "Recompute affected sections");
  assert.match(nextStepImpactItem?.detail ?? "", /Case change currently affects qualification reliability/);
  assert.equal(model.suggestedNextQuestions.length, 1);
  assert.equal(model.suggestedNextQuestions[0]?.value, "Recompute required");
  assert.match(model.suggestedNextQuestions[0]?.detail ?? "", /recompute stale qualification sections/i);
});

test("frontend projection marks RFQ-basis case as commercial handover ready", () => {
  const model = projectCaseStatePanel(
    {
      active_domain: "material_static_seal_prequalification",
      case_meta: {
        case_id: "case-rfq-1",
        analysis_cycle_id: "cycle-9",
        state_revision: 9,
        binding_level: "RFQ_BASIS",
      },
      raw_inputs: {
        medium: { value: "Wasser", confirmed: true },
      },
      derived_calculations: {},
      engineering_signals: {},
      qualification_results: {
        material_core: {
          status: "neutral_rfq_basis_ready",
          binding_level: "QUALIFIED_PRESELECTION",
          source_ref: "material_core.evaluate_material_qualification_core",
        },
      },
      result_contract: {
        analysis_cycle_id: "cycle-9",
        state_revision: 9,
        binding_level: "RFQ_BASIS",
        release_status: "rfq_ready",
        rfq_admissibility: "ready",
        specificity_level: "compound_required",
        scope_of_validity: ["specificity_level:compound_required"],
        contract_obsolete: false,
        invalidation_requires_recompute: false,
        evidence_ref_count: 1,
        evidence_refs: ["fc-qualified-1"],
        source_ref: "case_state.result_contract",
        qualified_action: {
          summary: "qualified_action_enabled",
          allowed: true,
          binding_level: "RFQ_BASIS",
        },
      },
      sealing_requirement_spec: {
        contract_version: "sealing_requirement_spec_v1",
        rendering_status: "rendered",
        release_status: "rfq_ready",
        rfq_admissibility: "ready",
        binding_level: "RFQ_BASIS",
        source_ref: "case_state.sealing_requirement_spec",
        render_artifact: {
          artifact_type: "sealing_requirement_spec_markdown",
          artifact_version: "sealing_requirement_spec_render_v1",
          filename: "sealing-requirement-spec-cycle-9.md",
          mime_type: "text/markdown",
          source_ref: "case_state.rendered_sealing_requirement_spec",
        },
      },
      qualified_action_gate: {
        action: "download_rfq",
        allowed: true,
        rfq_ready: true,
        binding_level: "RFQ_BASIS",
        block_reasons: [],
        summary: "qualified_action_enabled",
      },
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: true,
        missing_critical_inputs: [],
        missing_review_inputs: [],
      },
    },
    {
      bindingLevel: "RFQ_BASIS",
      hasCaseState: true,
    },
  );

  assert.ok(model);
  const handoverItem = model.caseSummary.find(item => item.key === "commercial_handover");
  assert.equal(handoverItem?.value, "Handover ready");
  assert.equal(handoverItem?.severity, "low");
  assert.match(handoverItem?.detail ?? "", /RFQ ready/);
  assert.match(handoverItem?.detail ?? "", /Gate enabled/);
  assert.match(handoverItem?.detail ?? "", /Technical snapshot available/);
});

test("frontend projection surfaces hard stop and review details in qualification status", () => {
  const model = projectCaseStatePanel(
    {
      active_domain: "rwdr_preselection",
      raw_inputs: {
        medium: { value: "Wasser", confirmed: true },
      },
      derived_calculations: {
        rwdr_surface_speed_mps: { value: 18.4, unit: "m/s" },
      },
      engineering_signals: {
        rwdr_pressure_risk_level: { value: "high", severity: "high", signal_class: "risk_level" },
        rwdr_tribology_risk_level: { value: "critical", severity: "high", signal_class: "risk_level" },
      },
      qualification_results: {
        rwdr_preselection: {
          status: "not_suitable",
          binding_level: "QUALIFIED_PRESELECTION",
          details: {
            type_class: "not_suitable",
            review_flags: ["review_water_with_pressure"],
            hard_stop: "hard_stop_surface_speed_over_limit",
          },
        },
      },
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: true,
        missing_review_inputs: [],
      },
    },
    {
      bindingLevel: "QUALIFIED_PRESELECTION",
      hasCaseState: true,
    },
  );

  assert.ok(model);
  const rwdrItem = model.qualificationStatus.find(item => item.key === "rwdr_preselection");
  assert.match(rwdrItem?.detail ?? "", /Hard stop hard_stop_surface_speed_over_limit/);
  assert.match(rwdrItem?.detail ?? "", /Review review_water_with_pressure/);
  const failureHypothesesItem = model.failureAnalysis.find(item => item.key === "failure_hypotheses");
  assert.equal(failureHypothesesItem?.value, "3");
  assert.match(failureHypothesesItem?.detail ?? "", /Leakage hypothesis/);
  assert.match(failureHypothesesItem?.detail ?? "", /Wear pattern hypothesis/);
  assert.match(failureHypothesesItem?.detail ?? "", /Deterministic hard stop indicates functional unsuitability/);
  const failureLimitsItem = model.failureAnalysis.find(item => item.key === "failure_confirmed_limits");
  assert.equal(failureLimitsItem?.value, "1 hard stop(s)");
  assert.match(failureLimitsItem?.detail ?? "", /hard_stop_surface_speed_over_limit/);
  const nextInputFocusItem = model.nextBestInputs.find(item => item.key === "next_input_focus");
  assert.equal(nextInputFocusItem?.value, "No immediate input gap");
  assert.match(nextInputFocusItem?.detail ?? "", /Qualification-ready from current visible inputs/);
  const nextStepImpactItem = model.nextBestInputs.find(item => item.key === "next_progress_step");
  assert.equal(nextStepImpactItem?.value, "Advance qualification");
  assert.equal(model.suggestedNextQuestions.length, 1);
  assert.equal(model.suggestedNextQuestions[0]?.value, "Qualification ready");
  assert.match(model.suggestedNextQuestions[0]?.detail ?? "", /No follow-up question is required/i);
  const boundaryItem = model.engineeringSignals.find(item => item.key === "boundary_summary");
  assert.equal(boundaryItem?.value, "2");
  assert.match(boundaryItem?.detail ?? "", /RWDR Pressure Risk Level: high/);
  assert.match(boundaryItem?.detail ?? "", /RWDR Tribology Risk Level: critical/);
  const hardStopsItem = model.qualificationStatus.find(item => item.key === "hard_stops");
  assert.equal(hardStopsItem?.value, "1");
  assert.match(hardStopsItem?.detail ?? "", /hard_stop_surface_speed_over_limit/);
  const reviewCasesItem = model.qualificationStatus.find(item => item.key === "review_cases");
  assert.equal(reviewCasesItem?.value, "1");
  assert.match(reviewCasesItem?.detail ?? "", /review_water_with_pressure/);
});

test("frontend projection shows last action status from case_state", () => {
  const model = projectCaseStatePanel(
    {
      active_domain: "material_static_seal_prequalification",
      raw_inputs: {
        medium: { value: "Wasser", confirmed: true },
      },
      derived_calculations: {},
      engineering_signals: {},
      qualification_results: {
        material_core: {
          status: "neutral_rfq_basis_ready",
          binding_level: "QUALIFIED_PRESELECTION",
        },
      },
      qualified_action_gate: {
        action: "download_technical_rfq",
        allowed: true,
        rfq_ready: true,
        block_reasons: [],
        summary: "qualified_action_enabled",
      },
      qualified_action_status: {
        action: "download_rfq",
        last_status: "blocked",
        executed: false,
        block_reasons: ["requires_recompute"],
        timestamp: "2026-03-13T00:00:00+00:00",
        current_gate_allows_action: true,
      },
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: true,
        missing_review_inputs: [],
      },
    },
    {
      bindingLevel: "QUALIFIED_PRESELECTION",
      hasCaseState: true,
    },
  );

  assert.ok(model);
  assert.equal(model.lastQualifiedAction?.lastStatus, "blocked");
  assert.deepEqual(model.lastQualifiedAction?.blockReasons, ["requires_recompute"]);
  assert.equal(model.lastQualifiedAction?.currentGateAllowsAction, true);
});

test("frontend projection shows action history from case_state", () => {
  const model = projectCaseStatePanel(
    {
      active_domain: "material_static_seal_prequalification",
      raw_inputs: {},
      derived_calculations: {},
      engineering_signals: {},
      qualification_results: {},
      qualified_action_gate: {
        action: "download_technical_rfq",
        allowed: false,
        rfq_ready: false,
        block_reasons: ["requires_recompute"],
        summary: "qualified_action_blocked",
      },
      qualified_action_status: {
        action: "download_rfq",
        last_status: "blocked",
        executed: false,
        block_reasons: ["requires_recompute"],
        timestamp: "2026-03-13T00:00:01+00:00",
        current_gate_allows_action: false,
      },
      qualified_action_history: [
        {
          action: "download_rfq",
          last_status: "blocked",
          executed: false,
          block_reasons: ["requires_recompute"],
          timestamp: "2026-03-13T00:00:01+00:00",
        },
        {
          action: "download_rfq",
          last_status: "executed",
          executed: true,
          block_reasons: [],
          timestamp: "2026-03-13T00:00:00+00:00",
        },
      ],
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: true,
        missing_review_inputs: [],
      },
    },
    {
      bindingLevel: "QUALIFIED_PRESELECTION",
      hasCaseState: true,
    },
  );

  assert.ok(model);
  assert.equal(model.qualifiedActionHistory.length, 2);
  assert.equal(model.qualifiedActionHistory[0]?.lastStatus, "blocked");
  assert.equal(model.qualifiedActionHistory[1]?.lastStatus, "executed");
});

test("frontend projection falls back to case contract binding and shows latest audit hint", () => {
  const model = projectCaseStatePanel({
    active_domain: "material_static_seal_prequalification",
    case_meta: {
      binding_level: "RFQ_BASIS",
    },
    raw_inputs: {
      medium: { value: "Wasser", confirmed: true },
    },
    derived_calculations: {
      surface_speed_mps: { value: 3.2, unit: "m/s" },
    },
    engineering_signals: {
      rwdr_pressure_risk_level: { value: "low", severity: "low", signal_class: "risk_level" },
    },
    qualification_results: {
      material_core: {
        status: "neutral_rfq_basis_ready",
        binding_level: "QUALIFIED_PRESELECTION",
      },
    },
    result_contract: {
      binding_level: "RFQ_BASIS",
      release_status: "rfq_ready",
      rfq_admissibility: "ready",
      specificity_level: "compound_required",
      contract_obsolete: false,
      invalidation_requires_recompute: false,
      qualified_action: {
        summary: "qualified_action_enabled",
        allowed: true,
        binding_level: "RFQ_BASIS",
      },
    },
    audit_trail: [
      {
        event_type: "readiness_snapshot",
        timestamp: "2026-03-13T00:00:00+00:00",
        source_ref: "case_state.readiness",
        details: {
          ready_for_qualification: false,
          missing_critical_inputs: ["pressure_bar"],
        },
      },
      {
        event_type: "qualified_action_gate_snapshot",
        timestamp: "2026-03-13T00:00:01+00:00",
        source_ref: "case_state.qualified_action_gate",
        details: {
          block_reasons: ["requires_recompute"],
        },
      },
    ],
  });

  assert.ok(model);
  assert.match(model.subtitle, /Binding: RFQ_BASIS/);
  const bindingLevelItem = model.qualificationStatus.find(item => item.key === "binding_level");
  assert.equal(bindingLevelItem?.value, "RFQ_BASIS");
  const rfqItem = model.qualificationStatus.find(item => item.key === "rfq_admissibility");
  assert.equal(rfqItem?.value, "ready");
  const qualificationLevelItem = model.qualificationStatus.find(item => item.key === "qualification_level");
  assert.equal(qualificationLevelItem?.value, "Neutral RFQ Basis Ready");
  const criticalSummary = model.qualificationStatus.find(item => item.key === "missing_critical_summary");
  assert.equal(criticalSummary?.value, "0");
  const auditItem = model.qualificationStatus.find(item => item.key === "latest_audit");
  assert.equal(auditItem?.value, "Qualified Action Gate Snapshot");
  assert.match(auditItem?.detail ?? "", /Blocked requires_recompute/);
  assert.match(auditItem?.detail ?? "", /case_state\.qualified_action_gate/);
});

test("frontend projection limits next best inputs to three prioritized items", () => {
  const model = projectCaseStatePanel(
    {
      active_domain: "material_static_seal_prequalification",
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: false,
        missing_critical_inputs: [
          "pressure_bar",
          "temperature_c",
          "medium",
          "shaft_diameter_mm",
        ],
        missing_review_inputs: ["available_width_mm"],
      },
      result_contract: {
        rfq_admissibility: "inadmissible",
      },
    },
    {
      bindingLevel: "ORIENTATION",
      hasCaseState: true,
    },
  );

  assert.ok(model);
  const nextInputFocusItem = model.nextBestInputs.find(item => item.key === "next_input_focus");
  assert.equal(nextInputFocusItem?.value, "3 input(s)");
  assert.match(nextInputFocusItem?.detail ?? "", /Pressure Bar/);
  assert.match(nextInputFocusItem?.detail ?? "", /Temperature C/);
  assert.match(nextInputFocusItem?.detail ?? "", /Medium/);
  assert.doesNotMatch(nextInputFocusItem?.detail ?? "", /Shaft Diameter Mm/);
  const nextInputSplitItem = model.nextBestInputs.find(item => item.key === "next_input_split");
  assert.equal(nextInputSplitItem?.value, "4 critical · 1 review");
  const nextStepImpactItem = model.nextBestInputs.find(item => item.key === "next_progress_step");
  assert.equal(nextStepImpactItem?.value, "Ask critical inputs first");
  assert.equal(model.suggestedNextQuestions.length, 3);
  assert.match(model.suggestedNextQuestions[0]?.detail ?? "", /operating pressure in bar/i);
  assert.match(model.suggestedNextQuestions[1]?.detail ?? "", /operating temperature in °C/i);
  assert.match(model.suggestedNextQuestions[2]?.detail ?? "", /medium or fluid/i);
});

test("fast path rendering stays empty without case_state", () => {
  const model = projectCaseStatePanel(null, {
    bindingLevel: "CALCULATION",
    hasCaseState: false,
  });

  assert.equal(model, null);
});

test("frontend projection prefers backend visible case narrative when provided", () => {
  const model = projectCaseStatePanel(
    {
      qualification_results: {},
      readiness: {},
      result_contract: {
        binding_level: "ORIENTATION",
        release_status: "inadmissible",
        rfq_admissibility: "inadmissible",
        specificity_level: "family_only",
        contract_obsolete: false,
        invalidation_requires_recompute: false,
        invalidation_reasons: [],
      },
    },
    {
      bindingLevel: "ORIENTATION",
      hasCaseState: true,
    },
    {
      governed_summary: "Aktuelle technische Richtung: PTFE.",
      technical_direction: [
        { key: "technical_direction_current", label: "Current Direction", value: "PTFE", detail: "Backend narrative", severity: "low" },
      ],
      validity_envelope: [
        { key: "validity_scope", label: "Scope of Validity", value: "1 marker(s)", detail: "specificity_level:family_only", severity: "low" },
      ],
      next_best_inputs: [
        { key: "next_input_focus", label: "Next Best Inputs", value: "1 input(s)", detail: "pressure_bar", severity: "high" },
      ],
      suggested_next_questions: [
        { key: "suggested_question_1", label: "Question 1", value: "Critical input", detail: "Please confirm pressure_bar.", severity: "high" },
      ],
      handover_status: { key: "commercial_handover", label: "Commercial Handover", value: "Guidance only", detail: "Binding ORIENTATION", severity: "high" },
      delta_status: { key: "delta_impact", label: "Delta Impact", value: "Case changed", detail: "Reasons pressure_bar_changed", severity: "medium" },
      failure_analysis: [
        { key: "failure_mode", label: "Failure Analysis", value: "No active hypothesis", detail: "Backend narrative", severity: "low" },
      ],
    },
  );

  assert.equal(model?.technicalDirection[0]?.detail, "Backend narrative");
  assert.equal(model?.validityEnvelope[0]?.detail, "specificity_level:family_only");
  assert.equal(model?.nextBestInputs[0]?.detail, "pressure_bar");
  assert.equal(model?.suggestedNextQuestions[0]?.detail, "Please confirm pressure_bar.");
  assert.equal(model?.failureAnalysis[0]?.detail, "Backend narrative");
  assert.equal(model?.caseSummary.find(item => item.key === "commercial_handover")?.value, "Guidance only");
  assert.equal(model?.caseSummary.find(item => item.key === "what_if_delta")?.value, "Case changed");
});

test("qualification_status happy-path: backend items pass through, FE adds only technical renderers", () => {
  // This test explicitly covers the happy-path branch of mapQualificationStatus():
  // visibleCaseNarrative.qualification_status is non-empty, triggering lines 648–684.
  const model = projectCaseStatePanel(
    {
      active_domain: "material_static_seal_prequalification",
      engineering_signals: {
        // Boundary signal — causes summarizeEngineeringSignalState() to return non-null.
        rwdr_pressure_risk_level: { value: "high", severity: "high", signal_class: "risk_level" },
      },
      qualification_results: {
        // Present in caseState but must NOT drive qualificationStatus items in happy path.
        material_core: { status: "exploratory_candidate_source_only", binding_level: "ORIENTATION" },
      },
      readiness: {
        ready_for_guidance: true,
        ready_for_qualification: false,
        missing_review_inputs: ["available_width_mm"],
      },
      audit_trail: [
        {
          event_type: "qualification_snapshot",
          timestamp: "2026-03-14T12:00:00+00:00",
          source_ref: "case_state.qualification_results",
          details: {},
        },
      ],
    },
    { bindingLevel: "ORIENTATION", hasCaseState: true },
    {
      governed_summary: "Backend summary.",
      // qualification_status is non-empty → triggers happy-path branch.
      qualification_status: [
        { key: "qualification_level", label: "Qualification Level", value: "Backend Level Value", detail: "Source backend_source", severity: "low" },
        { key: "rfq_admissibility", label: "RFQ Admissibility", value: "inadmissible", detail: "Release inadmissible", severity: "high" },
        { key: "hard_stops", label: "Hard Stops", value: "0", detail: "None", severity: "low" },
        { key: "review_cases", label: "Review Cases", value: "0", detail: "None", severity: "low" },
        { key: "missing_critical_summary", label: "Missing Critical Data", value: "0", detail: "None", severity: "low" },
      ],
    },
  );

  assert.ok(model);

  // 1. Backend items pass through with their original values unchanged.
  const qualLevel = model.qualificationStatus.find(i => i.key === "qualification_level");
  assert.equal(qualLevel?.value, "Backend Level Value", "qualification_level must come from backend narrative");
  assert.match(qualLevel?.detail ?? "", /Source backend_source/);

  const rfqItem = model.qualificationStatus.find(i => i.key === "rfq_admissibility");
  assert.equal(rfqItem?.value, "inadmissible", "rfq_admissibility must come from backend narrative");

  // 2. FE technical renderer: engineering_signal_summary is injected from local engineering_signals.
  const signalItem = model.qualificationStatus.find(i => i.key === "engineering_signal_summary");
  assert.ok(signalItem, "engineering_signal_summary must be present — FE technical renderer from local signals");
  assert.match(signalItem?.value ?? "", /boundary signal/i);

  // 3. FE technical renderer: binding_level is injected from runtimeMeta.
  const bindingItem = model.qualificationStatus.find(i => i.key === "binding_level");
  assert.equal(bindingItem?.value, "ORIENTATION", "binding_level must be present as FE transport renderer");

  // 4. FE technical renderer: readiness_status is injected from local readiness.
  const readinessItem = model.qualificationStatus.find(i => i.key === "readiness_status");
  assert.equal(readinessItem?.value, "Pending", "readiness_status must be present as FE renderer");

  // 5. FE technical renderer: latest_audit_item is injected from local audit_trail.
  const auditItem = model.qualificationStatus.find(i => i.key === "latest_audit");
  assert.ok(auditItem, "latest_audit must be present — FE technical renderer from local audit_trail");
  assert.equal(auditItem?.value, "Qualification Snapshot");

  // 6. result_contract must NOT be present in the happy path — no fachnahe FE reconstruction.
  const resultContractItem = model.qualificationStatus.find(i => i.key === "result_contract");
  assert.equal(
    resultContractItem,
    undefined,
    "result_contract item must NOT be reconstructed locally in the happy path (SoT drift prevention)",
  );
});

test("case_summary happy-path: null delta_status and null handover_status are not injected", () => {
  // Contract: mapCaseSummary() null-guards delta_status (L466) and handover_status (L476).
  // When the backend sends null for both, no extra items must appear in caseSummary.
  // Covers: Mixed-Path / Partial-Narrative — delta_status top-level null case.
  const model = projectCaseStatePanel(
    {
      qualification_results: {},
      readiness: {},
      result_contract: {
        binding_level: "ORIENTATION",
        rfq_admissibility: "inadmissible",
        release_status: "inadmissible",
        contract_obsolete: false,
        invalidation_requires_recompute: false,
        invalidation_reasons: [],
      },
    },
    { bindingLevel: "ORIENTATION", hasCaseState: true },
    {
      governed_summary: "Backend summary.",
      case_summary: [
        { key: "resume_readiness", label: "Resume Readiness", value: "Ready", detail: "Turn 1", severity: "low" },
        { key: "current_case_summary", label: "Case Summary", value: "ORIENTATION", detail: "Binding level", severity: "low" },
      ],
      // Explicitly null — null-guards at mapCaseSummary() L466/L476 must prevent injection
      delta_status: null,
      handover_status: null,
      qualification_status: [
        { key: "hard_stops", label: "Hard Stops", value: "0", detail: "None", severity: "low" },
      ],
    },
  );

  assert.ok(model);

  // Exactly the 2 backend-provided items — null delta/handover must NOT inject additional items
  assert.equal(
    model.caseSummary.length,
    2,
    "null delta_status and null handover_status must NOT inject items into caseSummary",
  );
  assert.equal(
    model.caseSummary.find(i => i.key === "what_if_delta"),
    undefined,
    "delta_status: null must not create a what_if_delta item in caseSummary",
  );
  assert.equal(
    model.caseSummary.find(i => i.key === "commercial_handover"),
    undefined,
    "handover_status: null must not create a commercial_handover item in caseSummary",
  );
});
