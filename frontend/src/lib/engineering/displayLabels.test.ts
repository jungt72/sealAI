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

  it("normalizes common German ASCII spellings in visible engineering text", () => {
    expect(
      humanizeDisplayText(
        "Welche Gegenlaufflaeche ist bekannt, zum Beispiel Rauheit, Haerte oder Huelse?",
      ),
    ).toBe("Welche Gegenlauffläche ist bekannt, zum Beispiel Rauheit, Härte oder Hülse?");
    expect(humanizeDisplayText("fuer Herstellerpruefung klaeren")).toBe("für Herstellerprüfung klären");
    expect(humanizeDisplayText("Waermeeintrag und Verschleiss pruefen")).toBe("Wärmeeintrag und Verschleiß prüfen");
  });
});
