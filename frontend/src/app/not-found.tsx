import Link from "next/link";
import { ArrowRight } from "lucide-react";

/**
 * Global 404 boundary. Next's default not-found is an English one-liner with
 * no navigation — a dead end for users and a weak quality signal on a German
 * site. The HTTP status stays a real 404 (Next sets it), so search engines
 * still drop the URL; this only fixes what the human sees.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#FAFAF9] px-6 text-center">
      <p className="text-sm font-semibold uppercase tracking-widest text-seal-blue/60">Fehler 404</p>
      <h1 className="mt-4 max-w-xl text-3xl font-bold tracking-tight text-foreground md:text-4xl">
        Diese Seite gibt es nicht — Ihr Dichtungsfall schon.
      </h1>
      <p className="mt-4 max-w-md text-[15px] leading-7 text-muted-foreground">
        Die aufgerufene Adresse existiert nicht oder wurde entfernt. Hier geht es weiter:
      </p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/anfrage/dichtung-auslegen-lassen"
          className="inline-flex h-11 items-center gap-2 rounded-full bg-seal-blue px-6 text-[14px] font-semibold text-white transition hover:bg-seal-blue/92"
        >
          Dichtungsfall vorprüfen
          <ArrowRight size={16} aria-hidden="true" />
        </Link>
        <Link
          href="/wissen"
          className="inline-flex h-11 items-center rounded-full border border-border bg-white px-6 text-[14px] font-medium text-foreground transition hover:bg-slate-50"
        >
          Dichtungswissen
        </Link>
        <Link
          href="/"
          className="inline-flex h-11 items-center rounded-full px-4 text-[14px] font-medium text-muted-foreground transition hover:text-seal-blue"
        >
          Zur Startseite
        </Link>
      </div>
    </div>
  );
}
