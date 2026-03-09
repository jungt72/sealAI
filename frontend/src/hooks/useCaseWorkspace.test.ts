import test from "node:test";
import assert from "node:assert/strict";

// Unit tests for the workspace API types and CaseStatusPanel rendering logic.
// These are pure data-shape tests since we cannot run React hooks outside a
// component tree without jsdom / react-testing-library (not in deps).

import type { CaseWorkspaceProjection } from "../lib/workspaceApi.js";

// -- Helper: minimal valid projection (matches backend default) --
function minimalProjection(): CaseWorkspaceProjection {
  return {
    case_summary: {
      thread_id: null, user_id: null, phase: null, intent_goal: null,
      application_category: null, seal_family: null, motion_type: null,
      user_persona: null, turn_count: 0, max_turns: 12,
    },
    completeness: {
      coverage_score: 0, coverage_gaps: [], completeness_depth: "precheck",
      missing_critical_parameters: [], discovery_missing: [],
      analysis_complete: false, recommendation_ready: false,
    },
    governance_status: {
      release_status: "inadmissible", scope_of_validity: [], assumptions_active: [],
      unknowns_release_blocking: [], unknowns_manufacturer_validation: [],
      gate_failures: [], governance_notes: [], required_disclaimers: [],
      verification_passed: true,
    },
    specificity: { material_specificity_required: "family_only", completeness_depth: "precheck" },
    candidate_clusters: {
      plausibly_viable: [], manufacturer_validation_required: [],
      inadmissible_or_excluded: [], total_candidates: 0,
    },
    conflicts: { total: 0, open: 0, resolved: 0, by_severity: {}, items: [] },
    claims_summary: { total: 0, by_type: {}, by_origin: {}, items: [] },
    manufacturer_questions: { mandatory: [], open_questions: [], total_open: 0 },
    rfq_status: {
      admissibility_status: "inadmissible", release_status: "inadmissible",
      rfq_confirmed: false, rfq_ready: false, blockers: [], open_points: [],
      has_pdf: false, has_html_report: false,
    },
    artifact_status: {
      has_answer_contract: false, contract_id: null, contract_obsolete: false,
      has_verification_report: false, has_sealing_requirement_spec: false,
      has_rfq_draft: false, has_recommendation: false,
      has_live_calc_tile: false, live_calc_status: "insufficient_data",
    },
    rfq_package: {
      has_draft: false, rfq_id: null, rfq_basis_status: "inadmissible",
      operating_context_redacted: {}, manufacturer_questions_mandatory: [],
      conflicts_visible_count: 0, buyer_assumptions_acknowledged: [],
    },
    partner_matching: {
      matching_ready: false, not_ready_reasons: [],
      material_fit_items: [], open_manufacturer_questions: [],
      data_source: "candidate_derived",
    },
    cycle_info: {
      current_assertion_cycle_id: 0, state_revision: 0,
      asserted_profile_revision: 0, derived_artifacts_stale: false, stale_reason: null,
    },
  };
}

