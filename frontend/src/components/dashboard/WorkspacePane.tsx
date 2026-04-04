"use client";

/**
 * WorkspacePane — Engineering-Dashboard-Spalte (292 px, statisch).
 * Desktop: immer sichtbar als rechte Spalte neben ChatPane.
 * Mobile: Overlay, steuerbar über isSidebarOpen.
 */

import { X } from "lucide-react";

import CaseLifecyclePanel from "@/components/dashboard/CaseLifecyclePanel";
import CaseStatusPanel from "@/components/dashboard/CaseStatusPanel";
import MediumStatusPanel from "@/components/dashboard/MediumStatusPanel";
import PartnerMatchingPanel from "@/components/dashboard/PartnerMatchingPanel";
import RfqPackagePanel from "@/components/dashboard/RfqPackagePanel";
import CaptureStatusTile from "@/components/dashboard/cockpit/tiles/CaptureStatusTile";
import MediumIntelligenceTile from "@/components/dashboard/cockpit/tiles/MediumIntelligenceTile";
import CockpitHeader from "@/components/dashboard/cockpit/CockpitHeader";
import { buildMediumStatusViewFromWorkspace } from "@/lib/mediumStatusView";
import { useChatStore } from "@/lib/store/chatStore";
import { useWorkspaceStore } from "@/lib/store/workspaceStore";
import { MediumContextPanel, PanelSkeleton, ParameterTablePanel, StreamWorkspaceCards } from "./workspace";

/** Uniform card chrome for all workspace panels */
function WorkspaceCard({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className="overflow-hidden rounded-[10px] border border-[#e8ecf1] bg-white"
      style={{
        boxShadow:
          "0 2px 8px rgba(15,30,60,0.06), 0 0 0 0.5px rgba(15,30,60,0.04)",
      }}
    >
      <div className="flex items-center justify-between border-b border-[#f0f2f6] px-3 py-[9px]">
        <span className="text-[10.5px] font-semibold uppercase tracking-[0.06em] text-[#64748b]">
          {title}
        </span>
        {badge && (
          <span className="rounded-[10px] px-[7px] py-[2px] text-[10px]">
            {badge}
          </span>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

export default function WorkspacePane() {
  const workspace = useWorkspaceStore((s) => s.workspace);
  const workspaceLoading = useWorkspaceStore((s) => s.workspaceLoading);
  const streamWorkspace = useWorkspaceStore((s) => s.streamWorkspace);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const isSidebarOpen = useWorkspaceStore((s) => s.isSidebarOpen);
  const isDesktopViewport = useWorkspaceStore((s) => s.isDesktopViewport);
  const closeSidebar = useWorkspaceStore((s) => s.closeSidebar);

  // On desktop always visible; on mobile only when toggled open
  if (!isDesktopViewport && !isSidebarOpen) {
    return null;
  }

  const showCanonical = Boolean(workspace && (!streamWorkspace || !isStreaming));
  const showStreamWorkspace = Boolean(streamWorkspace && (isStreaming || !workspace));
  const canonicalMediumStatus = workspace ? buildMediumStatusViewFromWorkspace(workspace) : null;

  const panelContent = (
    <>
    <CockpitHeader />
    <div className="flex flex-col gap-2 p-3">
      <PanelSkeleton />

      {/* ── COCKPIT TILES (new dark-card system) ──────────────────────── */}

      {/* 1. Capture status — always first, shows progress */}
      <CaptureStatusTile />

      {/* 2. Parameter table (classic, editable) */}
      <WorkspaceCard title="Parameter">
        <ParameterTablePanel />
      </WorkspaceCard>

      {/* 3. Medium Intelligence — appears when medium is identified */}
      <MediumIntelligenceTile />

      {/* ── EXISTING CANONICAL / STREAM CARDS ────────────────────────── */}

      {/* 4. Assumptions / governance */}
      {showCanonical && workspace && (
        <WorkspaceCard
          title="Technischer Status"
          badge={
            (workspace.communication?.confirmedFactsSummary?.length || 0) > 0
              ? String(workspace.communication?.confirmedFactsSummary?.length || 0)
              : undefined
          }
        >
          <CaseStatusPanel workspace={workspace} isLoading={workspaceLoading} />
        </WorkspaceCard>
      )}

      {/* 5. Live Workspace / stream cards */}
      {showStreamWorkspace ? <StreamWorkspaceCards /> : null}

      {/* 6. Lifecycle */}
      {showCanonical && workspace && (
        <WorkspaceCard title="Lifecycle">
          <CaseLifecyclePanel workspace={workspace} />
        </WorkspaceCard>
      )}

      {showCanonical && workspace && canonicalMediumStatus && (
        <WorkspaceCard title="Medium-Status" badge={canonicalMediumStatus.statusLabel}>
          <MediumStatusPanel view={canonicalMediumStatus} />
        </WorkspaceCard>
      )}

      {showCanonical &&
        workspace &&
        workspace.mediumContext.status === "available" &&
        workspace.mediumContext.mediumLabel && (
          <WorkspaceCard title="Medium-Kontext">
            <MediumContextPanel workspace={workspace} />
          </WorkspaceCard>
        )}

      {/* 7. Matching */}
      {showCanonical &&
        workspace &&
        (workspace.matching.ready || workspace.matching.items.length > 0) && (
          <WorkspaceCard title="Hersteller-Matching">
            <PartnerMatchingPanel workspace={workspace} />
          </WorkspaceCard>
        )}

      {/* 8. RFQ */}
      {showCanonical &&
        workspace &&
        (workspace.rfq.hasDraft ||
          workspace.rfq.releaseStatus !== "inadmissible") && (
          <WorkspaceCard title="RFQ-Paket">
            <RfqPackagePanel workspace={workspace} />
          </WorkspaceCard>
        )}
    </div>
    </>
  );

  // Desktop: fills the 50% column set by CaseScreen — no fixed width here
  if (isDesktopViewport) {
    return (
      <aside className="flex h-full w-full flex-col overflow-y-auto border-l border-[#e8ecf1] bg-[#f8fafc] [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
        {panelContent}
      </aside>
    );
  }

  // Mobile: overlay
  return (
    <div className="fixed inset-y-0 right-0 z-[80] flex w-[min(92vw,320px)] flex-col overflow-y-auto border-l border-[#e8ecf1] bg-[#f8fafc] shadow-xl [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
      <div className="flex items-center justify-between border-b border-[#e8ecf1] px-3 py-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          Engineering Dashboard
        </span>
        <button
          onClick={closeSidebar}
          className="flex h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          aria-label="Dashboard schließen"
        >
          <X size={16} />
        </button>
      </div>
      {panelContent}
    </div>
  );
}
