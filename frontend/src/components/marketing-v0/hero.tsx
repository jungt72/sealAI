"use client";

import { Button } from "@/components/ui/Button";

export function Hero() {
    return (
        <section className="relative overflow-hidden bg-[#020410]">
            {/* Ambient Background - Deep Trustworthy Blue */}
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,_var(--tw-gradient-stops))] from-[#0f172a] via-[#020410] to-[#020410] opacity-90" />

            {/* Main Light Source - Sharp Spotlight from Right */}
            <div
                className="absolute top-[30%] -right-[10%] w-[800px] h-[800px] rounded-full blur-[80px] opacity-80"
                style={{
                    background: 'radial-gradient(circle, rgba(255, 255, 255, 0.9) 0%, rgba(100, 180, 255, 0.6) 20%, rgba(30, 64, 175, 0.2) 60%, transparent 100%)',
                    zIndex: 0
                }}
            />

            {/* High Contrast Smoke/Cloud Layers */}
            <div className="absolute inset-0" aria-hidden="true" style={{ zIndex: 1 }}>

                {/* Cloud 1 - Structured "Waben" (Base Layer) - Slower */}
                <div
                    className="absolute top-[-10%] -right-[5%] w-[1300px] h-[1300px] rounded-full blur-[50px] opacity-70"
                    style={{
                        background: 'radial-gradient(circle at 70% 30%, rgba(147, 197, 253, 0.4) 0%, rgba(59, 130, 246, 0.2) 30%, transparent 60%)',
                        animation: 'cloudStructure 40s ease-in-out infinite',
                    }}
                />

                {/* Cloud 2 - Distinct Smoke Detail (Middle Layer) - Faster, sharper */}
                <div
                    className="absolute top-[10%] -right-[15%] w-[1000px] h-[800px] rounded-full blur-[40px] opacity-60"
                    style={{
                        background: 'radial-gradient(ellipse at center, rgba(255, 255, 255, 0.5) 0%, rgba(191, 219, 254, 0.3) 40%, transparent 80%)',
                        animation: 'cloudFlow 25s ease-in-out infinite alternate',
                    }}
                />

                {/* Cloud 3 - Bright Highlights (Top Layer) - Most defined */}
                <div
                    className="absolute top-[20%] -right-[10%] w-[800px] h-[600px] rounded-full blur-[30px] opacity-50"
                    style={{
                        background: 'radial-gradient(circle, rgba(230, 245, 255, 0.6) 0%, rgba(147, 197, 253, 0.2) 50%, transparent 80%)',
                        animation: 'cloudHighlight 20s ease-in-out infinite alternate-reverse',
                    }}
                />
            </div>

            {/* Main Content Container - Matching Header Width [1600px] */}
            <div className="relative z-10 max-w-[1600px] mx-auto px-6 md:px-6 lg:px-6 py-24 md:py-32 lg:py-40">
                {/* Content Block - Aligned to Header Separator (137px offset for exact visual alignment) */}
                <div className="ml-[137px] max-w-7xl">
                    <p className="text-sm font-semibold text-blue-400 mb-4 tracking-wide uppercase">
                        SEALING INTELLIGENCE
                    </p>

                    <h1 className="text-3xl md:text-4xl lg:text-[2.75rem] lg:leading-[1.1] font-semibold mb-6 text-white tracking-tight">
                        Technisch fundierte Dichtungsentscheidungen.{" "}<br className="hidden lg:block" />
                        Digital unterstützt. Nachvollziehbar begründet.
                    </h1>

                    <p className="text-lg md:text-xl text-gray-300 mb-10 leading-relaxed max-w-6xl">
                        SealAI ist der digitale Anwendungstechniker für industrielle Dichtungsauslegung.<br className="hidden lg:block" />
                        Die Plattform analysiert reale Einsatzparameter, schließt ungeeignete Lösungen aus und empfiehlt<br className="hidden lg:block" />
                        technisch belastbare Dichtungen – auf Basis von Normen, Materialdaten und Anwendungspraxis.
                    </p>

                    <div className="flex flex-wrap gap-4">
                        <Button
                            size="lg"
                            className="font-medium rounded-full px-8 py-3 text-[17px] transition-all duration-300 transform hover:scale-[1.02] hover:bg-white hover:text-black"
                            style={{ backgroundColor: 'transparent', border: '1px solid white', color: 'white' }}
                        >
                            Auslegung starten
                        </Button>
                    </div>
                </div>
            </div>

            {/* Global CSS for animations */}
            <style dangerouslySetInnerHTML={{
                __html: `
                @keyframes cloudStructure {
                    0% { transform: translate(0, 0) scale(1) rotate(0deg); }
                    50% { transform: translate(-30px, 10px) scale(1.05) rotate(2deg); }
                    100% { transform: translate(0, 0) scale(1) rotate(0deg); }
                }

                @keyframes cloudFlow {
                    0% { transform: translate(0, 0) scale(1); opacity: 0.6; }
                    100% { transform: translate(-60px, -20px) scale(1.15); opacity: 0.8; }
                }

                @keyframes cloudHighlight {
                    0% { transform: translate(0, 0) scale(1); filter: brightness(1); }
                    100% { transform: translate(-40px, 30px) scale(1.1); filter: brightness(1.2); }
                }
            `}} />
        </section>
    );
}
