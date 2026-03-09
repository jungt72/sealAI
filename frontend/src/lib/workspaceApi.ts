// frontend/src/lib/workspaceApi.ts
// API helper for the Case Workspace Projection endpoint.

export interface CaseSummary {
  thread_id: string | null;
  user_id: string | null;
  phase: string | null;
  intent_goal: string | null;
  application_category: string | null;
  seal_family: string | null;
  motion_type: string | null;
  user_persona: string | null;
  turn_count: number;
  max_turns: number;
}

export interface CompletenessStatus {
  coverage_score: number;
  coverage_gaps: string[];
  completeness_depth: string;
  missing_critical_parameters: string[];
  discovery_missing: string[];
  analysis_complete: boolean;
  recommendation_ready: boolean;
}

export interface GovernanceStatus {
  release_status: string;
  scope_of_validity: string[];
  assumptions_active: string[];
  unknowns_release_blocking: string[];
  unknowns_manufacturer_validation: string[];
  gate_failures: string[];
  governance_notes: string[];
  required_disclaimers: string[];
  verification_passed: boolean;
}

export interface ElevationHint {
  label: string;
  field_key: string | null;
  reason: string;
  priority: number;
  action_type: string;
}

export interface SpecificityInfo {
  material_specificity_required: string;
  completeness_depth: string;
  elevation_possible: boolean;
  elevation_hints: ElevationHint[];
  elevation_target: string | null;
}

export interface CandidateClusterSummary {
  plausibly_viable: Record<string, unknown>[];
  manufacturer_validation_required: Record<string, unknown>[];
  inadmissible_or_excluded: Record<string, unknown>[];
  total_candidates: number;
}

export interface ConflictSummaryItem {
  conflict_type: string;
  severity: string;
  summary: string;
  resolution_status: string;
}

export interface ConflictSummary {
  total: number;
  open: number;
  resolved: number;
  by_severity: Record<string, number>;
  items: ConflictSummaryItem[];
}

export interface ClaimItem {
  value: string | null;
  claim_type: string;
  claim_origin: string;
}

export interface ClaimsSummary {
  total: number;
  by_type: Record<string, number>;
  by_origin: Record<string, number>;
  items: ClaimItem[];
}

export interface ManufacturerQuestionItem {
  id: string;
  question: string;
  reason: string;
  priority: string;
  category: string;
}

export interface ManufacturerQuestions {
  mandatory: string[];
  open_questions: ManufacturerQuestionItem[];
  total_open: number;
}

export interface RFQStatus {
  admissibility_status: string;
  release_status: string;
  rfq_confirmed: boolean;
  rfq_ready: boolean;
  handover_ready: boolean;
  handover_initiated: boolean;
  blockers: string[];
  open_points: string[];
  has_pdf: boolean;
  has_html_report: boolean;
}

export interface ArtifactStatus {
  has_answer_contract: boolean;
  contract_id: string | null;
  contract_obsolete: boolean;
  has_verification_report: boolean;
  has_sealing_requirement_spec: boolean;
  has_rfq_draft: boolean;
  has_recommendation: boolean;
  has_live_calc_tile: boolean;
  live_calc_status: string;
}

export interface RFQPackageSummary {
  has_draft: boolean;
  rfq_id: string | null;
  rfq_basis_status: string;
  operating_context_redacted: Record<string, unknown>;
  manufacturer_questions_mandatory: string[];
  conflicts_visible_count: number;
  buyer_assumptions_acknowledged: string[];
}

export interface FactVariant {
  value: string;
  source: string;
  source_rank: number;
}

export interface GroundedFact {
  name: string;
  value: string;
  unit: string | null;
  source: string;
  source_rank: number;
  grounding_basis: string;
  is_divergent: boolean;
  variants: FactVariant[];
}

export interface MaterialFitItem {
  material: string;
  cluster: string;
  specificity: string;
  requires_validation: boolean;
  fit_basis: string;
  grounded_facts: GroundedFact[];
}

