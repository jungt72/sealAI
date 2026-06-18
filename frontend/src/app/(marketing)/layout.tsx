import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Menu } from "lucide-react";
import { TrackedLink } from "@/components/analytics/TrackedLink";

const loginHref = "/dashboard";
const startCaseHref = "/dashboard";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-white text-[#17201f]">
      <header className="sticky top-0 z-50 w-full bg-[#e8e9e5]/92 backdrop-blur-xl">
        <TrackedLink
          href="/wissen"
          analyticsEvent="landing_cta_clicked"
          analyticsPayload={{ cta: "announcement_sealingpedia", location: "announcement_bar" }}
          className="flex min-h-6 items-center justify-center gap-2 bg-[#004a2f] px-4 text-center text-[11px] font-medium text-white"
        >
          Der sealingAI Anfrage-Agent ist live
          <span className="inline-flex items-center gap-1 text-white/80">
            Mehr erfahren <ArrowRight size={13} />
          </span>
        </TrackedLink>
        <div className="mx-auto flex h-12 max-w-[1480px] items-center justify-between px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-8">
            <Link href="/" className="flex shrink-0 items-center" aria-label="sealingAI Startseite">
              <Image
                src="/images/logo/sealingai-wordmark-seal-blue.svg"
                alt="sealingAI"
                width={1225}
                height={249}
                priority
                sizes="(max-width: 768px) 86px, 102px"
                className="h-auto w-[86px] object-contain sm:w-[102px]"
              />
            </Link>

            <nav className="hidden items-center gap-6 lg:flex" aria-label="Hauptnavigation">
              <Link href="/werkstoffe" className="text-[12px] font-medium text-[#17201f]/58 transition-colors hover:text-seal-blue">
                Produkt
              </Link>
              <Link href="/medien" className="text-[12px] font-medium text-[#17201f]/58 transition-colors hover:text-seal-blue">
                Lösungen
              </Link>
              <Link href="/wissen" className="text-[12px] font-medium text-[#17201f]/58 transition-colors hover:text-seal-blue">
                Wissen
              </Link>
              <Link href={loginHref} className="text-[12px] font-medium text-[#17201f]/58 transition-colors hover:text-seal-blue">
                Cockpit
              </Link>
              <Link href="/anfrage/dichtung-auslegen-lassen" className="text-[12px] font-medium text-[#17201f]/58 transition-colors hover:text-seal-blue">
                Anfrage
              </Link>
            </nav>
          </div>

          <div className="hidden items-center gap-3 md:flex">
            <TrackedLink
              href={loginHref}
              analyticsEvent="landing_cta_clicked"
              analyticsPayload={{ cta: "header_login", location: "header" }}
              className="inline-flex h-9 items-center gap-1.5 rounded-full bg-[#002a5b] px-5 text-[13px] font-semibold text-white transition-all shadow-[4px_4px_9px_#b8b9be,-4px_-4px_9px_#ffffff] hover:bg-[#0a3a72] hover:shadow-[5px_5px_11px_#b0b1b8,-5px_-5px_11px_#ffffff] active:shadow-[inset_3px_3px_7px_rgba(0,0,0,0.55),inset_-3px_-3px_7px_rgba(255,255,255,0.14)] active:translate-y-px"
            >
              Login
              <ArrowRight size={14} />
            </TrackedLink>
          </div>

          <div className="flex items-center gap-3 md:hidden">
            <TrackedLink
              href={startCaseHref}
              analyticsEvent="landing_cta_clicked"
              analyticsPayload={{ cta: "mobile_start", location: "header" }}
              className="text-[13px] font-semibold text-[#002a5b]"
            >
              Login
            </TrackedLink>
            <button
              type="button"
              aria-label="Menü öffnen"
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[#17201f]/15 text-[#17201f]"
            >
              <Menu size={16} />
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-[#17201f]/10 bg-white py-16">
        <div className="mx-auto max-w-[1480px] px-5 sm:px-8">
          <div className="grid gap-10 md:grid-cols-[1fr_1.35fr]">
            <p className="max-w-xs text-[13px] leading-6 text-[#17201f]/55">
              Klär deinen Dichtungsfall, bevor du fragst. Neutral, strukturiert und ohne heimliche Weitergabe.
            </p>
            <div className="grid grid-cols-2 gap-8 sm:grid-cols-4">
              <div className="flex flex-col gap-3">
                <span className="text-[11px] font-bold uppercase text-[#17201f]/35">Plattform</span>
                <Link href="/medien" className="text-sm text-muted-foreground hover:text-seal-blue">Medien</Link>
                <Link href="/werkstoffe" className="text-sm text-muted-foreground hover:text-seal-blue">Werkstoffe</Link>
                <Link href="/wissen" className="text-sm text-muted-foreground hover:text-seal-blue">SealingPedia</Link>
              </div>
              <div className="flex flex-col gap-3">
                <span className="text-[11px] font-bold uppercase text-[#17201f]/35">Rechtliches</span>
                <Link href="/impressum" className="text-sm text-muted-foreground hover:text-seal-blue">Impressum</Link>
                <Link href="/datenschutz" className="text-sm text-muted-foreground hover:text-seal-blue">Datenschutz</Link>
                <Link href="/kontakt" className="text-sm text-muted-foreground hover:text-seal-blue">Kontakt</Link>
              </div>
            </div>
          </div>
          <div className="mt-16 flex flex-col items-center gap-8 border-t border-[#17201f]/10 pt-12">
            <Image
              src="/images/logo/sealingai-wordmark-seal-blue.svg"
              alt="sealingAI"
              width={1225}
              height={249}
              sizes="220px"
              className="h-auto w-[220px] object-contain sm:w-[280px]"
            />
            <p className="text-center text-[11px] text-muted-foreground">
              © {new Date().getFullYear()} sealingAI. Alle Rechte vorbehalten. Technische Freigaben erfolgen ausschließlich durch den Hersteller.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
