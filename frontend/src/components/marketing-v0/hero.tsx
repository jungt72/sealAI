import { Button } from "@/components/ui/Button";

export function Hero() {
  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-[#1e1548] via-[#2d1b69] to-[#c9379d]">
      <div className="absolute inset-0 opacity-30" aria-hidden="true">
        <div className="absolute top-1/4 right-0 w-[800px] h-[800px] bg-gradient-to-bl from-pink-500/60 to-transparent rounded-full blur-3xl" />
      </div>

      <div className="relative max-w-7xl mx-auto px-4 md:px-6 lg:px-8 py-24 md:py-32 lg:py-40">
        <div className="max-w-4xl">
          <p className="text-sm font-semibold text-cyan-400 mb-4 tracking-wide uppercase">
            Next GenAI in Power Platform
          </p>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-semibold mb-6 leading-tight text-balance text-white">
            Innovationen mit KI und Low-Code fördern
          </h1>

          <p className="text-lg md:text-xl text-gray-200 mb-8 leading-relaxed max-w-3xl">
            Erstellen Sie schnell KI-fähige Unternehmenslösungen, die Ihnen helfen, mit Copilot in Microsoft Power
            Platform Workflows zu optimieren und die Produktivität zu steigern.
          </p>

          <Button
            size="lg"
            className="bg-cyan-400 hover:bg-cyan-500 text-gray-900 font-semibold focus:ring-2 focus:ring-cyan-400 focus:ring-offset-2"
          >
            So loslegen
          </Button>
        </div>
      </div>
    </section>
  );
}
