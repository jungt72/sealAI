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

export type ProductEventName =
  | "landing_cta_clicked"
  | "register_started"
  | "register_completed"
  | "case_started"
  | "case_first_input_added"
  | "case_step_completed"
  | "case_summary_viewed"
  | "handover_clicked"
  | "sealingpedia_article_viewed"
  | "pedia_to_case_clicked";

export type ProductEventPayload = {
  article_type?: "wissen" | "werkstoffe" | "medien";
  case_present?: boolean;
  consent_status?: "requested" | "granted" | "blocked";
  cta?: string;
  has_value?: boolean;
  location?: string;
  method?: string;
  source?: string;
  slug?: string;
  step?: string;
};

type AnalyticsPrimitive = string | number | boolean;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    rybbit?: {
      event?: (name: string, data?: Record<string, AnalyticsPrimitive>) => void;
    };
  }
}

const PRODUCT_EVENT_ALLOWLIST = {
  landing_cta_clicked: ["cta", "location"],
  register_started: ["method", "source"],
  register_completed: ["method", "source"],
  case_started: ["case_present", "source"],
  case_first_input_added: ["case_present", "source"],
  case_step_completed: ["has_value", "source", "step"],
  case_summary_viewed: ["case_present", "source"],
  handover_clicked: ["case_present", "consent_status", "source"],
  sealingpedia_article_viewed: ["article_type", "slug"],
  pedia_to_case_clicked: ["article_type", "source", "slug"],
} as const satisfies Record<ProductEventName, readonly (keyof ProductEventPayload)[]>;

export function analyticsEnabled() {
  return (
    process.env.NEXT_PUBLIC_ANALYTICS_ENABLED === "true" &&
    Boolean(process.env.NEXT_PUBLIC_GTM_ID || process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID)
  );
}

export function rybbitAnalyticsEnabled() {
  return (
    process.env.NEXT_PUBLIC_RYBBIT_ENABLED !== "false" &&
    Boolean(process.env.NEXT_PUBLIC_RYBBIT_SITE_ID?.trim())
  );
}

export function cleanAnalyticsPayload(payload: SeoEventPayload = {}) {
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== undefined && value !== null && value !== ""),
  );
}

function normalizeSafeToken(value: string) {
  return value
    .trim()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9_.:-]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80);
}

export function cleanProductAnalyticsPayload(
  event: ProductEventName,
  payload: ProductEventPayload = {},
): Record<string, AnalyticsPrimitive> {
  const allowedKeys = PRODUCT_EVENT_ALLOWLIST[event];
  const cleaned: Record<string, AnalyticsPrimitive> = {
    event_category: "sealingai_product",
  };

  for (const key of allowedKeys) {
    const value = payload[key];
    if (value === undefined || value === null || value === "") {
      continue;
    }
    if (typeof value === "boolean" || typeof value === "number") {
      cleaned[key] = value;
      continue;
    }
    if (typeof value === "string") {
      const normalized = normalizeSafeToken(value);
      if (normalized) {
        cleaned[key] = normalized;
      }
    }
  }

  return cleaned;
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

export function trackProductEvent(event: ProductEventName, payload: ProductEventPayload = {}) {
  if (typeof window === "undefined" || !rybbitAnalyticsEnabled()) {
    return;
  }

  const eventPayload = cleanProductAnalyticsPayload(event, payload);
  window.rybbit?.event?.(event, eventPayload);
}
