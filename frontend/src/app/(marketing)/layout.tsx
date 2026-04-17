import Link from "next/link";
import { ArrowRight } from "lucide-react";

export default function MarketingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* HEADER */}
      <header className="sticky top-0 z-50 w-full border-b border-border/50 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <Link href="/" className="text-xl font-bold tracking-tight text-seal-blue">
            SealingAI
          </Link>
          
          <nav className="hidden md:flex items-center gap-8">
            <Link href="/medien" className="text-sm font-medium text-muted-foreground hover:text-seal-blue transition-colors">
              Medien
            </Link>
            <Link href="/werkstoffe" className="text-sm font-medium text-muted-foreground hover:text-seal-blue transition-colors">
              Werkstoffe
            </Link>
            <Link href="/wissen" className="text-sm font-medium text-muted-foreground hover:text-seal-blue transition-colors">
              Wissen
            </Link>
            <Link 
              href="/dashboard/new" 
              className="flex items-center gap-2 rounded-full bg-seal-blue px-5 py-2 text-sm font-bold text-white transition-all hover:opacity-90 active:scale-95"
            >
              Analyse starten
              <ArrowRight size={14} />
            </Link>
          </nav>

          {/* Mobile Menu Placeholder (Phase 8) */}
          <div className="md:hidden">
            <Link href="/dashboard/new" className="text-xs font-bold uppercase tracking-wider text-seal-blue">
              Start
            </Link>
          </div>
        </div>
      </header>

      {/* MAIN CONTENT */}
      <main className="flex-1">{children}</main>

      {/* FOOTER */}
      <footer className="border-t border-border bg-slate-50 py-12">
        <div className="mx-auto max-w-7xl px-6">
          <div className="flex flex-col md:flex-row justify-between gap-10">
            <div className="flex flex-col gap-4">
              <span className="text-lg font-bold text-seal-blue">SealingAI</span>
              <p className="text-sm text-muted-foreground max-w-xs">
                Sealing Intelligence — Professionelle technische Analyse und Vorqualifizierung von Dichtungslösungen.
              </p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-10">
              <div className="flex flex-col gap-3">
                <span className="text-[11px] font-bold uppercase tracking-widest text-foreground/40">Plattform</span>
                <Link href="/medien" className="text-sm text-muted-foreground hover:text-seal-blue">Medien</Link>
                <Link href="/werkstoffe" className="text-sm text-muted-foreground hover:text-seal-blue">Werkstoffe</Link>
                <Link href="/wissen" className="text-sm text-muted-foreground hover:text-seal-blue">Wissen</Link>
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
              © {new Date().getFullYear()} SealingAI. Alle Rechte vorbehalten. Technische Freigaben erfolgen ausschließlich durch den Hersteller.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
