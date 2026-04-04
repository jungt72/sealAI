"use client";

/**
 * PanelSkeleton — Lade-Skeleton für den Workspace.
 * Rendert sich selbst nur während des initialen Workspace-Ladens
 * (workspaceLoading=true, kein canonical/stream workspace vorhanden).
 * Liest Sichtbarkeitsbedingung aus useWorkspaceStore — keine Props.
 * Feste Höhen verhindern CLS.
 */

import { useWorkspaceStore } from "@/lib/store/workspaceStore";

export default function PanelSkeleton() {
  const workspaceLoading = useWorkspaceStore((s) => s.workspaceLoading);
  const workspace = useWorkspaceStore((s) => s.workspace);
  const streamWorkspace = useWorkspaceStore((s) => s.streamWorkspace);

  const shouldShow = workspaceLoading && !workspace && !streamWorkspace;

  if (!shouldShow) {
    return null;
  }

  return (
    <>
      {/* Lifecycle-Skeleton */}
      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
        <div className="mb-4 h-3 w-28 animate-pulse rounded-full bg-slate-200" />
        <div className="space-y-3">
          <div className="h-12 w-full animate-pulse rounded-2xl bg-white" />
          <div className="h-12 w-full animate-pulse rounded-2xl bg-white" />
          <div className="h-12 w-full animate-pulse rounded-2xl bg-white" />
        </div>
      </div>

      {/* Actions-Skeleton */}
      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5 shadow-sm">
        <div className="mb-4 h-3 w-36 animate-pulse rounded-full bg-slate-200" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <div className="h-24 w-full animate-pulse rounded-2xl bg-white" />
          <div className="h-24 w-full animate-pulse rounded-2xl bg-white" />
        </div>
      </div>
    </>
  );
}
