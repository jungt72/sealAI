import { Suspense } from "react";

import { Hero } from "@/components/marketing-v0/hero";
import { SubNavigation } from "@/components/marketing-v0/sub-navigation";
import { OverviewSection } from "@/components/marketing-v0/overview-section";
import { ProductTabs } from "@/components/marketing-v0/product-tabs";
import { NextStepsSection } from "@/components/marketing-v0/next-steps-section";

export default function Page() {
  return (
    <>
      <Hero />
      <SubNavigation />
      <OverviewSection />

      <Suspense fallback={<div className="py-16 px-6">Lade Inhalte…</div>}>
        <ProductTabs />
      </Suspense>

      <NextStepsSection />
    </>
  );
}
