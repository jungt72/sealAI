"use client";

import type { ElementType, ReactNode } from "react";

import {
  AlertTriangle,
  Beaker,
  CheckCircle2,
  Layers,
  RefreshCw,
  Shield,
} from "lucide-react";

import type {
  WorkspaceTechnicalDerivation,
  WorkspaceView,
} from "@/lib/contracts/workspace";

type Props = {
  workspace: WorkspaceView;
  isLoading?: boolean;
};

const RELEASE_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  inadmissible: { bg: "bg-slate-100 ring-1 ring-slate-300", text: "text-slate-600", label: "Noch nicht freigegeben" },
  precheck_only: { bg: "bg-amber-50 ring-1 ring-amber-300", text: "text-amber-700", label: "Vorpruefung" },
  manufacturer_validation_required: { bg: "bg-blue-50 ring-1 ring-blue-300", text: "text-blue-700", label: "Herstellerpruefung" },
  rfq_ready: { bg: "bg-emerald-50 ring-1 ring-emerald-300", text: "text-emerald-700", label: "Anfragebereit" },
};

function humanize(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(/_/g, " ");
}

function phaseLabel(phase: string | null | undefined): string {
  const labels: Record<string, string> = {
    rapport: "Einstieg",
    exploration: "Fallverstehen",
    clarification: "Gezielte Klaerung",
    recommendation: "Technische Einengung",
    matching: "Herstellerabgleich",
    rfq_handover: "Anfragebasis",
  };

  if (!phase) {
    return "Technischer Stand";
  }

  return labels[phase] || humanize(phase);
}

function formatMetric(value: number | null, digits: number): string | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }
  return value.toFixed(digits);
}

