import { describe, expect, it } from "vitest";

import {
  getUnavailableMatchingActions,
  getUnavailableRfqActions,
} from "@/lib/workspaceActionAvailability";

const workspace = {
  matching: { selectedPartnerId: null },
  rfq: {
    releaseStatus: "manufacturer_validation_required",
    confirmed: false,
    hasDraft: true,
    hasHtmlReport: false,
    handoverInitiated: false,
  },
} as any;

describe("workspace action labels", () => {
  it("keeps RFQ actions framed as preview/export instead of dispatch", () => {
    expect(getUnavailableRfqActions(workspace).map((action) => action.label)).toEqual([
      "RFQ-Preview bewusst bestätigen",
      "Anfragebasis exportieren",
      "Manuelle Weitergabe späterer Scope",
    ]);
  });

  it("keeps matching framed as later scope", () => {
    expect(getUnavailableMatchingActions(workspace).map((action) => action.label)).toEqual([
      "Partnerauswahl späterer Scope",
    ]);
  });
});
