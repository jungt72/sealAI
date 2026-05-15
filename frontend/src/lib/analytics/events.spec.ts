import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { cleanAnalyticsPayload, trackSeoEvent } from "./events";

describe("analytics events", () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    process.env = { ...originalEnv };
    window.dataLayer = [];
    window.gtag = vi.fn();
  });

  afterEach(() => {
    process.env = originalEnv;
    delete window.dataLayer;
    delete window.gtag;
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
});