function ReleaseBadge({ status }: { status: string }) {
  const style = RELEASE_STYLES[status] || RELEASE_STYLES.inadmissible;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ${style.bg} ${style.text}`}>
      {status === "rfq_ready" ? <CheckCircle2 className="h-3 w-3" /> : <Shield className="h-3 w-3" />}
      {style.label}
    </span>
  );
}

function ProgressBar({ value, max = 1 }: { value: number; max?: number }) {
  const pct = Math.min(100, Math.round((value / max) * 100));
  const color = pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-400" : "bg-slate-300";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right font-mono text-[11px] text-slate-500">{pct}%</span>
    </div>
  );
}

function SectionHeader({
  icon: Icon,
  title,
  badge,
}: {
  icon: ElementType;
  title: string;
  badge?: ReactNode;
}) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      {badge}
    </div>
  );
}

function InfoList({
  items,
  subdued = false,
}: {
  items: string[];
  subdued?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      {items.map((item) => (
        <div
          key={item}
          className={`rounded-xl border px-3 py-2 text-[11px] ${
            subdued
              ? "border-slate-200 bg-slate-50 text-slate-600"
              : "border-slate-200 bg-slate-50 text-slate-700"
          }`}
        >
          {item}
        </div>
      ))}
    </div>
  );
}

function DerivationCard({ item }: { item: WorkspaceTechnicalDerivation }) {
  const metrics = [
    { label: "Umfangsgeschwindigkeit", value: formatMetric(item.vSurfaceMPerS, 2), unit: "m/s" },
    { label: "PV-Wert", value: formatMetric(item.pvValueMpaMPerS, 2), unit: "MPa·m/s" },
    { label: "Dn-Wert", value: formatMetric(item.dnValue, 0), unit: "mm·min^-1" },
  ].filter((metric) => metric.value !== null);

  if (metrics.length === 0 && item.notes.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-700">
          {humanize(item.calcType || "technische_ableitung")}
        </p>
        <span className="text-[10px] font-medium text-slate-400 capitalize">
          {humanize(item.status)}
        </span>
      </div>
      {metrics.length > 0 ? (
        <div className="mt-2 grid gap-2">
          {metrics.map((metric) => (
            <div key={metric.label} className="flex items-baseline justify-between gap-3 text-[11px]">
              <span className="text-slate-500">{metric.label}</span>
              <span className="font-mono font-medium text-slate-700">
                {metric.value} {metric.unit}
              </span>
            </div>
          ))}
        </div>
      ) : null}
      {item.notes.length > 0 ? (
        <div className="mt-2 space-y-1">
          {item.notes.slice(0, 3).map((note) => (
            <p key={note} className="text-[10px] leading-relaxed text-slate-500">
              {note}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function buildTechnicalFrame(workspace: WorkspaceView): string[] {
  const items: string[] = [];
  const { mediumClassification, mediumContext, governance, specificity, matching, rfq } = workspace;

  if (mediumClassification.canonicalLabel) {
    items.push(`Medium eingeordnet: ${mediumClassification.canonicalLabel}`);
  }
  if (mediumClassification.family && mediumClassification.family !== "unknown") {
    items.push(`Medienfamilie: ${humanize(mediumClassification.family)}`);
  }
  if (mediumContext.status === "available" && mediumContext.scope) {
    items.push(`Medium-Kontext: ${mediumContext.scope}`);
  }
  if (specificity.materialSpecificityRequired && specificity.materialSpecificityRequired !== "family_only") {
    items.push(`Materialspezifizitaet: ${humanize(specificity.materialSpecificityRequired)}`);
  }
  if (matching.ready) {
    items.push("Hersteller-Matching technisch eingegrenzt");
  }
  if (rfq.status === "ready") {
    items.push("Anfragebasis freigabefaehig vorbereitet");
  } else if (rfq.status === "draft") {
    items.push("Anfragebasis als Entwurf vorhanden");
  }
  items.push(...governance.scopeOfValidity);

  return Array.from(new Set(items.filter(Boolean)));
}

export default function CaseStatusPanel({ workspace: ws, isLoading }: Props) {
  const { governance: gov, completeness: comp, summary } = ws;
  const confirmedFacts = ws.communication?.confirmedFactsSummary ?? [];
  const technicalFrame = buildTechnicalFrame(ws);
  const technicalDerivations = (ws.technicalDerivations ?? []).filter(
    (item) =>
      item.vSurfaceMPerS !== null ||
      item.pvValueMpaMPerS !== null ||
      item.dnValue !== null ||
      item.notes.length > 0,
  );

  return (
    <div className="space-y-4 rounded-2xl border border-slate-200/70 bg-white/60 p-4 backdrop-blur-sm">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
          {phaseLabel(ws.communication?.conversationPhase)}
        </p>
        {isLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin text-slate-400" /> : null}
      </div>

      <div className="flex items-center justify-between gap-2">
        <ReleaseBadge status={gov.releaseStatus} />
        {summary.derivedArtifactsStale ? (
          <span className="flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-600 ring-1 ring-amber-200">
            <AlertTriangle className="h-3 w-3" />
            Aktualisierung noetig
          </span>
        ) : null}
      </div>

      <section>
        <SectionHeader
          icon={Layers}
          title="Stand der Erfassung"
          badge={<span className="text-[10px] font-medium capitalize text-slate-400">{comp.completenessDepth}</span>}
        />
        <ProgressBar value={comp.coverageScore} />
        <p className="mt-2 text-[10px] leading-relaxed text-slate-500">
          Der technische Arbeitsstand wird aus dem Chat konsolidiert und hier als Zustandsansicht gespiegelt.
        </p>
      </section>

      {confirmedFacts.length > 0 ? (
        <section>
          <SectionHeader icon={Layers} title="Ermittelte Parameter" />
          <InfoList items={confirmedFacts} />
        </section>
      ) : null}

      {technicalFrame.length > 0 ? (
        <section>
          <SectionHeader icon={Shield} title="Technischer Rahmen" />
          <InfoList items={technicalFrame} subdued />
        </section>
      ) : null}

      {technicalDerivations.length > 0 ? (
        <section>
          <SectionHeader icon={Beaker} title="Technische Ableitungen" />
          <div className="space-y-2">
            {technicalDerivations.map((item, index) => (
              <DerivationCard key={`${item.calcType}-${index}`} item={item} />
            ))}
          </div>
        </section>
      ) : null}

      {(gov.assumptions.length > 0 || gov.requiredDisclaimers.length > 0) ? (
        <section className="border-t border-slate-100 pt-3">
          {gov.assumptions.length > 0 ? (
            <p className="text-[10px] leading-snug text-slate-400">
              <span className="font-semibold text-slate-500">Annahmen:</span>{" "}
              {gov.assumptions.slice(0, 3).join(", ")}
              {gov.assumptions.length > 3 ? ` +${gov.assumptions.length - 3}` : ""}
            </p>
          ) : null}
          {gov.requiredDisclaimers.length > 0 ? (
            <p className="mt-2 text-[10px] leading-snug text-amber-600">
              <span className="font-semibold">Hinweis:</span>{" "}
              {gov.requiredDisclaimers[0]}
            </p>
          ) : null}
        </section>
      ) : null}

      <div className="flex items-center justify-between border-t border-slate-100 pt-2 text-[10px] text-slate-400">
        <span>Zyklus {summary.analysisCycleId} / Rev {summary.assertedProfileRevision}</span>
        <span>Turn {summary.turnCount}/{summary.maxTurns}</span>
      </div>
    </div>
  );
}
