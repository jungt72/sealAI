import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Anmeldung nicht abgeschlossen | sealingAI",
  robots: { index: false, follow: false },
};

export default function AuthErrorPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#FAFAF9] px-6 text-[#0a121f]">
      <section className="w-full max-w-lg text-center" aria-labelledby="auth-error-title">
        <p className="mb-4 text-[13px] font-semibold uppercase text-seal-blue">Anmeldung</p>
        <h1 id="auth-error-title" className="text-4xl font-normal sm:text-5xl">
          Anmeldung nicht abgeschlossen
        </h1>
        <p className="mx-auto mt-6 max-w-md text-[17px] leading-7 text-[#4b5563]">
          Die Anmeldung ist abgelaufen oder konnte nicht bestätigt werden. Starten Sie die Anmeldung
          bitte erneut.
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/dashboard/"
            className="inline-flex h-11 items-center justify-center rounded-full bg-seal-blue px-6 text-[14px] font-semibold text-white transition-colors hover:bg-seal-blue/90"
          >
            Erneut anmelden
          </Link>
          <Link
            href="/"
            className="inline-flex h-11 items-center justify-center px-5 text-[14px] font-medium text-seal-blue hover:underline"
          >
            Zur Startseite
          </Link>
        </div>
      </section>
    </main>
  );
}
