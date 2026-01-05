"use client";

import * as React from "react";
import SidebarForm from "./SidebarForm";

export default function SidebarLeft({
  open = true,
  onOpenChange,
}: {
  open?: boolean;
  onOpenChange?: (v: boolean) => void;
}) {
  return (
    <aside
      className={[
        "relative border-r border-zinc-200 bg-white transition-all",
        open ? "w-[360px] max-w-[40vw]" : "w-0 max-w-0 overflow-hidden",
      ].join(" ")}
      aria-hidden={!open}
    >
      <div className="p-3 text-xs text-zinc-500 flex items-center justify-between">
        <span>Beratung</span>
        {onOpenChange && (
          <button
            className="rounded px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100"
            onClick={() => onOpenChange(false)}
            aria-label="Sidebar schließen"
            title="Sidebar schließen"
          >
            ✕
          </button>
        )}
      </div>
      <SidebarForm embedded />
    </aside>
  );
}
