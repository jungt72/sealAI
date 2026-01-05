"use client";

import SidebarForm from "./SidebarForm";

type Props = { open: boolean; onOpenChange: (open: boolean) => void };

export default function SidebarLeft({ open, onOpenChange }: Props) {
  return (
    <>
      {/* Kein Backdrop mehr. Chat bleibt voll klickbar. */}
      <aside
        className={[
          "fixed top-0 left-0 z-50 h-full",
          "w-[86vw] max-w-[360px]",
          "bg-white shadow-2xl rounded-r-2xl",
          "transform transition-[transform,opacity,box-shadow] duration-300 ease-out will-change-transform",
          open ? "translate-x-0 opacity-100" : "-translate-x-full opacity-0 pointer-events-none",
        ].join(" ")}
        role="dialog"
        aria-modal="false"
        aria-label="Beratungs-Formular"
      >
        <div className="p-4 border-b flex items-center justify-between">
          <h2 className="font-semibold">Beratungs-Formular</h2>
          <button
            type="button"
            className="text-xs px-2 py-1 border rounded hover:bg-gray-50"
            onClick={() => onOpenChange(false)}
          >
            Schließen
          </button>
        </div>
        <div className="p-4 h-[calc(100%-56px)] overflow-y-auto">
          <SidebarForm embedded />
        </div>
      </aside>
    </>
  );
}
