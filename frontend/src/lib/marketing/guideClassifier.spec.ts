import { describe, expect, it } from "vitest";

import { isTechnicalSealQuestion, resolveGuideAnswer, type GuideFaq } from "./guideClassifier";

const faq: GuideFaq[] = [
  { question: "Warum sollte ich sealingAI nutzen?", answer: "PLATFORM_WHY" },
  { question: "Was passiert nach dem kostenlosen Login?", answer: "PLATFORM_LOGIN" },
  { question: "Ist sealingAI neutral?", answer: "PLATFORM_NEUTRAL" },
  { question: "Wie hilft sealingAI Herstellern?", answer: "PLATFORM_MFG" },
  { question: "Wie werde ich Herstellerpartner?", answer: "PLATFORM_PARTNER" },
];
const GUARDRAIL = "GUARDRAIL_TEXT";

describe("isTechnicalSealQuestion", () => {
  it("flags a concrete technical sealing question", () => {
    expect(isTechnicalSealQuestion("Welche Dichtung soll ich für Hydrauliköl 80 °C nehmen?")).toBe(true);
  });

  it("flags material-recommendation questions", () => {
    expect(isTechnicalSealQuestion("Welches Material empfiehlst du für FKM bei 200 bar?")).toBe(true);
    expect(isTechnicalSealQuestion("Ist NBR für Bremsflüssigkeit geeignet?")).toBe(true);
  });

  it("does not flag platform questions", () => {
    expect(isTechnicalSealQuestion("Warum sollte ich sealingAI nutzen?")).toBe(false);
    expect(isTechnicalSealQuestion("Ist sealingAI neutral?")).toBe(false);
    expect(isTechnicalSealQuestion("")).toBe(false);
  });
});

describe("resolveGuideAnswer", () => {
  it("deflects a technical question to the guardrail, giving no recommendation", () => {
    const r = resolveGuideAnswer("Welche Dichtung soll ich für Hydrauliköl 80 °C nehmen?", faq, GUARDRAIL);
    expect(r.isGuardrail).toBe(true);
    expect(r.answer).toBe(GUARDRAIL);
    expect(r.matchedFaqIndex).toBeNull();
  });

  it("routes a neutrality question to the neutrality FAQ", () => {
    const r = resolveGuideAnswer("Ist die Bewertung käuflich?", faq, GUARDRAIL);
    expect(r.isGuardrail).toBe(false);
    expect(r.answer).toBe("PLATFORM_NEUTRAL");
  });

  it("routes a login question to the login FAQ", () => {
    const r = resolveGuideAnswer("Was passiert nach dem Login?", faq, GUARDRAIL);
    expect(r.answer).toBe("PLATFORM_LOGIN");
  });

  it("falls back to the platform 'why' answer for a generic question", () => {
    const r = resolveGuideAnswer("Erzähl mir etwas über euch", faq, GUARDRAIL);
    expect(r.isGuardrail).toBe(false);
    expect(r.answer).toBe("PLATFORM_WHY");
  });
});
