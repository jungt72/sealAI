"use client";

import { signIn } from "next-auth/react";
import ModernHero from "@/components/ui/ModernHero";
import type { HeroSection } from "@/lib/types";

interface LandingCtaClientProps {
  data?: HeroSection;
}

const buildCallbackUrl = () => {
  const configuredUrl = process.env.NEXT_PUBLIC_SITE_URL;
  const origin = typeof window !== "undefined" ? window.location.origin : undefined;
  const resolvedBase = origin || configuredUrl || "";
  const cleanedBase = resolvedBase.replace(/\/$/, "");
  return cleanedBase ? `${cleanedBase}/chat` : "/chat";
};

export default function LandingCtaClient({ data }: LandingCtaClientProps) {
  const handlePrimaryCta = () => {
    signIn("keycloak", {
      callbackUrl: buildCallbackUrl(),
    });
  };

  return <ModernHero data={data} onPrimaryCta={handlePrimaryCta} />;
}
