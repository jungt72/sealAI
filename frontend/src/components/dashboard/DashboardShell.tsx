"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { 
  Menu, 
  Plus, 
  MessageSquare, 
  History, 
  Settings, 
  HelpCircle, 
  Activity,
  Sparkles,
  Database,
  LayoutDashboard
} from "lucide-react";
import { cn } from "@/lib/utils";

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
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background font-sans">
      {/* Sidebar - Gemini Style */}
      <aside
        className={cn(
          "relative z-20 flex h-full flex-col bg-sidebar transition-all duration-300 ease-in-out",
          isExpanded ? "w-[280px]" : "w-[68px]"
        )}
      >
        {/* Top Header: Menu & Branding */}
        <div className="flex h-[60px] items-center px-[18px]">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex h-10 w-10 items-center justify-center rounded-full hover:bg-muted transition-colors"
          >
            <Menu size={20} className="text-muted-foreground" />
          </button>
          <div className={cn(
            "ml-3 flex items-center gap-2 transition-opacity duration-300",
            isExpanded ? "opacity-100" : "opacity-0 w-0 overflow-hidden"
          )}>
            <span className="text-xl font-medium tracking-tight text-foreground">Gemini</span>
          </div>
        </div>

        {/* New Chat Button */}
        <div className="px-3 mt-4 mb-8">
          <Link
            href="/dashboard/new"
            className={cn(
              "flex items-center gap-3 bg-muted hover:bg-[#E3E3E3] transition-all duration-200 text-muted-foreground",
              isExpanded 
                ? "h-12 px-4 rounded-full w-fit min-w-[140px]" 
                : "h-12 w-12 justify-center rounded-2xl"
            )}
          >
            <Plus size={24} className="shrink-0" />
            {isExpanded && <span className="text-sm font-medium">New Chat</span>}
          </Link>
        </div>

        {/* Nav Items & Recent History Placeholder */}
        <nav className="flex-1 px-3 space-y-1 overflow-y-auto custom-scrollbar">
          {isExpanded && (
            <p className="px-4 py-2 text-[13px] font-medium text-muted-foreground">Recent</p>
          )}
          
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/dashboard/new"
                ? pathname.startsWith("/dashboard")
                : pathname.startsWith(item.href);

            return (
              <Link
                key={item.label}
                href={item.href}
                className={cn(
                  "flex h-10 items-center gap-3 px-4 rounded-full transition-colors group",
                  isActive 
                    ? "bg-[#D3E3FD] text-[#041E49]" 
                    : "text-muted-foreground hover:bg-muted"
                )}
              >
                <item.icon size={20} className="shrink-0" />
                {isExpanded && (
                  <span className="text-sm font-medium whitespace-nowrap overflow-hidden">
                    {item.label}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Bottom Actions */}
        <div className="px-3 py-4 space-y-1">
          {[
            { icon: HelpCircle, label: "Help" },
            { icon: Activity, label: "Activity" },
            { icon: Settings, label: "Settings" },
          ].map((item) => (
            <button
              key={item.label}
              className="flex h-10 w-full items-center gap-3 px-4 rounded-full text-muted-foreground hover:bg-muted transition-colors"
            >
              <item.icon size={20} className="shrink-0" />
              {isExpanded && <span className="text-sm font-medium">{item.label}</span>}
            </button>
          ))}
          
          {/* Sparkle Brand Marker */}
          {isExpanded && (
            <div className="mt-4 px-4 py-3 flex items-center gap-3">
              <Sparkles size={18} className="sparkle-icon" />
              <div className="flex flex-col">
                <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground/60">
                  Gemini Advanced
                </span>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="relative flex flex-1 flex-col overflow-hidden bg-surface rounded-tl-[28px] my-1 mr-1 border border-border shadow-sm">
        {children}
      </main>
    </div>
  );
}
