import type {
  WorkspaceRfqPendingQuestion,
  WorkspaceRfqReadinessProjection,
} from "../contracts/workspace.ts";

function asStrings(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item || "").trim()).filter(Boolean);
}

function asStringOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asOptionalBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function asPendingQuestion(value: unknown): WorkspaceRfqPendingQuestion | null {
  const direct = asStringOrNull(value);
  if (direct) {
    return { question_text: direct };
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const raw = value as Record<string, unknown>;
  const questionText =
    asStringOrNull(raw.question_text) ||
    asStringOrNull(raw.question) ||
    asStringOrNull(raw.text);
  if (!questionText) {
    return null;
  }
  return {
    question_text: questionText,
    target_field: asStringOrNull(raw.target_field),
    label: asStringOrNull(raw.label),
    reason: asStringOrNull(raw.reason),
    required_for_rfq: asOptionalBoolean(raw.required_for_rfq),
    expected_answer_type: asStringOrNull(raw.expected_answer_type),
    source: asStringOrNull(raw.source),
    status: asStringOrNull(raw.status),
  };
}

export function mapRfqReadinessProjection(value: unknown): WorkspaceRfqReadinessProjection | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const raw = value as Record<string, unknown>;
  return {
    manufacturer_review_ready: Boolean(raw.manufacturer_review_ready),
    rfq_basis_ready: Boolean(raw.rfq_basis_ready),
    known_missing_fields: asStrings(raw.known_missing_fields),
    open_points: asStrings(raw.open_points),
    blocking_reasons: asStrings(raw.blocking_reasons),
    pending_question: asPendingQuestion(raw.pending_question),
    consent_required: raw.consent_required !== false,
    dispatch_allowed: Boolean(raw.dispatch_allowed),
    external_contact_allowed: Boolean(raw.external_contact_allowed),
    final_approval_claim_allowed: Boolean(raw.final_approval_claim_allowed),
    preview_available: Boolean(raw.preview_available),
    preview_possible: Boolean(raw.preview_possible),
    preview_action_available: Boolean(raw.preview_action_available),
    preview_action_name: asStringOrNull(raw.preview_action_name),
    preview_endpoint: asStringOrNull(raw.preview_endpoint),
    preview_creation_requires_explicit_user_intent:
      raw.preview_creation_requires_explicit_user_intent !== false,
    preview_export_requires_consent: raw.preview_export_requires_consent !== false,
    preview_requires_explicit_endpoint: raw.preview_requires_explicit_endpoint !== false,
    preview_service_boundary: asStringOrNull(raw.preview_service_boundary),
    projection_version: asStringOrNull(raw.projection_version),
  };
}
