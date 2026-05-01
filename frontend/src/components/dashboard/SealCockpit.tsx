"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Beaker,
  Calculator,
  CheckCircle2,
  ClipboardList,
  Factory,
  FileText,
  Layers,
  ShieldCheck,
} from "lucide-react";

import { DecisionUnderstandingPanel } from "@/components/dashboard/DecisionUnderstandingPanel";
import { ManufacturerFitPanel } from "@/components/dashboard/ManufacturerFitPanel";
import { ParameterWorkspaceTab } from "@/components/dashboard/ParameterWorkspaceTab";
import type { AgentOverrideItemRequest } from "@/lib/bff/parameterOverride";
import type { WorkspaceView } from "@/lib/contracts/workspace";
import {
  type CalculationEvidenceMetric,
  type CockpitTabId,
  type CriticalDriver,
  type ParameterDataRow,
  type SealCockpitOverview,
} from "@/lib/engineering/sealCockpitViewModel";
import { humanizeDisplayText, uniqueDisplayItems } from "@/lib/engineering/displayLabels";
import { cn } from "@/lib/utils";

export function CockpitTabs({
  tabs,
  activeTab,
  onTabChange,
}: {
  tabs: SealCockpitOverview["tabs"];
  activeTab: CockpitTabId;
  onTabChange: (tab: CockpitTabId) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="SealAI Cockpit"
      className="custom-scrollbar flex gap-2 overflow-x-auto bg-transparent px-4 pb-2 pt-4"
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              "h-10 shrink-0 rounded-full border px-4 text-sm font-semibold shadow-sm transition-colors",
              isActive
                ? "border-[#0B57D0] bg-[#0B57D0] text-white shadow-[0_8px_20px_rgba(11,87,208,0.18)]"
                : "border-[#E5EAF2] bg-white/70 text-[#4B5563] hover:border-[#D7E5FF] hover:bg-white hover:text-[#111827]",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

export function CockpitStatusStrip({ items }: { items: SealCockpitOverview["statusStrip"] }) {
  return (
    <div className="grid grid-cols-1 gap-2 rounded-tl-[20px] px-4 pt-4 sm:grid-cols-2 xl:grid-cols-5">
      {items.map((item) => (
        <div key={item.label} className="min-h-[78px] rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#6B7280]">{item.label}</div>
          <div className="mt-2 text-sm font-semibold leading-snug text-[#111827]">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

export function OverviewCard({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: typeof ClipboardList;
  children: React.ReactNode;
}) {
  return (
    <section className="min-h-[276px] rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="mb-4 flex items-center justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <h2 className="text-base font-semibold tracking-tight text-[#111827]">{title}</h2>
        <div className="grid h-9 w-9 place-items-center rounded-[14px] bg-[#F5F7FB] text-[#4B5563]">
          <Icon size={17} />
        </div>
      </div>
      {children}
    </section>
  );
}

export function ParameterDataCard({
  rows,
  warning,
}: {
  rows: ParameterDataRow[];
  warning: string;
}) {
  return (
    <OverviewCard title="Angaben zum Fall" icon={ClipboardList}>
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-start justify-between gap-3 border-b border-[#F0F2F5] pb-2 last:border-b-0">
            <span className="text-sm text-[#6B7280]">{row.label}</span>
            <span className="max-w-[58%] text-right text-sm font-semibold text-[#111827]">{row.value}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-[12px] border border-[#FFF4E5] bg-[#FFF4E5] px-3 py-2 text-sm font-medium text-[#9A3412]">
        {warning}
      </div>
    </OverviewCard>
  );
}

function riskTone(risk: CriticalDriver["risk"]) {
  switch (risk) {
    case "Hoch":
      return "border-[#FDECEC] bg-[#FDECEC] text-[#991B1B]";
    case "Mittel":
      return "border-[#FFF4E5] bg-[#FFF4E5] text-[#9A3412]";
    case "Gering":
      return "border-[#EAF7EE] bg-[#EAF7EE] text-[#166534]";
    case "Offen":
      return "border-[#E5E7EB] bg-[#F0F2F5] text-[#4B5563]";
  }
}

export function CriticalDriversCard({ drivers }: { drivers: CriticalDriver[] }) {
  return (
    <OverviewCard title="Was noch wichtig ist" icon={AlertTriangle}>
      <div className="space-y-2">
        {drivers.map((driver) => (
          <div key={driver.label} className="grid grid-cols-[minmax(0,1fr)_auto] gap-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2.5">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-[#111827]">{driver.label}</div>
              <div className="mt-1 text-sm text-[#4B5563]">{driver.consequence}</div>
            </div>
            <span className={cn("h-fit rounded-full border px-2 py-0.5 text-[11px] font-bold uppercase tracking-[0.08em]", riskTone(driver.risk))}>
              {driver.risk}
            </span>
          </div>
        ))}
      </div>
    </OverviewCard>
  );
}

export function SolutionConsequenceCard({ solution }: { solution: SealCockpitOverview["solution"] }) {
  return (
    <OverviewCard title="Einordnung" icon={CheckCircle2}>
      <div className="rounded-[14px] border border-[#CFE0FF] bg-[#EAF2FF] px-4 py-3">
        <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#0B57D0]">{solution.assessmentTitle}</div>
        <p className="mt-2 text-sm font-medium leading-relaxed text-[#1F3B63]">{solution.assessment}</p>
      </div>
      <div className="mt-4 space-y-3">
        {solution.rows.map((row) => (
          <div key={row.label}>
            <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{row.label}</div>
            <div className="mt-1 text-sm leading-relaxed text-[#111827]">{row.value}</div>
          </div>
        ))}
      </div>
    </OverviewCard>
  );
}

function CalculationMetric({ metric }: { metric: CalculationEvidenceMetric }) {
  return (
    <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="text-[12px] font-semibold text-[#4B5563]">{metric.label}</div>
      <div className="mt-2 text-lg font-semibold tracking-tight text-[#111827]">{metric.value}</div>
      <div className="mt-2 space-y-1 text-[12px] text-[#6B7280]">
        {metric.limit && <div>{metric.limit}</div>}
        {metric.reserve && <div>{metric.reserve}</div>}
      </div>
      <div className="mt-3 inline-flex rounded-full border border-[#D7E5FF] bg-[#EFF6FF] px-2 py-1 text-[11px] font-bold uppercase tracking-[0.08em] text-[#0B57D0]">
        {metric.status}
      </div>
    </div>
  );
}

export function CalculationsEvidenceCard({ metrics }: { metrics: CalculationEvidenceMetric[] }) {
  return (
    <OverviewCard title="Rechencheck" icon={Calculator}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {metrics.map((metric) => (
          <CalculationMetric key={metric.label} metric={metric} />
        ))}
      </div>
    </OverviewCard>
  );
}

function normalizeText(value: unknown): string | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (Array.isArray(value)) {
    const joined = value.map(normalizeText).filter(Boolean).join(" · ");
    return joined || null;
  }
  return humanizeDisplayText(String(value));
}

function compactItems(items: Array<unknown>, limit = 6) {
  return uniqueDisplayItems(items.map(normalizeText), limit);
}

function WorkspaceTabShell({
  title,
  icon: Icon,
  intro,
  children,
}: {
  title: string;
  icon: typeof ClipboardList;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-4 mt-4 rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <Icon size={17} />
            {title}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">{intro}</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-[#D7E5FF] bg-[#EFF6FF] px-3 py-1.5 text-[12px] font-semibold text-[#0B57D0]">
          <ShieldCheck size={14} />
          Nur zur Ansicht
        </div>
      </div>
      {children}
    </section>
  );
}

function InfoTile({
  title,
  value,
  note,
  tone = "neutral",
}: {
  title: string;
  value: string | null;
  note?: string | null;
  tone?: "neutral" | "info" | "warning";
}) {
  const toneClass =
    tone === "warning"
      ? "border-[#FDE2B8] bg-[#FFF4E5]"
      : tone === "info"
        ? "border-[#D7E5FF] bg-[#EFF6FF]"
        : "border-[#E5E7EB] bg-[#FAFAFB]";
  return (
    <div className={cn("rounded-[14px] border p-3", toneClass)}>
      <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{title}</div>
      <div className="mt-2 text-sm font-semibold leading-relaxed text-[#111827]">{value || "Noch offen"}</div>
      {note ? <p className="mt-1 text-[12px] leading-relaxed text-[#4B5563]">{note}</p> : null}
    </div>
  );
}

function ItemList({
  title,
  items,
  empty = "Noch keine Angaben vorhanden",
}: {
  title: string;
  items: Array<unknown>;
  empty?: string;
}) {
  const visibleItems = compactItems(items, 7);
  return (
    <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
      <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">{title}</div>
      {visibleItems.length ? (
        <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-[#111827]">
          {visibleItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">{empty}</p>
      )}
    </div>
  );
}

function designStatusLabel(status: string) {
  switch (status) {
    case "minimal_dataset_missing":
      return "Mindestdaten fehlen";
    case "preselection_ready_with_open_points":
      return "Vorprüfung mit offenen Punkten";
    case "design_review_ready_not_released":
      return "Prüfdatensatz vollständig";
    default:
      return "Noch kein Design-Datensatz";
  }
}

function screeningStatusLabel(status: string) {
  switch (status) {
    case "screening_ok":
      return "im Vorcheck unauffällig";
    case "warning":
      return "prüfen";
    case "low_review":
      return "zu niedrig prüfen";
    default:
      return humanizeDisplayText(status);
  }
}

export function DesignIntakePanel({ workspace }: { workspace: WorkspaceView | null }) {
  const intake = workspace?.designIntake;
  const hasContent = Boolean(
    intake &&
      intake.status !== "no_design_dataset" &&
      (intake.knownFields.length ||
        intake.missingFields.length ||
        intake.screeningChecks.length ||
        intake.escalationTriggers.length),
  );
  if (!hasContent || !intake) {
    return null;
  }

  const missingByKey = new Map(intake.missingFields.map((field) => [field.key, field]));
  const nextFields = intake.nextRequiredFields
    .map((key) => missingByKey.get(key)?.label || humanizeDisplayText(key))
    .filter(Boolean);
  const criticalMissing = intake.missingFields.filter((field) => field.criticality === "critical");
  const visibleKnown = intake.knownFields.slice(0, 4);
  const visibleMissing = criticalMissing.length ? criticalMissing.slice(0, 5) : intake.missingFields.slice(0, 5);

  return (
    <section className="rounded-[18px] border border-[#E5E7EB] bg-white p-4 shadow-[0_4px_18px_rgba(15,23,42,0.06)]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#F0F2F5] pb-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-[#111827]">
            <ClipboardList size={17} />
            Neuauslegung
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-[#4B5563]">
            Mindestdaten, Vorchecks und Eskalationspunkte aus dem Backend. Nur als Anfragebasis für spätere Prüfung.
          </p>
        </div>
        <span className="inline-flex rounded-full border border-[#D7E5FF] bg-[#EFF6FF] px-3 py-1.5 text-[12px] font-bold uppercase tracking-[0.08em] text-[#0B57D0]">
          {designStatusLabel(intake.status)}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] p-3">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#6B7280]">Schon vorhanden</div>
          {visibleKnown.length ? (
            <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-[#111827]">
              {visibleKnown.map((field) => (
                <li key={field.key}>
                  {field.label}: {normalizeText(field.value) || "angegeben"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[#6B7280]">Noch keine belastbare Angabe im Design-Datensatz.</p>
          )}
        </div>

        <div className="rounded-[14px] border border-[#FFF4E5] bg-[#FFF8ED] p-3">
          <div className="text-[12px] font-bold uppercase tracking-[0.12em] text-[#9A3412]">Als Nächstes klären</div>
          {nextFields.length || visibleMissing.length ? (
            <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-[#111827]">
              {(nextFields.length ? nextFields : visibleMissing.map((field) => field.label)).map((label) => (
                <li key={label}>{label}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-[#6B7280]">Keine Pflichtlücke gemeldet.</p>
          )}
        </div>
      </div>

      {intake.screeningChecks.length || intake.escalationTriggers.length ? (
        <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
          <ItemList
            title="Vorchecks"
            empty="Noch keine Vorchecks möglich"
            items={intake.screeningChecks.map((check) => {
              const value = check.value !== null ? `${check.value}${check.unit ? ` ${check.unit}` : ""}` : null;
              return `${check.label}: ${value ? `${value} · ` : ""}${screeningStatusLabel(check.status)}`;
            })}
          />
          <ItemList
            title="Eskalationspunkte"
            empty="Keine Eskalationspunkte gemeldet"
            items={intake.escalationTriggers.map((trigger) => `${trigger.label}: ${trigger.reason}`)}
          />
        </div>
      ) : null}

      <p className="mt-3 rounded-[12px] border border-[#E5E7EB] bg-[#FAFAFB] px-3 py-2 text-[12px] leading-relaxed text-[#4B5563]">
        {normalizeText(intake.boundaryNotice) ||
          "Read-only Vorqualifikation; die technische Auslegung bleibt später zu prüfen."}
      </p>
    </section>
  );
}

function sourceStatusLine(workspace: WorkspaceView | null) {
  if (!workspace) {
    return "Herkunft noch offen";
  }
  const source = normalizeText(workspace.mediumContext.sourceType) || "Herkunft unklar";
  const status = workspace.mediumContext.notForReleaseDecisions
    ? "noch nicht geprüft"
    : normalizeText(workspace.mediumContext.validationStatus) || "Status unklar";
  return `${source} · ${status}`;
}

function MediumTab({ workspace }: { workspace: WorkspaceView | null }) {
  return (
    <WorkspaceTabShell
      title="Medium"
      icon={Beaker}
      intro="Hier siehst du, welches Medium erkannt wurde, welche Risiken daran hängen und woher die Info kommt."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Erkanntes Medium" value={normalizeText(workspace?.mediumContext.mediumLabel ?? workspace?.parameters?.medium)} tone="info" />
        <InfoTile title="Woher kommt die Info?" value={sourceStatusLine(workspace)} tone={workspace?.mediumContext.notForReleaseDecisions ? "warning" : "neutral"} />
        <InfoTile title="Medienfamilie" value={normalizeText(workspace?.mediumClassification.family)} />
        <InfoTile title="Klassifizierung" value={normalizeText(workspace?.mediumClassification.status)} note={normalizeText(workspace?.mediumContext.disclaimer)} />
        <ItemList title="Eigenschaften" items={workspace?.mediumContext.properties ?? []} />
        <ItemList title="Risiken / Prüfpunkte" items={workspace?.mediumContext.challenges ?? []} />
        <ItemList title="Offen" items={[...(workspace?.mediumContext.followupPoints ?? []), ...(workspace?.completeness.coverageGaps ?? [])]} />
        <ItemList title="Nächste Frage" items={[workspace?.mediumClassification.followupQuestion, workspace?.communication?.primaryQuestion]} />
      </div>
    </WorkspaceTabShell>
  );
}

function ApplicationTab({ workspace }: { workspace: WorkspaceView | null }) {
  const profile = workspace?.sealApplicationProfile;
  return (
    <WorkspaceTabShell
      title="Anwendung"
      icon={Factory}
      intro="Anlage, Einbauort und Bewegung helfen, den Fall richtig einzuordnen, bevor eine Anfrage vorbereitet wird."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Anlage / Einbauort" value={normalizeText(workspace?.parameters?.installation)} tone="info" />
        <InfoTile title="Dichtstelle / Geometrie" value={normalizeText(workspace?.parameters?.geometry_context)} />
        <InfoTile title="Bewegung" value={normalizeText(profile?.motionType ?? workspace?.parameters?.motion_type)} />
        <InfoTile title="Anwendungsdomäne" value={normalizeText(profile?.applicationDomain)} />
        <ItemList title="Bekannt" items={workspace?.decisionUnderstanding?.currentStateAnalysis.knownFields ?? workspace?.communication?.confirmedFactsSummary ?? []} />
        <ItemList title="Offen" items={workspace?.decisionUnderstanding?.currentStateAnalysis.missingFields ?? workspace?.completeness.missingCriticalParameters ?? []} />
        <ItemList title="Warum das wichtig ist" items={workspace?.decisionUnderstanding?.technicalMeaning ?? []} />
        <ItemList title="Was der Hersteller prüfen muss" items={workspace?.decisionUnderstanding?.manufacturerReviewNeeds ?? workspace?.manufacturerQuestions.mandatory ?? []} />
      </div>
    </WorkspaceTabShell>
  );
}

function MaterialTab({ workspace }: { workspace: WorkspaceView | null }) {
  return (
    <WorkspaceTabShell
      title="Werkstoff"
      icon={Layers}
      intro="Werkstoffhinweise bleiben bewusst als Richtung sichtbar, bis Medium, Temperatur und Anwendung genug geklärt sind."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Spezifität" value={normalizeText(workspace?.specificity.materialSpecificityRequired)} tone="info" />
        <InfoTile title="Zielniveau" value={normalizeText(workspace?.specificity.elevationTarget)} />
        <InfoTile title="Dichtungstyp-Profil" value={normalizeText(workspace?.sealApplicationProfile?.sealType)} />
        <InfoTile title="Sicherheit der Einordnung" value={normalizeText(workspace?.sealApplicationProfile?.confidenceBand)} />
        <ItemList title="Werkstoffrelevante Hinweise" items={workspace?.specificity.elevationHints.map((hint) => `${hint.label}: ${hint.reason}`) ?? []} />
        <ItemList title="Plausible Richtungen" items={workspace?.decisionUnderstanding?.plausibleDirections ?? []} />
        <ItemList title="Noch nicht entscheidbar" items={workspace?.decisionUnderstanding?.notYetDecidable ?? []} />
        <ItemList title="Muss noch geprüft werden" items={workspace?.governance.unknownsManufacturerValidation ?? []} />
      </div>
    </WorkspaceTabShell>
  );
}

function CalculationTab({
  data,
  workspace,
}: {
  data: SealCockpitOverview;
  workspace: WorkspaceView | null;
}) {
  return (
    <WorkspaceTabShell
      title="Berechnung"
      icon={Calculator}
      intro="SeaLAI zeigt einfache Rechenchecks nur dann, wenn genug Angaben vorhanden sind. Fehlende Eingaben bleiben sichtbar."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        {data.calculations.map((metric) => (
          <InfoTile key={metric.label} title={metric.label} value={metric.value} note={compactItems([metric.limit, metric.reserve]).join(" · ")} tone={metric.value === "Noch nicht möglich" ? "warning" : "info"} />
        ))}
        <ItemList title="Hinweise aus dem System" items={workspace?.technicalDerivations?.flatMap((item) => item.notes) ?? []} />
        <ItemList title="Berechnete Hinweise" items={workspace?.evidence.deterministicFindings ?? []} />
      </div>
    </WorkspaceTabShell>
  );
}

function BriefingTab({
  data,
  workspace,
}: {
  data: SealCockpitOverview;
  workspace: WorkspaceView | null;
}) {
  const decision = workspace?.decisionUnderstanding;
  return (
    <WorkspaceTabShell
      title="Briefing"
      icon={FileText}
      intro="Kurze Zusammenfassung für interne Klärung und eine spätere Anfragevorschau. Hier wird nichts versendet."
    >
      <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-2">
        <InfoTile title="Fallzusammenfassung" value={normalizeText(decision?.caseSummary) || data.solution.assessment} tone="info" />
        <InfoTile title="Anfrage-Status" value={normalizeText(workspace?.rfq.status)} note={normalizeText(workspace?.rfq.releaseStatus)} />
        <ItemList title="Bekannt" items={decision?.understoodNow ?? workspace?.communication?.confirmedFactsSummary ?? []} />
        <ItemList title="Offen" items={[...(workspace?.rfq.openPoints ?? []), ...(workspace?.completeness.missingCriticalParameters ?? [])]} />
        <ItemList title="Was zu prüfen ist" items={decision?.manufacturerReviewNeeds ?? workspace?.manufacturerQuestions.mandatory ?? []} />
        <ItemList title="Nächste sinnvolle Frage" items={[decision?.nextBestQuestion, workspace?.communication?.primaryQuestion]} />
        <ItemList title="Grenzen" items={[...(workspace?.governance.requiredDisclaimers ?? []), "Der Hersteller muss die Auslegung später prüfen."]} />
        <ItemList title="Blocker" items={[...(workspace?.rfq.blockers ?? []), ...(workspace?.matching.blockingReasons ?? [])]} empty="Keine Blocker gemeldet" />
      </div>
    </WorkspaceTabShell>
  );
}

export function SealCockpit({
  data,
  workspace,
  isParameterSubmitting = false,
  onParameterSubmit,
  preferredTab,
}: {
  data: SealCockpitOverview;
  workspace: WorkspaceView | null;
  isParameterSubmitting?: boolean;
  onParameterSubmit?: (overrides: AgentOverrideItemRequest[], summary: string) => Promise<void> | void;
  preferredTab?: CockpitTabId | null;
}) {
  const [activeTab, setActiveTab] = useState<CockpitTabId>(preferredTab ?? "overview");

  return (
    <aside className="flex h-full min-h-[720px] min-w-0 flex-col overflow-hidden rounded-[20px] border border-transparent bg-transparent lg:min-h-0">
      <CockpitTabs tabs={data.tabs} activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto pb-4">
        {activeTab === "overview" ? (
          <>
            <CockpitStatusStrip items={data.statusStrip} />
            <div className="px-4 pt-4">
              <DecisionUnderstandingPanel workspace={workspace} />
            </div>
            <div className="px-4 pt-4">
              <DesignIntakePanel workspace={workspace} />
            </div>
            <div className="px-4 pt-4">
              <ManufacturerFitPanel workspace={workspace} />
            </div>
            <div className="grid grid-cols-1 gap-4 px-4 pt-4 xl:grid-cols-2">
              <ParameterDataCard rows={data.parameters.rows} warning={data.parameters.warning} />
              <CriticalDriversCard drivers={data.criticalDrivers} />
              <SolutionConsequenceCard solution={data.solution} />
              <CalculationsEvidenceCard metrics={data.calculations} />
            </div>
            <div className="mx-4 mt-4 rounded-[14px] border border-[#E5E7EB] bg-[#FAFAFB] px-4 py-3 text-sm font-medium text-[#4B5563]">
              {data.footerNote}
            </div>
          </>
        ) : activeTab === "parameters" ? (
          <ParameterWorkspaceTab
            key={workspace?.caseId ?? "new-parameter-case"}
            workspace={workspace}
            isSubmitting={isParameterSubmitting}
            onSubmit={onParameterSubmit ?? (async () => {})}
          />
        ) : activeTab === "medium" ? (
          <MediumTab workspace={workspace} />
        ) : activeTab === "application" ? (
          <ApplicationTab workspace={workspace} />
        ) : activeTab === "material" ? (
          <MaterialTab workspace={workspace} />
        ) : activeTab === "calculation" ? (
          <CalculationTab data={data} workspace={workspace} />
        ) : (
          <BriefingTab data={data} workspace={workspace} />
        )}
      </div>
    </aside>
  );
}
