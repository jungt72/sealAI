"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import SidebarLeft from "./components/Sidebar/SidebarLeft";
import ChatScreen from "./ChatScreen";

function LogoutButton() {
  const { status } = useSession();
  if (status !== "authenticated") return null;

  const handleLogout = () => {
    window.location.assign("/api/auth/sso-logout");
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

export default function DashboardShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const onNeed = () => setDrawerOpen(true);
    const onUi = (ev: any) => {
      const ua = ev?.detail ?? ev;
      const action = (typeof ua === "string") ? ua : (ua?.ui_action ?? ua?.action);
      if (action === "open_form") setDrawerOpen(true);
    };
    window.addEventListener("sai:need-params", onNeed as EventListener);
    window.addEventListener("sealai:ui_action", onUi as EventListener);
    return () => {
      window.removeEventListener("sai:need-params", onNeed as EventListener);
      window.removeEventListener("sealai:ui_action", onUi as EventListener);
    };
  }, []);

  // Esc schließt Drawer
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setDrawerOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="min-h-screen w-full bg-white">
      <header className="sticky top-0 z-30 flex items-center justify-end px-4 py-3 bg-white/80 backdrop-blur border-b">
        <LogoutButton />
      </header>
      <div className="flex min-h-[calc(100vh-56px)]">
        <SidebarLeft open={drawerOpen} onOpenChange={setDrawerOpen} />
        <main className="flex-1 min-w-0">
          <ChatScreen />
        </main>
      </div>
    </div>
  );
}