function richProjection(): CaseWorkspaceProjection {
  const proj = minimalProjection();
  proj.case_summary.thread_id = "t-abc-123";
  proj.case_summary.turn_count = 4;
  proj.governance_status.release_status = "precheck_only";
  proj.governance_status.assumptions_active = ["standard_surface_finish"];
  proj.governance_status.required_disclaimers = ["Precheck only"];
  proj.completeness.coverage_score = 0.65;
  proj.completeness.missing_critical_parameters = ["speed_rpm"];
  proj.completeness.completeness_depth = "prequalification";
  proj.candidate_clusters.plausibly_viable = [
    { kind: "material", value: "FKM", specificity: "family_only" },
  ];
  proj.candidate_clusters.manufacturer_validation_required = [
    { kind: "material", value: "HNBR", specificity: "compound_required" },
  ];
  proj.candidate_clusters.inadmissible_or_excluded = [
    { kind: "material", value: "NBR", excluded_by_gate: "chemical_resistance" },
  ];
  proj.candidate_clusters.total_candidates = 3;
  proj.conflicts.total = 2;
  proj.conflicts.open = 1;
  proj.conflicts.resolved = 1;
  proj.conflicts.by_severity = { HARD: 1, SOFT: 1 };
  proj.conflicts.items = [
    { conflict_type: "PARAMETER_CONFLICT", severity: "HARD", summary: "Pressure exceeds FKM limit", resolution_status: "OPEN" },
    { conflict_type: "SCOPE_CONFLICT", severity: "SOFT", summary: "Temperature range approximate", resolution_status: "RESOLVED" },
  ];
  proj.claims_summary.total = 3;
  proj.claims_summary.by_type = { evidence_based_assertion: 1, deterministic_fact: 2 };
  proj.claims_summary.by_origin = { evidence: 1, deterministic: 2 };
  proj.claims_summary.items = [
    { value: "FKM OK", claim_type: "evidence_based_assertion", claim_origin: "evidence" },
    { value: "HLP compat", claim_type: "deterministic_fact", claim_origin: "deterministic" },
    { value: "NBR excluded", claim_type: "deterministic_fact", claim_origin: "deterministic" },
  ];
  proj.manufacturer_questions.mandatory = ["Compound-Freigabe?"];
  proj.manufacturer_questions.total_open = 1;
  proj.rfq_status.admissibility_status = "provisional";
  proj.rfq_status.blockers = ["speed_rpm missing"];
  proj.artifact_status.has_answer_contract = true;
  proj.artifact_status.contract_id = "contract-c2-r3";
  proj.cycle_info.current_assertion_cycle_id = 2;
  proj.cycle_info.asserted_profile_revision = 3;
  return proj;
}

// ---------------------------------------------------------------------------
// A2 regression: Type shape matches backend contract
// ---------------------------------------------------------------------------

test("minimal projection has all required top-level sections", () => {
  const proj = minimalProjection();
  const expected = [
    "case_summary", "completeness", "governance_status", "specificity",
    "candidate_clusters", "conflicts", "claims_summary",
    "manufacturer_questions", "rfq_status", "artifact_status", "rfq_package",
    "partner_matching", "cycle_info",
  ];
  for (const k of expected) {
    assert.ok(k in proj, `Missing key: ${k}`);
  }
});

test("governance release_status is accessible from projection", () => {
  const proj = richProjection();
  assert.equal(proj.governance_status.release_status, "precheck_only");
  assert.deepStrictEqual(proj.governance_status.assumptions_active, ["standard_surface_finish"]);
});

test("accessing nested fields on minimal projection does not throw", () => {
  const proj = minimalProjection();
  assert.equal(proj.completeness.coverage_score, 0);
  assert.equal(proj.conflicts.total, 0);
  assert.equal(proj.candidate_clusters.total_candidates, 0);
  assert.equal(proj.claims_summary.items.length, 0);
  assert.equal(proj.cycle_info.derived_artifacts_stale, false);
});

// ---------------------------------------------------------------------------
// A3: Candidate detail data is accessible
// ---------------------------------------------------------------------------

test("candidate items carry kind, value, specificity for viable cluster", () => {
  const proj = richProjection();
  const viable = proj.candidate_clusters.plausibly_viable;
  assert.equal(viable.length, 1);
  assert.equal(viable[0].kind, "material");
  assert.equal(viable[0].value, "FKM");
  assert.equal(viable[0].specificity, "family_only");
});

test("candidate items carry excluded_by_gate for excluded cluster", () => {
  const proj = richProjection();
  const excl = proj.candidate_clusters.inadmissible_or_excluded;
  assert.equal(excl.length, 1);
  assert.equal(excl[0].value, "NBR");
  assert.equal(excl[0].excluded_by_gate, "chemical_resistance");
});

test("mfr validation candidates carry specificity", () => {
  const proj = richProjection();
  const mfr = proj.candidate_clusters.manufacturer_validation_required;
  assert.equal(mfr[0].specificity, "compound_required");
});

