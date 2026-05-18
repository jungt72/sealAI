"use client";

import Link from "next/link";
import type { ComponentProps, MouseEvent } from "react";

import {
  trackProductEvent,
  trackSeoEvent,
  type ProductEventName,
  type ProductEventPayload,
  type SeoEventName,
  type SeoEventPayload,
} from "@/lib/analytics/events";

type TrackedLinkProps = ComponentProps<typeof Link> & {
  analyticsEvent: ProductEventName;
  analyticsPayload?: ProductEventPayload;
  seoEvent?: SeoEventName;
  seoPayload?: SeoEventPayload;
};

export function TrackedLink({
  analyticsEvent,
  analyticsPayload,
  seoEvent,
  seoPayload,
  onClick,
  ...props
}: TrackedLinkProps) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(event);
    if (event.defaultPrevented) {
      return;
    }
    trackProductEvent(analyticsEvent, analyticsPayload);
    if (seoEvent) {
      trackSeoEvent(seoEvent, seoPayload);
    }
  };

  return <Link {...props} onClick={handleClick} />;
}
