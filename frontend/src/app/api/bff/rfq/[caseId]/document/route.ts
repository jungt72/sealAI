import { NextResponse } from "next/server";

const LEGACY_RFQ_DOCUMENT_DISABLED_RESPONSE = {
  error: {
    code: "rfq_document_legacy_disabled",
    message:
      "Legacy RFQ document access is disabled. Use the governed RFQ preview/export flow for the Anfragebasis for manufacturer review; consent required before export.",
  },
  dispatch_allowed: false,
  external_contact_allowed: false,
  export_requires_consent: true,
  final_approval_claim_allowed: false,
  preview_service_boundary: "RfqPreviewService.create_preview_for_case",
};

export async function GET(
  request: Request,
  context: { params: Promise<{ caseId: string }> },
) {
  await context.params;
  void request;
  return NextResponse.json(LEGACY_RFQ_DOCUMENT_DISABLED_RESPONSE, { status: 410 });
}
