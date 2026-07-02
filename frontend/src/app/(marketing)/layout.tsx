import Image from "next/image";
import Link from "next/link";
import { MarketingHeader } from "@/components/marketing/MarketingHeader";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-[#FAFAF9] text-[#17201f]">
      <MarketingHeader />

      <main className="flex-1">{children}</main>

      <footer className="border-t border-[#17201f]/10 bg-[#FAFAF9] py-16">
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
              src="/images/logo/sealing-wordmark-new.png"
              alt="sealingAI"
              width={1500}
              height={300}
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
