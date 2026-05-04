import type { WorkspaceView } from "@/lib/contracts/workspace";

export type WorkspaceUnavailableAction = {
  id:
    | "rfq_confirm"
    | "rfq_generate_document"
    | "rfq_handover"
    | "partner_select";
  label: string;
  reason: string;
};

const UNAVAILABLE_REASON =
  "Not yet available in the current governed runtime.";

export function getUnavailableRfqActions(
  workspace: WorkspaceView,
): WorkspaceUnavailableAction[] {
  const actions: WorkspaceUnavailableAction[] = [];
  const { rfq } = workspace;
  const rfqRelevant = rfq.hasDraft || rfq.releaseStatus !== "inadmissible";

  if (!rfqRelevant) {
    return actions;
  }

  if (!rfq.confirmed) {
    actions.push({
      id: "rfq_confirm",
      label: "RFQ-Preview bewusst bestätigen",
      reason: UNAVAILABLE_REASON,
    });
  }

  if (!rfq.documentUrl) {
    actions.push({
      id: "rfq_generate_document",
      label: "Anfragebasis exportieren",
      reason: UNAVAILABLE_REASON,
    });
  }

  if (!rfq.handoverInitiated) {
    actions.push({
      id: "rfq_handover",
      label: "Manuelle Weitergabe späterer Scope",
      reason: UNAVAILABLE_REASON,
    });
  }

  return actions;
}

export function getUnavailableMatchingActions(
  workspace: WorkspaceView,
): WorkspaceUnavailableAction[] {
  const { matching } = workspace;

  if (matching.selectedPartnerId) {
    return [];
  }

  return [
    {
      id: "partner_select",
      label: "Partnerauswahl späterer Scope",
      reason: UNAVAILABLE_REASON,
    },
  ];
}
