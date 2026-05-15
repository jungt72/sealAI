"use client";

export type SeoEventName =
  | "page_view"
  | "rfq_started"
  | "rfq_preview_generated"
  | "contact_clicked"
  | "material_page_viewed"
  | "medium_page_viewed"
  | "case_started"
  | "partner_inquiry_started";

export type SeoEventPayload = Record<string, string | number | boolean | null | undefined>;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
  }
}

export function analyticsEnabled() {
  return (
    process.env.NEXT_PUBLIC_ANALYTICS_ENABLED === "true" &&
    Boolean(process.env.NEXT_PUBLIC_GTM_ID || process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID)
  );
}

export function cleanAnalyticsPayload(payload: SeoEventPayload = {}) {
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );
}

export function trackSeoEvent(event: SeoEventName, payload: SeoEventPayload = {}) {
  if (typeof window === "undefined" || !analyticsEnabled()) {
    return;
  }

  const eventPayload = cleanAnalyticsPayload({
    ...payload,
    event_category: payload.event_category ?? "sealingai_seo",
  });

  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push({ event, ...eventPayload });
  window.gtag?.("event", event, eventPayload);
}
