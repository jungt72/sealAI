"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { logout } from "../../lib/logout";
import SidebarLeft from "./components/Sidebar/SidebarLeft";

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
  const [showAskMissing, setShowAskMissing] = useState(false);

  useEffect(() => {
    const onUi = (ev: Event) => {
      const ua: any = (ev as CustomEvent<any>).detail ?? (ev as any);
      const action = ua?.ui_action ?? ua?.action ?? ua?.event;
      try { console.debug("[sealai] UI event received", ua); } catch {}
      if (action) setShowAskMissing(true);
    };
    window.addEventListener("sealai:ui", onUi as EventListener);
    window.addEventListener("sealai:ui_action", onUi as EventListener);
    window.addEventListener("sai:need-params", onUi as EventListener);
    return () => {
      window.removeEventListener("sealai:ui", onUi as EventListener);
      window.removeEventListener("sealai:ui_action", onUi as EventListener);
      window.removeEventListener("sai:need-params", onUi as EventListener);
    };
  }, []);

  return (
    <div className="min-h-screen w-full bg-white">
      <header className="sticky top-0 z-30 flex items-center justify-end px-4 py-3 bg-white/80 backdrop-blur border-b">
        <LogoutButton />
      </header>
      <div className="flex min-h-[calc(100vh-56px)]">
        <SidebarLeft open={showAskMissing} onOpenChange={(v) => setShowAskMissing(v)} />
        <main className="flex-1 min-w-0">{children}</main>
      </div>
    </div>
  );
}
