"use client";

import { signIn } from "next-auth/react";
import ModernHero from "@/components/ui/ModernHero";
import type { HeroSection } from "@/lib/types";
import { DEFAULT_CALLBACK_URL } from "@/lib/utils";

interface LandingCtaClientProps {
  data?: HeroSection;
}

export default function LandingCtaClient({ data }: LandingCtaClientProps) {
  const handlePrimaryCta = () => {
    signIn("keycloak", {
      callbackUrl: DEFAULT_CALLBACK_URL,
    });
  };

  return <ModernHero data={data} onPrimaryCta={handlePrimaryCta} />;
}
