"use client";

import type { ReactNode } from "react";
import { useSession } from "next-auth/react";
import { logout } from "../../lib/logout";
import ContextSidebar from "./components/ContextSidebar";

function LogoutButton() {
  const { status } = useSession();
  if (status !== "authenticated") return null;

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error("Logout failed", error);
      window.location.assign("/");
    }
  };

  return (
    <button
      onClick={handleLogout}
      className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition"
      aria-label="Abmelden"
      title="Abmelden"
    >
      <span className="i-logout h-[14px] w-[14px] inline-block" />
      Abmelden
    </button>
  );
}

export default function DashboardShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full w-full flex-col bg-white min-h-0 overflow-hidden">
      <header className="sticky top-0 z-30 flex items-center justify-end px-4 py-3 bg-white/80 backdrop-blur border-b shrink-0">
        <LogoutButton />
      </header>

      {/* KEY: min-h-0 + overflow-hidden => der Main kann wirklich scrollen */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <main className="flex-1 min-w-0 min-h-0 overflow-y-auto">{children}</main>
        <div className="hidden xl:flex w-[360px] shrink-0 border-l border-slate-100 bg-white px-4 py-4 overflow-y-auto">
          <ContextSidebar />
        </div>
      </div>
    </div>
  );
}
