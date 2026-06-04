import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const RFQ_READINESS_CONTRACT_FIXTURE_PATH = resolve(
  process.cwd(),
  "../contracts/rfq_readiness_projection_v1.fixture.json",
);

vi.mock("@/lib/bff/auth-token", () => ({
  getAccessToken: vi.fn(async () => "test-token"),
  getAccessTokenResult: vi.fn(async () => ({ accessToken: "test-token", cookieUpdates: [] })),
  applyBffCookieUpdates: vi.fn(),
}));

vi.mock("@/lib/bff/backend", () => ({
  buildBackendUrl: vi.fn((path: string) => `https://backend.test${path}`),
}));

function rfqReadinessContractFixture(): Record<string, unknown> {
  return JSON.parse(
    readFileSync(RFQ_READINESS_CONTRACT_FIXTURE_PATH, "utf8"),
  ) as Record<string, unknown>;
}

function durableWorkspaceProjection(rfqReadinessProjection: Record<string, unknown>) {
  return {
    request_type: "new_rfq",
    engineering_path: "rwdr",
    rfq_readiness_projection: rfqReadinessProjection,
    case_summary: {
      thread_id: "durable-case-123",
      turn_count: 2,
      max_turns: 12,
      intent_goal: "new_rfq",
    },
    completeness: {
      coverage_score: 0.3,
      coverage_gaps: ["medium"],
      completeness_depth: "prequalification",
      missing_critical_parameters: ["medium"],
      analysis_complete: false,
      recommendation_ready: false,
    },
    governance_status: {
      release_status: "manufacturer_validation_required",
      scope_of_validity: [],
      assumptions_active: [],
      unknowns_release_blocking: ["medium"],
      unknowns_manufacturer_validation: [],
      gate_failures: [],
      governance_notes: [],
      required_disclaimers: ["Manufacturer review required."],
      verification_passed: false,
    },
    specificity: {
      material_specificity_required: "family_only",
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
      shortlist_ready: false,
      inquiry_ready: false,
      not_ready_reasons: ["rfq_basis_missing"],
      blocking_reasons: ["medium"],
      material_fit_items: [],
      open_manufacturer_questions: [],
      selected_partner_id: null,
      data_source: "durable_workspace_projection",
      manufacturer_fit_matrix: null,
    },
    rfq_status: {
      release_status: "manufacturer_validation_required",
      rfq_confirmed: false,
      rfq_ready: false,
      blockers: ["medium"],
      open_points: ["medium"],
      has_pdf: false,
      has_html_report: false,
      handover_ready: false,
      handover_initiated: false,
    },
    rfq_package: {
      has_draft: false,
      rfq_id: null,
      rfq_basis_status: "missing",
      operating_context_redacted: {},
      manufacturer_questions_mandatory: [],
      conflicts_visible_count: 0,
      buyer_assumptions_acknowledged: [],
    },
    cycle_info: {
      current_assertion_cycle_id: 1,
      state_revision: 3,
      asserted_profile_revision: 2,
      derived_artifacts_stale: false,
      stale_reason: null,
    },
  };
}

function workspaceReloadRequest() {
  return new Request(
    "https://sealai.test/api/bff/workspace/session-should-not-be-case?session_id=session-should-not-be-case&case_id=unrelated-case",
  );
}

function workspaceRouteContext(caseId = "durable-case-123") {
  return { params: Promise.resolve({ caseId }) };
}

describe("BFF workspace reload route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preserves durable rfq_readiness_projection as frontend rfqReadinessProjection", async () => {
    const rfqReadinessProjection = rfqReadinessContractFixture();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json(durableWorkspaceProjection(rfqReadinessProjection)),
    );

    const response = await GET(
      workspaceReloadRequest(),
      workspaceRouteContext("durable-case-123"),
    );
    const body = await response.json();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("https://backend.test/api/agent/workspace/durable-case-123");
    expect(String(url)).not.toContain("session-should-not-be-case");
    expect(String(url)).not.toContain("unrelated-case");
    expect(body.caseId).toBe("durable-case-123");

    expect(body.rfqReadinessProjection).toEqual(
      expect.objectContaining({
        manufacturer_review_ready: rfqReadinessProjection.manufacturer_review_ready,
        rfq_basis_ready: rfqReadinessProjection.rfq_basis_ready,
        known_missing_fields: rfqReadinessProjection.known_missing_fields,
        open_points: rfqReadinessProjection.open_points,
        blocking_reasons: rfqReadinessProjection.blocking_reasons,
        dispatch_allowed: false,
        external_contact_allowed: false,
        final_approval_claim_allowed: false,
        preview_action_available: rfqReadinessProjection.preview_action_available,
        preview_action_name: rfqReadinessProjection.preview_action_name,
        preview_endpoint: rfqReadinessProjection.preview_endpoint,
        preview_creation_requires_explicit_user_intent:
          rfqReadinessProjection.preview_creation_requires_explicit_user_intent,
        preview_export_requires_consent: rfqReadinessProjection.preview_export_requires_consent,
        preview_requires_explicit_endpoint:
          rfqReadinessProjection.preview_requires_explicit_endpoint,
        preview_service_boundary: rfqReadinessProjection.preview_service_boundary,
        projection_version: rfqReadinessProjection.projection_version,
      }),
    );
    expect(body.rfqReadinessProjection.pending_question).toEqual(
      expect.objectContaining({
        question_text: "Welches Medium soll abgedichtet werden?",
        target_field: "medium",
      }),
    );
  });
});
