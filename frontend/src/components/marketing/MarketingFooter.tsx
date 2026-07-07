import Image from "next/image";
import Link from "next/link";

import { footerColumns } from "@/lib/marketing/homeContent";

export function MarketingFooter() {
  return (
    <footer className="border-t border-border bg-white" aria-labelledby="footer-heading">
      <h2 id="footer-heading" className="sr-only">
        Fußbereich
      </h2>
      <div className="mx-auto max-w-[1240px] px-5 py-16 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[1.1fr_2.4fr]">
          <div className="max-w-xs">
            <Image
              src="/images/logo/sealingai-wordmark-seal-blue.svg"
              alt="sealingAI"
              width={200}
              height={40}
              className="h-7 w-auto"
            />
            <p className="mt-4 text-[13px] leading-6 text-muted-foreground">
              Dichtungstechnik ist Erfahrungswissenschaft. sealingAI macht Erfahrung systematisch
              nutzbar — neutral, strukturiert und nachvollziehbar.
            </p>
          </div>

          <nav aria-label="Fußnavigation" className="grid grid-cols-2 gap-8 sm:grid-cols-3 lg:grid-cols-6">
            {footerColumns.map((column) => (
              <div key={column.title} className="flex flex-col gap-3">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-foreground/70">
                  {column.title}
                </span>
                {column.links.map((link) => (
                  <Link
                    key={link.label}
                    href={link.href}
                    className="text-[13px] leading-5 text-muted-foreground transition-colors hover:text-seal-blue"
                  >
                    {link.label}
                  </Link>
                ))}
              </div>
            ))}
          </nav>
        </div>

        <div className="mt-14 flex flex-col gap-3 border-t border-border pt-8 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} sealingAI. Alle Rechte vorbehalten.</p>
          <p>Technische Freigaben erfolgen ausschließlich durch den Hersteller.</p>
        </div>
      </div>
    </footer>
  );
}
