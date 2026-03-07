"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { ChatMeta, RagSource } from "@/types/chatMeta";

type QualityMetaPanelProps = {
  meta: ChatMeta | null | undefined;
};

const formatPercent = (value?: number): string | null => {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return `${Math.round(value * 100)}%`;
};

const humanizeAgent = (raw?: string): string => {
  if (!raw) return "Agent";
  const cleaned = raw.replace(/_/g, " ").trim();
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
};

const parseCritique = (text?: string) => {
  if (!text) return { bullets: [] as string[], plain: "" };
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => Boolean(line));

  const bulletCandidates = lines
    .map((line) => line.replace(/^[-•\d.)\s]+/, "").trim())
    .filter((line) => line.length > 0);

  const hasListMarkers = lines.some((line) => /^[-•\d.)\s]+/.test(line));
  if (hasListMarkers && bulletCandidates.length > 0) {
    return { bullets: bulletCandidates, plain: "" };
  }
  return { bullets: [], plain: lines.join(" ") };
};

const SectionHeader = ({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) => (
  <div className="flex items-center justify-between text-xs font-semibold text-gray-700">
    <span>{title}</span>
    {action}
  </div>
);

const Pill = ({ children }: { children: ReactNode }) => (
  <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-700">
    {children}
  </span>
);

export default function QualityMetaPanel({ meta }: QualityMetaPanelProps) {
  const [showCritique, setShowCritique] = useState(false);
  const [showImprovedAnswer, setShowImprovedAnswer] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">(
    "idle",
  );

  const critique = useMemo(
    () => parseCritique(meta?.quality?.critique),
    [meta?.quality?.critique],
  );

  const improvedAnswer = meta?.quality?.improved_answer?.trim() || "";
  const approved = meta?.quality?.approved === true;
  const qualityConfidence = formatPercent(meta?.quality?.confidence);
  const routingConfidence = formatPercent(meta?.routing?.confidence);

  const ragSources = Array.isArray(meta?.ragSources) ? meta.ragSources : [];
  const normalizedSources = ragSources
    .map((source): RagSource | null => {
      if (!source) return null;
      if (typeof source === "string") {
        const label = source.trim();
        if (!label) return null;
        return { document_id: label, source: label };
      }
      if (typeof source !== "object") return null;
      const raw = source as RagSource;
      const documentId =
        typeof raw.document_id === "string" && raw.document_id.trim()
          ? raw.document_id.trim()
          : "";
      return {
        document_id: documentId,
        sha256: typeof raw.sha256 === "string" ? raw.sha256 : null,
        filename: typeof raw.filename === "string" ? raw.filename : null,
        page: typeof raw.page === "number" ? raw.page : null,
        section: typeof raw.section === "string" ? raw.section : null,
        score: typeof raw.score === "number" ? raw.score : null,
        source: typeof raw.source === "string" ? raw.source : null,
      };
    })
    .filter((source): source is RagSource => Boolean(source));

  const contributors = Array.isArray(meta?.contributors)
    ? meta.contributors.filter((entry) => Boolean(entry?.agent))
    : [];

  const warmupRapport = meta?.warmup?.rapport?.trim() || "";
  const warmupMood = meta?.warmup?.user_mood?.trim() || "";
  const warmupReady = meta?.warmup?.ready_for_analysis;
  const hasWarmup = Boolean(warmupRapport || warmupMood);

  useEffect(() => {
    if (copyState !== "copied") return;
    const timeout = window.setTimeout(() => setCopyState("idle"), 2000);
    return () => window.clearTimeout(timeout);
  }, [copyState]);

  const handleCopy = async () => {
    if (!improvedAnswer) return;
    if (!navigator?.clipboard?.writeText) {
      setCopyState("error");
      return;
    }
    try {
      await navigator.clipboard.writeText(improvedAnswer);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  if (!meta) return null;

  const statusLabel = approved ? "✅ Quality Gate PASS" : "⚠️ Quality Gate REVIEW";
  const statusTone = approved
    ? "text-emerald-700 bg-emerald-50"
    : "text-amber-700 bg-amber-50";

  const hasAnyDetail =
    Boolean(critique.bullets.length || critique.plain) ||
    Boolean(improvedAnswer) ||
    Boolean(routingConfidence || meta.routing?.domain) ||
    normalizedSources.length > 0 ||
    contributors.length > 0 ||
    hasWarmup;

  if (!hasAnyDetail && !meta.quality) {
    return null;
  }

  return (
    <div className="mx-auto mt-4 w-full max-w-[768px] px-4">
      <div className="rounded-2xl border border-gray-200 bg-white/80 px-5 py-4 text-sm text-gray-800 shadow-sm backdrop-blur">
        <div className="flex items-start justify-between gap-3">
          <div
            className={`rounded-full px-3 py-1 text-xs font-semibold ${statusTone}`}
          >
            {statusLabel}
            {qualityConfidence ? (
              <span className="ml-1 font-normal text-gray-600">
                ({qualityConfidence})
              </span>
            ) : null}
          </div>
          <span className="text-[11px] uppercase tracking-wide text-gray-400">
            LangGraph Insights
          </span>
        </div>

        {hasWarmup ? (
          <div className="mt-4 border-t border-gray-100 pt-4">
            <SectionHeader title="Einstiegsgespräch" />
            {warmupRapport ? (
              <p className="mt-2 text-xs text-gray-700">{warmupRapport}</p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-500">
              {warmupMood ? <Pill>Stimmung: {warmupMood}</Pill> : null}
              <Pill>
                Status:{" "}
                {warmupReady === false
                  ? "wartet noch auf Details"
                  : "bereit für Analyse"}
              </Pill>
            </div>
          </div>
        ) : null}

        {critique.bullets.length > 0 || critique.plain ? (
          <div className="mt-4 border-t border-gray-100 pt-4">
            <SectionHeader
              title="Kritikpunkte"
              action={
                <button
                  type="button"
                  onClick={() => setShowCritique((v) => !v)}
                  className="text-[11px] font-medium text-gray-500 hover:text-gray-700"
                >
                  {showCritique ? "ausblenden" : "Details einblenden"}
                </button>
              }
            />
            {showCritique ? (
              critique.bullets.length > 0 ? (
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-gray-700">
                  {critique.bullets.map((point, idx) => (
                    <li key={`critique-${idx}`}>{point}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-gray-700">{critique.plain}</p>
              )
            ) : null}
          </div>
        ) : null}

        {improvedAnswer ? (
          <div className="mt-4 border-t border-gray-100 pt-4">
            <SectionHeader
              title="Verbesserte Antwort des Quality-Gate-Agenten"
              action={
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setShowImprovedAnswer((v) => !v)}
                    className="text-[11px] font-medium text-gray-500 hover:text-gray-700"
                  >
                    {showImprovedAnswer ? "verbergen" : "anzeigen"}
                  </button>
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="text-[11px] font-medium text-gray-500 hover:text-gray-700"
                  >
                    {copyState === "copied"
                      ? "Kopiert ✓"
                      : copyState === "error"
                        ? "Kopieren nicht möglich"
                        : "Antwort kopieren"}
                  </button>
                </div>
              }
            />
            {showImprovedAnswer ? (
              <div className="mt-2 whitespace-pre-wrap rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-800">
                {improvedAnswer}
              </div>
            ) : null}
          </div>
        ) : null}

        {routingConfidence || meta.routing?.domain ? (
          <div className="mt-4 border-t border-gray-100 pt-4 text-xs text-gray-700">
            <SectionHeader title="Routing" />
            <div className="mt-2 flex flex-wrap gap-2">
              {routingConfidence ? (
                <Pill>Confidence: {routingConfidence}</Pill>
              ) : null}
              {meta.routing?.domain ? (
                <Pill>Domäne: {String(meta.routing.domain)}</Pill>
              ) : null}
            </div>
          </div>
        ) : null}

        {normalizedSources.length > 0 ? (
          <div className="mt-4 border-t border-gray-100 pt-4">
            <SectionHeader title="Quellen" />
            <div className="mt-2 space-y-2 text-xs text-gray-700">
              {normalizedSources.slice(0, 6).map((source, idx) => {
                const label =
                  (source.filename && source.filename.trim()) ||
                  (source.document_id && source.document_id.trim()) ||
                  "Quelle";
                const details = [
                  source.section ? `Abschnitt: ${source.section}` : null,
                  typeof source.page === "number" ? `Seite ${source.page}` : null,
                  typeof source.score === "number" ? `Score ${source.score.toFixed(2)}` : null,
                  source.source ? `Quelle: ${source.source}` : null,
                ].filter(Boolean);
                return (
                  <div
                    key={`source-${idx}`}
                    className="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2"
                  >
                    <div className="font-semibold text-gray-800">{label}</div>
                    {details.length > 0 ? (
                      <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-gray-500">
                        {details.map((detail, detailIdx) => (
                          <span key={`detail-${idx}-${detailIdx}`}>{detail}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                );
              })}
              {normalizedSources.length > 6 ? (
                <span className="text-xs text-gray-500">
                  +{normalizedSources.length - 6} weitere
                </span>
              ) : null}
            </div>
          </div>
        ) : null}

        {contributors.length > 0 ? (
          <div className="mt-4 border-t border-gray-100 pt-4">
            <SectionHeader title="Beteiligte Agenten" />
            <div className="mt-2 flex flex-wrap gap-2">
              {contributors.map((contrib, idx) => {
                const conf = formatPercent(contrib.confidence);
                return (
                  <Pill key={`contrib-${idx}`}>
                    {humanizeAgent(contrib.agent)}
                    {contrib.role ? ` · ${contrib.role}` : ""}
                    {conf ? ` (${conf})` : ""}
                  </Pill>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
