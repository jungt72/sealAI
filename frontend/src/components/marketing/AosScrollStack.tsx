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
    points: ["freie Eingabe", "unklare Angaben erlaubt"],
    action: "Falltext prüfen",
    icon: BrainCircuit,
  },
  {
    title: "Geführte Klärung",
    body: "Der Agent fragt nicht alles ab, sondern priorisiert die Lücke, die für Material, Bauform oder Herstellerprüfung wirklich zählt.",
    points: ["nächste Frage", "keine Checklistenflut"],
    action: "Lücke priorisieren",
    icon: Network,
  },
  {
    title: "Betriebsdaten",
    body: "Temperatur, Druck, Bewegung, Reinigung, Konzentration und Medienwechsel werden als prüfbare Fallparameter gesammelt.",
    points: ["Parameter sammeln", "Betriebspunkt trennen"],
    action: "Daten ordnen",
    icon: Database,
  },
  {
    title: "Medien & Werkstoffe",
    body: "EPDM, FKM, NBR, PTFE und andere Optionen werden im Kontext gelesen, nicht als vorschnelle Produktantwort.",
    points: ["Medium einordnen", "Werkstoffgrenzen sehen"],
    action: "Materialkontext prüfen",
    icon: BookOpen,
  },
  {
    title: "Dichtungssystem",
    body: "Dichtungstyp, Einbauraum, Bewegung, Oberfläche, Schadensbild und Anwendung werden als zusammenhängendes System betrachtet.",
    points: ["System statt Einzelwert", "Schadensbild sichtbar"],
    action: "System prüfen",
    icon: Layers3,
  },
  {
    title: "Anfragebasis",
    body: "Bekanntes, Geschätztes und Offenes werden so getrennt, dass Einkauf, Engineering oder Hersteller direkt weiterarbeiten können.",
    points: ["bekannt / geschätzt / offen", "Übergabe vorbereiten"],
    action: "Anfrage strukturieren",
    icon: MessageSquareText,
  },
  {
    title: "Governance",
    body: "Keine heimliche Weitergabe, keine Freigabe-Claims und keine Verwechslung von Orientierung mit Herstellerprüfung.",
    points: ["keine Scheinsicherheit", "bewusste Übergabe"],
    action: "Grenzen anzeigen",
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
      const settle = smoothstep((progress - 0.62) / 0.24);
      const fan = Math.sin(index * 1.7) * 58 * (1 - settle);
      const y = mix(196 - index * 4, 58 - index * 13, reveal);
      const rotateZ = mix(-36 + index * 2.8 + fan * 0.08, -28, settle);
      const rotateX = mix(68, 60, settle);
      const scale = mix(0.82, 1.16 - index * 0.012, reveal);
      const opacity = mix(index === 0 ? 0.78 : 0, 1, reveal);
      return { layer, y, rotateZ, rotateX, scale, opacity, reveal, zIndex: index + 2 };
    });
  }, [progress]);

  const modulesProgress = smoothstep((progress - 0.42) / 0.22);
  const governanceProgress = smoothstep((progress - 0.72) / 0.18);
  const finalBoxProgress = smoothstep((progress - 0.78) / 0.18);

  return (
    <section ref={sectionRef} className="relative h-[660vh] bg-[#FAFAF9]">
      <div className="sticky top-[72px] h-[calc(100vh-72px)] overflow-hidden bg-[#FAFAF9]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_58%_42%,rgba(255,255,255,0.96),rgba(250,250,249,0.72)_36%,rgba(214,216,214,0.82)_100%)]" />

        <div className="absolute left-4 top-6 z-20 flex w-[min(82vw,440px)] flex-col gap-2 sm:left-8 sm:top-10">
          {layers.map((layer, index) => {
            const active = index === activeIndex;
            return (
              <div
                key={layer.title}
                className={`relative overflow-hidden rounded-[18px] px-4 transition-[width,max-height,padding,box-shadow,transform,background-color] duration-300 ease-out will-change-transform ${
                  active
                    ? "max-h-[260px] w-full border border-white/70 bg-white/76 py-4 text-[#121719] backdrop-blur-md"
                    : "max-h-10 w-[min(54%,238px)] border border-white/50 bg-[#f7f7f8]/92 py-1.5 text-[#17201f]/76"
                }`}
                style={{
                  boxShadow: active
                    ? "10px 18px 34px rgba(20,24,24,0.18), inset 0 1px 0 rgba(255,255,255,0.86)"
                    : "2px 2px 6px rgba(20,24,24,0.08), -2px -2px 6px rgba(255,255,255,0.86)",
                  transform: active ? "translateX(6px)" : "translateX(0)",
                }}
              >
                {active ? (
                  <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(130deg,rgba(255,255,255,0.78),rgba(116,116,116,0.08)_58%,rgba(255,255,255,0.36))]" />
                ) : null}
                <div className="flex items-center justify-between gap-3">
                  <span className={`relative truncate font-semibold ${active ? "text-[18px] text-[#111517] sm:text-[21px]" : "text-[11px]"}`}>
                    {layer.title}
                  </span>
                  <ChevronRight
                    size={active ? 18 : 12}
                    strokeWidth={2}
                    className={`relative shrink-0 transition-transform duration-300 ${active ? "rotate-90 text-[#747474]" : "text-[#17201f]/35"}`}
                  />
                </div>
                <div
                  className={`grid transition-all duration-300 ease-out ${
                    active ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
                  }`}
                >
                  <div className="relative overflow-hidden">
                    <p className="pt-3 text-[13px] leading-6 text-[#17201f]/64 sm:text-[14px]">
                      {layer.body}
                    </p>
                    <div className="mt-4 grid gap-2 text-[12px] font-semibold text-[#17201f]/78 sm:grid-cols-2">
                      {layer.points.map((point, pointIndex) => (
                        <div key={point} className="flex items-center gap-2">
                          <span
                            className={`h-2 w-2 rounded-full ${
                              pointIndex === 0 ? "bg-[#002A5B]" : "bg-[#747474]"
                            }`}
                          />
                          <span>{point}</span>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4 flex justify-end">
                      <span className="rounded-full bg-[#002A5B] px-4 py-2 text-[12px] font-semibold text-white shadow-[0_8px_18px_rgba(0,42,91,0.22)]">
                        {layer.action}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="absolute left-1/2 top-6 z-20 hidden -translate-x-1/2 rounded-full bg-[#17201f]/36 px-4 py-1 text-[10px] font-semibold text-white/90 sm:block">
          Analysing sealing context...
        </div>

        <div className="absolute inset-0 flex items-center justify-center px-5 lg:justify-end lg:pr-[7vw]">
          <div className="relative h-[62vh] min-h-[390px] w-[min(92vw,980px)] lg:w-[min(62vw,900px)]">
            <div
              className="absolute left-1/2 top-1/2 h-[43%] w-[76%] rounded-[28px] border border-[#17201f]/10 bg-[#f7f7f5] shadow-[0_54px_120px_rgba(20,24,24,0.22)]"
              style={{
                opacity: finalBoxProgress,
                transform: [
                  "translate(-50%, -50%)",
                  "translate3d(0, 64px, 0)",
                  "perspective(920px) rotateX(60deg) rotateZ(-28deg)",
                  `scale(${mix(0.94, 1.04, finalBoxProgress)})`,
                ].join(" "),
              }}
            >
              <div className="absolute inset-0 rounded-[28px] bg-[linear-gradient(135deg,rgba(255,255,255,0.95),rgba(210,214,212,0.58)_54%,rgba(140,147,144,0.28))]" />
              <div className="absolute inset-x-[12%] top-[18%] h-1.5 rounded-full bg-[#17201f]/10" />
              <div className="absolute bottom-[16%] left-[14%] flex gap-2">
                <span className="h-2 w-8 rounded-full bg-[#17201f]/16" />
                <span className="h-2 w-2 rounded-full bg-[#002A5B]/45" />
              </div>
              <div className="absolute inset-x-[7%] bottom-[-16%] h-[28%] rounded-b-[26px] bg-[linear-gradient(180deg,rgba(186,191,189,0.82),rgba(118,126,122,0.42))] blur-[0.2px]" />
            </div>
            {plateStates.map(({ layer, y, rotateZ, rotateX, scale, opacity, reveal, zIndex }, index) => {
              const Icon = layer.icon;
              const isGovernance = index === layers.length - 1;
              return (
                <div
                  key={layer.title}
                  className="absolute left-1/2 top-1/2 h-[38%] w-[72%] rounded-[18px] border shadow-[0_42px_95px_rgba(20,24,24,0.2)] will-change-transform"
                  style={{
                    zIndex,
                    opacity,
                    borderColor: isGovernance
                      ? `rgba(255,255,255,${0.58 + governanceProgress * 0.34})`
                      : "rgba(160,166,163,0.9)",
                    backgroundColor: isGovernance
                      ? `rgba(255,255,255,${0.72 + governanceProgress * 0.2})`
                      : `rgba(${224 + index * 2}, ${226 + index * 2}, ${224 + index * 2}, ${0.86 + reveal * 0.1})`,
                    transform: [
                      "translate(-50%, -50%)",
                      `translate3d(0, ${mix(y, 66 - index * 7, finalBoxProgress)}px, 0)`,
                      `perspective(860px) rotateX(${rotateX}deg) rotateZ(${rotateZ}deg) scale(${scale})`,
                    ].join(" "),
                  }}
                >
                  <div className="absolute inset-0 rounded-[18px] bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(255,255,255,0.2)_48%,rgba(20,24,24,0.1))]" />
                  <div className="absolute inset-x-[5%] bottom-[-13%] h-[18%] rounded-b-[18px] bg-[linear-gradient(180deg,rgba(151,158,155,0.5),rgba(82,91,87,0.24))]" />
                  <div className="absolute left-[6%] top-[13%] flex items-center gap-2 rounded-full bg-white/62 px-3 py-1 text-[10px] font-bold text-[#002A5B]/72 shadow-sm">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                  <div className="absolute inset-0 flex items-center justify-center px-8">
                    <div className="flex max-w-[88%] items-center gap-3 text-center text-[12px] font-bold uppercase tracking-[0.06em] text-[#17201f]/54 sm:text-[16px]">
                      <Icon size={18} strokeWidth={1.8} className="shrink-0 text-[#002A5B]/58" />
                      {isGovernance && governanceProgress > 0.45 ? "aOS" : layer.title}
                    </div>
                  </div>
                </div>
              );
            })}

            <div
              className="absolute left-1/2 top-[7%] grid grid-cols-4 gap-2 will-change-transform sm:gap-3"
              style={{
                opacity: modulesProgress * (1 - governanceProgress * 0.2),
                transform: `translate(-50%, ${mix(-125, -18, modulesProgress)}px) perspective(780px) rotateX(58deg) rotateZ(-28deg) scale(${mix(0.86, 1.08, modulesProgress)})`,
              }}
            >
              {Array.from({ length: 12 }).map((_, index) => (
                <span
                  key={index}
                  className="flex h-9 w-14 items-center justify-center rounded-[6px] border border-white/80 bg-white/84 shadow-[0_20px_38px_rgba(20,24,24,0.14)] sm:h-14 sm:w-20"
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
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#002A5B] text-white">
                <ActiveIcon size={17} />
              </span>
              <h3 className="text-[15px] font-semibold text-[#17201f]">{activeLayer.title}</h3>
            </div>
            <p className="text-[13px] leading-6 text-[#17201f]/65">{activeLayer.body}</p>
          </div>
        </div>

      </div>
    </section>
  );
}
