/**
 * workspaceStore — Engineering-Sidebar-State, UI-Layout und registrierte Aktionen.
 *
 * Enthält:
 * - workspace / workspaceLoading / streamWorkspace (aus useWorkspace / useAgentStream)
 * - chatInput (Action-Bridge: WorkspacePane → ChatComposer)
 * - isSidebarOpen / isDesktopViewport (responsive Layout-State)
 * - activePanel (für Panel-Selection in Phase 3)
 *
 * CaseScreen synchronisiert Hook-State per useEffect; WorkspacePane und
 * ChatPane lesen direkt aus diesem Store.
 */
import { create } from "zustand";

import type { AssertionEntry } from "@/lib/contracts/agent";
import type { WorkspaceView } from "@/lib/contracts/workspace";
import type { StreamWorkspaceView } from "@/lib/streamWorkspace";

/** Aktives Panel in der Workspace-Sidebar (Vorbereitung Phase 3) */
export type ActivePanel =
  | "lifecycle"
  | "actions"
  | "status"
  | "rfq"
  | "matching"
  | null;

// ── Medium Intelligence types (fetched via BFF) ────────────────────────────
export interface MediumIntelligenceData {
  canonicalName: string;
  family: string;
  subFamily?: string;
  pH: { min: number | null; max: number | null; note: string };
  viscosityMpas: { at20c: number | null; at40c: number | null; at80c: number | null };
  temperatureRange: { minC: number; maxC: number; criticalNoteC: number | null };
  pressureTypical: { maxBar: number | null; note: string };
  corrosiveness: "low" | "medium" | "high" | "very_high";
  chemicalAggressiveness: "low" | "medium" | "high" | "very_high";
  compatibleMaterials: string[];
  incompatibleMaterials: Array<string | { material: string; reason: string }>;
  specialChallenges: string[];
  sealingConsiderations: string[];
  typicalIndustries: string[];
  normsStandards: string[];
  warningFlags: string[];
  confidenceLevel: "high" | "medium" | "low";
}

interface WorkspaceStore {
  // ── Workspace-Daten ───────────────────────────────────────────────────────
  workspace: WorkspaceView | null;
  workspaceLoading: boolean;
  streamWorkspace: StreamWorkspaceView | null;
  /** Letzte bekannte Assertions aus dem Governed-Stream — bleibt nach Stream-Ende erhalten */
  streamAssertions: Record<string, AssertionEntry> | null;

  // ── Medium Intelligence ────────────────────────────────────────────────────
  mediumIntelligence: MediumIntelligenceData | null;
  mediumIntelligenceLoading: boolean;
  /** Which medium label was last fetched — prevents duplicate fetches */
  mediumIntelligenceFor: string | null;

  // ── UI-State ──────────────────────────────────────────────────────────────
  /** Text der im Composer vorausgefüllt werden soll (Action-Bridge) */
  chatInput: string | null;
  isSidebarOpen: boolean;
  isDesktopViewport: boolean;
  activePanel: ActivePanel;
  /** Letzte bekannte Response Class aus dem Stream (persistiert nach Stream-Ende) */
  activeResponseClass: string | null;

  // ── Registrierte Aktionen (werden von CaseScreen eingehängt) ──────────────
  /** Lädt den Workspace-State neu */
  refreshWorkspace: () => void;
  /** Schreibt einen Text in den ChatComposer (NBA-Aktion) */
  actionBridge: (text: string) => void;

  // ── State-Sync-Setter ─────────────────────────────────────────────────────
  setWorkspace: (w: WorkspaceView | null) => void;
  setWorkspaceLoading: (v: boolean) => void;
  setStreamWorkspace: (v: StreamWorkspaceView | null) => void;
  setStreamAssertions: (v: Record<string, AssertionEntry> | null) => void;
  setChatInput: (v: string | null) => void;
  setIsSidebarOpen: (v: boolean) => void;
  setIsDesktopViewport: (v: boolean) => void;
  setActivePanel: (panel: ActivePanel) => void;
  setActiveResponseClass: (v: string | null) => void;
  setMediumIntelligence: (data: MediumIntelligenceData | null) => void;
  setMediumIntelligenceLoading: (v: boolean) => void;
  setMediumIntelligenceFor: (label: string | null) => void;

  // ── UI-Aktionen ───────────────────────────────────────────────────────────
  toggleSidebar: () => void;
  closeSidebar: () => void;

  // ── Registrierung ─────────────────────────────────────────────────────────
  registerCallbacks: (callbacks: {
    refreshWorkspace: () => void;
    actionBridge: (text: string) => void;
  }) => void;

  reset: () => void;
}

const noopRefresh = (): void => {};
const noopBridge = (_text: string): void => {};

export const useWorkspaceStore = create<WorkspaceStore>()((set) => ({
  workspace: null,
  workspaceLoading: false,
  streamWorkspace: null,
  streamAssertions: null,
  mediumIntelligence: null,
  mediumIntelligenceLoading: false,
  mediumIntelligenceFor: null,
  chatInput: null,
  isSidebarOpen: true,
  isDesktopViewport: false,
  activePanel: null,
  activeResponseClass: null,

  refreshWorkspace: noopRefresh,
  actionBridge: noopBridge,

  setWorkspace: (w) => set({ workspace: w }),
  setWorkspaceLoading: (v) => set({ workspaceLoading: v }),
  setStreamWorkspace: (v) =>
    set((s) => ({
      streamWorkspace: v,
      // Stream assertions are only a temporary projection aid. When the stream
      // view is cleared after canonical workspace refresh, they must not remain
      // as a competing parameter authority.
      streamAssertions: v === null ? null : v.assertions ?? s.streamAssertions,
    })),
  setStreamAssertions: (v) => set({ streamAssertions: v }),
  setChatInput: (v) => set({ chatInput: v }),
  setIsSidebarOpen: (v) => set({ isSidebarOpen: v }),
  setIsDesktopViewport: (v) => set({ isDesktopViewport: v }),
  setActivePanel: (panel) => set({ activePanel: panel }),
  setActiveResponseClass: (v) => set({ activeResponseClass: v }),
  setMediumIntelligence: (data) => set({ mediumIntelligence: data }),
  setMediumIntelligenceLoading: (v) => set({ mediumIntelligenceLoading: v }),
  setMediumIntelligenceFor: (label) => set({ mediumIntelligenceFor: label }),

  toggleSidebar: () => set((s) => ({ isSidebarOpen: !s.isSidebarOpen })),
  closeSidebar: () => set({ isSidebarOpen: false }),

  registerCallbacks: ({ refreshWorkspace, actionBridge }) =>
    set({ refreshWorkspace, actionBridge }),

  reset: () =>
    set({
      workspace: null,
      workspaceLoading: false,
      streamWorkspace: null,
      streamAssertions: null,
      chatInput: null,
      activeResponseClass: null,
      mediumIntelligence: null,
      mediumIntelligenceLoading: false,
      mediumIntelligenceFor: null,
    }),
}));
