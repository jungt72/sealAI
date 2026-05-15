"use client";

import Script from "next/script";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { analyticsEnabled, trackSeoEvent } from "@/lib/analytics/events";

const gtmId = process.env.NEXT_PUBLIC_GTM_ID?.trim();
const gaMeasurementId = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID?.trim();
const consentDefault =
  process.env.NEXT_PUBLIC_GOOGLE_CONSENT_DEFAULT === "granted" ? "granted" : "denied";

function contentGroupForPath(pathname: string) {
  if (pathname.startsWith("/werkstoffe/")) return "materials";
  if (pathname.startsWith("/medien/")) return "media";
  if (pathname.startsWith("/wissen/")) return "knowledge";
  if (pathname.startsWith("/anfrage/")) return "rfq";
  if (pathname.startsWith("/dashboard/seo")) return "seo_suite";
  if (pathname.startsWith("/dashboard")) return "app";
  return "marketing";
}

function slugForPath(pathname: string) {
  const parts = pathname.split("/").filter(Boolean);
  return parts[1] ?? null;
}

function AnalyticsRouteEvents() {
  const pathname = usePathname();

  useEffect(() => {
    if (!pathname || !analyticsEnabled()) {
      return;
    }

    const contentGroup = contentGroupForPath(pathname);
    trackSeoEvent("page_view", {
      page_path: pathname,
      content_group: contentGroup,
    });

    if (contentGroup === "materials") {
      trackSeoEvent("material_page_viewed", {
        page_path: pathname,
        material_slug: slugForPath(pathname),
      });
    }

    if (contentGroup === "media") {
      trackSeoEvent("medium_page_viewed", {
        page_path: pathname,
        medium_slug: slugForPath(pathname),
      });
    }
  }, [pathname]);

  return null;
}

export function GoogleMarketingTags() {
  if (!analyticsEnabled()) {
    return null;
  }

  return (
    <>
      <Script id="sealingai-google-consent" strategy="afterInteractive">
        {`
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          window.gtag = window.gtag || gtag;
          gtag('consent', 'default', {
            ad_storage: '${consentDefault}',
            analytics_storage: '${consentDefault}',
            ad_user_data: '${consentDefault}',
            ad_personalization: '${consentDefault}',
            wait_for_update: 500
          });
          gtag('js', new Date());
          ${gaMeasurementId ? `gtag('config', '${gaMeasurementId}', { send_page_view: false });` : ""}
        `}
      </Script>
      {gtmId ? (
        <>
          <Script id="sealingai-gtm-init" strategy="afterInteractive">
            {`
              window.dataLayer = window.dataLayer || [];
              window.dataLayer.push({'gtm.start': new Date().getTime(), event: 'gtm.js'});
            `}
          </Script>
          <Script
            id="sealingai-gtm"
            src={`https://www.googletagmanager.com/gtm.js?id=${gtmId}`}
            strategy="afterInteractive"
          />
        </>
      ) : null}
      {gaMeasurementId && !gtmId ? (
        <Script
          id="sealingai-ga4"
          src={`https://www.googletagmanager.com/gtag/js?id=${gaMeasurementId}`}
          strategy="afterInteractive"
        />
      ) : null}
      <AnalyticsRouteEvents />
    </>
  );
}
