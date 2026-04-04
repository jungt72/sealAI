/**
 * Barrel-Export aller Workspace-Subkomponenten.
 * Die externen Panels (CaseLifecyclePanel etc.) liegen in dashboard/ und
 * werden dort direkt importiert.
 */
export { default as StreamWorkspaceCards } from "./StreamWorkspaceCards";
export { default as PanelSkeleton } from "./PanelSkeleton";
export { default as ParameterTablePanel } from "./ParameterTablePanel";
export type { PanelBaseProps } from "./types";
export { default as MediumStatusPanel } from "../MediumStatusPanel";
export { default as MediumContextPanel } from "../MediumContextPanel";
