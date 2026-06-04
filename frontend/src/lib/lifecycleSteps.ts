// frontend/src/lib/lifecycleSteps.ts
// Pure lifecycle step derivation logic — no React, no JSX.
// Shared between CaseLifecyclePanel.tsx and tests.

import type { WorkspaceView } from "./contracts/workspace";

export type LifecycleStepStatus = "done" | "active" | "pending";

export type LifecycleStep = {
  label: string;
  status: LifecycleStepStatus;
  detail?: string;
  iconName: string;
};

export function deriveLifecycleSteps(ws: WorkspaceView): LifecycleStep[] {
  return ws.lifecycle.steps;
}
