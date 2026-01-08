import Image from "next/image";

export function OverviewSection() {
    return (
        <section
            id="overview"
            className="relative bg-gray-50 py-16 px-4 md:px-6 lg:px-8 overflow-hidden"
            aria-labelledby="overview-heading"
        >

            <div className="max-w-[1600px] mx-auto relative z-10 px-6">
                <div className="grid md:grid-cols-2 gap-12 items-center ml-[137px]">
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

                    <div id="neutralitaet" className="space-y-6">
                        <div className="text-xs font-semibold tracking-wider text-[#0071e3] uppercase">ÜBERBLICK</div>
                        <h2 id="overview-heading" className="text-2xl md:text-3xl font-medium text-balance leading-snug text-[#1d1d1f]">
                            Entscheidungssicherheit in der Dichtungsauslegung
                        </h2>
                        <div className="space-y-4 text-[17px] leading-relaxed text-[#1d1d1f]">
                            <p>
                                Fehlerhafte Dichtungsentscheidungen entstehen selten durch fehlendes Fachwissen –
                                sondern durch unvollständige Einsatzparameter, verstreute Informationen und Zeitdruck im Entwicklungsprozess.
                            </p>
                            <p>
                                SealAI unterstützt Konstrukteure und Anwendungstechniker dabei, alle relevanten Randbedingungen strukturiert zu erfassen, technisch zu bewerten und konsistent zusammenzuführen.
                                Auf dieser Basis werden ungeeignete Lösungen ausgeschlossen und geeignete Dichtungen nachvollziehbar empfohlen.
                            </p>
                            <p>
                                Das Ergebnis sind belastbare Entscheidungen, weniger Rückfragen und eine deutlich reduzierte Fehlerquote – bereits vor der Freigabe.
                            </p>
                            <p className="font-medium pt-2">
                                SealAI ersetzt keine Verantwortung, sondern schafft Transparenz und Sicherheit in technischen Entscheidungen.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
