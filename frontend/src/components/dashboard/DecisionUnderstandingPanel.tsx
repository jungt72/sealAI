"use client";

import { AlertTriangle, ClipboardCheck, FileQuestion, Gauge, HelpCircle, ShieldCheck } from "lucide-react";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import { cn } from "@/lib/utils";

type BadgeTone = "neutral" | "info" | "warning" | "danger" | "success";

const EMPTY_TEXT =
  "SeaLAI bildet hier den technischen Arbeitsstand ab, sobald ein konkreter Dichtungsfall beschrieben wurde.";

const SOURCE_LABELS: Record<string, string> = {
  user_stated: "Nutzerangabe",
  uploaded_evidence: "Dokument / Upload",
  rag_verified: "Wissensbasis",
  deterministic_calculation: "Berechnung",
  llm_research_fallback: "LLM-Recherche",
  inferred: "abgeleitet",
  system_derived: "systemseitig abgeleitet",
  unknown: "Quelle unklar",
};

const VALIDATION_LABELS: Record<string, string> = {
  validated: "geprüft",
  documented: "dokumentiert",
  user_stated: "Nutzerangabe",
  candidate: "Kandidat",
  unvalidated: "nicht validiert",
  conflicting: "widersprüchlich",
  calculated: "berechnet",
  unknown: "unklar",
};

function unique(items: Array<string | null | undefined>, limit = 6) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of items) {
    const value = String(item || "").trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    result.push(value);
    if (result.length >= limit) {
      break;
    }
  }
  return result;
}

function readable(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  return value.replace(/_/g, " ");
}

function badgeToneForValidation(status: string | null | undefined): BadgeTone {
  switch (status) {
    case "validated":
    case "documented":
    case "calculated":
      return "success";
    case "candidate":
    case "user_stated":
      return "info";
    case "conflicting":
      return "danger";
    case "unvalidated":
      return "warning";
    default:
      return "neutral";
  }
}

function badgeClasses(tone: BadgeTone) {
  switch (tone) {
    case "success":
      return "border-[#BDECCB] bg-[#EAF7EE] text-[#166534]";
    case "info":
      return "border-[#D7E5FF] bg-[#EFF6FF] text-[#0B57D0]";
    case "warning":
      return "border-[#FDE2B8] bg-[#FFF4E5] text-[#9A3412]";
    case "danger":
      return "border-[#F7C8C8] bg-[#FDECEC] text-[#991B1B]";
    default:
      return "border-[#E5E7EB] bg-[#F0F2F5] text-[#4B5563]";
  }
}

function Badge({ label, tone = "neutral" }: { label: string; tone?: BadgeTone }) {
  return (
    <span className={cn("inline-flex rounded-full border px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em]", badgeClasses(tone))}>
      {label}
    </span>
  );
}

