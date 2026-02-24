"use client";

import React, { useState } from "react";
import {
    LayoutDashboard,
    Users,
    Shield,
    Settings,
    Package,
    Database,
    Menu,
    Search,
    X
} from "lucide-react";
import LogoutButton from "@/components/dashboard/LogoutButton";

export default function DashboardLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    // Default: closed (schmale hellblaue Leiste)
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);

    return (
        <div className="flex h-screen w-full bg-white text-seal-rich overflow-hidden font-sans">

            {/* Sidebar (Permanent im Flex-Layout, ändert nur die Breite) */}
            <aside
                className={`relative flex flex-col h-full bg-[#F0F4F8] border-r border-seal-silver/20 shadow-sm transition-all duration-300 ease-in-out ${
                    isSidebarOpen ? "w-64" : "w-20"
                }`}
            >
                {/* Header: Logo & Toggle Button */}
                <div className="p-4 flex items-center justify-between h-20">
                    {isSidebarOpen ? (
                        <>
                            <div className="flex items-center gap-3 overflow-hidden">
                                {/* Das neue Dashboard-Logo */}
                                <img 
                                    src="/images/logo/Logo_sealai_dashboard.png" 
                                    alt="SealAI Logo" 
                                    className="h-8 w-auto object-contain drop-shadow-sm"
                                />
                            </div>
                            <button
                                onClick={() => setIsSidebarOpen(false)}
                                className="p-1.5 rounded-lg hover:bg-white/50 text-seal-ylnmn transition-all hover:text-seal-rich shrink-0"
                                title="Sidebar schließen"
                            >
                                <X size={20} />
                            </button>
                        </>
                    ) : (
                        /* Hamburger Button im geschlossenen Zustand zentriert */
                        <button
                            onClick={() => setIsSidebarOpen(true)}
                            className="w-full flex justify-center p-2 rounded-xl hover:bg-white/50 text-seal-ylnmn transition-all hover:text-seal-rich"
                            title="Menü öffnen"
                        >
                            <Menu size={24} />
                        </button>
                    )}
                </div>

                {/* Navigation */}
                <nav className="flex-1 px-3 space-y-2 mt-2 overflow-x-hidden">
                    {[
                        { href: "/dashboard", icon: LayoutDashboard, label: "Workbench", active: true },
                        { href: "#", icon: Search, label: "Discovery" },
                        { href: "#", icon: Shield, label: "Verification" },
                        { href: "/rag", icon: Database, label: "Knowledge Base" },
                        { href: "#", icon: Package, label: "Components" },
                        { href: "#", icon: Users, label: "Collaboration" },
                        { href: "#", icon: Settings, label: "Settings" },
                    ].map((item) => (
                        <a
                            key={item.label}
                            href={item.href}
                            title={!isSidebarOpen ? item.label : undefined} // Tooltip bei schmaler Leiste
                            className={`flex items-center rounded-xl p-3 text-sm font-medium transition-all group overflow-hidden ${
                                item.active
                                    ? "bg-white text-seal-oxford shadow-sm border border-seal-silver/10"
                                    : "text-seal-ylnmn hover:bg-white/30 hover:text-seal-rich"
                            }`}
                        >
                            <item.icon className="h-6 w-6 shrink-0" />
                            
                            {/* Text wird nur eingeblendet, wenn Sidebar offen ist */}
                            <span 
                                className={`ml-3 whitespace-nowrap transition-opacity duration-300 ${
                                    isSidebarOpen ? "opacity-100" : "opacity-0 hidden"
                                }`}
                            >
                                {item.label}
                            </span>
                        </a>
                    ))}
                </nav>

                {/* Footer mit Logout */}
                <div className="px-3 pb-6 border-t border-seal-silver/10 pt-4 flex flex-col gap-2 overflow-hidden">
                    <div className={`transition-all duration-300 ${isSidebarOpen ? "block" : "flex justify-center"}`}>
                        {/* Gibt den Zustand an den Button weiter, damit dieser z.B. nur das Icon zeigt */}
                        <LogoutButton showLabel={isSidebarOpen} />
                    </div>
                </div>
            </aside>

            {/* Main Content (passt sich automatisch dem restlichen Platz an) */}
            <main className="flex-1 relative flex flex-col bg-white overflow-hidden w-full">
                <div className="flex-1 overflow-hidden relative">
                    {children}
                </div>
            </main>
            
        </div>
    );
}
