import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { TrackedLink } from "@/components/analytics/TrackedLink";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <header className="sticky top-0 z-50 w-full border-b border-slate-200 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <Link href="/" className="flex items-center" aria-label="sealingAI Startseite">
            <Image
              src="/images/logo/sealingai-wordmark-seal-blue.svg"
              alt="sealingAI"
              width={1225}
              height={249}
              priority
              sizes="(max-width: 768px) 108px, 118px"
              className="h-auto w-[108px] object-contain sm:w-[118px]"
            />
          </Link>

          <nav className="hidden items-center gap-8 md:flex">
            <Link href="/medien" className="text-sm font-medium text-muted-foreground transition-colors hover:text-seal-blue">
              Medien
            </Link>
            <Link href="/werkstoffe" className="text-sm font-medium text-muted-foreground transition-colors hover:text-seal-blue">
              Werkstoffe
            </Link>
            <Link href="/wissen" className="text-sm font-medium text-muted-foreground transition-colors hover:text-seal-blue">
              SealingPedia
            </Link>
            <TrackedLink
              href="/dashboard/new"
              analyticsEvent="landing_cta_clicked"
              analyticsPayload={{ cta: "fall_klaeren", location: "header" }}
              className="flex items-center gap-2 bg-seal-blue px-5 py-2.5 text-sm font-bold text-white transition-all hover:bg-[#082b64] active:scale-[0.98]"
            >
              Fall klären
              <ArrowRight size={14} />
            </TrackedLink>
          </nav>

          <div className="flex items-center gap-4 md:hidden">
            <Link href="/wissen" className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              SealingPedia
            </Link>
            <TrackedLink
              href="/dashboard/new"
              analyticsEvent="landing_cta_clicked"
              analyticsPayload={{ cta: "start", location: "mobile_header" }}
              className="text-xs font-bold uppercase tracking-wider text-seal-blue"
            >
              Start
            </TrackedLink>
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-slate-200 bg-[#f6f8fa] py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex flex-col justify-between gap-10 md:flex-row">
            <div className="flex flex-col gap-4">
              <Image
                src="/images/logo/sealingai-wordmark-seal-blue.svg"
                alt="sealingAI"
                width={1225}
                height={249}
                sizes="122px"
                className="h-auto w-[122px] object-contain"
              />
              <p className="max-w-xs text-sm text-muted-foreground">
                Klär deinen Dichtungsfall, bevor du fragst. Neutral, strukturiert und ohne heimliche Weitergabe.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-10 sm:grid-cols-3">
              <div className="flex flex-col gap-3">
                <span className="text-[11px] font-bold uppercase tracking-widest text-foreground/40">Plattform</span>
                <Link href="/medien" className="text-sm text-muted-foreground hover:text-seal-blue">Medien</Link>
                <Link href="/werkstoffe" className="text-sm text-muted-foreground hover:text-seal-blue">Werkstoffe</Link>
                <Link href="/wissen" className="text-sm text-muted-foreground hover:text-seal-blue">SealingPedia</Link>
              </div>
              <div className="flex flex-col gap-3">
                <span className="text-[11px] font-bold uppercase tracking-widest text-foreground/40">Rechtliches</span>
                <Link href="/impressum" className="text-sm text-muted-foreground hover:text-seal-blue">Impressum</Link>
                <Link href="/datenschutz" className="text-sm text-muted-foreground hover:text-seal-blue">Datenschutz</Link>
                <Link href="/kontakt" className="text-sm text-muted-foreground hover:text-seal-blue">Kontakt</Link>
              </div>
            </div>
          </div>
          <div className="mt-12 border-t border-border/50 pt-8 text-center">
            <p className="text-[12px] text-muted-foreground">
              © {new Date().getFullYear()} sealingAI. Alle Rechte vorbehalten. Technische Freigaben erfolgen ausschließlich durch den Hersteller.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
