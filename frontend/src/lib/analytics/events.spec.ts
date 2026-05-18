import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import {
  cleanAnalyticsPayload,
  cleanProductAnalyticsPayload,
  trackProductEvent,
  trackSeoEvent,
} from "./events";

describe("analytics events", () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    process.env = { ...originalEnv };
    window.dataLayer = [];
    window.gtag = vi.fn();
    window.rybbit = { event: vi.fn() };
  });

  afterEach(() => {
    process.env = originalEnv;
    delete window.dataLayer;
    delete window.gtag;
    delete window.rybbit;
  });

  it("removes empty values from payloads", () => {
    expect(cleanAnalyticsPayload({ page_path: "/wissen", empty: "", nil: null, ok: true })).toEqual({
      page_path: "/wissen",
      ok: true,
    });
  });

  it("pushes enabled SEO events without user message content", () => {
    process.env.NEXT_PUBLIC_ANALYTICS_ENABLED = "true";
    process.env.NEXT_PUBLIC_GTM_ID = "GTM-TEST";

    trackSeoEvent("rfq_started", {
      case_id: "case-1",
      source: "agent_chat",
    });

    expect(window.dataLayer).toEqual([
      {
        event: "rfq_started",
        event_category: "sealingai_seo",
        case_id: "case-1",
        source: "agent_chat",
      },
    ]);
    expect(window.gtag).toHaveBeenCalledWith("event", "rfq_started", {
      event_category: "sealingai_seo",
      case_id: "case-1",
      source: "agent_chat",
    });
  });

  it("does nothing until analytics is explicitly enabled", () => {
    process.env.NEXT_PUBLIC_ANALYTICS_ENABLED = "false";
    process.env.NEXT_PUBLIC_GTM_ID = "GTM-TEST";

    trackSeoEvent("page_view", { page_path: "/" });

    expect(window.dataLayer).toEqual([]);
    expect(window.gtag).not.toHaveBeenCalled();
  });

  it("allowlists Rybbit product event metadata and drops sensitive free-form fields", () => {
    expect(
      cleanProductAnalyticsPayload("case_step_completed", {
        step: "temperature_c",
        has_value: true,
        source: "direct parameter intake",
        cta: "not allowed here",
      }),
    ).toEqual({
      event_category: "sealingai_product",
      has_value: true,
      source: "direct_parameter_intake",
      step: "temperature_c",
    });
  });

  it("sends Rybbit events only when a site id is configured", () => {
    process.env.NEXT_PUBLIC_RYBBIT_ENABLED = "true";
    process.env.NEXT_PUBLIC_RYBBIT_SITE_ID = "site-test";

    trackProductEvent("landing_cta_clicked", {
      cta: "Dichtungsfall klären",
      location: "Hero CTA",
    });

    expect(window.rybbit?.event).toHaveBeenCalledWith("landing_cta_clicked", {
      event_category: "sealingai_product",
      cta: "dichtungsfall_klaren",
      location: "hero_cta",
    });
  });

  it("does not send Rybbit events while disabled", () => {
    process.env.NEXT_PUBLIC_RYBBIT_ENABLED = "false";
    process.env.NEXT_PUBLIC_RYBBIT_SITE_ID = "site-test";

    trackProductEvent("case_started", {
      case_present: true,
      source: "case_bound_event",
    });

    expect(window.rybbit?.event).not.toHaveBeenCalled();
  });
});