test("candidate total matches sum of all clusters", () => {
  const proj = richProjection();
  const computed =
    proj.candidate_clusters.plausibly_viable.length +
    proj.candidate_clusters.manufacturer_validation_required.length +
    proj.candidate_clusters.inadmissible_or_excluded.length;
  assert.equal(proj.candidate_clusters.total_candidates, computed);
});

// ---------------------------------------------------------------------------
// A3: Conflict detail data is accessible
// ---------------------------------------------------------------------------

test("conflict items carry severity, type, summary, resolution_status", () => {
  const proj = richProjection();
  assert.equal(proj.conflicts.items.length, 2);
  const open = proj.conflicts.items.find(c => c.resolution_status === "OPEN");
  assert.ok(open);
  assert.equal(open.severity, "HARD");
  assert.equal(open.conflict_type, "PARAMETER_CONFLICT");
  assert.ok(open.summary.length > 0);
});

test("conflict items sort: open before resolved", () => {
  const proj = richProjection();
  const sorted = [...proj.conflicts.items].sort(
    (a, b) => (a.resolution_status === "OPEN" ? 0 : 1) - (b.resolution_status === "OPEN" ? 0 : 1),
  );
  assert.equal(sorted[0].resolution_status, "OPEN");
  assert.equal(sorted[1].resolution_status, "RESOLVED");
});

test("severity breakdown matches items", () => {
  const proj = richProjection();
  assert.equal(proj.conflicts.by_severity.HARD, 1);
  assert.equal(proj.conflicts.by_severity.SOFT, 1);
});

// ---------------------------------------------------------------------------
// A3: Claim detail data is accessible
// ---------------------------------------------------------------------------

test("claim items carry value, claim_type, claim_origin", () => {
  const proj = richProjection();
  assert.equal(proj.claims_summary.items.length, 3);
  const det = proj.claims_summary.items.filter(c => c.claim_origin === "deterministic");
  assert.equal(det.length, 2);
  const ev = proj.claims_summary.items.filter(c => c.claim_origin === "evidence");
  assert.equal(ev.length, 1);
});

test("claims distinguish deterministic vs evidence vs heuristic origins", () => {
  const proj = minimalProjection();
  proj.claims_summary.items = [
    { value: "A", claim_type: "deterministic_fact", claim_origin: "deterministic" },
    { value: "B", claim_type: "evidence_based_assertion", claim_origin: "evidence" },
    { value: "C", claim_type: "heuristic_hint", claim_origin: "heuristic" },
  ];
  const origins = proj.claims_summary.items.map(c => c.claim_origin);
  assert.ok(origins.includes("deterministic"));
  assert.ok(origins.includes("evidence"));
  assert.ok(origins.includes("heuristic"));
});

test("claims by_type count matches items", () => {
  const proj = richProjection();
  const totalFromType = Object.values(proj.claims_summary.by_type).reduce((a, b) => a + b, 0);
  assert.equal(totalFromType, proj.claims_summary.total);
});

// ---------------------------------------------------------------------------
// A3: Empty/partial data robustness
// ---------------------------------------------------------------------------

test("empty candidate clusters do not produce items", () => {
  const proj = minimalProjection();
  assert.equal(proj.candidate_clusters.plausibly_viable.length, 0);
  assert.equal(proj.candidate_clusters.total_candidates, 0);
});

test("empty conflicts produce no items", () => {
  const proj = minimalProjection();
  assert.equal(proj.conflicts.items.length, 0);
  assert.equal(proj.conflicts.total, 0);
});

test("empty claims produce no items", () => {
  const proj = minimalProjection();
  assert.equal(proj.claims_summary.items.length, 0);
  assert.equal(proj.claims_summary.total, 0);
});

test("staleness and cycle info remain correct", () => {
  const proj = richProjection();
  assert.equal(proj.cycle_info.current_assertion_cycle_id, 2);
  assert.equal(proj.cycle_info.asserted_profile_revision, 3);
});

