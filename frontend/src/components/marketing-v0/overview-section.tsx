import Image from "next/image";

export function OverviewSection() {
  return (
    <section
      className="relative bg-gray-50 py-16 px-4 md:px-6 lg:px-8 overflow-hidden"
      aria-labelledby="overview-heading"
    >
      <div
        className="absolute left-0 top-0 bottom-0 w-1/3 bg-gradient-to-br from-purple-300 via-purple-400 to-pink-400 rounded-r-full opacity-40 -translate-x-1/4"
        aria-hidden="true"
      />

      <div className="max-w-7xl mx-auto relative z-10">
        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div className="relative">
            <div className="relative rounded-3xl overflow-hidden shadow-2xl">
              <Image
                src="/images/team-collaboration.png"
                alt="Team bei der Zusammenarbeit - Menschen arbeiten gemeinsam an innovativen Lösungen"
                width={800}
                height={600}
                className="w-full h-auto"
                priority
                quality={90}
              />
            </div>
          </div>

          <div className="space-y-6">
            <div className="text-xs font-semibold tracking-wider text-muted-foreground uppercase">Übersicht</div>
            <h2 id="overview-heading" className="text-4xl md:text-5xl font-semibold text-balance leading-tight">
              Transformieren, wie Ihr Unternehmen arbeitet und Lösungen erstellt
            </h2>
            <p className="text-lg text-muted-foreground leading-relaxed">
              Ermöglichen Sie allen Mitarbeitern in Ihrem Unternehmen die schnelle Entwicklung von Apps, Webseiten,
              Workflows und Agents mit Copilot-Funktionen über Power Platform hinweg. Erstellen Sie ganz einfach Lösungen
              mit natürlicher Sprache, und gewinnen Sie zusätzlich wertvolle Datenerkenntnisse, indem Sie einfach Fragen
              stellen.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
