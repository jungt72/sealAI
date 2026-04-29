"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import ChatPane from "@/components/dashboard/ChatPane";
import { SealCockpit } from "@/components/dashboard/SealCockpit";
import { useWorkspace } from "@/hooks/useWorkspace";
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

  useEffect(() => {
    setWorkspace(workspaceResult.workspace);
  }, [setWorkspace, workspaceResult.workspace]);

  useEffect(() => {
    setWorkspaceLoading(workspaceResult.isLoading);
  }, [setWorkspaceLoading, workspaceResult.isLoading]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-x-hidden overflow-y-auto bg-[#F5F7FB] p-3 sm:p-4 lg:grid lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)] lg:overflow-hidden xl:gap-5 xl:p-5">
      <section className="min-h-[calc(100dvh-120px)] min-w-0 overflow-hidden lg:min-h-0">
        <ChatPane
          caseId={resolvedCaseId ?? undefined}
          onCaseBound={handleCaseBound}
          onTurnComplete={() => void workspaceResult.refresh()}
        />
      </section>
      <SealCockpit data={cockpitViewModel} workspace={workspaceResult.workspace} />
    </div>
  );
}
