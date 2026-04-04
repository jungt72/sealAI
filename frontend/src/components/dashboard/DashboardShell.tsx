"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Database, LayoutDashboard } from "lucide-react";

import LogoutButton from "@/components/dashboard/LogoutButton";

const NAV_ITEMS = [
  { href: "/dashboard/new", icon: LayoutDashboard, label: "Workbench" },
  { href: "/rag", icon: Database, label: "Knowledge Base" },
];

export default function DashboardShell({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-gemini-bg font-sans">
      {/* Sidebar */}
      <aside
        onMouseEnter={() => setIsSidebarOpen(true)}
        onMouseLeave={() => setIsSidebarOpen(false)}
        className={`relative z-10 flex h-full flex-col bg-[#0f1e30] transition-all duration-200 ease-in-out ${
          isSidebarOpen ? "w-[200px]" : "w-14"
        }`}
      >
        {/* Logo mark */}
        <div className="flex h-14 shrink-0 items-center px-[10px]">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
            S
          </div>
          {isSidebarOpen && (
            <span className="ml-3 overflow-hidden whitespace-nowrap text-sm font-semibold text-white">
              SealAI
            </span>
          )}
        </div>

        {/* Nav icons */}
        <nav className="mt-2 flex flex-1 flex-col gap-1 overflow-hidden px-[10px]">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/dashboard/new"
                ? pathname.startsWith("/dashboard")
                : pathname.startsWith(item.href);

            return (
              <Link
                key={item.label}
                href={item.href}
                title={!isSidebarOpen ? item.label : undefined}
                className={`flex h-9 items-center rounded-lg transition-colors duration-150 ${
                  isSidebarOpen ? "w-full px-2" : "w-9 justify-center"
                } ${
                  isActive
                    ? "bg-blue-500/20"
                    : "hover:bg-white/[0.07]"
                }`}
              >
                <item.icon className="h-5 w-5 shrink-0 text-white/80" />
                {isSidebarOpen && (
                  <span className="ml-2.5 overflow-hidden whitespace-nowrap text-[13px] font-medium text-white/80">
                    {item.label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Sign-out at bottom */}
        <div className="shrink-0 px-[10px] pb-5">
          <LogoutButton
            showLabel={isSidebarOpen}
            className="text-white/50 hover:bg-white/10 hover:text-red-400"
          />
        </div>
      </aside>

      {/* Main content */}
      <main className="relative flex flex-1 flex-col overflow-hidden">
        {children}
      </main>
    </div>
  );
}
