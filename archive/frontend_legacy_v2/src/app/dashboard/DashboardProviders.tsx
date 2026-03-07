"use client";

import type { ReactNode } from "react";
import { ContextStateProvider } from "./context/ContextStateProvider";

export default function DashboardProviders({ children }: { children: ReactNode }) {
  return <ContextStateProvider>{children}</ContextStateProvider>;
}
