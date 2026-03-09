// frontend/src/lib/lifecycleSteps.ts
// Pure lifecycle step derivation logic — no React, no JSX.
// Shared between CaseLifecyclePanel.tsx and tests.

import type { CaseWorkspaceProjection } from "./workspaceApi.js";

export type LifecycleStepStatus = "done" | "active" | "pending";

export type LifecycleStep = {
  label: string;
  status: LifecycleStepStatus;
  detail?: string;
  iconName: string;
};

export function deriveLifecycleSteps(ws: CaseWorkspaceProjection): LifecycleStep[] {
  const { case_summary: cs, artifact_status: art, rfq_status: rfq, governance_status: gov } = ws;

  const steps: LifecycleStep[] = [];

  // 1. Case started
  const caseStarted = !!cs.thread_id || cs.turn_count > 0;
  steps.push({
    label: "Case Started",
    status: caseStarted ? "done" : "pending",
    detail: cs.turn_count > 0 ? `Turn ${cs.turn_count}/${cs.max_turns}` : undefined,
    iconName: "Layers",
  });

  // 2. Contract generated
  steps.push({
    label: "Contract Generated",
    status: art.has_answer_contract ? (art.contract_obsolete ? "active" : "done") : "pending",
    detail: art.contract_obsolete ? "Obsolete — needs update" : art.contract_id || undefined,
    iconName: "Shield",
  });

  // 3. Verification
  steps.push({
    label: "Verification",
    status: art.has_verification_report ? (gov.verification_passed ? "done" : "active") : "pending",
    detail: art.has_verification_report
      ? (gov.verification_passed ? "Passed" : "Issues found")
      : undefined,
    iconName: "CheckCircle2",
  });

  // 4. RFQ draft
  steps.push({
    label: "RFQ Draft",
    status: art.has_rfq_draft ? "done" : "pending",
    detail: art.has_rfq_draft ? gov.release_status.replace(/_/g, " ") : undefined,
    iconName: "FileText",
  });

  // 5. RFQ confirmed
  steps.push({
    label: "RFQ Confirmed",
    status: rfq.rfq_confirmed ? "done" : (art.has_rfq_draft ? "active" : "pending"),
    iconName: "ClipboardCheck",
  });

  // 6. Document generated
  steps.push({
    label: "Document Generated",
    status: rfq.has_html_report ? "done" : (rfq.rfq_confirmed ? "active" : "pending"),
    detail: rfq.has_pdf ? "PDF available" : (rfq.has_html_report ? "HTML report" : undefined),
    iconName: "FileDown",
  });

  // 7. Partner matching / Handover
  const pm = ws.partner_matching;
  if (rfq.handover_initiated) {
    steps.push({
      label: "RFQ Submitted",
      status: "done",
      detail: pm.selected_partner_id || undefined,
      iconName: "Zap",
    });
  } else {
    steps.push({
      label: "Partner Matching",
      status: pm.matching_ready ? "active" : "pending",
      detail: pm.material_fit_items.length > 0
        ? `${pm.material_fit_items.length} material fit${pm.material_fit_items.length !== 1 ? "s" : ""}`
        : undefined,
      iconName: "Factory",
    });
  }

  return steps;
}