// ---------------------------------------------------------------------------
// B1: RFQ Package Surface
// ---------------------------------------------------------------------------

test("rfq_package defaults are safe for no-draft state", () => {
  const proj = minimalProjection();
  assert.equal(proj.rfq_package.has_draft, false);
  assert.equal(proj.rfq_package.rfq_id, null);
  assert.equal(proj.rfq_package.rfq_basis_status, "inadmissible");
  assert.deepStrictEqual(proj.rfq_package.operating_context_redacted, {});
  assert.equal(proj.rfq_package.manufacturer_questions_mandatory.length, 0);
  assert.equal(proj.rfq_package.conflicts_visible_count, 0);
  assert.equal(proj.rfq_package.buyer_assumptions_acknowledged.length, 0);
});

test("rfq_package exposes redacted operating context", () => {
  const proj = minimalProjection();
  proj.rfq_package = {
    has_draft: true,
    rfq_id: "rfq-c3-r5",
    rfq_basis_status: "manufacturer_validation_required",
    operating_context_redacted: {
      medium: "HLP 46",
      pressure_bar: 250.0,
      temperature_C: 80.0,
    },
    manufacturer_questions_mandatory: ["Compound release?"],
    conflicts_visible_count: 1,
    buyer_assumptions_acknowledged: ["Standard surface finish"],
  };
  assert.equal(proj.rfq_package.has_draft, true);
  assert.equal(proj.rfq_package.operating_context_redacted.medium, "HLP 46");
  assert.equal(proj.rfq_package.operating_context_redacted.pressure_bar, 250.0);
  assert.equal(Object.keys(proj.rfq_package.operating_context_redacted).length, 3);
});

test("rfq_package mandatory questions are accessible", () => {
  const proj = minimalProjection();
  proj.rfq_package.manufacturer_questions_mandatory = ["Q1", "Q2"];
  assert.equal(proj.rfq_package.manufacturer_questions_mandatory.length, 2);
  assert.equal(proj.rfq_package.manufacturer_questions_mandatory[0], "Q1");
});

test("rfq_package buyer assumptions are accessible", () => {
  const proj = minimalProjection();
  proj.rfq_package.buyer_assumptions_acknowledged = ["Assumption A", "Assumption B"];
  assert.equal(proj.rfq_package.buyer_assumptions_acknowledged.length, 2);
});

test("rfq_package basis status reflects governance level", () => {
  for (const status of ["inadmissible", "precheck_only", "manufacturer_validation_required", "rfq_ready"]) {
    const proj = minimalProjection();
    proj.rfq_package.rfq_basis_status = status;
    assert.equal(proj.rfq_package.rfq_basis_status, status);
  }
});

// ---------------------------------------------------------------------------
// B2: RFQ Confirmation Flow — CTA state logic
// ---------------------------------------------------------------------------

function confirmableProjection(): CaseWorkspaceProjection {
  const proj = minimalProjection();
  proj.rfq_package.has_draft = true;
  proj.rfq_package.rfq_basis_status = "precheck_only";
  proj.rfq_status.release_status = "precheck_only";
  proj.rfq_status.rfq_confirmed = false;
  proj.cycle_info.derived_artifacts_stale = false;
  return proj;
}

test("confirm CTA: enabled when draft exists, not inadmissible, not stale, not confirmed", () => {
  const proj = confirmableProjection();
  const canConfirm = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && !proj.rfq_status.rfq_confirmed;
  assert.equal(canConfirm, true);
});

test("confirm CTA: disabled when inadmissible", () => {
  const proj = confirmableProjection();
  proj.rfq_status.release_status = "inadmissible";
  const canConfirm = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && !proj.rfq_status.rfq_confirmed;
  assert.equal(canConfirm, false);
});

test("confirm CTA: disabled when stale", () => {
  const proj = confirmableProjection();
  proj.cycle_info.derived_artifacts_stale = true;
  const canConfirm = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && !proj.rfq_status.rfq_confirmed;
  assert.equal(canConfirm, false);
});

