import { MarketingFooter } from "@/components/marketing/MarketingFooter";
import { MarketingHeader } from "@/components/marketing/MarketingHeader";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <MarketingHeader />
      {/* The header is fixed (overlays content, transparent over the hero), so
          non-hero pages need top padding to clear it. The homepage's hero
          section cancels this with a matching negative margin so it can sit
          full-bleed at y=0 under the transparent header. */}
      <main className="flex-1 pt-[76px]">{children}</main>
      <MarketingFooter />
    </div>
  );
}
