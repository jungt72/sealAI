// frontend/src/app/dashboard/components/Sidebar/SidebarLeft.tsx
'use client';

import { useState, ReactNode } from 'react';
import {
  FileText as FormIcon,
  MessagesSquare as ChatIcon,
  Settings as SettingsIcon,
} from 'lucide-react';

interface SidebarLeftProps {
  isOpen: boolean;
}

export default function SidebarLeft({ isOpen }: SidebarLeftProps) {
  type TabKey = 'form' | 'history' | 'settings';
  const [active, setActive] = useState<TabKey>('form');

  /* ------------ Tab-Definition ------------ */
  const tabs: { key: TabKey; label: string; icon: ReactNode }[] = [
    { key: 'form',    label: 'Formular',     icon: <FormIcon  className="h-5 w-5" /> },
    { key: 'history', label: 'Chat-History', icon: <ChatIcon  className="h-5 w-5" /> },
    { key: 'settings',label: 'Settings',     icon: <SettingsIcon className="h-5 w-5" /> },
  ];

  /* ------------ Inhalte Platzhalter ------------ */
  function renderContent() {
    switch (active) {
      case 'form':
        return (
          <form className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <input className="border rounded px-3 py-2" placeholder="Feld A" />
            <input className="border rounded px-3 py-2" placeholder="Feld B" />
            <input className="border rounded px-3 py-2" placeholder="Feld C" />
            <textarea
              className="border rounded px-3 py-2 col-span-full"
              rows={4}
              placeholder="Beschreibung"
            />
            <button className="col-span-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition">
              Speichern
            </button>
          </form>
        );
      case 'history':
        return (
          <div className="space-y-2">
            <p className="text-sm text-gray-500">Hier könnte deine Chat-History stehen …</p>
          </div>
        );
      case 'settings':
        return <p className="text-sm text-gray-500">Settings-Panel (Demo-Platzhalter)</p>;
      default:
        return null;
    }
  }

  /* Sidebar geschlossen? — gar nichts rendern */
  if (!isOpen) return null;

  return (
    <div className="mt-12 flex h-full w-full overflow-hidden">
      {/* ---------- Tab-Leiste ---------- */}
      <nav className="flex flex-col shrink-0 w-14 border-r">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setActive(t.key)}
            className={`flex flex-col items-center gap-1 py-4 text-xs hover:bg-gray-100 
              ${t.key === active ? 'bg-gray-100 font-semibold text-blue-600' : 'text-gray-500'}`}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </nav>

      {/* ---------- Panel-Inhalt ---------- */}
      <div className="flex-1 overflow-y-auto px-4">
        <h2 className="text-lg font-semibold text-gray-700 mb-4">
          {tabs.find(t => t.key === active)?.label}
        </h2>
        {renderContent()}
      </div>
    </div>
  );
}