export interface PartnerMatchingSummary {
  matching_ready: boolean;
  not_ready_reasons: string[];
  material_fit_items: MaterialFitItem[];
  open_manufacturer_questions: string[];
  selected_partner_id: string | null;
  data_source: string;
}

export interface CycleInfo {
  current_assertion_cycle_id: number;
  state_revision: number;
  asserted_profile_revision: number;
  derived_artifacts_stale: boolean;
  stale_reason: string | null;
}

export interface CaseWorkspaceProjection {
  case_summary: CaseSummary;
  completeness: CompletenessStatus;
  governance_status: GovernanceStatus;
  specificity: SpecificityInfo;
  candidate_clusters: CandidateClusterSummary;
  conflicts: ConflictSummary;
  claims_summary: ClaimsSummary;
  manufacturer_questions: ManufacturerQuestions;
  rfq_status: RFQStatus;
  artifact_status: ArtifactStatus;
  rfq_package: RFQPackageSummary;
  partner_matching: PartnerMatchingSummary;
  cycle_info: CycleInfo;
}

function resolveApiUrl(path: string): string {
  const apiBase = (process.env.NEXT_PUBLIC_API_BASE || "").trim();
  if (!apiBase || apiBase.startsWith("http://backend")) {
    return path;
  }
  return `${apiBase}${path}`;
}

async function parseErrorCode(
  res: Response,
  fallback: string,
): Promise<string> {
  const body = await res.json().catch(() => ({}));
  return body?.detail?.code || fallback;
}

async function requestWorkspace(
  url: string,
  token: string,
  init?: RequestInit,
): Promise<CaseWorkspaceProjection> {
  const res = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });

  if (!res.ok) {
    const method = (init?.method || "GET").toLowerCase();
    const fallback = `workspace_${method}_failed:${res.status}`;
    throw new Error(await parseErrorCode(res, fallback));
  }

  return (await res.json()) as CaseWorkspaceProjection;
}

export async function fetchCaseWorkspace(
  token: string,
  threadId: string,
): Promise<CaseWorkspaceProjection> {
  const url = resolveApiUrl(
    `/api/v1/langgraph/state/workspace?thread_id=${encodeURIComponent(threadId)}`,
  );
  return requestWorkspace(url, token);
}

export async function confirmRfqPackage(
  token: string,
  threadId: string,
): Promise<CaseWorkspaceProjection> {
  const url = resolveApiUrl(
    `/api/v1/langgraph/state/workspace/rfq-confirm?thread_id=${encodeURIComponent(threadId)}`,
  );
  return requestWorkspace(url, token, { method: "POST" });
}

export async function generateRfqPdf(
  token: string,
  threadId: string,
): Promise<CaseWorkspaceProjection> {
  const url = resolveApiUrl(
    `/api/v1/langgraph/state/workspace/rfq-generate-pdf?thread_id=${encodeURIComponent(threadId)}`,
  );
  return requestWorkspace(url, token, { method: "POST" });
}

export async function selectPartner(
  token: string,
  threadId: string,
  partnerId: string,
): Promise<CaseWorkspaceProjection> {
  const url = resolveApiUrl(
    `/api/v1/langgraph/state/workspace/partner-select?thread_id=${encodeURIComponent(threadId)}&partner_id=${encodeURIComponent(partnerId)}`,
  );
  return requestWorkspace(url, token, { method: "POST" });
}

export async function initiateRfqHandover(
  token: string,
  threadId: string,
): Promise<CaseWorkspaceProjection> {
  const url = resolveApiUrl(
    `/api/v1/langgraph/state/workspace/rfq-handover?thread_id=${encodeURIComponent(threadId)}`,
  );
  return requestWorkspace(url, token, { method: "POST" });
}

export function rfqDocumentUrl(threadId: string): string {
  return resolveApiUrl(
    `/api/v1/langgraph/state/workspace/rfq-document?thread_id=${encodeURIComponent(threadId)}`,
  );
}
