"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  BrainCircuit,
  ChevronRight,
  Database,
  FileCheck2,
  Layers3,
  LockKeyhole,
  MessageSquareText,
  Network,
  ShieldCheck,
} from "lucide-react";

const layers = [
  {
    title: "Freie Fallbeschreibung",
    body: "Der Anwender beschreibt Leckage, Medium, Anlage oder Schadensbild in normalen Worten. Unvollständige Angaben sind ausdrücklich erlaubt.",
    icon: BrainCircuit,
  },
  {
    title: "Geführte Klärung",
    body: "Der Agent fragt nicht alles ab, sondern priorisiert die Lücke, die für Material, Bauform oder Herstellerprüfung wirklich zählt.",
    icon: Network,
  },
  {
    title: "Betriebsdaten",
    body: "Temperatur, Druck, Bewegung, Reinigung, Konzentration und Medienwechsel werden als prüfbare Fallparameter gesammelt.",
    icon: Database,
  },
  {
    title: "Medien & Werkstoffe",
    body: "EPDM, FKM, NBR, PTFE und andere Optionen werden im Kontext gelesen, nicht als vorschnelle Produktantwort.",
    icon: BookOpen,
  },
  {
    title: "Dichtungssystem",
    body: "Dichtungstyp, Einbauraum, Bewegung, Oberfläche, Schadensbild und Anwendung werden als zusammenhängendes System betrachtet.",
    icon: Layers3,
  },
  {
    title: "Anfragebasis",
    body: "Bekanntes, Geschätztes und Offenes werden so getrennt, dass Einkauf, Engineering oder Hersteller direkt weiterarbeiten können.",
    icon: MessageSquareText,
  },
  {
    title: "Governance",
    body: "Keine heimliche Weitergabe, keine Freigabe-Claims und keine Verwechslung von Orientierung mit Herstellerprüfung.",
    icon: ShieldCheck,
  },
];

function clamp(value: number, min = 0, max = 1) {
  return Math.min(max, Math.max(min, value));
}

function mix(from: number, to: number, progress: number) {
  return from + (to - from) * progress;
}

function smoothstep(value: number) {
  const x = clamp(value);
  return x * x * (3 - 2 * x);
}

export function AosMiniStack() {
  return (
    <div className="relative h-full min-h-[260px] w-full overflow-hidden bg-[#ececea]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_35%,rgba(255,255,255,0.95),rgba(236,236,234,0.4)_42%,rgba(214,216,214,0.72)_100%)]" />
      <div className="absolute left-1/2 top-1/2 h-40 w-56 -translate-x-1/2 -translate-y-1/2">
        {Array.from({ length: 6 }).map((_, index) => (
          <div
            key={index}
            className="absolute left-1/2 top-1/2 h-24 w-44 rounded-sm border border-white/80 bg-white/68 shadow-[0_24px_48px_rgba(20,24,24,0.14)] [transform:translate(-50%,-50%)_perspective(760px)_rotateX(62deg)_rotateZ(-28deg)]"
            style={{ marginTop: `${28 - index * 11}px`, zIndex: index + 1 }}
          />
        ))}
      </div>
    </div>
  );
}

