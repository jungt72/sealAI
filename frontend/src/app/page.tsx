import Navbar from "@/components/landing/Navbar";
import HeroSection from "@/components/landing/HeroSection";
import FeatureCards from "@/components/landing/FeatureCards";

export default function Home() {
  return (
    <main className="relative min-h-screen bg-seal-command font-body text-slate-300">
      {/* Subtle engineering-grid overlay — CSS only, no image */}
      <div
        className="pointer-events-none fixed inset-0 -z-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(27,38,59,0.45) 1px, transparent 1px), " +
            "linear-gradient(90deg, rgba(27,38,59,0.45) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
      />

      <Navbar />
      <HeroSection />
      <FeatureCards />

      <footer className="relative border-t border-white/[0.05] px-6 py-5 text-center font-body text-xs text-slate-700">
        © 2026 SealAI GmbH · B2B Industrial AI Platform ·{" "}
        <a
          href="/dashboard"
          className="ml-1 text-slate-600 transition hover:text-slate-400"
        >
          Dashboard
        </a>
      </footer>
    </main>
  );
}
