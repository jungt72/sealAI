"use client";

import { PanelRightClose, SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import ChatPane from "@/components/dashboard/ChatPane";
import { SealCockpit } from "@/components/dashboard/SealCockpit";
import { useWorkspace } from "@/hooks/useWorkspace";
import { patchAgentOverrides, type AgentOverrideItemRequest } from "@/lib/bff/parameterOverride";
import { buildSealCockpitViewModel } from "@/lib/engineering/buildSealCockpitViewModel";
import type { CockpitTabId } from "@/lib/engineering/sealCockpitViewModel";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

interface CaseScreenProps {
  caseId?: string;
  initialRequestType?: string;
}

function isConcreteWorkspaceValue(value: unknown) {
  if (value === null || value === undefined || value === "") {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some(isConcreteWorkspaceValue);
  }
  if (typeof value === "object") {
    return Object.values(value).some(isConcreteWorkspaceValue);
  }
  const normalized = String(value).trim().toLowerCase();
  return Boolean(normalized) && !["unknown", "unklar", "offen", "none", "null"].includes(normalized);
}

function hasEnteredCaseData(workspace: ReturnType<typeof useWorkspace>["workspace"]) {
  if (!workspace) {
    return false;
  }

  const hasConcreteParameter = Object.values(workspace.parameters ?? {}).some(isConcreteWorkspaceValue);
  const hasCoverage =
    (workspace.completeness.coveragePercent ?? 0) > 0 || (workspace.completeness.coverageScore ?? 0) > 0;
  const hasConcreteCalculation = workspace.technicalDerivations?.some((item) => item.status === "ok") ?? false;
  const hasDecisionFacts =
    workspace.decisionUnderstanding?.understoodNow?.some((item) => {
      const normalized = item.toLowerCase();
      return !normalized.includes("offen") && !normalized.includes("unklar");
    }) ?? false;

  return hasConcreteParameter || hasCoverage || hasConcreteCalculation || hasDecisionFacts;
}

export default function CaseScreen({ caseId }: CaseScreenProps) {
  const propCaseId = caseId ?? null;
  const [caseBinding, setCaseBinding] = useState(() => ({
    propCaseId,
    resolvedCaseId: propCaseId,
  }));
  const [parameterConfirmation, setParameterConfirmation] = useState<string | null>(null);
  const [isParameterSubmitting, setIsParameterSubmitting] = useState(false);
  const [isCockpitManuallyOpen, setIsCockpitManuallyOpen] = useState(false);
  const [isCockpitDismissed, setIsCockpitDismissed] = useState(false);
  const [cockpitWidthPercent, setCockpitWidthPercent] = useState(52);
  const [preferredCockpitTab, setPreferredCockpitTab] = useState<CockpitTabId | null>(null);
  const layoutRef = useRef<HTMLDivElement | null>(null);

  if (caseBinding.propCaseId !== propCaseId) {
    setCaseBinding({
      propCaseId,
      resolvedCaseId: propCaseId,
    });
  }

  const resolvedCaseId = caseBinding.resolvedCaseId;
  const workspaceResult = useWorkspace(resolvedCaseId);
  const cockpitViewModel = useMemo(() => buildSealCockpitViewModel(workspaceResult.workspace), [workspaceResult.workspace]);
  const hasCockpitData = useMemo(() => hasEnteredCaseData(workspaceResult.workspace), [workspaceResult.workspace]);
  const isCockpitVisible = (hasCockpitData || isCockpitManuallyOpen) && !isCockpitDismissed;
  const setWorkspace = useWorkspaceStore((state) => state.setWorkspace);
  const setWorkspaceLoading = useWorkspaceStore((state) => state.setWorkspaceLoading);

  const openCockpit = useCallback((tab: CockpitTabId = "overview") => {
    setPreferredCockpitTab(tab);
    setIsCockpitDismissed(false);
    setIsCockpitManuallyOpen(true);
  }, []);

  const closeCockpit = useCallback(() => {
    setIsCockpitDismissed(true);
    setIsCockpitManuallyOpen(false);
  }, []);

  const handleResizeStart = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const container = layoutRef.current;
    if (!container) {
      return;
    }

    const resizeFromClientX = (clientX: number) => {
      const rect = container.getBoundingClientRect();
      const rightWidth = rect.right - clientX;
      const nextPercent = Math.round((rightWidth / rect.width) * 100);
      setCockpitWidthPercent(Math.min(64, Math.max(34, nextPercent)));
    };

    resizeFromClientX(event.clientX);

    const handlePointerMove = (moveEvent: PointerEvent) => {
      resizeFromClientX(moveEvent.clientX);
    };

    const handlePointerUp = () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", handlePointerUp, { once: true });
  }, []);

  const handleCaseBound = useCallback((nextCaseId: string) => {
    setCaseBinding((current) => ({
      ...current,
      resolvedCaseId: nextCaseId,
    }));
  }, []);

  const handleParameterSubmit = useCallback(
    async (overrides: AgentOverrideItemRequest[], summary: string) => {
      if (!resolvedCaseId) {
        setParameterConfirmation("Bitte starte zuerst im Chat einen konkreten Dichtungsfall. Danach kann SeaLAI die Angaben dem Fall zuordnen.");
        return;
      }

      setIsParameterSubmitting(true);
      setParameterConfirmation(null);
      try {
        await patchAgentOverrides(resolvedCaseId, { overrides });
        await workspaceResult.refresh();
        setParameterConfirmation(
          summary
            ? `Alles klar, ich habe ${summary} übernommen.`
            : "Alles klar, ich habe die Angaben übernommen.",
        );
      } catch (error) {
        setParameterConfirmation(
          error instanceof Error
            ? `Parameter konnten nicht übernommen werden: ${error.message}`
            : "Parameter konnten nicht übernommen werden.",
        );
      } finally {
        setIsParameterSubmitting(false);
      }
    },
    [resolvedCaseId, workspaceResult],
  );

  useEffect(() => {
    setWorkspace(workspaceResult.workspace);
  }, [setWorkspace, workspaceResult.workspace]);

  useEffect(() => {
    setWorkspaceLoading(workspaceResult.isLoading);
  }, [setWorkspaceLoading, workspaceResult.isLoading]);

  return (
    <div
      ref={layoutRef}
      className="relative flex h-full min-h-0 flex-col gap-4 overflow-x-hidden overflow-y-auto bg-white p-3 sm:p-4 lg:flex-row lg:gap-0 lg:overflow-hidden xl:p-5"
    >
      {!isCockpitVisible ? (
        <button
          type="button"
          onClick={() => openCockpit("parameters")}
          className="z-20 inline-flex items-center justify-center gap-2 rounded-full border border-[#CFE0FF] bg-white px-4 py-2 text-sm font-semibold text-[#0B5BD3] shadow-[0_12px_30px_rgba(15,23,42,0.10)] transition-colors hover:border-[#AFC7EC] hover:bg-[#F8FBFF] lg:absolute lg:right-5 lg:top-5"
        >
          <SlidersHorizontal size={16} />
          Werte eintragen
        </button>
      ) : null}

      <section
        className="min-h-[calc(100dvh-120px)] min-w-0 overflow-hidden lg:min-h-0"
        style={isCockpitVisible ? { flexBasis: `${100 - cockpitWidthPercent}%` } : { flexBasis: "100%" }}
      >
        <ChatPane
          caseId={resolvedCaseId ?? undefined}
          onCaseBound={handleCaseBound}
          onTurnComplete={() => void workspaceResult.refresh()}
          parameterConfirmation={parameterConfirmation}
        />
      </section>

      {isCockpitVisible ? (
        <>
          <button
            type="button"
            aria-label="Cockpit-Breite anpassen"
            title="Cockpit-Breite anpassen"
            onPointerDown={handleResizeStart}
            className="group relative hidden h-[calc(100%-124px)] w-7 shrink-0 cursor-col-resize items-stretch justify-center lg:flex"
          >
            <span className="absolute bottom-0 left-1/2 top-[100px] w-px -translate-x-1/2 rounded-full bg-[#D6DEE9] shadow-[7px_0_22px_rgba(15,23,42,0.18)] transition-colors group-hover:bg-[#9DBDED]" />
            <span className="absolute left-1/2 top-1/2 flex h-16 w-3 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-[4px] border border-[#C7D6EA] bg-white shadow-[0_10px_24px_rgba(15,23,42,0.14)] transition-colors group-hover:border-[#8FB2E6] group-hover:bg-[#F8FBFF]">
              <span className="h-9 w-px rounded-full bg-[#9AA9BC]" />
            </span>
          </button>
          <div
            className="relative min-h-[720px] min-w-0 lg:min-h-0"
            style={{ flexBasis: `${cockpitWidthPercent}%` }}
          >
            <button
              type="button"
              aria-label="Cockpit schließen"
              title="Cockpit schließen"
              onClick={closeCockpit}
              className="absolute left-3 top-2 z-30 inline-flex h-9 w-9 items-center justify-center rounded-full border border-[#DDE6F2] bg-white text-[#526273] shadow-[0_10px_24px_rgba(15,23,42,0.10)] transition-colors hover:border-[#B8C9E0] hover:bg-[#F8FBFF] hover:text-[#0F172A]"
            >
              <PanelRightClose size={16} />
            </button>
            <SealCockpit
              data={cockpitViewModel}
              workspace={workspaceResult.workspace}
              isParameterSubmitting={isParameterSubmitting}
              onParameterSubmit={handleParameterSubmit}
              preferredTab={preferredCockpitTab}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
