"use client";

/**
 * Deterministic hero precheck card — NO LLM, NO recommendation.
 * Runs evaluatePrecheck() locally, shows a compact readiness result and hands the
 * captured input to the auth-gated analysis via localStorage before navigating.
 */

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowRight, Gauge, Lock } from "lucide-react";

import {
  evaluatePrecheck,
  formatSpeedDe,
  type HeroPrecheckInput,
  type SealType,
  type Situation,
} from "@/lib/hero-precheck/precheck";
import { ANALYZE_HREF, TEASER_STORAGE_KEY } from "@/lib/marketing/homeContent";

const SEAL_TYPES: { value: SealType; label: string }[] = [
  { value: "rwdr", label: "RWDR" },
  { value: "o_ring", label: "O-Ring" },
  { value: "hydraulic_seal", label: "Hydraulikdichtung" },
  { value: "ptfe_part", label: "PTFE-Teil" },
  { value: "unknown", label: "Unbekannt" },
];

const SITUATIONS: { value: Situation; label: string }[] = [
  { value: "replacement", label: "Ersatz" },
  { value: "leakage", label: "Leckage" },
  { value: "new_design", label: "Neuauslegung" },
  { value: "material_question", label: "Materialfrage" },
];

/** Deterministic, locale-tolerant integer parse ("45 mm" → 45, "1.500 U/min" → 1500). */
function parseIntish(raw: string): number | undefined {
  const digits = raw.replace(/[^\d]/g, "");
  if (digits.length === 0) return undefined;
  const n = Number.parseInt(digits, 10);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

const TONE: Record<string, string> = {
  initial: "text-muted-foreground",
  insufficient: "text-[#B45309]",
  critical_unknowns: "text-[#DC2626]",
  preliminary: "text-seal-blue",
  actionable: "text-[#15803D]",
};

export function HeroPrecheckCard() {
  const router = useRouter();
  const [sealType, setSealType] = useState<SealType | "">("");
  const [situation, setSituation] = useState<Situation | "">("");
  const [medium, setMedium] = useState("");
  const [shaft, setShaft] = useState("");
  const [rpm, setRpm] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const input: HeroPrecheckInput = useMemo(
    () => ({
      sealType: sealType || undefined,
      situation: situation || undefined,
      medium: medium.trim() || undefined,
      shaftDiameterMm: parseIntish(shaft),
      rpm: parseIntish(rpm),
    }),
    [sealType, situation, medium, shaft, rpm],
  );

  const result = useMemo(() => evaluatePrecheck(input), [input]);

  function handleContinue() {
    try {
      const state = {
        source: "homepage_teaser",
        sealType: input.sealType,
        situation: input.situation,
        medium: input.medium,
        shaftDiameterMm: input.shaftDiameterMm,
        rpm: input.rpm,
        calculated: { circumferentialSpeedMs: result.circumferentialSpeedMs },
      };
      window.localStorage.setItem(TEASER_STORAGE_KEY, JSON.stringify(state));
    } catch {
      // localStorage may be unavailable (private mode) — the analysis still works,
      // it just won't be prefilled. TODO(frontend-v2): read TEASER_STORAGE_KEY on /dashboard/new.
    }
    router.push(ANALYZE_HREF);
  }

  const selectClass =
    "w-full rounded-[12px] border border-border bg-white px-3 py-2.5 text-[14px] text-foreground outline-none transition focus:border-seal-blue focus:ring-2 focus:ring-seal-blue/15";

  return (
    <div className="w-full rounded-xl border border-border bg-white p-5 sm:p-6">
      <div className="flex items-center gap-2 text-seal-blue">
        <Gauge size={18} strokeWidth={1.6} aria-hidden />
        <h2 className="text-[15px] font-semibold text-foreground">Dichtungsfall vorprüfen</h2>
      </div>
      <p className="mt-1.5 text-[13px] leading-6 text-muted-foreground">
        Prüfen Sie in wenigen Sekunden, ob Ihr Fall bereits technisch bewertbar ist.
      </p>

      <form
        className="mt-5 grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(true);
        }}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5">
            <span className="text-[12px] font-medium text-muted-foreground">Dichtungstyp</span>
            <select
              className={selectClass}
              value={sealType}
              onChange={(e) => setSealType(e.target.value as SealType | "")}
            >
              <option value="">Bitte wählen</option>
              {SEAL_TYPES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1.5">
            <span className="text-[12px] font-medium text-muted-foreground">Situation</span>
            <select
              className={selectClass}
              value={situation}
              onChange={(e) => setSituation(e.target.value as Situation | "")}
            >
              <option value="">Bitte wählen</option>
              {SITUATIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="grid gap-1.5">
          <span className="text-[12px] font-medium text-muted-foreground">Medium</span>
          <input
            className={selectClass}
            type="text"
            inputMode="text"
            placeholder="z. B. Hydrauliköl"
            value={medium}
            onChange={(e) => setMedium(e.target.value)}
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1.5">
            <span className="text-[12px] font-medium text-muted-foreground">Wellendurchmesser</span>
            <input
              className={selectClass}
              type="text"
              inputMode="numeric"
              placeholder="45 mm"
              value={shaft}
              onChange={(e) => setShaft(e.target.value)}
            />
          </label>
          <label className="grid gap-1.5">
            <span className="text-[12px] font-medium text-muted-foreground">Drehzahl</span>
            <input
              className={selectClass}
              type="text"
              inputMode="numeric"
              placeholder="1.500 U/min"
              value={rpm}
              onChange={(e) => setRpm(e.target.value)}
            />
          </label>
        </div>

        <button
          type="submit"
          className="mt-1 inline-flex h-11 items-center justify-center gap-2 rounded-full bg-seal-blue px-5 text-[14px] font-semibold text-white transition hover:bg-seal-blue/92 active:translate-y-px"
        >
          Vorcheck starten
          <ArrowRight size={16} />
        </button>
      </form>

      {submitted && result.status !== "initial" && (
        <div
          className="mt-5 rounded-[14px] border border-border bg-[#FAFAFB] p-4"
          aria-live="polite"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className={`text-[13px] font-semibold ${TONE[result.status]}`}>{result.statusLabel}</span>
            <span className="rounded-full border border-border bg-white px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
              Datenqualität: {result.dataQualityLabel}
            </span>
          </div>

          {result.circumferentialSpeedMs !== undefined && (
            <div className="mt-3 flex items-baseline gap-2 border-t border-border pt-3">
              <span className="text-[12px] text-muted-foreground">Umfangsgeschwindigkeit</span>
              <span className="text-[22px] font-normal leading-none text-seal-blue">
                {formatSpeedDe(result.circumferentialSpeedMs)}
              </span>
              <span className="text-[12px] text-muted-foreground">m/s</span>
            </div>
          )}

          {result.missingPoints.length > 0 && (
            <div className="mt-3 border-t border-border pt-3">
              <p className="text-[12px] font-medium text-muted-foreground">Noch offen</p>
              <ul className="mt-1.5 flex flex-wrap gap-1.5">
                {result.missingPoints.map((point) => (
                  <li
                    key={point}
                    className="rounded-full bg-[#FFF4E5] px-2.5 py-1 text-[11px] font-medium text-[#B45309]"
                  >
                    {point}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="mt-3 text-[12px] leading-5 text-muted-foreground">{result.message}</p>

          <button
            type="button"
            onClick={handleContinue}
            className="mt-4 inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-seal-accent px-5 text-[14px] font-semibold text-white transition hover:brightness-105 active:translate-y-px"
          >
            Kostenlos vollständig analysieren
            <ArrowRight size={16} />
          </button>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-muted-foreground">
            <Lock size={12} aria-hidden />
            Ihre Eingaben werden übernommen. Die vollständige Analyse startet nach dem kostenlosen Login.
          </p>
        </div>
      )}
    </div>
  );
}