test("confirm CTA: disabled when no draft", () => {
  const proj = confirmableProjection();
  proj.rfq_package.has_draft = false;
  const canConfirm = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && !proj.rfq_status.rfq_confirmed;
  assert.equal(canConfirm, false);
});

test("confirm CTA: disabled when already confirmed", () => {
  const proj = confirmableProjection();
  proj.rfq_status.rfq_confirmed = true;
  const canConfirm = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && !proj.rfq_status.rfq_confirmed;
  assert.equal(canConfirm, false);
});

test("confirmed state is reflected in projection after confirmation", () => {
  const proj = confirmableProjection();
  // Simulate post-confirm state
  proj.rfq_status.rfq_confirmed = true;
  assert.equal(proj.rfq_status.rfq_confirmed, true);
  // Draft should still be present
  assert.equal(proj.rfq_package.has_draft, true);
});

test("confirm CTA: rfq_ready status allows confirmation", () => {
  const proj = confirmableProjection();
  proj.rfq_status.release_status = "rfq_ready";
  const canConfirm = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && !proj.rfq_status.rfq_confirmed;
  assert.equal(canConfirm, true);
});

// ---------------------------------------------------------------------------
// B4: Partner Matching Surface
// ---------------------------------------------------------------------------

test("partner_matching defaults are safe for minimal state", () => {
  const proj = minimalProjection();
  assert.equal(proj.partner_matching.matching_ready, false);
  assert.equal(proj.partner_matching.material_fit_items.length, 0);
  assert.equal(proj.partner_matching.open_manufacturer_questions.length, 0);
  assert.equal(proj.partner_matching.data_source, "candidate_derived");
});

test("partner_matching: not ready when not confirmed", () => {
  const proj = minimalProjection();
  proj.partner_matching.not_ready_reasons = ["RFQ package not yet confirmed."];
  assert.equal(proj.partner_matching.matching_ready, false);
  assert.ok(proj.partner_matching.not_ready_reasons.length > 0);
});

test("partner_matching: material fit items carry material/cluster/specificity", () => {
  const proj = minimalProjection();
  proj.partner_matching = {
    matching_ready: true,
    not_ready_reasons: [],
    material_fit_items: [
      { material: "FKM", cluster: "viable", specificity: "family_only", requires_validation: false, fit_basis: "FKM viable at family_only level" },
      { material: "HNBR", cluster: "manufacturer_validation", specificity: "compound_required", requires_validation: true, fit_basis: "HNBR requires manufacturer validation" },
    ],
    open_manufacturer_questions: ["Compound release?"],
    data_source: "candidate_derived",
  };
  assert.equal(proj.partner_matching.material_fit_items.length, 2);
  assert.equal(proj.partner_matching.material_fit_items[0].material, "FKM");
  assert.equal(proj.partner_matching.material_fit_items[0].requires_validation, false);
  assert.equal(proj.partner_matching.material_fit_items[1].requires_validation, true);
  assert.equal(proj.partner_matching.material_fit_items[1].cluster, "manufacturer_validation");
});

test("partner_matching: open questions are accessible", () => {
  const proj = minimalProjection();
  proj.partner_matching.open_manufacturer_questions = ["Q1", "Q2"];
  assert.equal(proj.partner_matching.open_manufacturer_questions.length, 2);
});

test("partner_matching: ready state with items and no blockers", () => {
  const proj = minimalProjection();
  proj.partner_matching.matching_ready = true;
  proj.partner_matching.material_fit_items = [
    { material: "FKM", cluster: "viable", specificity: "family_only", requires_validation: false, fit_basis: "test" },
  ];
  assert.equal(proj.partner_matching.matching_ready, true);
  assert.equal(proj.partner_matching.not_ready_reasons.length, 0);
  assert.equal(proj.partner_matching.material_fit_items.length, 1);
});

// ---------------------------------------------------------------------------
// B3: RFQ PDF Generation Trigger
// ---------------------------------------------------------------------------

