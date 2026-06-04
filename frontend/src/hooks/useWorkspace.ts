import { useCallback, useEffect, useState } from "react";

import type { WorkspaceView } from "@/lib/contracts/workspace";
import { fetchWorkspace } from "@/lib/bff/workspace";

type UseWorkspaceOptions = {
  autoLoad?: boolean;
};

export function useWorkspace(caseId: string | null, options: UseWorkspaceOptions = {}) {
  const [workspace, setWorkspace] = useState<WorkspaceView | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!caseId) {
      setWorkspace(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const nextWorkspace = await fetchWorkspace(caseId);
      setWorkspace(nextWorkspace);
    } catch (error) {
      const message = error instanceof Error ? error.message : "workspace_fetch_failed";
      if (message.includes("404")) {
        setError(null);
        return;
      }
      setError(message);
      setWorkspace(null);
    } finally {
      setIsLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    if (options.autoLoad === false) {
      return;
    }
    void refresh();
  }, [options.autoLoad, refresh]);

  const applyWorkspace = useCallback((nextWorkspace: WorkspaceView | null) => {
    if (!nextWorkspace) {
      return;
    }
    setWorkspace(nextWorkspace);
    setError(null);
  }, []);

  const reset = useCallback(() => {
    setWorkspace(null);
    setError(null);
    setIsLoading(false);
  }, []);

  return {
    workspace,
    isLoading,
    error,
    refresh,
    applyWorkspace,
    reset,
  };
}
