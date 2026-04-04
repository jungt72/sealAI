"use client";

import type { ReactNode } from "react";

import MediumStatusPanel from "@/components/dashboard/MediumStatusPanel";
import { buildMediumStatusViewFromStream } from "@/lib/mediumStatusView";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import type { StreamWorkspaceView } from "@/lib/streamWorkspace";

function humanize(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  return value.replace(/_/g, " ");
}

function phaseLabel(phase: string | null | undefined): string | undefined {
  if (!phase) {
    return undefined;
  }

  const labels: Record<string, string> = {
    rapport: "Einstieg",
    exploration: "Fallverstehen",
    clarification: "Gezielte Klaerung",
    recommendation: "Technische Einengung",
    matching: "Herstellerabgleich",
    rfq_handover: "Anfragebasis",
  };

  return labels[phase] || humanize(phase);
}

function formatMetric(value: unknown, digits: number): string | null {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : null;
}

function SectionCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200/70 bg-white/60 p-4 backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">{title}</p>
        {subtitle ? <span className="text-[10px] font-medium text-slate-400">{subtitle}</span> : null}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function InfoList({ items }: { items: string[] }) {
  return (
    <>
      {items.map((item) => (
        <div
          key={item}
          className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-700"
        >
          {item}
        </div>
      ))}
    </>
  );
}

function buildTechnicalFrame(streamWorkspace: StreamWorkspaceView): string[] {
  const items: string[] = [];
  const { ui, structuredState } = streamWorkspace;

  if (ui.medium_classification.canonical_label) {
    items.push(`Medium eingeordnet: ${ui.medium_classification.canonical_label}`);
  }
  if (ui.medium_classification.family && ui.medium_classification.family !== "unknown") {
    items.push(`Medienfamilie: ${humanize(ui.medium_classification.family)}`);
  }
  if (ui.medium_context.status === "available" && ui.medium_context.scope) {
    items.push(`Medium-Kontext: ${ui.medium_context.scope}`);
  }
  if (ui.recommendation.requirement_class) {
    items.push(`Requirement Class: ${ui.recommendation.requirement_class}`);
  }
  if (ui.matching.status && ui.matching.status !== "pending") {
    items.push(`Matching: ${humanize(ui.matching.status)}`);
  }
  if (ui.rfq.status && ui.rfq.status !== "pending") {
    items.push(`Anfragebasis: ${humanize(ui.rfq.status)}`);
  }
  const caseStatus = typeof structuredState?.["case_status"] === "string"
    ? structuredState["case_status"]
    : null;
  if (caseStatus && caseStatus.trim()) {
    items.push(`Arbeitsstatus: ${humanize(caseStatus)}`);
  }

  return Array.from(new Set(items));
}

