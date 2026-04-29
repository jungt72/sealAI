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
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 bg-[#F5F7FB] p-4 lg:grid-cols-[minmax(420px,0.86fr)_minmax(620px,1.14fr)] xl:gap-5 xl:p-5">
      <section className="min-h-0 overflow-hidden">
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
