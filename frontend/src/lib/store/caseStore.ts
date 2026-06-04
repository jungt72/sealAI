/**
 * caseStore — verwaltet die aktive Case-ID und ihren Lifecycle-Status.
 * Einzige Quelle der Wahrheit für Case-Identität im gesamten Dashboard.
 */
import { create } from "zustand";

export type CaseStatus = "idle" | "loading" | "active" | "error";

interface CaseStore {
  caseId: string | null;
  caseStatus: CaseStatus;
  setCaseId: (id: string | null) => void;
  setCaseStatus: (status: CaseStatus) => void;
  reset: () => void;
}

export const useCaseStore = create<CaseStore>()((set) => ({
  caseId: null,
  caseStatus: "idle",

  setCaseId: (id) =>
    set({ caseId: id, caseStatus: id ? "active" : "idle" }),

  setCaseStatus: (status) => set({ caseStatus: status }),

  reset: () => set({ caseId: null, caseStatus: "idle" }),
}));
