"use client";

import React from "react";

export type BedarfsanalyseData = {
  einbausituation?: string;
  rahmenbedingungen?: unknown;
  problem?: string;
  offene_punkte?: unknown;
  confidence?: number;
  [key: string]: unknown;
};

type BedarfsanalyseCardProps = {
  data: BedarfsanalyseData;
};

const isEmptyObject = (value: unknown): boolean => {
  if (!value || typeof value !== "object") return false;
  return Object.keys(value as Record<string, unknown>).length === 0;
};

const formatConfidence = (value?: number): string | null => {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return `${Math.round(value * 100)}%`;
};

const normalizeArray = (value: unknown): string[] => {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value
      .map((v) => String(v).trim())
      .filter((v) => v.length > 0);
  }
  const text = String(value);
  return text
    .split(/\r?\n|[;•-]/)
    .map((v) => v.trim())
    .filter((v) => v.length > 0);
};

const normalizeDict = (value: unknown): [string, string][] => {
  if (!value || typeof value !== "object") return [];
  const entries = Object.entries(value as Record<string, unknown>);
  return entries
    .map(([k, v]) => [k, typeof v === "string" ? v : JSON.stringify(v)] as [string, string])
    .filter(([, v]) => v.trim().length > 0);
};

export default function BedarfsanalyseCard({ data }: BedarfsanalyseCardProps) {
  if (!data || typeof data !== "object" || isEmptyObject(data)) {
    return null;
  }

  const {
    einbausituation,
    rahmenbedingungen,
    problem,
    offene_punkte,
    confidence,
    ...rest
  } = data;

  const confidenceLabel = formatConfidence(confidence);
  const rahmenListe = normalizeDict(rahmenbedingungen);
  const offenePunkteListe = normalizeArray(offene_punkte);

  const restPairs = normalizeDict(rest);

  return (
    <div className="mx-auto mt-3 w-full max-w-[768px] px-4">
      <div className="overflow-hidden rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-3 text-sm text-gray-800 shadow-sm backdrop-blur">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-amber-800">
            <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-amber-100 text-[11px]">
              1
            </span>
            <span>Phase 1 · Bedarfsanalyse</span>
          </div>
          {confidenceLabel && (
            <span className="text-[11px] font-medium text-amber-700">
              Confidence: {confidenceLabel}
            </span>
          )}
        </div>

        <p className="mt-2 text-[11px] uppercase tracking-wide text-amber-500">
          Strukturierte Zusammenfassung – bevor Spezialisten übernehmen
        </p>

        {einbausituation && (
          <div className="mt-3">
            <div className="text-xs font-semibold text-gray-800">Einbausituation</div>
            <p className="mt-1 text-xs text-gray-700 whitespace-pre-wrap">
              {einbausituation}
            </p>
          </div>
        )}

        {(rahmenListe.length > 0 || typeof rahmenbedingungen === "string") && (
          <div className="mt-3">
            <div className="text-xs font-semibold text-gray-800">Rahmenbedingungen</div>
            {rahmenListe.length > 0 ? (
              <dl className="mt-1 grid grid-cols-1 gap-1 text-xs text-gray-700 sm:grid-cols-2">
                {rahmenListe.map(([key, value]) => (
                  <div key={key} className="flex flex-col rounded-xl bg-white/60 px-2 py-1">
                    <dt className="text-[11px] font-medium text-gray-500">
                      {key.replace(/_/g, " ")}
                    </dt>
                    <dd className="text-xs text-gray-800">{value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-1 text-xs text-gray-700 whitespace-pre-wrap">
                {String(rahmenbedingungen)}
              </p>
            )}
          </div>
        )}

        {problem && (
          <div className="mt-3">
            <div className="text-xs font-semibold text-gray-800">Kernproblem</div>
            <p className="mt-1 text-xs text-gray-700 whitespace-pre-wrap">
              {problem}
            </p>
          </div>
        )}

        {offenePunkteListe.length > 0 && (
          <div className="mt-3">
            <div className="text-xs font-semibold text-gray-800">Offene Punkte / Klärungsbedarf</div>
            <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-gray-700">
              {offenePunkteListe.map((item, idx) => (
                <li key={`offen-${idx}`}>{item}</li>
              ))}
            </ul>
          </div>
        )}

        {restPairs.length > 0 && (
          <div className="mt-3 border-t border-amber-100 pt-2">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-500">
              Weitere Details
            </div>
            <dl className="mt-1 grid grid-cols-1 gap-1 text-xs text-gray-700 sm:grid-cols-2">
              {restPairs.map(([key, value]) => (
                <div key={key} className="flex flex-col rounded-xl bg-white/60 px-2 py-1">
                  <dt className="text-[11px] font-medium text-gray-500">
                    {key.replace(/_/g, " ")}
                  </dt>
                  <dd className="text-xs text-gray-800 break-words">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </div>
    </div>
  );
}