function pdfReadyProjection(): CaseWorkspaceProjection {
  const proj = confirmableProjection();
  proj.rfq_status.rfq_confirmed = true;
  return proj;
}

test("PDF CTA: enabled when confirmed, draft exists, not inadmissible, not stale", () => {
  const proj = pdfReadyProjection();
  const canGenerate = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && proj.rfq_status.rfq_confirmed
    && !proj.rfq_status.has_html_report;
  assert.equal(canGenerate, true);
});

test("PDF CTA: disabled when not confirmed", () => {
  const proj = pdfReadyProjection();
  proj.rfq_status.rfq_confirmed = false;
  const canGenerate = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && proj.rfq_status.rfq_confirmed;
  assert.equal(canGenerate, false);
});

test("PDF CTA: disabled when inadmissible", () => {
  const proj = pdfReadyProjection();
  proj.rfq_status.release_status = "inadmissible";
  const canGenerate = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && proj.rfq_status.rfq_confirmed;
  assert.equal(canGenerate, false);
});

test("PDF CTA: disabled when stale", () => {
  const proj = pdfReadyProjection();
  proj.cycle_info.derived_artifacts_stale = true;
  const canGenerate = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && proj.rfq_status.rfq_confirmed;
  assert.equal(canGenerate, false);
});

test("PDF CTA: disabled when no draft", () => {
  const proj = pdfReadyProjection();
  proj.rfq_package.has_draft = false;
  const canGenerate = proj.rfq_package.has_draft
    && proj.rfq_status.release_status !== "inadmissible"
    && !proj.cycle_info.derived_artifacts_stale
    && proj.rfq_status.rfq_confirmed;
  assert.equal(canGenerate, false);
});

test("PDF CTA: shows generated state when has_html_report is true", () => {
  const proj = pdfReadyProjection();
  proj.rfq_status.has_html_report = true;
  assert.equal(proj.rfq_status.has_html_report, true);
  assert.equal(proj.rfq_status.rfq_confirmed, true);
});

test("PDF CTA: has_pdf and has_html_report default to false", () => {
  const proj = minimalProjection();
  assert.equal(proj.rfq_status.has_pdf, false);
  assert.equal(proj.rfq_status.has_html_report, false);
});

// ---------------------------------------------------------------------------
// A4: Case Lifecycle Surface — step derivation logic
// ---------------------------------------------------------------------------

// Import the derivation function for testing (pure TS, no JSX)
import { deriveLifecycleSteps, type LifecycleStep } from "../lib/lifecycleSteps.ts";

test("lifecycle: minimal state produces 7 steps, all pending except case started", () => {
  const proj = minimalProjection();
  const steps = deriveLifecycleSteps(proj);
  assert.equal(steps.length, 7);
  // Case started is pending (no thread_id, turn_count=0)
  assert.equal(steps[0].label, "Case Started");
  assert.equal(steps[0].status, "pending");
  // All others pending
  for (let i = 1; i < steps.length; i++) {
    assert.equal(steps[i].status, "pending", `Step ${steps[i].label} should be pending`);
  }
});

test("lifecycle: case with thread_id shows case started as done", () => {
  const proj = minimalProjection();
  proj.case_summary.thread_id = "t-123";
  proj.case_summary.turn_count = 3;
  const steps = deriveLifecycleSteps(proj);
  assert.equal(steps[0].status, "done");
  assert.ok(steps[0].detail?.includes("3/12"));
});

test("lifecycle: contract generated shows done when present and not obsolete", () => {
  const proj = minimalProjection();
  proj.artifact_status.has_answer_contract = true;
  proj.artifact_status.contract_id = "c-1";
  proj.artifact_status.contract_obsolete = false;
  const steps = deriveLifecycleSteps(proj);
  const contractStep = steps.find(s => s.label === "Contract Generated");
  assert.ok(contractStep);
  assert.equal(contractStep.status, "done");
  assert.equal(contractStep.detail, "c-1");
});

