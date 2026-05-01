"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import ChatPane from "@/components/dashboard/ChatPane";
import { SealCockpit } from "@/components/dashboard/SealCockpit";
import { useWorkspace } from "@/hooks/useWorkspace";
import { patchAgentOverrides, type AgentOverrideItemRequest } from "@/lib/bff/parameterOverride";
import { buildSealCockpitViewModel } from "@/lib/engineering/buildSealCockpitViewModel";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";

interface CaseScreenProps {
  caseId?: string;
  initialRequestType?: string;
}

export default function CaseScreen({ caseId }: CaseScreenProps) {
  const propCaseId = caseId ?? null;
  const [caseBinding, setCaseBinding] = useState(() => ({
    propCaseId,
    resolvedCaseId: propCaseId,
  }));
  const [parameterConfirmation, setParameterConfirmation] = useState<string | null>(null);
  const [isParameterSubmitting, setIsParameterSubmitting] = useState(false);

  if (caseBinding.propCaseId !== propCaseId) {
    setCaseBinding({
      propCaseId,
      resolvedCaseId: propCaseId,
    });
  }

  const resolvedCaseId = caseBinding.resolvedCaseId;
  const workspaceResult = useWorkspace(resolvedCaseId);
  const cockpitViewModel = useMemo(() => buildSealCockpitViewModel(workspaceResult.workspace), [workspaceResult.workspace]);
  const setWorkspace = useWorkspaceStore((state) => state.setWorkspace);
  const setWorkspaceLoading = useWorkspaceStore((state) => state.setWorkspaceLoading);

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
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-x-hidden overflow-y-auto bg-[#EEF2F7] p-3 sm:p-4 lg:grid lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)] lg:overflow-hidden xl:gap-5 xl:p-5">
      <section className="min-h-[calc(100dvh-120px)] min-w-0 overflow-hidden lg:min-h-0">
        <ChatPane
          caseId={resolvedCaseId ?? undefined}
          onCaseBound={handleCaseBound}
          onTurnComplete={() => void workspaceResult.refresh()}
          parameterConfirmation={parameterConfirmation}
        />
      </section>
      <SealCockpit
        data={cockpitViewModel}
        workspace={workspaceResult.workspace}
        isParameterSubmitting={isParameterSubmitting}
        onParameterSubmit={handleParameterSubmit}
      />
    </div>
  );
}
