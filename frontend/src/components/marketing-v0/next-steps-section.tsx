import Image from "next/image";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/Button";

function ActionCard({
  image,
  imageAlt,
  title,
  description,
  buttonText,
  buttonHref = "#",
}: {
  image: string;
  imageAlt: string;
  title: string;
  description: string;
  buttonText: string;
  buttonHref?: string;
}) {
  return (
    <article className="bg-white rounded-2xl shadow-lg overflow-hidden">
      <div className="relative h-64">
        <Image
          src={image || "/placeholder.svg"}
          alt={imageAlt}
          fill
          className="object-cover"
          sizes="(max-width: 768px) 100vw, 50vw"
        />
      </div>

      <div className="p-8">
        <h3 className="text-2xl font-semibold text-gray-900 mb-4">{title}</h3>
        <p className="text-base text-gray-700 mb-6">{description}</p>

        <Button
          variant="link"
          className="text-[#0078D4] hover:text-[#106EBE] p-0 h-auto font-semibold text-base flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded"
          asChild
        >
          <a href={buttonHref}>
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-[#0078D4] text-white" aria-hidden="true">
              <ArrowRight className="w-4 h-4" />
            </span>
            {buttonText}
          </a>
        </Button>
      </div>
    </article>
  );
}

export function NextStepsSection() {
  return (
    <section
      className="relative py-24 overflow-hidden bg-gradient-to-r from-cyan-50 via-white to-purple-50"
      aria-labelledby="next-steps-heading"
    >
      <div className="absolute left-0 top-0 bottom-0 w-1/3 bg-gradient-to-r from-cyan-200 to-transparent opacity-40" aria-hidden="true" />
      <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-fuchsia-400 to-transparent opacity-40" aria-hidden="true" />

      <div className="container relative z-10 mx-auto px-6 max-w-7xl">
        <article className="bg-white rounded-2xl shadow-lg overflow-hidden mb-8">
          <div className="grid md:grid-cols-2 gap-0">
            <div className="p-12 flex flex-col justify-center">
              <span className="text-sm font-semibold text-[#C239B3] uppercase tracking-wide mb-6">Nächste Schritte</span>

              <h2 id="next-steps-heading" className="text-4xl font-semibold text-gray-900 mb-6">
                Platform-Produkte testen
              </h2>

              <p className="text-lg text-gray-700 mb-8">
                Ermöglichen Sie es allen in Ihrem Unternehmen, mit generativer KI schnell und einfach innovative Low-Code-Lösungen zu erstellen.
              </p>

              <div>
                <Button
                  size="lg"
                  className="bg-[#0078D4] hover:bg-[#106EBE] text-white px-8 py-6 text-base font-semibold focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                >
                  Erste Schritte
                </Button>
              </div>
            </div>

            <div className="relative h-[400px] md:h-auto">
              <Image
                src="/images/next-steps-woman.jpg"
                alt="Geschäftsfrau mit Tablet - Professionelle nutzt moderne Technologie"
                fill
                className="object-cover"
                sizes="(max-width: 768px) 100vw, 50vw"
                priority
              />
            </div>
          </div>
        </article>

        <div className="grid md:grid-cols-2 gap-8">
          <ActionCard
            image="/images/sales-support.jpg"
            imageAlt="Kundenservice-Team - Vertriebsspezialist berät Kunden"
            title="An den Vertrieb wenden"
            description="Kontaktieren Sie einen Vertriebsspezialisten per Chat oder telefonisch unter (0)800 8088014. Mo-Fr von 8 bis 17:00 Uhr erreichbar."
            buttonText="Jetzt chatten"
            buttonHref="#chat"
          />

          <ActionCard
            image="/images/contact-request.jpg"
            imageAlt="Business Meeting - Professionelle Beratung und Kontaktaufnahme"
            title="Kontakt anfordern"
            description="Senden Sie eine Anfrage, um sich innerhalb von zwei Werktagen von einer fachlichen Ansprechperson bei Microsoft oder einem Partner kontaktieren zu lassen."
            buttonText="Anfrage senden"
            buttonHref="#contact"
          />
        </div>
      </div>
    </section>
  );
}