test("lifecycle: obsolete contract shows active with detail", () => {
  const proj = minimalProjection();
  proj.artifact_status.has_answer_contract = true;
  proj.artifact_status.contract_obsolete = true;
  const steps = deriveLifecycleSteps(proj);
  const contractStep = steps.find(s => s.label === "Contract Generated");
  assert.ok(contractStep);
  assert.equal(contractStep.status, "active");
  assert.ok(contractStep.detail?.includes("Obsolete"));
});

test("lifecycle: rfq confirmed shows done", () => {
  const proj = minimalProjection();
  proj.artifact_status.has_rfq_draft = true;
  proj.rfq_status.rfq_confirmed = true;
  const steps = deriveLifecycleSteps(proj);
  const confirmStep = steps.find(s => s.label === "RFQ Confirmed");
  assert.ok(confirmStep);
  assert.equal(confirmStep.status, "done");
});

test("lifecycle: rfq draft present but not confirmed shows active", () => {
  const proj = minimalProjection();
  proj.artifact_status.has_rfq_draft = true;
  proj.rfq_status.rfq_confirmed = false;
  const steps = deriveLifecycleSteps(proj);
  const confirmStep = steps.find(s => s.label === "RFQ Confirmed");
  assert.ok(confirmStep);
  assert.equal(confirmStep.status, "active");
});

test("lifecycle: document generated shows done when has_html_report", () => {
  const proj = minimalProjection();
  proj.rfq_status.rfq_confirmed = true;
  proj.rfq_status.has_html_report = true;
  const steps = deriveLifecycleSteps(proj);
  const docStep = steps.find(s => s.label === "Document Generated");
  assert.ok(docStep);
  assert.equal(docStep.status, "done");
});

test("lifecycle: full progression shows correct step sequence", () => {
  const proj = minimalProjection();
  proj.case_summary.thread_id = "t-123";
  proj.case_summary.turn_count = 8;
  proj.artifact_status.has_answer_contract = true;
  proj.artifact_status.contract_id = "c-2";
  proj.artifact_status.has_verification_report = true;
  proj.governance_status.verification_passed = true;
  proj.artifact_status.has_rfq_draft = true;
  proj.governance_status.release_status = "precheck_only";
  proj.rfq_status.rfq_confirmed = true;
  proj.rfq_status.has_html_report = true;
  proj.partner_matching.matching_ready = true;
  proj.partner_matching.material_fit_items = [
    { material: "FKM", cluster: "viable", specificity: "family_only", requires_validation: false, fit_basis: "" },
  ];
  const steps = deriveLifecycleSteps(proj);
  // All steps should be done
  for (const step of steps) {
    assert.equal(step.status, "done", `Step ${step.label} should be done`);
  }
});

test("lifecycle: stale state is available from cycle_info", () => {
  const proj = minimalProjection();
  proj.cycle_info.derived_artifacts_stale = true;
  proj.cycle_info.stale_reason = "parameter_changed";
  assert.equal(proj.cycle_info.derived_artifacts_stale, true);
  assert.equal(proj.cycle_info.stale_reason, "parameter_changed");
});

test("lifecycle: cycle and revision numbers are accessible", () => {
  const proj = minimalProjection();
  proj.cycle_info.current_assertion_cycle_id = 3;
  proj.cycle_info.state_revision = 12;
  proj.cycle_info.asserted_profile_revision = 5;
  assert.equal(proj.cycle_info.current_assertion_cycle_id, 3);
  assert.equal(proj.cycle_info.state_revision, 12);
  assert.equal(proj.cycle_info.asserted_profile_revision, 5);
});

test("lifecycle: partial data does not crash step derivation", () => {
  const proj = minimalProjection();
  // Set some fields, leave others at defaults
  proj.artifact_status.has_rfq_draft = true;
  proj.rfq_status.rfq_confirmed = false;
  const steps = deriveLifecycleSteps(proj);
  assert.equal(steps.length, 7);
  // No throws, no undefined
  for (const step of steps) {
    assert.ok(["done", "active", "pending"].includes(step.status));
    assert.ok(step.label.length > 0);
  }
});