function StreamCards({ streamWorkspace }: { streamWorkspace: StreamWorkspaceView }) {
  const { ui, responseClass, turnContext } = streamWorkspace;
  const mediumStatus = buildMediumStatusViewFromStream(streamWorkspace);
  const mediumContext = ui.medium_context;
  const confirmedFacts = turnContext?.confirmedFactsSummary || [];
  const technicalFrame = buildTechnicalFrame(streamWorkspace);
  const recommendationNotes = [
    ...(ui.recommendation.requirement_summary ? [ui.recommendation.requirement_summary] : []),
    ...(ui.recommendation.validity_notes ?? []),
  ];
  const derivations = ui.compute.items || [];
  const matchingStatus = ui.matching.status || "pending";
  const manufacturers = ui.matching.manufacturers || [];
  const matchingNotes = ui.matching.notes || [];
  const rfqStatus = ui.rfq.status || "pending";
  const rfqReady = Boolean(ui.rfq.rfq_ready);
  const dispatchReady = Boolean(ui.rfq.dispatch_ready);
  const rfqNotes = ui.rfq.notes || [];
  const phaseSubtitle = phaseLabel(turnContext?.conversationPhase) || humanize(responseClass) || undefined;

  return (
    <>
      <SectionCard title="Live Technischer Stand" subtitle={phaseSubtitle}>
        {confirmedFacts.length > 0 ? <InfoList items={confirmedFacts} /> : null}
        {technicalFrame.length > 0 ? <InfoList items={technicalFrame} /> : null}
        {recommendationNotes.length > 0 ? (
          <div className="space-y-1">
            {recommendationNotes.map((note) => (
              <p key={note} className="text-[10px] leading-relaxed text-slate-500">
                {note}
              </p>
            ))}
          </div>
        ) : null}
        {confirmedFacts.length === 0 && technicalFrame.length === 0 && recommendationNotes.length === 0 ? (
          <p className="text-[10px] leading-relaxed text-slate-500">
            Der technische Arbeitsstand wird waehrend des laufenden Turns aktualisiert.
          </p>
        ) : null}
      </SectionCard>

      {derivations.length > 0 ? (
        <SectionCard title="Technische Ableitungen">
          {derivations.map((item, index) => {
            const metrics = [
              { label: "Umfangsgeschwindigkeit", value: formatMetric(item.v_surface_m_s, 2), unit: "m/s" },
              { label: "PV-Wert", value: formatMetric(item.pv_value_mpa_m_s, 2), unit: "MPa·m/s" },
              { label: "Dn-Wert", value: formatMetric(item.dn_value, 0), unit: "mm·min^-1" },
            ].filter((metric) => metric.value !== null);

            return (
              <div
                key={`${item.calc_type || "calc"}-${index}`}
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-700">
                    {humanize(item.calc_type || "technische_ableitung")}
                  </p>
                  <span className="text-[10px] font-medium capitalize text-slate-400">
                    {humanize(item.status || "insufficient_data")}
                  </span>
                </div>
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
                {(item.notes || []).length > 0 ? (
                  <div className="mt-2 space-y-1">
                    {(item.notes || []).slice(0, 3).map((note) => (
                      <p key={note} className="text-[10px] leading-relaxed text-slate-500">
                        {note}
                      </p>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </SectionCard>
      ) : null}

      {(manufacturers.length > 0 || matchingNotes.length > 0) ? (
        <SectionCard title="Matching" subtitle={humanize(matchingStatus)}>
          {manufacturers.map((name) => (
            <div
              key={name}
              className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-medium text-slate-700"
            >
              {name}
            </div>
          ))}
          {matchingNotes.map((note) => (
            <p key={note} className="text-[10px] leading-relaxed text-slate-500">
              {note}
            </p>
          ))}
        </SectionCard>
      ) : null}

      {(rfqReady || dispatchReady || rfqNotes.length > 0) ? (
        <SectionCard title="RFQ" subtitle={humanize(rfqStatus)}>
          <div className="grid gap-2 text-[11px] text-slate-700">
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
              Anfragebasis: {rfqReady ? "bereit" : "in Arbeit"}
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
              Uebergabe: {dispatchReady ? "vorbereitet" : "noch nicht vorbereitet"}
            </div>
            {rfqNotes.map((note) => (
              <p key={note} className="text-[10px] leading-relaxed text-slate-500">
                {note}
              </p>
            ))}
          </div>
        </SectionCard>
      ) : null}

      <SectionCard title="Medium-Status" subtitle={mediumStatus.statusLabel}>
        <MediumStatusPanel view={mediumStatus} />
      </SectionCard>

      {mediumContext.status === "available" && mediumContext.medium_label ? (
        <SectionCard title="Medium-Kontext" subtitle={mediumContext.scope || "orientierend"}>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
            <p className="text-[11px] font-semibold text-slate-700">
              Erkannt: {mediumContext.medium_label}
            </p>
            {mediumContext.summary ? (
              <p className="mt-1 text-[10px] leading-relaxed text-slate-600">
                {mediumContext.summary}
              </p>
            ) : null}
            <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-400">
              Einordnung: {mediumContext.scope || "orientierend"}
            </p>
          </div>

          <InfoList items={mediumContext.properties ?? []} />
          <InfoList items={mediumContext.challenges ?? []} />

          {(mediumContext.disclaimer || mediumContext.not_for_release_decisions) ? (
            <p className="text-[10px] leading-relaxed text-slate-500">
              {mediumContext.disclaimer || "Allgemeiner Medium-Kontext, nicht als Freigabe."}
            </p>
          ) : null}
        </SectionCard>
      ) : null}
    </>
  );
}

export default function StreamWorkspaceCards() {
  const streamWorkspace = useWorkspaceStore((s) => s.streamWorkspace);

  if (!streamWorkspace) {
    return null;
  }

  return <StreamCards streamWorkspace={streamWorkspace} />;
}