export function AosScrollStack() {
  const sectionRef = useRef<HTMLElement | null>(null);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    let frame = 0;
    const update = () => {
      frame = 0;
      const rect = section.getBoundingClientRect();
      const scrollable = Math.max(1, rect.height - window.innerHeight);
      setProgress(clamp(-rect.top / scrollable));
    };

    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const activeIndex = Math.min(layers.length - 1, Math.floor(progress * layers.length));
  const activeLayer = layers[activeIndex];
  const ActiveIcon = activeLayer.icon;

  const plateStates = useMemo(() => {
    return layers.map((layer, index) => {
      const reveal = smoothstep((progress - index * 0.105) / 0.18);
      const settle = smoothstep((progress - 0.66) / 0.2);
      const fan = Math.sin(index * 1.7) * 46 * (1 - settle);
      const y = mix(170 - index * 2, 20 - index * 15, reveal);
      const rotateZ = mix(-35 + index * 2.5 + fan * 0.08, -28, settle);
      const rotateX = mix(70, 62, settle);
      const scale = mix(0.78, 1.03 - index * 0.018, reveal);
      const opacity = mix(index === 0 ? 0.75 : 0, 1, reveal);
      return { layer, y, rotateZ, rotateX, scale, opacity, reveal, zIndex: index + 2 };
    });
  }, [progress]);

  const modulesProgress = smoothstep((progress - 0.42) / 0.22);
  const governanceProgress = smoothstep((progress - 0.72) / 0.18);

  return (
    <section ref={sectionRef} className="relative h-[660vh] bg-white">
      <div className="sticky top-[72px] h-[calc(100vh-72px)] overflow-hidden bg-[#ececea]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(255,255,255,0.98),rgba(236,236,234,0.45)_38%,rgba(207,210,208,0.82)_100%)]" />

        <div className="absolute left-4 top-6 z-20 flex w-[min(72vw,340px)] flex-col gap-3 sm:left-8 sm:top-10">
          {layers.map((layer, index) => {
            const active = index === activeIndex;
            return (
              <div
                key={layer.title}
                className="flex items-center justify-between rounded-2xl bg-[#f3f4f7] px-5 py-3.5 transition-all duration-300 will-change-transform"
                style={{
                  boxShadow: active
                    ? "8px 8px 18px rgba(20,24,24,0.20), -6px -6px 15px rgba(255,255,255,0.95)"
                    : "5px 5px 13px rgba(20,24,24,0.12), -5px -5px 12px rgba(255,255,255,0.9)",
                  transform: active ? "translateX(12px) scale(1.025)" : "translateX(0) scale(1)",
                }}
              >
                <span className={`text-[15px] font-semibold ${active ? "text-[#002a5b]" : "text-[#17201f]"}`}>
                  {layer.title}
                </span>
                <ChevronRight size={18} strokeWidth={2} className={active ? "text-[#002a5b]" : "text-[#17201f]/40"} />
              </div>
            );
          })}
        </div>

        <div className="absolute left-1/2 top-6 z-20 hidden -translate-x-1/2 rounded-full bg-[#17201f]/36 px-4 py-1 text-[10px] font-semibold text-white/90 sm:block">
          Analysing sealing context...
        </div>

        <div className="absolute inset-0 flex items-center justify-center">
          <div className="relative h-[52vh] min-h-[310px] w-[min(78vw,780px)]">
            {plateStates.map(({ layer, y, rotateZ, rotateX, scale, opacity, reveal, zIndex }, index) => {
              const Icon = layer.icon;
              const isGovernance = index === layers.length - 1;
              return (
                <div
                  key={layer.title}
                  className="absolute left-1/2 top-1/2 h-[42%] w-[68%] rounded-[3px] border shadow-[0_42px_95px_rgba(20,24,24,0.18)] will-change-transform"
                  style={{
                    zIndex,
                    opacity,
                    borderColor: isGovernance
                      ? `rgba(255,255,255,${0.45 + governanceProgress * 0.45})`
                      : "rgba(181,186,184,0.9)",
                    backgroundColor: isGovernance
                      ? `rgba(255,255,255,${0.62 + governanceProgress * 0.28})`
                      : `rgba(${217 + index * 3}, ${220 + index * 3}, ${218 + index * 3}, ${0.72 + reveal * 0.12})`,
                    transform: [
                      "translate(-50%, -50%)",
                      `translate3d(${mix(0, 0, reveal)}px, ${y}px, 0)`,
                      `perspective(860px) rotateX(${rotateX}deg) rotateZ(${rotateZ}deg) scale(${scale})`,
                    ].join(" "),
                  }}
                >
                  <div className="absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.82),rgba(255,255,255,0.08)_48%,rgba(20,24,24,0.1))]" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="flex items-center gap-2 text-[10px] font-semibold uppercase text-[#17201f]/30 sm:text-[13px]">
                      <Icon size={15} strokeWidth={1.6} />
                      {isGovernance && governanceProgress > 0.45 ? "aOS" : layer.title}
                    </div>
                  </div>
                </div>
              );
            })}

            <div
              className="absolute left-1/2 top-[8%] grid grid-cols-4 gap-2 will-change-transform sm:gap-3"
              style={{
                opacity: modulesProgress * (1 - governanceProgress * 0.2),
                transform: `translate(-50%, ${mix(-120, -12, modulesProgress)}px) perspective(780px) rotateX(58deg) rotateZ(-28deg) scale(${mix(0.82, 1, modulesProgress)})`,
              }}
            >
              {Array.from({ length: 12 }).map((_, index) => (
                <span
                  key={index}
                  className="flex h-8 w-12 items-center justify-center rounded-[2px] border border-white/75 bg-white/72 shadow-[0_20px_38px_rgba(20,24,24,0.12)] sm:h-12 sm:w-16"
                  style={{ transform: `translateY(${Math.sin(index) * 5}px)` }}
                >
                  {index % 3 === 0 ? <Database size={13} /> : index % 3 === 1 ? <FileCheck2 size={13} /> : <LockKeyhole size={13} />}
                </span>
              ))}
            </div>
          </div>
        </div>

        <div
          className="absolute inset-x-0 bottom-0 z-30 border-t border-white/60 bg-white/80 px-5 py-5 shadow-[0_-20px_55px_rgba(20,24,24,0.08)] backdrop-blur-md transition-opacity duration-300 sm:px-8"
          style={{ opacity: progress > 0.12 && progress < 0.92 ? 1 : 0 }}
        >
          <div className="mx-auto grid max-w-[980px] gap-4 sm:grid-cols-[210px_1fr] sm:items-start">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#004a2f] text-white">
                <ActiveIcon size={17} />
              </span>
              <h3 className="text-[15px] font-semibold text-[#17201f]">{activeLayer.title}</h3>
            </div>
            <p className="text-[13px] leading-6 text-[#17201f]/65">{activeLayer.body}</p>
          </div>
        </div>

        <div
          className="absolute bottom-6 right-6 z-20 hidden rounded-full border border-[#17201f]/15 bg-white/72 px-4 py-1.5 text-[11px] font-semibold text-[#17201f]/55 backdrop-blur sm:block"
          style={{ opacity: smoothstep((progress - 0.86) / 0.12) }}
        >
          sealingAI aOS verstehen
        </div>
      </div>
    </section>
  );
}