function Section({
  title,
  items,
  empty = "Noch offen",
}: {
  title: string;
  items: string[];
  empty?: string;
}) {
  return (
    <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <h3 className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{title}</h3>
      {items.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {items.map((item) => (
            <li key={item} className="text-sm leading-relaxed text-[#111827]">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">{empty}</p>
      )}
    </div>
  );
}

function sourceLabel(sourceType: string | null | undefined) {
  return SOURCE_LABELS[sourceType || "unknown"] || readable(sourceType) || SOURCE_LABELS.unknown;
}

function validationLabel(status: string | null | undefined) {
  return VALIDATION_LABELS[status || "unknown"] || readable(status) || VALIDATION_LABELS.unknown;
}

function hasDecisionData(workspace: WorkspaceView | null) {
  const du = workspace?.decisionUnderstanding;
  return Boolean(
    workspace &&
      ((du &&
        (du.caseSummary ||
        du.understoodNow.length ||
        du.technicalMeaning.length ||
        du.notYetDecidable.length ||
        du.keyRisks.length ||
        du.nextBestQuestion ||
        du.nextBestQuestions.length ||
        du.currentStateAnalysis.knownFields.length ||
          du.currentStateAnalysis.missingFields.length)) ||
        workspace.communication?.primaryQuestion ||
        workspace.completeness.missingCriticalParameters.length ||
        workspace.completeness.coverageGaps.length ||
        workspace.rfq.openPoints.length ||
        workspace.mediumContext.mediumLabel ||
        workspace.parameters?.medium ||
        workspace.parameters?.temperature_c ||
        workspace.parameters?.pressure_bar),
  );
}

export function DecisionUnderstandingPanel({ workspace }: { workspace: WorkspaceView | null }) {
  if (!hasDecisionData(workspace)) {
    return (
      <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
        <div className="flex items-center gap-2 text-base font-semibold text-[#111827]">
          <HelpCircle size={17} />
          Arbeitsstand
        </div>
        <p className="mt-2 text-sm leading-relaxed text-[#4B5563]">{EMPTY_TEXT}</p>
      </section>
    );
  }

  const decision = workspace!.decisionUnderstanding;
  const current = decision?.currentStateAnalysis ?? {
    knownFields: unique([
      workspace!.parameters?.medium ? `Medium: ${workspace!.parameters.medium}` : null,
      workspace!.parameters?.temperature_c ? `Temperatur: ${workspace!.parameters.temperature_c} °C` : null,
      workspace!.parameters?.pressure_bar ? `Druck: ${workspace!.parameters.pressure_bar} bar` : null,
      workspace!.parameters?.installation ? `Anlage: ${workspace!.parameters.installation}` : null,
      workspace!.parameters?.motion_type ? `Bewegung: ${workspace!.parameters.motion_type}` : null,
    ]),
    missingFields: unique([...workspace!.completeness.missingCriticalParameters, ...workspace!.completeness.coverageGaps]),
    uncertainFields: workspace!.governance.assumptions,
    conflictingFields: workspace!.conflicts.items.map((item) => item.summary),
    evidenceBackedFields: workspace!.evidence?.sourceBackedFindings ?? [],
    sealTypeStatus: workspace!.sealApplicationProfile?.confidenceBand ?? "unknown",
    readinessHint: workspace!.governance.releaseStatus || workspace!.rfq.status || "precheck",
    confidence: workspace!.completeness.coverageScore,
  };
  const needs = decision?.needsAnalysis ?? {
    primaryNeed: workspace!.requestType || workspace!.caseType || "technical_clarification",
    secondaryNeeds: workspace!.communication?.openPointsSummary ?? [],
    urgency: "unknown",
    userSide: null,
    contextSide: workspace!.parameters?.installation ?? null,
    confidence: workspace!.completeness.coverageScore,
    notes: [],
  };
  const primaryQuestion = decision?.nextBestQuestions?.[0] ?? null;
  const sourceType = workspace!.mediumContext.sourceType || "unknown";
  const validationStatus = workspace!.mediumContext.notForReleaseDecisions
    ? "unvalidated"
    : workspace!.mediumContext.validationStatus || "unknown";
  const sourceIsFallback = sourceType === "llm_research_fallback";
  const displayValidationStatus = sourceIsFallback ? "unvalidated" : validationStatus;
  const knownItems = unique([...(decision?.understoodNow ?? []), ...current.knownFields], 7);
  const missingItems = unique([...current.missingFields, ...workspace!.completeness.missingCriticalParameters, ...workspace!.rfq.openPoints], 7);
  const riskItems = unique([...(decision?.keyRisks ?? []), ...(decision?.manufacturerReviewNeeds ?? []), ...workspace!.governance.unknownsManufacturerValidation], 7);
  const notDecidable = unique([...(decision?.notYetDecidable ?? []), ...current.uncertainFields, ...current.conflictingFields], 7);
  const sealProfile = workspace!.sealApplicationProfile;
  const caseSummary =
    decision?.caseSummary ||
    workspace!.communication?.confirmedFactsSummary?.join(" · ") ||
    workspace!.mediumContext.summary ||
    "SeaLAI fasst hier den aktuellen technischen Arbeitsstand aus der Backend-Projektion zusammen.";

  return (
    <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <div className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <ClipboardCheck size={17} />
            Arbeitsstand
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            {caseSummary}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge label={`Datenherkunft: ${sourceLabel(sourceType)}`} tone={sourceIsFallback ? "warning" : "info"} />
          <Badge label={`Validierungsstatus: ${validationLabel(displayValidationStatus)}`} tone={badgeToneForValidation(displayValidationStatus)} />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <Section title="Verstanden" items={knownItems} />
        <Section
          title="Bedarf"
          items={unique([
            readable(needs.primaryNeed),
            ...needs.secondaryNeeds,
            needs.urgency !== "unknown" ? `Dringlichkeit: ${readable(needs.urgency)}` : null,
            needs.contextSide ? `Kontext: ${needs.contextSide}` : null,
          ])}
        />
        <Section title="Ist-Zustand" items={unique([...current.evidenceBackedFields, `Readiness: ${readable(current.readinessHint) || "precheck"}`])} />
        <Section title="Offen" items={missingItems} />
        <Section title="Nicht entscheidbar" items={notDecidable} />
        <Section title="Risiken / Herstellerprüfung" items={riskItems} empty="Keine zusätzlichen Herstellerprüfpunkte aus der Projektion gemeldet" />
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="rounded-[14px] border border-[#D7E5FF] bg-[#EFF6FF] p-3">
          <div className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.12em] text-[#0B57D0]">
            <FileQuestion size={14} />
            Nächste sinnvolle Frage
          </div>
          <p className="mt-2 text-sm font-semibold leading-relaxed text-[#111827]">
            {primaryQuestion?.question || decision?.nextBestQuestion || workspace!.communication?.primaryQuestion || "Noch keine nächste Frage aus der Projektion verfügbar"}
          </p>
          {(primaryQuestion?.reason || workspace!.communication?.supportingReason) && (
            <p className="mt-2 text-sm leading-relaxed text-[#4B5563]">
              {primaryQuestion?.reason || workspace!.communication?.supportingReason}
            </p>
          )}
        </div>
        <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
          <div className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">
            <Gauge size={14} />
            Dichtungstyp-Profil
          </div>
          <div className="mt-2 space-y-1 text-sm leading-relaxed text-[#111827]">
            <div>{readable(sealProfile?.sealType) || "Dichtungstyp noch offen"}</div>
            <div className="text-[#4B5563]">
              {readable(sealProfile?.sealFamily) || "Dichtungsfamilie noch offen"}
              {sealProfile?.confidenceBand ? ` · Confidence: ${readable(sealProfile.confidenceBand)}` : ""}
            </div>
            {sealProfile?.typeSpecificMissingHints.length ? (
              <div className="text-[#4B5563]">Offen: {sealProfile.typeSpecificMissingHints.slice(0, 3).join(" · ")}</div>
            ) : null}
          </div>
        </div>
      </div>

      {(sourceIsFallback || current.conflictingFields.length > 0 || workspace!.conflicts.open > 0) && (
        <div className="mt-3 flex items-start gap-2 rounded-[14px] border border-[#FDE2B8] bg-[#FFF4E5] px-3 py-2 text-sm leading-relaxed text-[#9A3412]">
          <AlertTriangle className="mt-0.5 shrink-0" size={15} />
          <span>
            {sourceIsFallback
              ? "LLM-Recherche ist nicht validiert und bleibt Orientierung."
              : "Konflikte oder widersprüchliche Angaben bleiben sichtbar und müssen geklärt werden."}
          </span>
        </div>
      )}

      <div className="mt-3 flex items-center gap-2 text-[12px] font-medium text-[#6B7280]">
        <ShieldCheck size={14} />
        Frontend rendert die Backend-Projektion read-only; Herstellerprüfung bleibt erforderlich.
      </div>
    </section>
  );
}
