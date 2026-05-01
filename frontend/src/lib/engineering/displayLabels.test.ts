import { describe, expect, it } from "vitest";

import { humanizeDisplayText } from "./displayLabels";

describe("humanizeDisplayText", () => {
  it("translates backend engineering tokens before they reach the cockpit", () => {
    expect(humanizeDisplayText("static or dynamic")).toBe("statisch oder dynamisch");
    expect(humanizeDisplayText("shaft surface")).toBe("Gegenlauffläche");
    expect(humanizeDisplayText("installation direction")).toBe("Einbaurichtung");
    expect(humanizeDisplayText("rfq preparable with open points")).toBe("RFQ mit offenen Punkten vorbereitbar");
    expect(humanizeDisplayText("radial shaft seal · rotary shaft")).toBe("Radialwellendichtring · rotierende Welle");
  });
});
